"""Publish-time THEMIS integration."""

from __future__ import annotations

import base64
import hashlib
import json

from unittest.mock import ANY

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.supply_chain_admission import (
    AUDITOR_CAPABILITY_ID,
    AUDITOR_PRODUCT_ID,
    AdmissionConfig,
    SupplyChainAdmission,
)


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _signature(private_key: Ed25519PrivateKey, result: dict, input_payload: dict) -> str:
    canonical = _canonical(
        {
            "capability_id": AUDITOR_CAPABILITY_ID,
            "product_id": AUDITOR_PRODUCT_ID,
            "input_sha256": hashlib.sha256(_canonical(input_payload)).hexdigest(),
            "result": result,
        }
    )
    return base64.b64encode(private_key.sign(canonical)).decode()


def _config(private_key: Ed25519PrivateKey, mode: str = "advisory") -> AdmissionConfig:
    pubkey = base64.b64encode(private_key.public_key().public_bytes_raw()).decode()
    return AdmissionConfig(
        mode=mode,
        # A globally-routable literal. It was 203.0.113.10 (TEST-NET-3) with a comment
        # calling that "public", which it is not: 203.0.113.0/24 is IANA-reserved for
        # documentation and `ip_address(...).is_global` says so. It only passed because the
        # old guard was an enumerated blocklist that happened not to list documentation
        # ranges; once the guard refuses anything non-global, the premise breaks. Nothing is
        # dialled here — httpx.AsyncClient is monkeypatched in every test that uses this.
        auditor_url="https://93.184.216.34/invoke",
        auditor_pubkey=pubkey,
        timeout_seconds=2,
        request_metis=True,
        max_price_per_call_usd=1,
        max_monthly_cost_usd=1_000,
        minimum_score=80,
        minimum_evidence_count=0,
        require_https=True,
        require_provider_key=True,
        require_metis_declaration=False,
        allow_insecure_auditor=False,
    )


@pytest.fixture
def manifest():
    return {
        "product_id": "invoice-reader",
        "capability_id": "invoice.read@v1",
        "name": "Invoice Reader",
        "description": "Extracts invoice fields",
        "invoke_url": "https://agents.example/invoke",
        "publisher_id": "trusted-vendor",
        "provider_pubkey": base64.b64encode(bytes(32)).decode(),
        "price_per_call_usd": 0.02,
        "input_schema": {
            "type": "object",
            "properties": {"document_id": {"type": "string", "maxLength": 128}},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"total": {"type": "number"}},
            "additionalProperties": False,
        },
        "verification": {"metis": True, "mode": "advisory-async"},
        "permissions": {"read_personal_data": True, "human_approval_for_high_impact": True},
        "evidence": [],
        "usage": {"monthly_invocations": 100, "data_classification": "confidential"},
    }


class _Response:
    def __init__(self, body: dict, signature: str = "", status_code: int = 200):
        self._body = body
        self.status_code = status_code
        self.headers = {"X-Provider-Signature": signature}
        self.content = _canonical(body)

    def json(self):
        return self._body


def _client_factory(private_key, result, *, verification=None, bad_signature=False):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, _url, *, json, headers=None, extensions=None):
            input_payload = json["input"]
            sig = _signature(private_key, result, input_payload)
            if bad_signature:
                sig = base64.b64encode(bytes(64)).decode()
            return _Response({"success": True, "result": result}, sig)

        async def get(self, url, headers=None, extensions=None):
            verification_id = url.rsplit("/", 1)[-1]
            metis = verification or {"status": "completed", "score": 94, "route": "fast"}
            wrapped = {"metis": metis}
            sig = _signature(private_key, wrapped, {"verification_id": verification_id})
            return _Response({"success": True, "result": wrapped}, sig)

    return _Client


def _result(decision="approve", *, metis_status="pending"):
    metis = {"status": metis_status}
    if metis_status == "pending":
        metis["verification_id"] = "verification-123"
    return {
        "decision": decision,
        "score": 96 if decision == "approve" else 71,
        "risk_tier": "low" if decision == "approve" else "high",
        "findings": [],
        "remediations": [],
        "owasp_agentic_risks": [],
        "metis": metis,
    }


async def test_off_mode_never_contacts_auditor(tmp_path, manifest, monkeypatch):
    private = Ed25519PrivateKey.generate()
    db = HubDatabase(tmp_path / "off.db")
    service = SupplyChainAdmission(db, _config(private, "off"))

    class _MustNotRun:
        def __init__(self, *args, **kwargs):
            raise AssertionError("off mode attempted a network call")

    monkeypatch.setattr("aimarket_hub.supply_chain_admission.httpx.AsyncClient", _MustNotRun)
    verdict = await service.evaluate(manifest)
    assert verdict == {"status": "disabled", "mode": "off", "blocked": False}
    assert db.supply_audit_summary()["total"] == 0


async def test_advisory_accepts_only_a_valid_signed_result(tmp_path, manifest, monkeypatch):
    private = Ed25519PrivateKey.generate()
    db = HubDatabase(tmp_path / "advisory.db")
    service = SupplyChainAdmission(db, _config(private))
    monkeypatch.setattr(
        "aimarket_hub.supply_chain_admission.httpx.AsyncClient",
        _client_factory(private, _result()),
    )

    verdict = await service.evaluate(manifest)
    assert verdict["decision"] == "approve"
    assert verdict["blocked"] is False
    assert verdict["receipt"]["signature"]
    assert verdict["metis"]["status"] == "pending"
    assert db.supply_audit_summary() == {
        "total": 1,
        "approved": 1,
        "review": 0,
        "rejected": 0,
        "unavailable": 0,
        "metis_pending": 1,
        "latest": {
            "decision": "approve",
            "score": 96,
            "risk_tier": "low",
            "metis_status": "pending",
            "capability_id": "invoice.read@v1",
            "product_id": "invoice-reader",
            "created_at": db.supply_audits_recent()[0]["created_at"],
        },
    }


async def test_invalid_signature_is_unavailable_not_a_verdict(tmp_path, manifest, monkeypatch):
    private = Ed25519PrivateKey.generate()
    db = HubDatabase(tmp_path / "bad-signature.db")
    service = SupplyChainAdmission(db, _config(private))
    monkeypatch.setattr(
        "aimarket_hub.supply_chain_admission.httpx.AsyncClient",
        _client_factory(private, _result(), bad_signature=True),
    )
    verdict = await service.evaluate(manifest)
    assert verdict["status"] == "unavailable"
    assert verdict["decision"] is None
    assert verdict["blocked"] is False  # advisory is observable, not a gate
    assert verdict["error_code"] == "auditor_unavailable"


@pytest.mark.parametrize("decision", ["review", "reject"])
async def test_enforce_blocks_non_approval(tmp_path, manifest, monkeypatch, decision):
    private = Ed25519PrivateKey.generate()
    db = HubDatabase(tmp_path / f"{decision}.db")
    service = SupplyChainAdmission(db, _config(private, "enforce"))
    monkeypatch.setattr(
        "aimarket_hub.supply_chain_admission.httpx.AsyncClient",
        _client_factory(private, _result(decision)),
    )
    verdict = await service.evaluate(manifest)
    assert verdict["decision"] == decision
    assert verdict["blocked"] is True


async def test_enforce_fails_closed_when_not_configured(tmp_path, manifest):
    private = Ed25519PrivateKey.generate()
    config = _config(private, "enforce")
    config = AdmissionConfig(**{**config.__dict__, "auditor_pubkey": ""})
    db = HubDatabase(tmp_path / "misconfigured.db")
    verdict = await SupplyChainAdmission(db, config).evaluate(manifest)
    assert verdict["status"] == "unavailable"
    assert verdict["blocked"] is True


async def test_lazy_metis_status_is_verified_and_persisted(tmp_path, manifest, monkeypatch):
    private = Ed25519PrivateKey.generate()
    db = HubDatabase(tmp_path / "metis.db")
    service = SupplyChainAdmission(db, _config(private))
    monkeypatch.setattr(
        "aimarket_hub.supply_chain_admission.httpx.AsyncClient",
        _client_factory(private, _result(), verification={"status": "completed", "score": 93}),
    )
    verdict = await service.evaluate(manifest)
    await service.refresh_pending()
    row = db.supply_audits_recent()[0]
    assert row["audit_id"] == verdict["audit_id"]
    assert row["metis"]["status"] == "completed"
    assert row["metis"]["score"] == 93
    assert row["receipt"]["signature"] == verdict["receipt"]["signature"]
    assert row["metis"].get("poll_signature")
    assert db.supply_audit_summary()["metis_pending"] == 0


def test_auditor_url_rejects_cloud_metadata(tmp_path):
    private = Ed25519PrivateKey.generate()
    pubkey = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    config = AdmissionConfig(
        mode="enforce",
        auditor_url="https://169.254.169.254/latest/meta-data",
        auditor_pubkey=pubkey,
        timeout_seconds=2,
        request_metis=False,
        max_price_per_call_usd=1,
        max_monthly_cost_usd=1_000,
        minimum_score=80,
        minimum_evidence_count=0,
        require_https=True,
        require_provider_key=True,
        require_metis_declaration=False,
        allow_insecure_auditor=False,
    )
    service = SupplyChainAdmission(HubDatabase(tmp_path / "ssrf.db"), config)
    assert service._endpoint is None
    assert "blocked" in service._config_error or "private" in service._config_error or "network" in service._config_error


async def test_oversized_evidence_is_fail_closed_in_enforce(tmp_path, manifest, monkeypatch):
    private = Ed25519PrivateKey.generate()
    db = HubDatabase(tmp_path / "huge.db")
    service = SupplyChainAdmission(db, _config(private, "enforce"))

    class _MustNotRun:
        def __init__(self, *args, **kwargs):
            raise AssertionError("oversized dossier must not reach the auditor")

    monkeypatch.setattr("aimarket_hub.supply_chain_admission.httpx.AsyncClient", _MustNotRun)
    manifest = {
        **manifest,
        "input_schema": {"type": "object", "pad": "y" * 300_000},
    }
    verdict = await service.evaluate(manifest)
    assert verdict["status"] == "unavailable"
    assert verdict["blocked"] is True
    assert verdict["error_code"] == "auditor_unavailable"


def test_public_rows_never_persist_manifest_or_evidence_urls(tmp_path, manifest, monkeypatch):
    private = Ed25519PrivateKey.generate()
    db_path = tmp_path / "privacy.db"
    db = HubDatabase(db_path)
    service = SupplyChainAdmission(db, _config(private))
    monkeypatch.setattr(
        "aimarket_hub.supply_chain_admission.httpx.AsyncClient",
        _client_factory(private, _result(metis_status="skipped")),
    )
    import asyncio

    asyncio.run(service.evaluate(manifest))
    raw = db_path.read_bytes()
    assert b"agents.example" not in raw
    assert b"Extracts invoice fields" not in raw


@pytest.mark.parametrize(
    ("decision", "expected_status", "published"),
    [("approve", 200, True), ("review", 403, False)],
)
def test_supply_register_runs_admission_before_catalog_write(
    tmp_path, manifest, monkeypatch, decision, expected_status, published
):
    manifest = {**manifest, "invoke_url": "http://127.0.0.1:3456/invoke"}
    private = Ed25519PrivateKey.generate()
    pubkey = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    monkeypatch.setenv("AIMARKET_PUBLISH_TOKEN", "publish-secret")
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")
    monkeypatch.setenv("AIMARKET_SKIP_SEED", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE", "enforce")
    monkeypatch.setenv(
        # Globally routable, for the same reason as in _config above.
        "AIMARKET_SUPPLY_CHAIN_AUDITOR_URL", "https://93.184.216.34/invoke"
    )
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", pubkey)
    monkeypatch.setattr(
        "aimarket_hub.supply_chain_admission.httpx.AsyncClient",
        _client_factory(private, _result(decision, metis_status="skipped")),
    )

    config = HubConfig()
    config.db_path = str(tmp_path / f"api-{decision}.db")
    config.signing_key_path = str(tmp_path / f"key-{decision}")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    with TestClient(app) as client:
        response = client.post(
            "/ai-market/v2/supply/register",
            json=manifest,
            headers={"Authorization": "Bearer publish-secret"},
        )
        assert response.status_code == expected_status, response.text
        if published:
            assert response.json()["supply_chain_admission"]["decision"] == "approve"
        else:
            assert response.json()["detail"]["code"] == "supply_chain_admission_denied"
        telemetry = client.get("/ai-market/v2/stats/live").json()
        assert telemetry["summary"]["supply_chain_admission"]["total"] == 1
        assert telemetry["supply_chain_audits"][0]["decision"] == decision

    assert (db.get_capability(manifest["product_id"], manifest["capability_id"]) is not None) is published


# ───────────────── default mode and attestation policy passthrough ─────────────────


def test_a_pinned_auditor_records_verdicts_without_a_second_env_var(monkeypatch):
    """A fully wired gate used to sit at mode=off recording nothing."""
    monkeypatch.delenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE", raising=False)
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", "a" * 43 + "=")
    assert AdmissionConfig.from_env().mode == "advisory"


def test_an_unpinned_auditor_stays_off_and_says_so(monkeypatch, caplog):
    monkeypatch.delenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE", raising=False)
    monkeypatch.delenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", raising=False)
    with caplog.at_level("WARNING"):
        assert AdmissionConfig.from_env().mode == "off"
    assert "admission is off" in caplog.text


@pytest.mark.parametrize("raw,expected", [("off", "off"), ("enforce", "enforce"), ("nonsense", "off")])
def test_an_explicit_mode_always_wins(monkeypatch, raw, expected):
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE", raw)
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", "a" * 43 + "=")
    assert AdmissionConfig.from_env().mode == expected


def test_default_policy_stays_compatible_with_an_older_auditor(tmp_path):
    private = Ed25519PrivateKey.generate()
    service = SupplyChainAdmission(HubDatabase(tmp_path / "policy.db"), _config(private))
    policy = service._policy()
    for key in (
        "require_evidence_digests",
        "require_evidence_attestation",
        "require_independent_attestation",
        "require_permission_attestation",
    ):
        assert key not in policy, "an auditor that forbids unknown fields would 400"


def test_operator_can_demand_attestations_through_the_hub(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_ADMISSION_REQUIRE_EVIDENCE_ATTESTATION", "1")
    monkeypatch.setenv("AIMARKET_ADMISSION_REQUIRE_INDEPENDENT_ATTESTATION", "true")
    monkeypatch.setenv("AIMARKET_ADMISSION_REQUIRE_PERMISSION_ATTESTATION", "on")
    monkeypatch.setenv("AIMARKET_ADMISSION_REQUIRE_EVIDENCE_DIGESTS", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE", "advisory")
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", "a" * 43 + "=")
    config = AdmissionConfig.from_env()
    service = SupplyChainAdmission(HubDatabase(tmp_path / "knobs.db"), config)
    policy = service._policy()
    assert policy["require_evidence_attestation"] is True
    assert policy["require_independent_attestation"] is True
    assert policy["require_permission_attestation"] is True
    assert policy["require_evidence_digests"] is False


# ═════════════ persisted attestations and runtime counter-evidence ═════════════

from aimarket_hub.supply_chain_admission import (  # noqa: E402
    declared_permissions,
    permissions_digest,
    violation_message,
)


def _audit_row(db, manifest, attestations, decision="approve"):
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))
    record = service._base_record(manifest)
    record.update(
        status="completed",
        decision=decision,
        score=100,
        risk_tier="low",
        attestations=service._sanitize_attestations(attestations),
    )
    db.supply_audit_record(record)
    return record


def test_the_audit_row_keeps_what_was_actually_verified(tmp_path, manifest):
    db = HubDatabase(tmp_path / "attest.db")
    _audit_row(db, manifest, {
        "evidence_declared": 2,
        "evidence_verified": 1,
        "evidence_counted_kinds": ["sbom", "independent_audit"],
        "evidence_independently_attested": True,
        "permissions_signed": True,
        "permissions_signature_valid": True,
        "permissions_bound_to_provider_key": True,
        "permissions_sha256": "a" * 64,
        "runtime_violations_verified": 0,
        "runtime_violations_contradicting": [],
    })
    row = db.supply_audits_recent(limit=1)[0]
    stored = row["attestations"]
    assert stored["evidence_verified"] == 1
    assert stored["evidence_independently_attested"] is True
    assert stored["permissions_bound_to_provider_key"] is True
    assert stored["evidence_counted_kinds"] == ["independent_audit", "sbom"]
    assert row["permissions_sha256"] == permissions_digest(declared_permissions(manifest))


def test_the_attestation_block_is_bounded_not_trusted(tmp_path, manifest):
    db = HubDatabase(tmp_path / "bounded.db")
    _audit_row(db, manifest, {
        "evidence_declared": -5,
        "evidence_verified": 10 ** 9,
        "evidence_counted_kinds": ["x" * 400] + [f"k{i}" for i in range(50)],
        "permissions_signature_valid": "yes",
        "permissions_sha256": "not-a-digest",
        "runtime_violations_contradicting": ["spend_money", "made_up_permission"],
        "dossier": "https://secret.example/internal",
    })
    stored = db.supply_audits_recent(limit=1)[0]["attestations"]
    assert stored["evidence_declared"] == 0 and stored["evidence_verified"] == 0
    assert len(stored["evidence_counted_kinds"]) <= 16
    assert all(len(kind) <= 48 for kind in stored["evidence_counted_kinds"])
    assert stored["permissions_signature_valid"] is None
    assert stored["permissions_sha256"] == ""
    assert stored["runtime_violations_contradicting"] == ["spend_money"]
    assert "dossier" not in stored


def test_declaration_digest_matches_the_auditor_wire_format():
    """Pinned bytes: THEMIS verifies these statements with its own implementation."""
    assert violation_message(
        capability_id="invoice.read@v1",
        permission="spend_money",
        permissions_sha256="CD" * 32,
        product_id="invoice-reader",
    ) == (
        b'{"capability_id":"invoice.read@v1","permission":"spend_money",'
        b'"permissions_sha256":"' + b"cd" * 32 + b'",'
        b'"product_id":"invoice-reader","statement":"aimarket.violation.v1"}'
    )
    assert permissions_digest({"spend_money": False}) == hashlib.sha256(
        b'{"spend_money":false}'
    ).hexdigest()
    # Every known flag is present, so an absent key and an explicit false agree.
    assert declared_permissions({}) == declared_permissions({"execute_code": False})
    assert len(declared_permissions({})) == 7


def _sign_violation(private, manifest, permission, digest=None):
    message = violation_message(
        capability_id=manifest["capability_id"],
        permission=permission,
        permissions_sha256=digest or permissions_digest(declared_permissions(manifest)),
        product_id=manifest["product_id"],
    )
    return base64.b64encode(private.sign(message)).decode()


def _reporter():
    private = Ed25519PrivateKey.generate()
    return private, base64.b64encode(private.public_key().public_bytes_raw()).decode()


def test_two_reporters_contradict_a_declaration_and_reach_the_stake_ladder(tmp_path, manifest):
    db = HubDatabase(tmp_path / "violations.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))

    first, first_key = _reporter()
    outcome = service.record_permission_violation(
        product_id=manifest["product_id"], capability_id=manifest["capability_id"],
        permission="spend_money", reporter_pubkey=first_key,
        signature=_sign_violation(first, manifest, "spend_money"),
    )
    assert (outcome["accepted"], outcome["distinct_reporters"], outcome["contradicted"]) == (True, 1, False)

    # the same reporter again is one voice, not two
    repeat = service.record_permission_violation(
        product_id=manifest["product_id"], capability_id=manifest["capability_id"],
        permission="spend_money", reporter_pubkey=first_key,
        signature=_sign_violation(first, manifest, "spend_money"),
    )
    assert (repeat["duplicate"], repeat["distinct_reporters"]) == (True, 1)

    second, second_key = _reporter()
    final = service.record_permission_violation(
        product_id=manifest["product_id"], capability_id=manifest["capability_id"],
        permission="spend_money", reporter_pubkey=second_key,
        signature=_sign_violation(second, manifest, "spend_money"),
    )
    # Two distinct KEYS, but neither identity was authenticated -- and minting a keypair
    # is free, so this must NOT reach the stake ladder. (This assertion used to read
    # `== (2, True)`: the two-reporter consensus was satisfiable at zero cost, which is
    # how an anonymous caller could slash any publisher.)
    assert (final["distinct_reporters"], final["contradicted"]) == (2, False)
    assert final["bound_reporters"] == 0


def test_two_authenticated_reporters_do_reach_the_stake_ladder(tmp_path, manifest):
    """The feature still works — for reporters whose identity the hub verified."""
    db = HubDatabase(tmp_path / "violations_bound.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))

    outcomes = []
    for i in range(2):
        private, pub = _reporter()
        outcomes.append(service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=pub,
            signature=_sign_violation(private, manifest, "spend_money"),
            consumer_id=f"agent-{i}", consumer_bound=True,
        ))
    assert outcomes[0]["contradicted"] is False           # one voice is not consensus
    assert outcomes[1]["bound_reporters"] == 2
    assert outcomes[1]["contradicted"] is True


def test_many_keys_from_one_authenticated_identity_are_one_voice(tmp_path, manifest):
    """Rotating reporter keys under one bound identity does not manufacture consensus."""
    db = HubDatabase(tmp_path / "violations_rotate.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))

    last = None
    for _ in range(5):
        private, pub = _reporter()
        last = service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=pub,
            signature=_sign_violation(private, manifest, "spend_money"),
            consumer_id="agent-solo", consumer_bound=True,
        )
    assert last["distinct_reporters"] == 5
    assert last["bound_reporters"] == 1
    assert last["contradicted"] is False


@pytest.mark.parametrize("case", ["forged", "declared", "unknown_capability", "unknown_permission"])
def test_unverifiable_or_meaningless_reports_are_refused(tmp_path, manifest, case):
    db = HubDatabase(tmp_path / f"refuse-{case}.db")
    declaring = dict(manifest)
    if case == "declared":
        declaring = {**manifest, "permissions": {**manifest.get("permissions", {}), "spend_money": True}}
    _audit_row(db, declaring, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))
    private, key = _reporter()

    if case == "forged":
        outcome = service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=key,
            signature=_sign_violation(private, manifest, "execute_code"),
        )
        assert outcome == {"accepted": False, "reason": "signature_invalid"}
    elif case == "declared":
        outcome = service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=key,
            signature=_sign_violation(private, declaring, "spend_money"),
        )
        assert outcome == {"accepted": False, "reason": "permission_was_declared"}
    elif case == "unknown_capability":
        outcome = service.record_permission_violation(
            product_id="never-published", capability_id="nope@v1",
            permission="spend_money", reporter_pubkey=key,
            signature=_sign_violation(private, manifest, "spend_money"),
        )
        assert outcome == {"accepted": False, "reason": "no_declaration_on_record"}
    else:
        outcome = service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="become_root", reporter_pubkey=key,
            signature=_sign_violation(private, manifest, "spend_money"),
        )
        assert outcome == {"accepted": False, "reason": "unknown_permission"}


def test_a_report_against_an_old_declaration_stops_applying(tmp_path, manifest):
    """Declaring honestly must retire stale accusations."""
    db = HubDatabase(tmp_path / "retire.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))
    private, key = _reporter()
    stale = permissions_digest({"spend_money": False})
    outcome = service.record_permission_violation(
        product_id=manifest["product_id"], capability_id=manifest["capability_id"],
        permission="spend_money", reporter_pubkey=key,
        signature=_sign_violation(private, manifest, "spend_money", digest=stale),
    )
    assert outcome == {"accepted": False, "reason": "signature_invalid"}


def test_counter_evidence_reaches_the_auditor_only_when_it_exists(tmp_path, manifest):
    """An AUTHENTICATED reporter's contradiction is what the auditor is allowed to see.

    This test used to pass an UNBOUND report and assert it reached the auditor, which was
    the defect rather than the contract: THEMIS counts distinct issuer KEYS against
    ``runtime_violation_min_reporters``, and its own docstring delegates the Sybil
    resistance to this hub precisely because keys are free.
    """
    db = HubDatabase(tmp_path / "passthrough.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))
    assert "runtime_violations" not in service._audit_input(manifest)

    private, key = _reporter()
    service.record_permission_violation(
        product_id=manifest["product_id"], capability_id=manifest["capability_id"],
        permission="spend_money", reporter_pubkey=key,
        signature=_sign_violation(private, manifest, "spend_money"),
        consumer_id="consumer-real", consumer_bound=True,
    )
    payload = service._audit_input(manifest)
    assert payload["runtime_violations"] == [
        {"permission": "spend_money", "attestation": {"issuer": key, "signature": ANY}}
    ]


def test_two_throwaway_keys_cannot_contradict_a_declaration(tmp_path, manifest):
    """The attack, as a regression: free keypairs must not reach the reporter threshold.

    THEMIS's default ``runtime_violation_min_reporters`` is 2 and it counts DISTINCT ISSUER
    KEYS. Anyone can POST /api/v2/supply/permission-violation with no Authorization header,
    so two generated keypairs used to produce a critical
    ``permissions.declaration_contradicted`` — decision "reject", and under enforce mode a
    refused publish for any capability in the catalogue, at zero cost to the attacker.
    """
    db = HubDatabase(tmp_path / "sybil.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))

    for _ in range(5):  # comfortably over any threshold
        private, key = _reporter()
        outcome = service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=key,
            signature=_sign_violation(private, manifest, "spend_money"),
        )
        assert outcome["accepted"] is True, "the report is still RECORDED"

    # Recorded and inspectable...
    assert len(db.supply_permission_violations_for(
        manifest["product_id"], manifest["capability_id"],
        permissions_digest(declared_permissions(manifest)),
    )) == 5
    # ...but it cannot vote.
    assert "runtime_violations" not in service._audit_input(manifest)


def test_one_authenticated_reporter_still_reaches_the_auditor_alongside_anonymous_noise(
    tmp_path, manifest
):
    """The filter must drop the unbound reports, not the whole batch."""
    db = HubDatabase(tmp_path / "mixed.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))

    for _ in range(3):
        private, key = _reporter()
        service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=key,
            signature=_sign_violation(private, manifest, "spend_money"),
        )
    bound_private, bound_key = _reporter()
    service.record_permission_violation(
        product_id=manifest["product_id"], capability_id=manifest["capability_id"],
        permission="spend_money", reporter_pubkey=bound_key,
        signature=_sign_violation(bound_private, manifest, "spend_money"),
        consumer_id="consumer-paid", consumer_bound=True,
    )

    payload = service._audit_input(manifest)
    issuers = [r["attestation"]["issuer"] for r in payload["runtime_violations"]]
    assert issuers == [bound_key]


def test_the_report_store_is_capped_so_a_public_route_cannot_grow_forever(tmp_path, manifest):
    db = HubDatabase(tmp_path / "cap.db")
    _audit_row(db, manifest, {})
    service = SupplyChainAdmission(db, _config(Ed25519PrivateKey.generate()))
    accepted = 0
    for _ in range(db.MAX_VIOLATION_REPORTERS + 5):
        private, key = _reporter()
        outcome = service.record_permission_violation(
            product_id=manifest["product_id"], capability_id=manifest["capability_id"],
            permission="spend_money", reporter_pubkey=key,
            signature=_sign_violation(private, manifest, "spend_money"),
        )
        assert outcome["accepted"] is True
        accepted += 0 if outcome["duplicate"] else 1
    assert accepted == db.MAX_VIOLATION_REPORTERS
    assert len(db.supply_permission_violations_for(
        manifest["product_id"], manifest["capability_id"],
        permissions_digest(declared_permissions(manifest)),
    )) == db.MAX_VIOLATION_REPORTERS


def test_reporting_a_violation_over_http_is_rate_limited_and_signature_checked(
    tmp_path, manifest, monkeypatch
):
    monkeypatch.setenv("AIMARKET_SKIP_SEED", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE", "advisory")
    monkeypatch.setenv("AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY", "a" * 43 + "=")
    config = HubConfig()
    config.db_path = str(tmp_path / "api-violation.db")
    config.signing_key_path = str(tmp_path / "api-violation-key")
    db = HubDatabase(config.db_path)
    _audit_row(db, manifest, {})
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))

    private, key = _reporter()
    body = {
        "product_id": manifest["product_id"],
        "capability_id": manifest["capability_id"],
        "permission": "spend_money",
        "reporter_pubkey": key,
        "signature": _sign_violation(private, manifest, "spend_money"),
        "consumer_id": "consumer:argus-1",
    }
    with TestClient(app) as client:
        ok = client.post("/ai-market/v2/supply/permission-violation", json=body)
        forged = client.post(
            "/ai-market/v2/supply/permission-violation",
            json={**body, "reporter_pubkey": _reporter()[1]},
        )
        flood = [
            client.post("/ai-market/v2/supply/permission-violation", json=body)
            for _ in range(14)
        ]
    assert ok.status_code == 200, ok.text
    payload = ok.json()
    assert (payload["recorded"], payload["distinct_reporters"], payload["contradicted"]) == (
        True, 1, False,
    )
    assert payload["slashed"] is False
    assert forged.status_code == 400
    assert forged.json()["error"] == "signature_invalid"
    assert any(r.status_code == 429 for r in flood), "the public intake must be rate limited"


def test_enforce_readiness_names_what_is_missing(tmp_path, manifest):
    db = HubDatabase(tmp_path / "ready.db")
    private = Ed25519PrivateKey.generate()

    off = SupplyChainAdmission(db, _config(private, mode="off"))
    assert off.enforce_readiness()["ready_for_enforce"] is False
    assert "mode_off_no_verdicts_observed" in off.enforce_readiness()["blockers"]

    unpinned = SupplyChainAdmission(
        db, AdmissionConfig(**{**_config(private).__dict__, "auditor_pubkey": ""})
    )
    assert "auditor_pubkey_not_pinned" in unpinned.enforce_readiness()["blockers"]

    advisory = SupplyChainAdmission(db, _config(private))
    assert advisory.enforce_readiness()["blockers"] == ["no_completed_verdict_observed"]

    _audit_row(db, manifest, {})
    ready = advisory.enforce_readiness()
    assert (ready["ready_for_enforce"], ready["blockers"]) == (True, [])
    assert ready["recent_completed"] == 1
    assert advisory.public_summary()["enforce_readiness"]["ready_for_enforce"] is True
