"""Supply-chain admission gate for community-published capabilities.

The Hub deliberately talks to the standalone THEMIS over
HTTP instead of importing its implementation.  They remain independently
deployable satellites and the Hub consumes the auditor exactly like any other
signed AIMarket capability provider.

Only operator-owned environment variables select the endpoint and its pinned
Ed25519 key.  Publisher input can never redirect the Hub to another host.  The
auditor receives a bounded declaration; it does not fetch the evidence URLs.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import math
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from aimarket_hub.database import SUPPLY_AUDITS_PENDING_MAX
from aimarket_hub.paging import page_limit


logger = logging.getLogger(__name__)

# Wire format shared with THEMIS (themis/attestations.py). Canonical JSON, sorted
# keys, no spaces — the Hub verifies observer reports with its own implementation,
# so the byte layout is pinned by a test on both sides rather than trusted.
VIOLATION_STATEMENT = "aimarket.violation.v1"
DECLARED_PERMISSIONS = (
    "execute_code",
    "access_secrets",
    "spend_money",
    "write_external_systems",
    "unrestricted_network",
    "read_personal_data",
    "human_approval_for_high_impact",
)
CONTRADICTABLE_PERMISSIONS = frozenset(DECLARED_PERMISSIONS[:6])
MAX_VIOLATION_REPORTS = 64

AUDITOR_PRODUCT_ID = "themis"
AUDITOR_CAPABILITY_ID = "agent.security.supply-chain.audit@v1"
VALID_MODES = frozenset({"off", "advisory", "enforce"})
FINAL_METIS_STATES = frozenset(
    {"completed", "not_performed", "timeout", "unavailable", "failed", "skipped"}
)
MAX_AUDITOR_RESPONSE_BYTES = 512 * 1024
MAX_PUBLIC_FINDINGS = 20
MAX_EVIDENCE_ITEMS = 32
MAX_AUDIT_INPUT_BYTES = 256 * 1024
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if math.isfinite(value) and low <= value <= high else default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if low <= value <= high else default


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(manifest)).hexdigest()


def declared_permissions(manifest: dict[str, Any]) -> dict[str, bool]:
    """The declaration exactly as the auditor's model will see it.

    The digest must match what THEMIS computes from its own parsed model, so
    every known flag is present and defaults to False — an absent key and an
    explicit ``false`` have to hash identically.
    """
    raw = manifest.get("permissions")
    raw = raw if isinstance(raw, dict) else {}
    return {name: bool(raw.get(name, False)) for name in DECLARED_PERMISSIONS}


def permissions_digest(permissions: dict[str, bool]) -> str:
    return hashlib.sha256(
        _canonical({key: bool(value) for key, value in sorted(permissions.items())})
    ).hexdigest()


def violation_message(
    *, capability_id: str, permission: str, permissions_sha256: str, product_id: str
) -> bytes:
    return _canonical(
        {
            "capability_id": capability_id,
            "permission": permission,
            "permissions_sha256": permissions_sha256.lower(),
            "product_id": product_id,
            "statement": VIOLATION_STATEMENT,
        }
    )


def _validate_endpoint(url: str, *, allow_insecure: bool) -> str:
    """Operator-owned auditor URL only — never taken from a publisher dossier.

    Loopback is allowed so the gate can reach a co-located auditor. Every other
    host must pass the Hub SSRF blocklist (RFC1918, link-local, cloud metadata).
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValueError("auditor URL is malformed") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("auditor URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("auditor URL must not contain credentials, query, or fragment")
    host = parsed.hostname.lower()
    loopback = host in _LOOPBACK_HOSTS
    if parsed.scheme != "https" and not loopback and not allow_insecure:
        raise ValueError(
            "auditor URL must use HTTPS outside loopback "
            "(or explicitly set AIMARKET_SUPPLY_CHAIN_AUDITOR_ALLOW_INSECURE=1)"
        )
    if not loopback:
        # Import lazily so unit tests can monkeypatch crawler without loading httpx paths.
        from aimarket_hub.crawler import _url_is_safe

        if not _url_is_safe(url):
            raise ValueError(
                "auditor URL must not target a blocked, private, or unresolvable network"
            )
    return url.rstrip("/")


async def _auditor_http(
    method: str,
    url: str,
    *,
    timeout: float,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    """POST/GET the pinned auditor endpoint without following redirects."""
    from aimarket_hub.outbound_http import _pin_target

    target, pin_headers, ext = _pin_target(url, allow_hosts=set(_LOOPBACK_HOSTS))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        if method == "GET":
            return await client.get(
                target, headers=pin_headers or None, extensions=ext or None
            )
        return await client.post(
            target,
            json=json_body,
            headers=pin_headers or None,
            extensions=ext or None,
        )


def _decode_public_key(value: str) -> Ed25519PublicKey:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("auditor public key must be canonical base64") from exc
    if len(raw) != 32:
        raise ValueError("auditor public key must encode 32 Ed25519 bytes")
    from aimarket_hub.signing import has_small_order

    if has_small_order(raw):
        # A placeholder such as 32 zero bytes is a key anyone can sign for (see has_small_order).
        raise ValueError("auditor public key is a small-order point, not a real key")
    return Ed25519PublicKey.from_public_bytes(raw)


@dataclass(frozen=True)
class AdmissionConfig:
    mode: str
    auditor_url: str
    auditor_pubkey: str
    timeout_seconds: float
    request_metis: bool
    max_price_per_call_usd: float
    max_monthly_cost_usd: float
    minimum_score: int
    minimum_evidence_count: int
    require_https: bool
    require_provider_key: bool
    require_metis_declaration: bool
    allow_insecure_auditor: bool
    # Defaults mirror the auditor's own, so existing construction sites and
    # pinned test configs keep their exact behaviour.
    require_evidence_digests: bool = True
    require_evidence_attestation: bool = False
    require_independent_attestation: bool = False
    require_permission_attestation: bool = False
    runtime_violation_min_reporters: int = 2

    @classmethod
    def from_env(cls) -> AdmissionConfig:
        raw_mode = os.getenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE")
        auditor_pubkey = os.getenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", "").strip()
        if raw_mode is None:
            # An operator who deployed and pinned an auditor gets recorded
            # verdicts by default; blocking still requires an explicit
            # `enforce`. Silently defaulting to `off` meant a fully wired gate
            # could sit there recording nothing.
            mode = "advisory" if auditor_pubkey else "off"
            if mode == "off":
                logger.warning(
                    "Supply-chain admission is off: set "
                    "AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY to record verdicts, or "
                    "AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE=off to silence this."
                )
        else:
            mode = raw_mode.strip().lower()
            if mode not in VALID_MODES:
                logger.warning(
                    "Unknown AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE=%r; admission disabled", mode
                )
                mode = "off"
        return cls(
            mode=mode,
            auditor_url=os.getenv(
                "AIMARKET_SUPPLY_CHAIN_AUDITOR_URL", "http://127.0.0.1:8080/invoke"
            ).strip(),
            auditor_pubkey=os.getenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", "").strip(),
            timeout_seconds=_env_float(
                "AIMARKET_SUPPLY_CHAIN_AUDITOR_TIMEOUT_SECONDS", 15.0, 1.0, 60.0
            ),
            request_metis=_env_bool("AIMARKET_SUPPLY_CHAIN_AUDITOR_METIS", True),
            max_price_per_call_usd=_env_float(
                "AIMARKET_ADMISSION_MAX_PRICE_PER_CALL_USD", 10.0, 0.0, 1_000.0
            ),
            max_monthly_cost_usd=_env_float(
                "AIMARKET_ADMISSION_MAX_MONTHLY_COST_USD", 10_000.0, 0.0, 100_000_000.0
            ),
            minimum_score=_env_int("AIMARKET_ADMISSION_MINIMUM_SCORE", 80, 0, 100),
            minimum_evidence_count=_env_int(
                "AIMARKET_ADMISSION_MINIMUM_EVIDENCE", 2, 0, 6
            ),
            require_https=_env_bool("AIMARKET_ADMISSION_REQUIRE_HTTPS", True),
            require_provider_key=_env_bool("AIMARKET_ADMISSION_REQUIRE_PROVIDER_KEY", True),
            require_metis_declaration=_env_bool(
                "AIMARKET_ADMISSION_REQUIRE_METIS_DECLARATION", False
            ),
            allow_insecure_auditor=_env_bool(
                "AIMARKET_SUPPLY_CHAIN_AUDITOR_ALLOW_INSECURE", False
            ),
            require_evidence_digests=_env_bool(
                "AIMARKET_ADMISSION_REQUIRE_EVIDENCE_DIGESTS", True
            ),
            require_evidence_attestation=_env_bool(
                "AIMARKET_ADMISSION_REQUIRE_EVIDENCE_ATTESTATION", False
            ),
            require_independent_attestation=_env_bool(
                "AIMARKET_ADMISSION_REQUIRE_INDEPENDENT_ATTESTATION", False
            ),
            require_permission_attestation=_env_bool(
                "AIMARKET_ADMISSION_REQUIRE_PERMISSION_ATTESTATION", False
            ),
            runtime_violation_min_reporters=_env_int(
                "AIMARKET_ADMISSION_VIOLATION_MIN_REPORTERS", 2, 1, 16
            ),
        )


class SupplyChainAdmission:
    """Evaluate and persist publication admission decisions.

    ``off`` performs no network call. ``advisory`` records any valid verdict but
    never blocks. ``enforce`` accepts only a verified ``approve`` verdict and
    fails closed on misconfiguration, timeout, malformed output, ``review`` or
    ``reject``.
    """

    def __init__(self, db: Any, config: AdmissionConfig | None = None):
        self.db = db
        self.config = config or AdmissionConfig.from_env()
        self._endpoint: str | None = None
        self._public_key: Ed25519PublicKey | None = None
        self._config_error = ""
        self._refresh_task: asyncio.Task | None = None
        self._last_refresh = 0.0
        if self.config.mode != "off":
            try:
                self._endpoint = _validate_endpoint(
                    self.config.auditor_url,
                    allow_insecure=self.config.allow_insecure_auditor,
                )
                self._public_key = _decode_public_key(self.config.auditor_pubkey)
            except ValueError as exc:
                self._config_error = str(exc)
                logger.error("Supply-chain admission misconfigured: %s", exc)

    @property
    def mode(self) -> str:
        return self.config.mode

    def _policy(self) -> dict[str, Any]:
        policy = {
            "max_price_per_call_usd": self.config.max_price_per_call_usd,
            "max_monthly_cost_usd": self.config.max_monthly_cost_usd,
            "minimum_score": self.config.minimum_score,
            "minimum_evidence_count": self.config.minimum_evidence_count,
            "require_https": self.config.require_https,
            "require_provider_key": self.config.require_provider_key,
            "require_metis_declaration": self.config.require_metis_declaration,
            "approved_publishers": [],
        }
        # The auditor forbids unknown policy fields, so an attestation knob is
        # only transmitted when an operator actually changed it. A default Hub
        # therefore keeps working against an auditor deployed before these
        # existed, instead of turning every publish into a 400 — which in
        # enforce mode would block the whole catalogue.
        for key, value, default in (
            ("require_evidence_digests", self.config.require_evidence_digests, True),
            ("require_evidence_attestation", self.config.require_evidence_attestation, False),
            (
                "require_independent_attestation",
                self.config.require_independent_attestation,
                False,
            ),
            ("require_permission_attestation", self.config.require_permission_attestation, False),
            (
                "runtime_violation_min_reporters",
                self.config.runtime_violation_min_reporters,
                2,
            ),
        ):
            if value != default:
                policy[key] = value
        return policy

    def _audit_input(self, manifest: dict[str, Any]) -> dict[str, Any]:
        verification = manifest.get("verification")
        metis_declared = bool(verification.get("metis")) if isinstance(verification, dict) else False
        permissions = manifest.get("permissions") if isinstance(manifest.get("permissions"), dict) else {}
        evidence = manifest.get("evidence") if isinstance(manifest.get("evidence"), list) else []
        usage = manifest.get("usage") if isinstance(manifest.get("usage"), dict) else {}
        input_schema = manifest.get("input_schema") if isinstance(manifest.get("input_schema"), dict) else {}
        output_schema = (
            manifest.get("output_schema") if isinstance(manifest.get("output_schema"), dict) else {}
        )
        payload = {
            "candidate": {
                "product_id": str(manifest.get("product_id", ""))[:128],
                "capability_id": str(manifest.get("capability_id", ""))[:192],
                "name": str(manifest.get("name") or manifest.get("capability_id") or "")[:256],
                "description": str(manifest.get("description", ""))[:2_000],
                "invoke_url": str(manifest.get("invoke_url", ""))[:2_048],
                "publisher_id": str(
                    manifest.get("publisher_id") or manifest.get("publisher") or ""
                )[:128],
                "provider_pubkey": str(manifest.get("provider_pubkey", ""))[:128],
                "price_per_call_usd": manifest.get("price_per_call_usd", 0.01),
                "input_schema": input_schema,
                "output_schema": output_schema,
                "verification": {"metis": metis_declared},
            },
            "permissions": permissions,
            "evidence": evidence[:MAX_EVIDENCE_ITEMS],
            "usage": usage,
            "policy": self._policy(),
            "request_metis": self.config.request_metis,
        }
        # Counter-evidence, only when it exists: an auditor deployed before
        # runtime_violations existed forbids the unknown field, and in enforce
        # mode a 400 would block every publish.
        reports = self._violation_reports(manifest)
        if reports:
            payload["runtime_violations"] = reports
        encoded = _canonical(payload)
        if len(encoded) > MAX_AUDIT_INPUT_BYTES:
            raise ValueError("admission dossier exceeds size limit")
        return payload

    def _violation_reports(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        """Signed observer reports bound to the declaration being published now.

        AUTHENTICATED reporters only, and that is the whole point of the filter. THEMIS
        counts DISTINCT ISSUER KEYS against ``runtime_violation_min_reporters`` (default 2)
        and says so in its own docstring — it is stateless, so it explicitly delegates the
        Sybil resistance to "whoever COLLECTED the reports and binds each reporter to a paid
        or registered identity". That is this hub. The slash ladder already honours the
        delegation (``supply_security`` acts on ``bound_reporters``, never on the key count);
        this path handed over every stored row, unbound observations included, so two free
        keypairs produced a critical ``permissions.declaration_contradicted`` and — under
        enforce — refused any publisher's capability at zero cost.

        Unbound observations are still recorded and still visible to the operator; they just
        cannot vote.
        """
        digest = permissions_digest(declared_permissions(manifest))
        product_id = str(manifest.get("product_id", ""))[:128]
        capability_id = str(manifest.get("capability_id", ""))[:192]
        if not product_id or not capability_id:
            return []
        try:
            rows = self.db.supply_permission_violations_for(
                product_id, capability_id, digest, limit=MAX_VIOLATION_REPORTS,
                bound_only=True,
            )
        except Exception:  # a Hub without the migration must still admit
            logger.warning("permission violation store unavailable", exc_info=True)
            return []
        return [
            {
                "permission": row["permission"],
                "attestation": {
                    "issuer": row["reporter_pubkey"],
                    "signature": row["signature"],
                },
            }
            for row in rows
            if row.get("permission") in CONTRADICTABLE_PERMISSIONS
        ]

    def record_permission_violation(
        self,
        *,
        product_id: str,
        capability_id: str,
        permission: str,
        reporter_pubkey: str,
        signature: str,
        consumer_id: str = "",
        consumer_bound: bool = False,
    ) -> dict[str, Any]:
        """Accept one signed observation that contradicts a published declaration.

        Verified here rather than trusted: an unverifiable report is refused
        outright, so the store only ever holds evidence the auditor will also
        accept. Reaching the reporter threshold is reported back to the caller —
        acting on it (fault ledger, stake) stays with supply security, which owns
        the griefing-resistant rules.

        ``consumer_bound`` says the hub AUTHENTICATED ``consumer_id`` (a registered
        agent/publisher credential or the admin token). Only bound reports count toward
        ``contradicted``: counting distinct ``reporter_pubkey`` made the two-reporter
        consensus free to satisfy, since anyone can mint two keypairs.
        """
        if permission not in CONTRADICTABLE_PERMISSIONS:
            return {"accepted": False, "reason": "unknown_permission"}
        product_id = str(product_id or "")[:128]
        capability_id = str(capability_id or "")[:192]
        if not product_id or not capability_id:
            return {"accepted": False, "reason": "unknown_capability"}
        record = self.db.supply_audit_declaration(product_id, capability_id)
        if not record or not record.get("permissions_sha256"):
            # Nothing was ever declared here, so there is nothing to contradict.
            return {"accepted": False, "reason": "no_declaration_on_record"}
        declaration = record["permissions"]
        if declaration.get(permission) is True:
            # Doing what you declared is not a violation of the declaration.
            return {"accepted": False, "reason": "permission_was_declared"}
        digest = record["permissions_sha256"]
        publisher_id = str(record.get("publisher_id") or "")[:128]

        message = violation_message(
            capability_id=capability_id,
            permission=permission,
            permissions_sha256=digest,
            product_id=product_id,
        )
        try:
            key = _decode_public_key(reporter_pubkey)
            key.verify(base64.b64decode(signature, validate=True), message)
        except (ValueError, TypeError, InvalidSignature):
            return {"accepted": False, "reason": "signature_invalid"}

        # Only an AUTHENTICATED reporter identity is persisted. The signature proves the
        # reporter committed to this declaration digest; it does not prove the reporter
        # ever ran the capability, and reporter_pubkey costs nothing to mint -- so an
        # unbound report is an observation to record, not a vote that may take stake.
        bound_consumer = consumer_id[:128] if consumer_bound else ""
        stored = self.db.supply_permission_violation_record(
            publisher_id=publisher_id,
            product_id=product_id,
            capability_id=capability_id,
            permission=permission,
            permissions_sha256=digest,
            reporter_pubkey=reporter_pubkey,
            signature=signature,
            consumer_id=bound_consumer,
        )
        reporters = self.db.supply_permission_violation_reporters(
            product_id, capability_id, digest, permission
        )
        bound_reporters = self.db.supply_permission_violation_bound_reporters(
            product_id, capability_id, digest, permission
        )
        threshold = max(1, self.config.runtime_violation_min_reporters)
        contradicted = bound_reporters >= threshold
        if reporters >= threshold and not contradicted:
            logger.warning(
                "permission-violation consensus for %s/%s reached %d distinct KEYS but only "
                "%d authenticated reporter(s) (threshold %d) — not slashing. Keys are free; "
                "register reporters in AIMARKET_AGENT_TOKENS so real observations can count.",
                product_id, permission, reporters, bound_reporters, threshold,
            )
        return {
            "accepted": True,
            "duplicate": not stored,
            "permission": permission,
            "permissions_sha256": digest,
            "publisher_id": publisher_id,
            "distinct_reporters": reporters,
            "bound_reporters": bound_reporters,
            "reporter_bound": bool(consumer_bound),
            "threshold": threshold,
            "contradicted": contradicted,
        }

    def _verify_signature(
        self, *, result: dict[str, Any], audit_input: dict[str, Any], signature: str
    ) -> None:
        if self._public_key is None:
            raise ValueError("auditor public key is not configured")
        try:
            signature_bytes = base64.b64decode(signature, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("auditor signature is not canonical base64") from exc
        if len(signature_bytes) != 64:
            raise ValueError("auditor signature must encode 64 Ed25519 bytes")
        canonical = _canonical(
            {
                "capability_id": AUDITOR_CAPABILITY_ID,
                "product_id": AUDITOR_PRODUCT_ID,
                "input_sha256": hashlib.sha256(_canonical(audit_input)).hexdigest(),
                "result": result,
            }
        )
        try:
            self._public_key.verify(signature_bytes, canonical)
        except InvalidSignature as exc:
            raise ValueError("auditor response signature is invalid") from exc

    @staticmethod
    def _sanitize_findings(value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        findings: list[dict[str, str]] = []
        for item in value[:MAX_PUBLIC_FINDINGS]:
            if not isinstance(item, dict):
                continue
            findings.append(
                {
                    "code": str(item.get("code", ""))[:96],
                    "severity": str(item.get("severity", ""))[:24],
                    "title": str(item.get("title", ""))[:240],
                    "remediation": str(item.get("remediation", ""))[:500],
                }
            )
        return findings

    @classmethod
    def _sanitize_result(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("auditor result must be a JSON object")
        decision = value.get("decision")
        risk_tier = value.get("risk_tier")
        score = value.get("score")
        if decision not in {"approve", "review", "reject"}:
            raise ValueError("auditor returned an unknown decision")
        if risk_tier not in {"low", "medium", "high", "critical"}:
            raise ValueError("auditor returned an unknown risk tier")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise ValueError("auditor returned an invalid score")
        metis = value.get("metis") if isinstance(value.get("metis"), dict) else {}
        metis_status = str(metis.get("status") or "skipped")
        if metis_status not in FINAL_METIS_STATES | {"pending", "running"}:
            metis_status = "failed"
        return {
            "decision": decision,
            "score": score,
            "risk_tier": risk_tier,
            "findings": cls._sanitize_findings(value.get("findings")),
            "remediations": [str(x)[:500] for x in (value.get("remediations") or [])[:20]],
            "owasp_agentic_risks": [
                str(x)[:32] for x in (value.get("owasp_agentic_risks") or [])[:20]
            ],
            "metis_status": metis_status,
            "metis_verification_id": str(metis.get("verification_id") or "")[:64],
            "attestations": cls._sanitize_attestations(value.get("attestations")),
        }

    @staticmethod
    def _sanitize_attestations(value: Any) -> dict[str, Any]:
        """Bounded, typed copy of the auditor's attestation block.

        Counts and booleans only — the same dossier-free rule the rest of this
        record follows. An unknown key from a newer auditor is dropped rather
        than persisted, so the column can never become a data-exfiltration path.
        """
        source = value if isinstance(value, dict) else {}

        def _count(name: str) -> int:
            raw = source.get(name)
            return int(raw) if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 10_000 else 0

        def _flag(name: str) -> bool | None:
            raw = source.get(name)
            return raw if isinstance(raw, bool) else None

        def _names(name: str, allowed: frozenset[str] | None = None) -> list[str]:
            raw = source.get(name)
            if not isinstance(raw, list):
                return []
            out = [str(item)[:48] for item in raw[:16] if isinstance(item, str)]
            return sorted({item for item in out if allowed is None or item in allowed})

        digest = source.get("permissions_sha256")
        return {
            "evidence_declared": _count("evidence_declared"),
            "evidence_verified": _count("evidence_verified"),
            "evidence_counted_kinds": _names("evidence_counted_kinds"),
            "evidence_independently_attested": bool(source.get("evidence_independently_attested")),
            "permissions_signed": bool(source.get("permissions_signed")),
            "permissions_signature_valid": _flag("permissions_signature_valid"),
            "permissions_bound_to_provider_key": _flag("permissions_bound_to_provider_key"),
            "permissions_sha256": digest.lower() if isinstance(digest, str) and len(digest) == 64 else "",
            "runtime_violations_verified": _count("runtime_violations_verified"),
            "runtime_violations_contradicting": _names(
                "runtime_violations_contradicting", CONTRADICTABLE_PERMISSIONS
            ),
        }

    async def _post(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if self._endpoint is None:
            raise ValueError(self._config_error or "auditor endpoint is not configured")
        response = await _auditor_http(
            "POST",
            self._endpoint,
            timeout=self.config.timeout_seconds,
            json_body={
                "input": payload,
                "product_id": AUDITOR_PRODUCT_ID,
                "capability_id": AUDITOR_CAPABILITY_ID,
            },
        )
        if len(response.content) > MAX_AUDITOR_RESPONSE_BYTES:
            raise ValueError("auditor response exceeds 512 KiB")
        if response.status_code != 200:
            raise ValueError(f"auditor refused the dossier (HTTP {response.status_code})")
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("auditor returned invalid JSON") from exc
        if not isinstance(body, dict) or body.get("success") is not True:
            raise ValueError("auditor returned an unsuccessful envelope")
        result = body.get("result")
        if not isinstance(result, dict):
            raise ValueError("auditor result is missing")
        signature = response.headers.get("X-Provider-Signature", "")
        self._verify_signature(result=result, audit_input=payload, signature=signature)
        return result, signature

    def _base_record(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            "audit_id": secrets.token_urlsafe(16),
            "publisher_id": str(
                manifest.get("publisher_id") or manifest.get("publisher") or ""
            )[:128],
            "product_id": str(manifest.get("product_id", ""))[:128],
            "capability_id": str(manifest.get("capability_id", ""))[:192],
            "manifest_sha256": _manifest_sha256(manifest),
            "mode": self.mode,
            "status": "unavailable",
            "decision": "",
            "score": None,
            "risk_tier": "",
            "findings": [],
            "remediations": [],
            "owasp_agentic_risks": [],
            "signature": "",
            "auditor_pubkey": self.config.auditor_pubkey,
            "metis_status": "skipped",
            "metis_verification_id": "",
            "error_code": "",
            "attestations": {},
            "permissions": declared_permissions(manifest),
            "permissions_sha256": permissions_digest(declared_permissions(manifest)),
        }

    async def evaluate(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "off":
            return {"status": "disabled", "mode": "off", "blocked": False}

        record = self._base_record(manifest)
        try:
            audit_input = self._audit_input(manifest)
            raw_result, signature = await self._post(audit_input)
            result = self._sanitize_result(raw_result)
            record.update(
                status="completed",
                signature=signature,
                **result,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            # Never persist upstream detail: it may contain an internal hostname,
            # validation path or a reflected piece of the publisher dossier.
            logger.warning("Supply-chain admission unavailable: %s", exc)
            record["status"] = "unavailable"
            record["error_code"] = "auditor_unavailable"

        self.db.supply_audit_record(record)
        blocked = self.mode == "enforce" and (
            record["status"] != "completed" or record["decision"] != "approve"
        )
        return {
            "audit_id": record["audit_id"],
            "mode": self.mode,
            "status": record["status"],
            "decision": record["decision"] or None,
            "score": record["score"],
            "risk_tier": record["risk_tier"] or None,
            "findings": record["findings"],
            "metis": {
                "status": record["metis_status"],
                "verification_id": record["metis_verification_id"] or None,
            },
            "receipt": {
                "manifest_sha256": record["manifest_sha256"],
                "signature": record["signature"] or None,
                "auditor_pubkey": record["auditor_pubkey"] or None,
            },
            "error_code": record["error_code"] or None,
            "blocked": blocked,
        }

    async def _get_verification(self, verification_id: str) -> tuple[dict[str, Any], str]:
        if self._endpoint is None:
            raise ValueError("auditor endpoint is not configured")
        if not 8 <= len(verification_id) <= 64 or not all(
            char.isalnum() or char in "-_" for char in verification_id
        ):
            raise ValueError("auditor verification id is malformed")
        base = self._endpoint.rsplit("/invoke", 1)[0]
        url = f"{base}/verification/{verification_id}"
        response = await _auditor_http(
            "GET",
            url,
            timeout=min(self.config.timeout_seconds, 10.0),
        )
        if len(response.content) > MAX_AUDITOR_RESPONSE_BYTES or response.status_code != 200:
            raise ValueError("auditor verification status is unavailable")
        body = response.json()
        result = body.get("result") if isinstance(body, dict) else None
        metis = result.get("metis") if isinstance(result, dict) else None
        if not isinstance(metis, dict):
            raise ValueError("auditor verification response is malformed")
        signature = response.headers.get("X-Provider-Signature", "")
        self._verify_signature(
            result={"metis": metis},
            audit_input={"verification_id": verification_id},
            signature=signature,
        )
        status = str(metis.get("status") or "failed")
        if status not in FINAL_METIS_STATES | {"pending", "running"}:
            status = "failed"
        return {
            "status": status,
            "score": metis.get("score") if isinstance(metis.get("score"), (int, float)) else None,
            "route": str(metis.get("route") or "")[:24],
            "reason": str(metis.get("reason") or "")[:96],
        }, signature

    async def refresh_pending(self, limit: int = 5) -> None:
        for row in self.db.supply_audits_pending(limit=page_limit(limit, maximum=SUPPLY_AUDITS_PENDING_MAX)):
            audit_id = str(row.get("audit_id") or "")
            verification_id = str(row.get("metis_verification_id") or "")
            if not audit_id or not verification_id:
                continue
            try:
                metis, signature = await self._get_verification(verification_id)
            except (httpx.HTTPError, ValueError, TypeError):
                continue
            self.db.supply_audit_update_metis(audit_id, metis, signature)

    def schedule_refresh(self) -> None:
        """Refresh lazy Metis jobs without delaying the public stats response."""
        if self.mode == "off" or self._config_error or time.monotonic() - self._last_refresh < 3:
            return
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._last_refresh = time.monotonic()
        self._refresh_task = loop.create_task(self.refresh_pending())

    def enforce_readiness(self) -> dict[str, Any]:
        """Whether switching to ``enforce`` would gate publishes or just break them.

        ``enforce`` fails closed by design: an auditor that is unpinned,
        unreachable or returning malformed output turns every publish into a
        refusal. That is correct behaviour and a terrible surprise, so the
        operator gets to see the three preconditions and a recent success rate
        before flipping the switch instead of after.
        """
        recent = self.db.supply_audits_recent(limit=20)
        completed = [row for row in recent if row.get("status") == "completed"]
        blockers: list[str] = []
        if not self.config.auditor_pubkey:
            blockers.append("auditor_pubkey_not_pinned")
        if self._config_error:
            blockers.append("auditor_endpoint_invalid")
        if self.mode == "off":
            blockers.append("mode_off_no_verdicts_observed")
        elif not completed:
            blockers.append("no_completed_verdict_observed")
        return {
            "mode": self.mode,
            "ready_for_enforce": not blockers,
            "blockers": blockers,
            "recent_audits": len(recent),
            "recent_completed": len(completed),
            "auditor_pinned": bool(self.config.auditor_pubkey),
            "endpoint_valid": not self._config_error,
        }

    def public_summary(self) -> dict[str, Any]:
        summary = self.db.supply_audit_summary()
        summary.update(
            {
                "mode": self.mode,
                "configured": self.mode == "off" or not self._config_error,
                "capability_id": AUDITOR_CAPABILITY_ID,
                "enforce_readiness": self.enforce_readiness(),
            }
        )
        return summary
