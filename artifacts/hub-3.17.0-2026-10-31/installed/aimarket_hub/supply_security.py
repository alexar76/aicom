"""Supply-side security — stake, anti-spam, LUMEN trust, response signatures, input limits."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any

# _normalize_tx_hash is shared with the channel ledger on purpose: both modules decide
# "is this the SAME on-chain deposit?" and a second, independently written definition is
# exactly how the two money paths would drift apart on what counts as a replay.
# The payer-proof primitives are shared for the same reason: a stake deposit and a channel
# deposit ask the identical question ("does the claimant control the wallet that paid?"),
# and this module answering it with its own challenge/verifier would be the FOURTH
# incompatible payer-proof scheme in the codebase (three were just merged into one).
from aimarket_hub.channels import (
    _is_evm_address,
    _is_production_mode,
    _normalize_tx_hash,
    _recover_payer_address,
    _verify_tx_onchain,
    _wallet_matches,
    payer_proof_challenge,
)
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.db_backend import claim_unique
from aimarket_hub.lumen_client import NO_SIGNAL_REASONS, LumenTrustClient, clamp01
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

logger = logging.getLogger(__name__)

_HUB_ANCHOR = "hub:local"
_SENSITIVE_KEY = re.compile(
    r"(password|secret|api[_-]?key|private[_-]?key|mnemonic|seed|token|ssn|credit)",
    re.I,
)

class TrustOracleUnavailable(Exception):
    """LUMEN could not be consulted and this hub has no last-known score.

    Distinct from a policy deny (publisher trust below the invoke floor): the
    consumer did nothing wrong, a hub dependency is down. Mapped to HTTP 502,
    never 403 — a LUMEN outage (including the oracle answering 403/5xx) must
    not look like "this caller is forbidden".
    """


# ── Trust policy constants ────────────────────────────────────────────────────
# These are LOCAL policy, deliberately not oracle output: they only apply when LUMEN
# cannot deliver a verdict (see SupplySecurity.refresh_publisher_trust).
_TRUST_UNTRUSTED = 0.0   # below min_trust_discover AND min_trust_invoke → fail closed
_TRUST_BOOTSTRAP = 0.5   # a graph with no signal at all about a brand-new publisher
# Persisted on the capability row when publish-time LUMEN was down and this hub
# has never scored the publisher. Not a percentile: ``_last_known_trust`` skips
# it so the outage cannot become a retained 0.0 "verdict" that check_invoke_trust
# would map to HTTP 403.
_TRUST_UNSCORED = -1.0
_SLASH_EDGE_WEIGHT = -0.5  # the trust edge a slash writes; also the local outage penalty
# How many local capability rows to scan when recovering a publisher's last stored trust
# score after a restart. Rows are ordered by trust DESC, so a miss (publisher beyond the
# window) yields "unknown" → the untrusted fallback, i.e. it errs closed.
_TRUST_LOOKUP_CAP_LIMIT = 5000
# Written into supply_stakes.tx_hash for a credit that was NOT backed by a verified
# on-chain deposit. See _unverified_stake_marker.
_UNVERIFIED_STAKE_TX = "unverified-dev-credit"
# supply_stakes key under which a SPENT deposit hash is burned. See _consume_stake_tx.
_TX_CONSUMED_PREFIX = "tx-consumed:"
# publisher_id values the stake ledger uses for its own bookkeeping rows. A caller that
# could stake to one of them would overwrite that row's tx_hash and un-burn a deposit /
# drop a dev-credit sentinel, so they are not addressable from outside.
_RESERVED_PUBLISHER_PREFIXES = (_TX_CONSUMED_PREFIX, _UNVERIFIED_STAKE_TX)


def _reject_reserved_publisher(publisher_id: str) -> None:
    for prefix in _RESERVED_PUBLISHER_PREFIXES:
        if publisher_id.startswith(prefix):
            raise ValueError(
                f"publisher_id must not start with the reserved prefix {prefix!r} "
                "(it addresses an internal stake-ledger bookkeeping row)"
            )


def manifest_publisher_id(manifest: dict[str, Any]) -> str:
    """The publisher id a manifest claims to publish AS.

    Shared with the API layer on purpose. ``/supply/register`` must authenticate the
    caller against the SAME id ``validate_publish`` charges the publish-rate budget to,
    reads the stake balance from, and stamps onto the capability row (which is what a
    later slash lands on). A second, independently written extraction in api.py is
    exactly how the authorization check and the ledger write would end up naming
    different publishers.
    """
    return str(manifest.get("publisher_id") or manifest.get("publisher") or "").strip()


def _consumed_tx_key(tx_hash: str) -> str:
    """Synthetic ``supply_stakes`` key recording that a deposit hash was already credited."""
    return f"{_TX_CONSUMED_PREFIX}{tx_hash}"


def _finite_trust(value: Any) -> float:
    """A stored trust score coerced to a finite number, or untrusted.

    ``nan < min_trust`` is False, so a non-finite score stored by anything (an older build,
    a hand-edited row, a future writer) would make a trust gate silently PASS. A score that
    cannot be compared is not a score. The unscored marker (``_TRUST_UNSCORED``) is also
    untrusted for gate comparisons — it is not a LUMEN percentile.
    """
    try:
        score = float(value)
    except (TypeError, ValueError):
        return _TRUST_UNTRUSTED
    if not math.isfinite(score) or score < 0.0:
        return _TRUST_UNTRUSTED
    return score


def _is_unscored(value: Any) -> bool:
    """True when the row carries the 'oracle never delivered a verdict' marker."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(score) and score < 0.0


def _unverified_stake_marker(publisher_id: str) -> str:
    """Per-publisher sentinel recorded as the stake row's ``tx_hash`` for a dev/relaxed
    (unverified) credit.

    It is readable back through ``db.supply_stake_tx_exists`` — the only per-publisher
    handle on the stake row's tx_hash that exists without a schema change — which is how
    the production gates detect a balance accumulated without on-chain verification. Its
    purpose: a hub cannot credit itself stake in dev, flip ``AIFACTORY_PROD`` on and then
    publish (or bond) against money nobody ever deposited.
    """
    return f"{_UNVERIFIED_STAKE_TX}:{publisher_id}"


def _stake_anchor_weight(total_stake_usd: float) -> float:
    """Hub-anchor trust edge weight for a stake balance (log-scaled, capped at 1.0)."""
    return min(math.log10(max(total_stake_usd, 1)) / 2.0, 1.0)


@dataclass
class SupplySecurityPolicy:
    min_stake_usd: float = 10.0
    publish_per_hour: int = 5
    min_trust_discover: float = 0.25
    min_trust_invoke: float = 0.35
    require_response_signature: bool = True
    max_input_keys: int = 32
    max_input_json_bytes: int = 32_768
    product_allowlist: tuple[str, ...] = ()
    # First-party providers the operator runs itself. Documented behaviour (see
    # attested-memory-hub/docs/production-postgres.md): this "bypasses only the
    # external collateral requirement for those exact IDs; every unlisted community
    # publisher still needs verified stake". The variable was set in production and
    # read by nothing, so the operator's own bundled providers could not publish at
    # all — a gate stricter than documented, failing closed and silently.
    operator_publishers: tuple[str, ...] = ()
    relaxed: bool = False
    # Griefing-resistant provider slashing: only slash after this many genuine
    # failures within the window, not on every single failure.
    slash_failure_threshold: int = 3
    slash_failure_window_s: float = 600.0
    # Calibration: slash is a trust floor, not a death penalty. After a slash
    # fires, further failure-driven slashes are suppressed for the cool-down
    # (failures keep being recorded and keep hurting trust), and the rolling
    # 24h total of failure-driven slashes is capped — one bad day can't zero a
    # new agent's stake. 0 disables the respective knob.
    slash_cooldown_s: float = 3600.0
    slash_daily_cap_usd: float = 10.0
    # Verify-first escalation: a Metis verdict "failed" already refunded the
    # buyer (escrow), so a single verified failure costs trust, not stake.
    # Only REPEAT verified failures within the window escalate to a slash — and
    # only when they come from >= verified_fail_min_consumers DISTINCT paying
    # consumers. The Metis verdict is judged against a buyer-supplied intent the
    # buyer fully controls, so (unlike a provider-side 5xx) one actor's repeated
    # failures are one voice, never proof of misbehavior. Mirrors the weak-tier
    # federation rule (a lone issuer moves nothing).
    verified_fail_threshold: int = 3
    verified_fail_window_s: float = 86_400.0
    verified_fail_min_consumers: int = 2
    # Explicit bound on how much of the trust graph is scored. It used to be a bare
    # `limit=1000` inside refresh_publisher_trust with no signal when it bit, so past
    # 1000 edges the graph silently became an arbitrary recent subset and every score
    # drifted for no visible reason. Now it is configurable and truncation is logged.
    max_trust_graph_edges: int = 1000

    @staticmethod
    def _positive_window(env_name: str, default: float) -> float:
        """A slash WINDOW must stay strictly positive. A non-positive (or empty/garbage)
        value would build an invalid ``datetime('now', '--N seconds')`` modifier → SQLite
        returns NULL → the fault count is always 0 → the slash ladder silently fail-OPENS.
        Fall back to the documented default with a warning instead (fail-closed, visible).
        Unlike the cool-down/cap knobs, 0 is NOT a documented 'disable' value for windows."""
        raw = os.environ.get(env_name, str(default))
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = -1.0
        # 'inf'/'nan' parse fine and are worse than a negative number: an infinite window
        # never expires (nothing is ever "recent" enough to close it in SQLite) and NaN
        # loses every comparison, so both disable the ladder silently.
        if not math.isfinite(val):
            val = -1.0
        if val <= 0:
            logger.warning(
                "%s=%r is non-positive; falling back to %s (a non-positive window would "
                "silently disable slashing)", env_name, raw, default,
            )
            return float(default)
        return val

    @staticmethod
    def _finite_float(env_name: str, default: float) -> float:
        """A threshold a gate COMPARES against must be a finite number.

        ``float("nan")`` parses happily and then disables the very gate it configures —
        ``stake < nan`` and ``trust < nan`` are both False — so one typo'd env var silently
        turns off the stake or trust check with no error anywhere. Same for a non-numeric
        value, which used to raise out of hub construction. Fall back to the documented
        default, loudly."""
        raw = os.environ.get(env_name, str(default))
        try:
            num = float(raw)
        except (TypeError, ValueError):
            num = float("nan")
        if not math.isfinite(num):
            logger.warning(
                "%s=%r is not a finite number; falling back to %s (a NaN/inf threshold "
                "silently disables the gate it configures)", env_name, raw, default,
            )
            return float(default)
        return num

    @classmethod
    def from_config(cls, config: HubConfig) -> SupplySecurityPolicy:
        relaxed = os.environ.get("AIMARKET_SUPPLY_SECURITY_RELAXED", "").strip() == "1"
        allow_raw = os.environ.get("AIMARKET_SUPPLY_PRODUCT_ALLOWLIST", "").strip()
        allowlist = tuple(x.strip() for x in allow_raw.split(",") if x.strip())
        operator_raw = os.environ.get("AIMARKET_SUPPLY_OPERATOR_PUBLISHERS", "").strip()
        operator_publishers = tuple(x.strip() for x in operator_raw.split(",") if x.strip())
        prod = _is_production_mode()
        default_stake = 25.0 if prod and not relaxed else 10.0
        min_stake = cls._finite_float("AIMARKET_SUPPLY_MIN_STAKE_USD", default_stake)
        if relaxed:
            min_stake = 0.0
        require_sig = os.environ.get("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "").strip()
        if require_sig == "":
            require_sig_bool = _is_production_mode() and not relaxed
        else:
            require_sig_bool = require_sig not in ("0", "false", "no")
        return cls(
            min_stake_usd=min_stake,
            publish_per_hour=int(os.environ.get("AIMARKET_SUPPLY_PUBLISH_PER_HOUR", "5")),
            min_trust_discover=cls._finite_float(
                "AIMARKET_SUPPLY_MIN_TRUST_DISCOVER", float(config.min_trust_score)
            ),
            min_trust_invoke=cls._finite_float("AIMARKET_SUPPLY_MIN_TRUST_INVOKE", 0.35),
            require_response_signature=require_sig_bool,
            max_input_keys=int(os.environ.get("AIMARKET_SUPPLY_MAX_INPUT_KEYS", "32")),
            max_input_json_bytes=int(os.environ.get("AIMARKET_SUPPLY_MAX_INPUT_JSON_BYTES", "32768")),
            product_allowlist=allowlist,
            operator_publishers=operator_publishers,
            relaxed=relaxed,
            slash_failure_threshold=int(os.environ.get("AIMARKET_SUPPLY_SLASH_FAILURE_THRESHOLD", "3")),
            slash_failure_window_s=cls._positive_window("AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S", 600),
            slash_cooldown_s=cls._finite_float("AIMARKET_SUPPLY_SLASH_COOLDOWN_S", 3600.0),
            slash_daily_cap_usd=cls._finite_float("AIMARKET_SUPPLY_SLASH_DAILY_CAP_USD", 10.0),
            verified_fail_threshold=int(os.environ.get("AIMARKET_SUPPLY_VERIFIED_FAIL_THRESHOLD", "3")),
            verified_fail_window_s=cls._positive_window("AIMARKET_SUPPLY_VERIFIED_FAIL_WINDOW_S", 86400),
            verified_fail_min_consumers=int(os.environ.get("AIMARKET_SUPPLY_VERIFIED_FAIL_MIN_CONSUMERS", "2")),
            max_trust_graph_edges=cls._positive_int(
                "AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES", 1000
            ),
        )

    @staticmethod
    def _positive_int(env_name: str, default: int) -> int:
        """A non-positive edge bound would score an EMPTY graph and hand every publisher
        the no-signal bootstrap — fall back to the documented default, visibly."""
        raw = os.environ.get(env_name, str(default))
        try:
            num = float(raw)
            # int(float('inf')) raises OverflowError, not ValueError — an unhandled crash at
            # hub construction. int(float('nan')) raises ValueError. Screen both first.
            val = int(num) if math.isfinite(num) else -1
        except (TypeError, ValueError, OverflowError):
            val = -1
        if val <= 0:
            logger.warning(
                "%s=%r is non-positive; falling back to %s (a non-positive bound would "
                "score an empty trust graph)", env_name, raw, default,
            )
            return int(default)
        return val


class SupplySecurity:
    """Guards publish + invoke for community ``invoke_url`` capabilities."""

    def __init__(
        self,
        db: HubDatabase,
        config: HubConfig,
        signer: Signer | None = None,
        slash_registry: Any = None,
    ):
        self.db = db
        self.config = config
        self.signer = signer or Signer()
        self.slash_registry = slash_registry
        self.policy = SupplySecurityPolicy.from_config(config)
        # Last HEALTHY score per publisher (process-local read-through cache in front of the
        # durable capability rows). Used to retain trust across a LUMEN outage instead of
        # re-deriving a passing default — see refresh_publisher_trust.
        self._trust_cache: dict[str, float] = {}
        # Oracle health of the last refresh, keyed BY PUBLISHER. A single shared flag was a
        # cross-request fail-open: one instance serves every worker thread, so a concurrent
        # healthy refresh of publisher B (between slash()'s own refresh of A and its read of
        # the flag) told slash() the oracle was up and skipped A's local penalty — restoring
        # the "slash erased by an outage" hole. Absent key ⇒ degraded ⇒ fail closed.
        self._lumen_health: dict[str, bool] = {}
        oracle_url = os.environ.get(
            "AIMARKET_ORACLE_FAMILY_URL",
            os.environ.get("ARGUS_ORACLE_FAMILY_URL", "https://oracles.modelmarket.dev/family"),
        ).strip()
        # "This hub runs no trust oracle" is a THIRD state, and it has to be sayable.
        # Without it the only options were "reachable" and "outage", and the default URL
        # points at one specific operator's host — so anyone else who deployed this hub
        # inherited a hard dependency on a stranger's service: publish while it is
        # unreachable and the capability is stored UNSCORED, after which every invoke of it
        # answers 502 forever (`check_invoke_trust`). Set AIMARKET_ORACLE_FAMILY_URL=off to
        # declare that this deployment simply has no trust oracle; the gate then does not
        # apply instead of failing closed on an outage that will never end.
        self.trust_oracle_configured = oracle_url.lower() not in ("", "off", "none", "local", "disabled")
        self.lumen = LumenTrustClient(oracle_url) if self.trust_oracle_configured else None
        if not self.trust_oracle_configured:
            logger.info(
                "supply security: no trust oracle configured (AIMARKET_ORACLE_FAMILY_URL=off) "
                "— publisher trust gates are inactive on this hub",
            )

    # ── Publish guards ────────────────────────────────────────

    def validate_publish(self, manifest: dict[str, Any]) -> tuple[str, str]:
        """Returns (publisher_id, provider_pubkey). Raises ValueError."""
        publisher_id = manifest_publisher_id(manifest)
        if not publisher_id:
            raise ValueError("publisher_id is required (wallet address or stable publisher slug)")
        _reject_reserved_publisher(publisher_id)
        product_id = str(manifest.get("product_id", "")).strip()
        if self.policy.product_allowlist and product_id not in self.policy.product_allowlist:
            raise ValueError(f"product_id not on allowlist: {product_id}")
        pubkey = str(manifest.get("provider_pubkey", "")).strip()
        if self.policy.require_response_signature and not pubkey:
            raise ValueError("provider_pubkey is required — responses must be Ed25519-signed")
        invoke_url = str(manifest.get("invoke_url", "")).strip()
        # Dedup only a REAL invoke_url. An empty one is legitimate (a non-invoke capability),
        # and looking "" up matched the first OTHER product that also had none — a legitimate
        # publish was rejected with "invoke_url already registered to another product".
        if invoke_url:
            existing = self.db.supply_capability_by_invoke_url(invoke_url)
            if existing and existing.product_id != product_id:
                raise ValueError("invoke_url already registered to another product (dedup)")
        # WHO OWNS THIS ROW? `after_publish` stores via db.upsert_capability, which is an
        # INSERT OR REPLACE against UNIQUE(capability_id, product_id, source_hub) — so a
        # publish naming an existing local capability REPLACES it, price, invoke_url,
        # publisher_id and provider_pubkey included. Every guard above authenticates the
        # publisher; none of them asked whether the listing was already somebody else's.
        # After a takeover, each paid invoke sends the buyer's input to the new invoke_url,
        # verifies the reply against the new provider_pubkey, and pays the new publisher its
        # share. The invoke_url dedup does not cover it: that only fires when the product_id
        # differs, and a takeover reuses the same one.
        #
        # An absent row is a first publish; an EMPTY publisher_id is a row from the seeder or
        # a factory import and stays claimable, or legacy listings would become unpublishable.
        # Only the LOCAL row matters — a peer's listing under the same ids is a different row.
        capability_id = str(manifest.get("capability_id", "")).strip()
        if product_id and capability_id:
            try:
                owned = self.db.get_capability(product_id, capability_id, "local")
            except TypeError:  # older signature without source_hub
                owned = self.db.get_capability(product_id, capability_id)
            owner = str(getattr(owned, "publisher_id", "") or "").strip() if owned else ""
            if owner and owner != publisher_id:
                raise ValueError(
                    f"{capability_id} under {product_id} is already published by another "
                    "publisher — a republish may only be made by its owner"
                )
        if self.policy.publish_per_hour > 0:
            recent = self.db.supply_publish_count_recent(publisher_id, hours=1)
            if recent >= self.policy.publish_per_hour:
                raise ValueError(f"publish rate limit exceeded ({self.policy.publish_per_hour}/hour)")
        if self.policy.min_stake_usd > 0:
            if publisher_id in self.policy.operator_publishers:
                # Collateral only. Every other gate above — credential, ownership,
                # rate limit, allowlist, signature — has already been applied to this
                # publisher exactly as it is to a stranger. Logged at INFO because a
                # security exemption that leaves no trace is how one outlives its
                # reason for existing.
                logger.info(
                    "publisher %s is a first-party operator provider: collateral gate "
                    "waived, every other supply gate still applied", publisher_id,
                )
            else:
                stake = self.db.supply_stake_get(publisher_id)
                if stake < self.policy.min_stake_usd:
                    raise ValueError(
                        f"minimum stake ${self.policy.min_stake_usd:.2f} required "
                        f"(current ${stake:.2f}) — POST /ai-market/v2/supply/stake"
                    )
                self._require_verified_stake(publisher_id, "publish")
        return publisher_id, pubkey

    def _require_verified_stake(self, publisher_id: str, gate: str) -> None:
        """Refuse to let an UNVERIFIED stake balance satisfy a production money gate.

        Complements the per-credit check in ``stake()``: that one guarantees no unverified
        credit can be created while the hub runs in production, this one guarantees a balance
        accumulated *before* production (dev/relaxed, where credits are free) can never be
        spent as collateral by flipping ``AIFACTORY_PROD`` on.
        """
        if self.policy.relaxed or not _is_production_mode():
            return
        if self.db.supply_stake_tx_exists(_unverified_stake_marker(publisher_id)):
            raise ValueError(
                f"{gate} refused: stake balance for {publisher_id} contains unverified "
                "credits deposited outside production — it cannot back a production gate. "
                "Write the balance off to zero, then re-stake with a verified on-chain "
                "tx_hash (a verified deposit on a zero balance clears the marker)."
            )

    def after_publish(self, cap: Capability, publisher_id: str) -> float:
        self.db.supply_publish_log(publisher_id, cap.product_id, cap.invoke_url or "")
        trust = self.refresh_publisher_trust(publisher_id)
        cap.publisher_id = publisher_id
        # Persist a LUMEN verdict (healthy, retained last-known, or no-signal bootstrap).
        # An outage with nothing stored must NOT write 0.0: that would become last-known
        # and look like a policy deny (HTTP 403) instead of a hub-dependency failure
        # (HTTP 502). Also strip any client-supplied trust_score so a publisher cannot
        # fail-open by putting 0.9 in the manifest while the oracle is down.
        if self._lumen_health.get(publisher_id) or publisher_id in self._trust_cache:
            cap.trust_score = trust
        else:
            cap.trust_score = _TRUST_UNSCORED
        self.db.upsert_capability(cap)
        return trust

    # ── Invoke guards ─────────────────────────────────────────

    def sanitize_input(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        raw = json.dumps(payload, ensure_ascii=False)
        if len(raw.encode("utf-8")) > self.policy.max_input_json_bytes:
            raise ValueError(f"input exceeds {self.policy.max_input_json_bytes} bytes")
        if len(payload) > self.policy.max_input_keys:
            raise ValueError(f"input has more than {self.policy.max_input_keys} top-level keys")
        for key in payload:
            if _SENSITIVE_KEY.search(str(key)):
                raise ValueError(f"sensitive field name blocked in input: {key}")
        return payload

    def check_invoke_trust(self, cap: Capability) -> None:
        if not (cap.invoke_url or "").strip():
            return
        # A hub with no trust oracle has no verdict to enforce. Falling through would
        # compare the unscored marker (-1.0) against the minimum and deny every capability
        # published while the oracle was off — a gate that refuses everything is not a gate,
        # it is an outage with a policy error message.
        if not self.trust_oracle_configured:
            return
        min_t = self.policy.min_trust_invoke
        publisher_id = (cap.publisher_id or "").strip()
        # Only the unscored marker means "oracle never delivered a verdict".
        # Re-consult so a recovered LUMEN can unlock; if it is still down, that is
        # a hub-dependency failure (502), not a policy deny (403). A real stored
        # score — including NaN coerced to untrusted — stays a 403 without a
        # network round-trip on every invoke.
        if publisher_id and _is_unscored(cap.trust_score) and self.trust_oracle_configured:
            score = self.refresh_publisher_trust(publisher_id)
            if (
                not self._lumen_health.get(publisher_id, False)
                and publisher_id not in self._trust_cache
            ):
                raise TrustOracleUnavailable(
                    "trust oracle unavailable; cannot authorize invoke"
                )
            if score < min_t:
                raise ValueError(
                    f"capability trust {score:.3f} below minimum {min_t:.3f} for invoke"
                )
            return
        score = _finite_trust(cap.trust_score)
        if score < min_t:
            raise ValueError(
                f"capability trust {score:.3f} below minimum {min_t:.3f} for invoke"
            )

    def verify_provider_response(
        self,
        cap: Capability,
        result: Any,
        signature_b64: str,
        *,
        product_id: str = "",
        input_payload: Any = None,
    ) -> None:
        if not (cap.invoke_url or "").strip():
            return
        if not self.policy.require_response_signature:
            return
        pubkey = (cap.provider_pubkey or "").strip()
        if not pubkey:
            raise ValueError("capability missing provider_pubkey")
        if not signature_b64:
            raise ValueError("provider response signature required (X-Provider-Signature)")
        # Only request-bound signatures authenticate this invocation. A legacy
        # result-only signature can be replayed for another input or capability.
        bound = _bound_response_canonical(cap.capability_id, product_id, input_payload, result)
        if self.signer.verify(pubkey, signature_b64, bound):
            return
        raise ValueError("invalid provider response signature")

    def record_invoke(
        self,
        *,
        publisher_id: str,
        consumer_id: str,
        success: bool,
        product_id: str,
        capability_id: str,
    ) -> float:
        weight = 0.15 if success else -0.25
        event = "invoke_success" if success else "invoke_failure"
        self.db.trust_add_edge(consumer_id or "consumer:anonymous", publisher_id, weight, event)
        if success:
            # A success clears the consecutive-failure streak for this provider.
            self.db.supply_fault_clear(publisher_id, "invoke_failure")
        else:
            # Griefing-resistant slashing: slash only after N genuine failures within
            # the window, not on every single failure — a lone failure (or a burst of
            # them driven by one consumer) must not drain provider stake. Transient
            # provider-unreachability and consumer-side 4xx never reach here (see the
            # /invoke handler); only genuine provider faults (5xx / bad response
            # signature) are recorded as failures. The streak is DB-backed so a
            # restart doesn't amnesty it.
            self.db.supply_fault_log(
                publisher_id, "invoke_failure", product_id, capability_id,
                consumer_id=consumer_id or "",
            )
            fails = self.db.supply_fault_count_recent(
                publisher_id, "invoke_failure", self.policy.slash_failure_window_s
            )
            if fails >= self.policy.slash_failure_threshold:
                self._slash_for_failure(publisher_id, product_id, capability_id, reason="invoke_failure")
                # Reset after acting so we don't slash again on every later failure.
                self.db.supply_fault_clear(publisher_id, "invoke_failure")
        return self.refresh_publisher_trust(publisher_id)

    def record_verified_failure(
        self,
        *,
        publisher_id: str,
        product_id: str,
        capability_id: str,
        consumer_id: str = "",
        paid: bool = False,
        rejection: dict[str, Any] | None = None,
    ) -> None:
        """Verify-first escalation: a genuine Metis verdict "failed" against this provider.

        Griefing-resistant by construction — the Metis verdict is judged against a
        buyer-supplied ``intent`` the buyer fully controls (unlike a provider-side
        5xx, which the provider controls), so a "failed" verdict is only weak evidence:

        * **Only a PAID verification** (real escrow-backed transaction) can feed the
          stake ladder. An advisory/free verdict (sandbox, crypto-off, sub-floor) risked
          nothing for the buyer, so it must never cost the provider stake — it is a
          no-op here (the soft ``verify_failed`` reputation signal still fires upstream
          in ``_emit_reputation`` regardless).
        * The trust ding is attributed to the **consumer** node (not the hub anchor),
          so a low-rank/anonymous buyer's complaint carries little structural weight and
          cannot be hub-amplified.
        * A slash requires BOTH the failure-count threshold AND **≥ N distinct paying
          consumers** (``verified_fail_min_consumers``). One buyer's repeated failures
          count as a single voice and can never drain a competitor's stake alone —
          mirroring the weak-tier federation rule (a lone issuer moves nothing).

        The buyer is already made whole by the escrow refund; slash is the last resort
        for a provider that repeatedly fails DISTINCT paying buyers, not the QA system.
        """
        publisher_id = (publisher_id or "").strip()
        if not publisher_id:
            return
        # Advisory (unpaid) verdicts never reach the stake ladder — see docstring.
        if not paid:
            return
        consumer = (consumer_id or "").strip() or "consumer:anonymous"
        self.db.trust_add_edge(consumer, publisher_id, -0.25, "verified_failure")
        self.db.supply_fault_log(publisher_id, "verified_failure", product_id, capability_id, consumer_id=consumer)
        fails = self.db.supply_fault_count_recent(
            publisher_id, "verified_failure", self.policy.verified_fail_window_s
        )
        distinct = self.db.supply_fault_distinct_consumers_recent(
            publisher_id, "verified_failure", self.policy.verified_fail_window_s
        )
        if fails >= self.policy.verified_fail_threshold and distinct >= self.policy.verified_fail_min_consumers:
            self._slash_for_failure(
                publisher_id, product_id, capability_id,
                reason="verified_failure",
                evidence=rejection,
                evidence_kind="verification_rejection" if rejection else "",
            )
            self.db.supply_fault_clear(publisher_id, "verified_failure")
        self.refresh_publisher_trust(publisher_id)

    def record_permission_violation(
        self,
        *,
        publisher_id: str,
        product_id: str,
        capability_id: str,
        permission: str,
        distinct_reporters: int,
        threshold: int,
        consumer_id: str = "",
        reporter_bound: bool = False,
    ) -> dict[str, Any]:
        """A declared permission was contradicted by enough independent observers.

        The report itself is verified upstream (the admission service owns the
        statement format and refuses anything that does not verify), so what is
        left here is the part supply security owns: the fault ledger, the trust
        edge, and whether this crosses into stake.

        Reuses the distinct-reporter rule rather than counting reports: one observer
        filing the same observation repeatedly is one voice, exactly as one buyer's
        repeated failures are in ``record_verified_failure``.

        ``distinct_reporters`` MUST be the count of reporters the hub authenticated.
        The original rule counted distinct ``reporter_pubkey`` on the theory that "a
        signed lie about your own permissions is strong evidence … so it needs no paid
        gate". The signature proves only that the *reporter* signed — it says nothing
        about whether the capability misbehaved — and an Ed25519 keypair is free, so two
        throwaway keys reached the two-reporter threshold and took a publisher's stake at
        zero cost. Identity now has to be bound (see api.supply_permission_violation).

        An UNBOUND report writes no trust edge either: trust_graph_edges is a bounded
        recent window, so anonymous edges displace real ones and move every publisher's
        score.
        """
        publisher_id = (publisher_id or "").strip()
        if not publisher_id:
            return {"slashed": False, "reason": "unknown_publisher"}
        reporter = (consumer_id or "").strip() if reporter_bound else ""
        if reporter:
            self.db.trust_add_edge(reporter, publisher_id, -0.25, "permission_violation")
        self.db.supply_fault_log(
            publisher_id, "permission_violation", product_id, capability_id,
            consumer_id=reporter,
        )
        if distinct_reporters < max(1, threshold):
            self.refresh_publisher_trust(publisher_id)
            return {"slashed": False, "reason": "below_reporter_threshold"}
        self._slash_for_failure(
            publisher_id, product_id, capability_id,
            reason="permission_violation",
            evidence={
                "permission": permission,
                "distinct_reporters": distinct_reporters,
                "capability_id": capability_id,
            },
            evidence_kind="permission_violation",
        )
        self.db.supply_fault_clear(publisher_id, "permission_violation")
        self.refresh_publisher_trust(publisher_id)
        return {"slashed": True, "reason": "declaration_contradicted"}

    def _trust_graph_edges(self, publisher_id: str) -> list[tuple[str, str, float]]:
        """The bounded trust graph fed to LUMEN, plus this publisher's stake anchor.

        We ask the DB for one row MORE than the bound so truncation is detectable and can be
        logged with real numbers — an invisible cut was the whole complaint: past the bound
        the graph became an arbitrary recent subset and scores moved for no stated reason.
        """
        bound = self.policy.max_trust_graph_edges
        edges_raw = self.db.trust_list_edges(limit=bound + 1)
        if len(edges_raw) > bound:
            edges_raw = edges_raw[:bound]
            logger.warning(
                "trust graph truncated to the %d most recent edges "
                "(AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES) — the score for %s is computed on a "
                "partial graph; raise the bound or prune trust_graph_edges",
                bound, publisher_id,
            )
        edges: list[tuple[str, str, float]] = []
        stake = self.db.supply_stake_get(publisher_id)
        if stake > 0:
            # Appended outside the bound so a publisher's own stake anchor is never the edge
            # that gets truncated away.
            edges.append((_HUB_ANCHOR, publisher_id, _stake_anchor_weight(stake)))
        edges.extend((src, dst, w) for src, dst, w, _ in edges_raw)
        return edges

    def _last_known_trust(self, publisher_id: str) -> float | None:
        """The last trust score this hub actually computed for the publisher, or None.

        Read-through: the process-local cache first (exact), then the durable capability rows
        that ``supply_set_publisher_trust`` writes — so a restart in the middle of a LUMEN
        outage still retains the score instead of falling back to a passing default. The
        minimum across the publisher's rows is used: if they ever disagree, the lower value
        is the safe one to gate on.
        """
        cached = self._trust_cache.get(publisher_id)
        if cached is not None:
            return cached
        if not publisher_id:
            return None
        stored: float | None = None
        for cap in self.db.list_capabilities(source_hub="local", limit=_TRUST_LOOKUP_CAP_LIMIT):
            if cap.publisher_id != publisher_id:
                continue
            try:
                raw = float(cap.trust_score)
            except (TypeError, ValueError):
                continue
            # The unscored marker is the absence of a verdict, not a retained 0.0.
            if not math.isfinite(raw) or raw < 0.0:
                continue
            value = _finite_trust(raw)
            stored = value if stored is None else min(stored, value)
        return stored

    def refresh_publisher_trust(self, publisher_id: str) -> float:
        """Recompute + store the publisher's trust score from the LUMEN trust graph.

        Fail-closed on a degraded oracle. LUMEN answered every failure mode with a
        manufactured ``score: 0.5`` and this method read only ``score``, so an oracle outage
        wrote 0.5 for everybody — above both the discover (0.25) and invoke (0.35) gates, and
        including a provider slashed seconds earlier (``slash()`` refreshes right after adding
        its -0.5 edge, so the outage erased the slash's trust effect entirely).

        Policy now, by oracle verdict:

        * **healthy** → store it. The only path that writes an oracle-derived score.
        * **unavailable** (HTTP/transport/malformed) → never overwrite a stored score. Retain
          the last known one; if this hub has never scored the publisher, report untrusted
          (0.0) for the gates without persisting it, so recovery is automatic once LUMEN is
          reachable again.
        * **no signal** (``no_edges``/``empty_graph``, a deterministic answer rather than an
          outage) → a brand-new publisher with no stake, no invokes and no slashes. Locking
          them out forever would make the hub unpublishable, so they get the documented
          neutral bootstrap (0.5) — but ONLY when nothing is stored yet, so a previously
          scored (or slashed) publisher can never be reset upward through this path.

        Recovery from the untrusted case is not manual: any later refresh — re-registering
        the capability, another stake deposit, or a recorded invoke — rescores the publisher
        as soon as the oracle answers again.
        """
        if not self.trust_oracle_configured:
            # No oracle to consult: report the documented neutral bootstrap and mark the
            # publisher healthy so `after_publish` stores a real number. Storing the
            # unscored marker here would brick every future invoke of the capability on a
            # hub that never had an oracle to be unavailable in the first place.
            self._lumen_health[publisher_id] = True
            self._trust_cache[publisher_id] = _TRUST_BOOTSTRAP
            return _TRUST_BOOTSTRAP
        edges = self._trust_graph_edges(publisher_id)
        result = self.lumen.score_entity(publisher_id, edges)
        raw = result.get("score")
        healthy = False
        if not result.get("degraded"):
            try:
                score = clamp01(raw)
                healthy = True
            except ValueError:
                # A "healthy" verdict carrying a non-finite score is unusable; treat it as
                # an outage rather than clamping garbage into a passing number.
                logger.error("LUMEN returned a non-finite score for %s: %r", publisher_id, raw)
        self._lumen_health[publisher_id] = healthy
        if healthy:
            self._trust_cache[publisher_id] = score
            self.db.supply_set_publisher_trust(publisher_id, score)
            return score

        reason = str(result.get("reason") or "degraded")
        last = self._last_known_trust(publisher_id)
        if last is not None:
            # Cache the recovered value so a prolonged outage doesn't re-scan capability
            # rows on every invoke. It is the same score the DB already holds.
            self._trust_cache[publisher_id] = last
            logger.warning(
                "LUMEN degraded (%s) for %s — retaining last known trust %.3f (not overwritten)",
                reason, publisher_id, last,
            )
            return last
        if not result.get("unavailable") and reason in NO_SIGNAL_REASONS:
            logger.info(
                "trust graph carries no signal for %s (%s) — bootstrapping at %.2f",
                publisher_id, reason, _TRUST_BOOTSTRAP,
            )
            self._trust_cache[publisher_id] = _TRUST_BOOTSTRAP
            self.db.supply_set_publisher_trust(publisher_id, _TRUST_BOOTSTRAP)
            return _TRUST_BOOTSTRAP
        # Unavailable oracle and no score ever computed here: gate as untrusted. Deliberately
        # NOT cached and NOT persisted — this is the absence of a verdict, not a verdict.
        logger.error(
            "LUMEN unavailable (%s) and no stored trust for %s — gating as untrusted",
            reason, publisher_id,
        )
        return _TRUST_UNTRUSTED

    def _penalize_trust_locally(self, publisher_id: str, penalty: float, reason: str) -> float:
        """Apply a trust penalty without the oracle, and persist it.

        Used when a slash lands while LUMEN is unreachable: the -0.5 graph edge the slash
        writes only bites through the oracle, so without this the refresh would retain the
        PRE-slash score and the slash would have no trust effect at all.
        """
        base = self._last_known_trust(publisher_id)
        value = max(_TRUST_UNTRUSTED, (base if base is not None else _TRUST_UNTRUSTED) - penalty)
        self._trust_cache[publisher_id] = value
        self.db.supply_set_publisher_trust(publisher_id, value)
        logger.warning(
            "LUMEN unavailable — applied local trust penalty %.2f for %s (%s) → %.3f",
            penalty, publisher_id, reason, value,
        )
        return value

    def filter_for_discover(self, caps: list[Capability]) -> list[Capability]:
        """Apply the trust floor and de-duplicate providers, preserving the caller's order.

        The trust sort here used to be the emitted order, which silently overruled whatever
        ranking the caller had computed: `search_capabilities` returns rows by relevance, and
        this re-sorted them by trust_score, so the most-trusted capability answered every
        query regardless of what was asked. Trust is still what decides WHICH of two rows
        sharing an invoke_url survives — that part was correct — so the decision is made on
        a trust-ordered pass and the surviving rows are then emitted in their input order.
        """
        min_t = self.policy.min_trust_discover
        seen_urls: set[str] = set()
        keep: set[int] = set()
        # Decide on a trust-descending pass: for a duplicated provider URL the highest-trust
        # row wins, exactly as before.
        for idx, c in sorted(
            enumerate(caps), key=lambda p: _finite_trust(p[1].trust_score), reverse=True
        ):
            if (c.invoke_url or "").strip():
                if _finite_trust(c.trust_score) < min_t:
                    continue
                url = c.invoke_url.strip()
                if url in seen_urls:
                    continue
                seen_urls.add(url)
            keep.add(idx)
        return [c for idx, c in enumerate(caps) if idx in keep]

    # ── Stake / slash ─────────────────────────────────────────

    def _stake_ledger_backend(self) -> Any:
        """The DB backend behind ``supply_stakes``, for the atomic burn claim.

        ``HubDatabase`` exposes the backend as ``_backend`` (and the ``_conn`` alias its own
        methods use). Fail CLOSED if neither is there: without a backend the burn cannot be
        made atomic, and an un-burnable deposit must be refused, not credited.
        """
        backend = getattr(self.db, "_backend", None) or getattr(self.db, "_conn", None)
        if backend is None or not hasattr(backend, "execute"):
            raise ValueError(
                "stake ledger backend unavailable — refusing to credit a deposit whose "
                "single-use burn cannot be claimed atomically"
            )
        return backend

    def _consume_stake_tx(self, tx_hash: str) -> None:
        """Burn a verified deposit hash so it can never be credited a second time.

        ``supply_stakes`` keeps ONE tx_hash per publisher and every credit overwrites it, so
        the replay guard forgot a deposit as soon as the same publisher staked again: after A
        credits 0xA then 0xB, ``supply_stake_tx_exists('0xA')`` is False and 0xA is free for
        anyone (including A) to claim again. A per-deposit table would need migrations.py
        (owned elsewhere), so the hash is burned as its own zero-amount stake row under a
        reserved publisher_id — a row no publisher can address (see
        ``_reject_reserved_publisher``) and therefore no later credit overwrites.

        The burn is an INSERT-first CLAIM on ``supply_stakes.publisher_id`` (PRIMARY KEY) —
        the same primary-key claim channels.py relies on for ``consumed_deposits``, decided
        by the database rather than by a prior read (see ``claim_unique``).
        It used to go through ``supply_stake_add``, which SELECTs and then UPDATEs an
        existing row: two requests that both passed ``supply_stake_tx_exists`` before either
        burned would BOTH succeed (the loser silently updated the winner's burn row) and the
        one deposit was credited twice. Only the writer whose INSERT the database accepts may
        continue; every other caller is a replay.

        Called BEFORE the credit: if crediting then fails, the deposit is spent and unusable
        rather than creditable twice. That is the fail-closed direction for money.

        The claim key is the CANONICAL transaction id, not the caller's string. An atomic
        claim on a non-canonical key is not single-use: ``eth_getTransactionByHash``
        resolves ``0xAB…`` and ``0xab…`` to the same transaction, so both verified, both
        burned under different primary keys, and one $10 deposit funded one publisher per
        capitalisation. (Solana base58 signatures keep their case — there it is part of
        the identifier.)
        """
        canonical = _normalize_tx_hash(tx_hash)
        own_key = _consumed_tx_key(canonical)
        won = claim_unique(
            self._stake_ledger_backend(),
            "INSERT INTO supply_stakes (publisher_id, amount_usd, slashed_usd, tx_hash) "
            "VALUES (?, ?, 0, ?)",
            (own_key, 0.0, canonical),
        )
        if not won:
            raise ValueError("stake tx_hash already recorded (replay rejected)")
        if self._deposit_recorded_under_another_key(canonical, own_key):
            # Canonicalising the key would otherwise UN-burn every deposit already
            # recorded verbatim: a hash burned as `tx-consumed:0xAB…` by an earlier build
            # is a fresh key once we lower-case it, and the replay would win the claim.
            # The row just inserted stays — it burns the canonical key from here on.
            raise ValueError("stake tx_hash already recorded (replay rejected)")

    def _deposit_recorded_under_another_key(self, canonical_tx: str, own_key: str) -> bool:
        """Is this deposit already on the ledger under a differently-cased ``tx_hash``?

        Only rows written before the burn key was canonicalised can be in that state, so
        this is a plain lookup rather than part of the claim — the claim above already
        decides every live race (all racers canonicalise to the same key).
        """
        if not canonical_tx.startswith("0x"):
            # Case IS significant for a base58 id; folding it would merge distinct txs
            # and reject a legitimate deposit.
            return False
        row = self._stake_ledger_backend().execute(
            "SELECT 1 FROM supply_stakes WHERE LOWER(tx_hash) = ? AND publisher_id <> ? LIMIT 1",
            (canonical_tx, own_key),
        ).fetchone()
        return row is not None

    def _require_stake_payer_proof(
        self, *, tx_hash: str, amount_usd: float, payer: str, signature: str
    ) -> str:
        """Bind a stake deposit to the wallet that actually paid it. Raises ValueError.

        Every stake deposit lands in the same platform settlement wallet, so a verifier
        that checks only recipient/amount/confirmations answers "did SOMEBODY pay?" —
        anyone watching inbound transfers could quote a stranger's tx hash and have the
        deposit credited as their own collateral. The atomic burn added earlier stops the
        SAME hash being credited twice; it does nothing about who gets the first credit.

        Same two-part rule the channel path uses (PAYAUTH-003 / 003b):
          1. the chain must tell us WHO paid (an unattributable transfer is refused), and
          2. the caller must prove CONTROL of that wallet by signing the canonical
             payer-proof challenge — the payer address is public in the transaction being
             quoted, so "I know the sender" proves nothing.

        There is deliberately NO escape hatch here: ``AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER``
        is scoped to the channel ledger, and stake is collateral a slash later consumes.
        """
        chain = _stake_chain()
        if not payer:
            logger.error(
                "Rejected stake deposit %s: verifier confirmed the transfer but reported "
                "no sender — the deposit cannot be bound to a payer", tx_hash[:12],
            )
            raise ValueError(
                "on-chain verification did not report the paying wallet — refusing to "
                "credit stake that cannot be bound to its payer"
            )
        if not _is_evm_address(payer):
            # No proof-of-control scheme exists for base58/Solana payers; refuse rather
            # than credit an unproven deposit (mirrors the channel ledger).
            raise ValueError(
                "proof of control over the paying wallet is only implemented for EVM "
                "addresses — contact the operator"
            )
        recovered = _recover_stake_payer(
            payer=payer, tx_hash=tx_hash, chain=chain,
            amount_usd=amount_usd, signature=signature,
        )
        if not recovered or not _wallet_matches(recovered, payer):
            logger.warning(
                "Rejected stake deposit %s claimed for payer %s without a valid payer "
                "proof (recovered %s)",
                tx_hash[:12], payer[:10], (recovered or "none")[:10],
            )
            # Hand back the exact text to sign: the challenge is tx-, chain- and
            # amount-bound, so a client reconstructing it by hand gets it wrong and
            # reads the refusal as "stake deposits are broken".
            challenge = payer_proof_challenge(
                payer=payer, tx_hash=tx_hash, chain=chain, deposit_usd=amount_usd,
            )
            raise ValueError(
                "missing or invalid payer proof — sign this exact message with the "
                f"wallet that paid and resend it as payer_signature: {challenge!r}"
            )
        return payer

    def stake(
        self,
        publisher_id: str,
        amount_usd: float,
        tx_hash: str = "",
        payer_signature: str = "",
        *,
        settled_ref: str = "",
    ) -> dict[str, Any]:
        """Post collateral for a publisher.

        ``settled_ref`` names collateral this hub has ALREADY collected itself — today a
        debit against the publisher's credit account, which is money the operator is
        physically holding, in their own ledger, and can slash. It is not a caller-supplied
        value: the route constructs it only after the debit succeeded, which is why it is
        keyword-only and never read from a request body. It exists because the on-chain path
        is unreachable for most deployments — the deposit verifier lives in a module the hub
        wheel and image do not ship, so in production every stake attempt failed and the only
        way through was AIMARKET_SUPPLY_SECURITY_RELAXED=1, which disables the collateral
        requirement wholesale. A hub with a working ledger should not have to choose between
        "no collateral at all" and "a verifier I do not have".
        """
        publisher_id = str(publisher_id or "").strip()
        if not publisher_id:
            raise ValueError("publisher_id is required")
        _reject_reserved_publisher(publisher_id)
        try:
            amount_usd = float(amount_usd)
        except (TypeError, ValueError) as exc:
            raise ValueError("amount_usd must be a number") from exc
        # `nan <= 0` and `inf <= 0` are both False, so the positivity check alone let a
        # non-finite credit through to the ledger — and a NaN/inf balance then satisfies
        # `stake < min_stake_usd` as False, i.e. it clears the stake gate outright.
        if not math.isfinite(amount_usd):
            raise ValueError("amount_usd must be a finite number")
        if amount_usd <= 0:
            raise ValueError("amount_usd must be positive")
        # Canonical form up front so the replay check below, the burn and the tx_hash the
        # credit row stores all name the deposit the same way — a check that runs on a
        # different spelling than the burn is not a replay check.
        tx_hash = _normalize_tx_hash(tx_hash)
        # In production EVERY stake credit must be backed by a verified, single-use on-chain
        # deposit — whatever its size. The amount condition this check used to carry
        # (`amount_usd >= self.policy.min_stake_usd`) was a complete bypass of the stake
        # requirement, not a shortcut: a publisher could credit itself $9.99 at a time
        # against a $25 minimum with no tx_hash, no on-chain verification and no replay
        # check, and supply_stake_add would accumulate the total straight past the publish
        # gate (inflating the hub trust anchor edge with it). Size never made a deposit
        # trustworthy, so size no longer decides whether we check it.
        if settled_ref:
            # Already collected by this hub. Recorded under its own reference so the
            # production gates can tell it from the dev sentinel: it is real collateral,
            # just not on a chain.
            tx_hash = settled_ref
            total = self.db.supply_stake_add(publisher_id, amount_usd, tx_hash)
            self.db.trust_add_edge(
                _HUB_ANCHOR, publisher_id, _stake_anchor_weight(total), "stake",
            )
            return {
                "publisher_id": publisher_id,
                "stake_usd": total,
                "trust_score": self.refresh_publisher_trust(publisher_id),
                "collateral": "credits",
            }
        if not self.policy.relaxed and _is_production_mode():
            if not tx_hash:
                raise ValueError(
                    "tx_hash required for stake deposits in production "
                    "(AIMARKET_SUPPLY_SECURITY_RELAXED=1 to bypass for dev)"
                )
            if tx_hash.startswith(_RESERVED_PUBLISHER_PREFIXES):
                # The ledger's own bookkeeping values share the tx_hash column. A caller
                # supplying one could plant another publisher's dev-credit sentinel and lock
                # them out of production; the on-chain verifier is not relied on to reject it.
                raise ValueError("tx_hash must not use a reserved stake-ledger prefix")
            if self.db.supply_stake_tx_exists(tx_hash):
                raise ValueError("stake tx_hash already recorded (replay rejected)")
            # A verified credit must not launder an unverified one: the stake row keeps a
            # single tx_hash, so allowing this write would overwrite the dev-credit sentinel
            # and make the whole (partly unverified) balance look verified. Once the balance
            # is back to ZERO there is no unverified money left on the books to launder, so
            # that is the (only) recovery route out of the sentinel — and it is the route the
            # refusal message names, which would otherwise be un-actionable: nothing else
            # clears the marker, so the publisher would be locked out of production forever.
            if (
                self.db.supply_stake_get(publisher_id) > 0
                and self.db.supply_stake_tx_exists(_unverified_stake_marker(publisher_id))
            ):
                raise ValueError(
                    "existing stake balance contains unverified dev credits — write the "
                    "balance off to zero before staking in production"
                )
            verified, onchain_payer = _verify_stake_deposit(tx_hash, amount_usd)
            if not verified:
                raise ValueError(
                    "stake deposit not verified on-chain — the transaction must pay the "
                    "platform recipient at least the staked amount with enough confirmations"
                )
            # PAYER-BOUND (see _require_stake_payer_proof): recipient+amount alone let a
            # publisher claim a stranger's inbound transfer as its own collateral.
            self._require_stake_payer_proof(
                tx_hash=tx_hash, amount_usd=amount_usd,
                payer=onchain_payer, signature=payer_signature,
            )
            self._consume_stake_tx(tx_hash)
        else:
            # Explicit dev/relaxed bypass. Nothing was verified, so the credit is TAGGED
            # durably instead of recording whatever hash the caller claimed; the production
            # gates refuse a tagged balance (see _require_verified_stake).
            tx_hash = _unverified_stake_marker(publisher_id)
        total = self.db.supply_stake_add(publisher_id, amount_usd, tx_hash)
        self.db.trust_add_edge(_HUB_ANCHOR, publisher_id, _stake_anchor_weight(total), "stake")
        trust = self.refresh_publisher_trust(publisher_id)
        return {"publisher_id": publisher_id, "stake_usd": total, "trust_score": trust}

    def slash(
        self,
        publisher_id: str,
        amount_usd: float,
        reason: str,
        *,
        evidence: dict[str, Any] | None = None,
        evidence_kind: str = "",
    ) -> dict[str, Any]:
        slashed, remaining = self.db.supply_stake_slash(publisher_id, amount_usd)
        self.db.trust_add_edge(_HUB_ANCHOR, publisher_id, _SLASH_EDGE_WEIGHT, "slash")
        trust = self.refresh_publisher_trust(publisher_id)
        # Consume the verdict for THIS publisher (pop: a leftover verdict from an earlier
        # refresh must never stand in for the one this slash just triggered — and a
        # monkeypatched/failed refresh leaves no verdict at all, which reads as degraded).
        if not self._lumen_health.pop(publisher_id, False):
            # The slash edge above only reaches the score through LUMEN. With the oracle
            # degraded the refresh retains the PRE-slash score, which silently erased the
            # slash's trust effect (the original fail-open: slash → 0.5 → still invokable).
            # Apply the same-magnitude penalty locally so the effect is durable regardless.
            trust = self._penalize_trust_locally(publisher_id, -_SLASH_EDGE_WEIGHT, reason)
        if slashed > 0:
            # Durable per-event log: feeds the cool-down + rolling daily cap and
            # keeps every slash auditable (the stake row only holds a cumulative sum).
            self.db.supply_slash_log(publisher_id, slashed, reason, evidence_kind)
        federated = False
        if self.slash_registry and slashed > 0:
            try:
                self.slash_registry.record_local_slash(
                    provider_hub=publisher_id,
                    slashed_usd=slashed,
                    dispute_id=f"supply_{int(time.time())}",
                    reason=reason,
                    signer=self.signer,
                    pom=None,
                    evidence=evidence,
                    evidence_kind=evidence_kind,
                )
                federated = True
            except Exception:
                federated = False
        return {
            "publisher_id": publisher_id,
            "slashed_usd": slashed,
            "stake_remaining_usd": remaining,
            "trust_score": trust,
            "federated": federated,
            "reason": reason,
        }

    def _slash_for_failure(
        self,
        publisher_id: str,
        product_id: str,
        capability_id: str,
        reason: str,
        *,
        evidence: dict[str, Any] | None = None,
        evidence_kind: str = "",
    ) -> None:
        if self.policy.relaxed:
            return
        stake = self.db.supply_stake_get(publisher_id)
        if stake <= 0:
            return
        # Cool-down: at most one failure-driven slash per window. Failures during
        # the cool-down still count against trust — only the stake is spared.
        cooldown = self.policy.slash_cooldown_s
        if cooldown > 0:
            age = self.db.supply_slash_last_age_s(publisher_id)
            if age is not None and age < cooldown:
                logger.info(
                    "slash cool-down active for %s (%.0fs of %.0fs) — %s not slashed",
                    publisher_id, age, cooldown, reason,
                )
                return
        slash_amt = min(stake * 0.05, 5.0)
        # Rolling daily cap: repeated bad days drain reputation and discoverability,
        # not the whole bond at once (innovation room for agents that can recover).
        cap = self.policy.slash_daily_cap_usd
        if cap > 0:
            already = self.db.supply_slash_total_recent(publisher_id, hours=24.0)
            slash_amt = min(slash_amt, max(0.0, cap - already))
            if slash_amt <= 0:
                logger.info(
                    "daily slash cap $%.2f reached for %s — %s not slashed",
                    cap, publisher_id, reason,
                )
                return
        self.slash(
            publisher_id, slash_amt, f"{reason}:{product_id}/{capability_id}",
            evidence=evidence, evidence_kind=evidence_kind,
        )

    # ── Self-bond (consumer cost/conduct bond → self-slash enforcement) ──
    # ARGUS stakes collateral and registers a bonded spend CEILING + its client self-bond
    # commitment. /self-bond/slash slashes that staked collateral on a declared-ceiling-
    # vs-observed-spend breach and federates the attestation. SCOPE: the observed spend
    # reaching slash_self_bond is already grounded — the API layer caps the submitted claim
    # at the spend the hub ledger actually debited for the bonded wallet, and refuses
    # outright when the hub holds no settlement record for it. This method therefore slashes
    # against a hub-verified number, not against whatever the disputer asserted; it clamps
    # the penalty at the declared bond on top of that.

    def register_self_bond(
        self,
        agent_id: str,
        evm_address: str,
        ceiling_usd: float,
        bond_usd: float,
        commitment: str = "",
    ) -> dict[str, Any]:
        agent_id = str(agent_id or "").strip()
        if not agent_id:
            raise ValueError("agent_id required")
        _reject_reserved_publisher(agent_id)
        if bond_usd <= 0 or ceiling_usd < 0:
            raise ValueError("bond_usd must be positive and ceiling_usd non-negative")
        # The bond must be backed by real staked collateral (same store publishers use).
        staked = self.db.supply_stake_get(agent_id)
        if not self.policy.relaxed and staked < bond_usd:
            raise ValueError(
                f"bond ${bond_usd:.2f} exceeds staked collateral ${staked:.2f} — "
                f"POST /ai-market/v2/supply/stake (publisher_id={agent_id}) first"
            )
        # A bond is a slashable promise; in production it must be backed by verified money.
        self._require_verified_stake(agent_id, "self-bond registration")
        self.db.self_bond_register(agent_id, str(evm_address or ""), float(ceiling_usd), float(bond_usd), "USDC", str(commitment or ""))
        return {
            "agent_id": agent_id,
            "ceiling_usd": float(ceiling_usd),
            "bond_usd": float(bond_usd),
            "staked_usd": staked,
            "commitment": str(commitment or ""),
            "status": "bonded",
        }

    def slash_self_bond(self, agent_id: str, observed_spend_usd: float, evidence: str = "") -> dict[str, Any]:
        agent_id = str(agent_id or "").strip()
        bond = self.db.self_bond_get(agent_id)
        if not bond:
            raise ValueError(f"no self-bond registered for agent_id={agent_id}")
        ceiling = float(bond.get("ceiling_usd", 0))
        bond_usd = float(bond.get("bond_usd", 0))
        observed = max(0.0, float(observed_spend_usd))
        overspend = max(0.0, observed - ceiling)
        if overspend <= 0:
            return {
                "agent_id": agent_id, "verdict": "within-bond", "overspend_usd": 0.0,
                "slashed_usd": 0.0, "ceiling_usd": ceiling, "observed_spend_usd": observed,
            }
        penalty = min(bond_usd, overspend)  # honest: capped at the declared bond
        result = self.slash(agent_id, penalty, f"self_bond_breach:declared_ceiling_{ceiling:.6f}_lt_observed_{observed:.6f}")
        self.db.self_bond_record_slash(agent_id, float(result.get("slashed_usd", 0.0)))
        return {
            "agent_id": agent_id, "verdict": "self-slash",
            "overspend_usd": overspend, "ceiling_usd": ceiling, "observed_spend_usd": observed,
            "slashed_usd": result.get("slashed_usd", 0.0),
            "stake_remaining_usd": result.get("stake_remaining_usd", 0.0),
            "federated": result.get("federated", False),
            "evidence": str(evidence or "")[:200],
        }


def _stake_chain() -> str:
    """Chain a stake deposit is expected on (also part of the payer-proof preimage)."""
    return os.getenv("AIMARKET_PAYMENT_CHAIN", "base")


def _verify_stake_deposit(tx_hash: str, amount_usd: float) -> tuple[bool, str]:
    """``(verified, on-chain payer address)`` for a stake deposit. Fail-closed.

    Uses the SENDER-returning verifier the channel ledger uses
    (``channels._verify_tx_onchain`` → ``on_chain.verify_tx_payment_details``) instead of
    the unbound ``on_chain.verify_tx_payment``. That unbound verifier's own docstring says
    it only answers "did *somebody* pay the recipient", which is not enough to decide
    WHOSE collateral a deposit becomes — the caller binds the credit to the reported
    payer (see ``SupplySecurity._require_stake_payer_proof``).

    ``verified`` is False whenever the verifier is unreachable, errors, or the transfer
    does not match recipient/amount/token/confirmations, so a standalone or misconfigured
    deploy never accepts an unverified stake in production. ``payer`` is "" when the
    transfer cannot be attributed — the caller refuses to credit then.
    """
    tx = (tx_hash or "").strip()
    if not tx:
        return False, ""
    try:
        result = _verify_tx_onchain(
            tx_hash=tx, amount_usd=amount_usd,
            chain=_stake_chain(), token=os.getenv("AIMARKET_PAYMENT_TOKEN", "USDC"),
        )
    except Exception as exc:
        logger.error("stake tx verification raised for %s: %s", tx[:12], exc)
        return False, ""
    if not result.get("ok"):
        logger.warning(
            "stake deposit %s not verified: %s", tx[:12], result.get("error", "unknown"),
        )
        return False, ""
    return True, str(result.get("sender") or "").strip()


def _recover_stake_payer(
    *, payer: str, tx_hash: str, chain: str, amount_usd: float, signature: str
) -> str | None:
    """Address that signed the CANONICAL payer-proof challenge for this deposit, or None.

    Delegates to the channel ledger's recovery helper, which delegates to
    ``on_chain.recover_channel_open_payer`` — one challenge definition, one
    normalisation rule, one verifier for both money doors. None on any failure
    (no signature, malformed signature, primitive not importable) and the caller
    treats None as unproven, so a deployment that cannot evaluate a proof never
    grants a credit on one.
    """
    return _recover_payer_address(
        payer=payer, tx_hash=tx_hash, chain=chain,
        deposit_usd=amount_usd, signature=signature,
    )


def _response_canonical(result: Any) -> str:
    return json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _bound_response_canonical(capability_id: str, product_id: str, input_payload: Any, result: Any) -> str:
    """Canonical binding the response to the exact request it answers.

    Includes capability_id, product_id and a hash of the request input so a
    provider's signature is valid only for THIS invocation — preventing replay of
    a stale signed response against a different request.
    """
    import hashlib

    input_json = json.dumps(input_payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    input_hash = hashlib.sha256(input_json.encode("utf-8")).hexdigest()
    return json.dumps(
        {
            "capability_id": capability_id or "",
            "product_id": product_id or "",
            "input_sha256": input_hash,
            "result": result,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
