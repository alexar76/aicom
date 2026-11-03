"""Post-quarantine assay: sandbox evidence, then automatic admission.

A fluent well-known is not a reason to trust anyone. These tests pin that
the scorecard ignores names/descriptions, that a pass auto-admits a pending
peer, and that an LLM judge may only veto live evidence — never mint a pass
from marketing copy.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.federation_assay import (
    HARD_CHECKS,
    MAX_SANDBOX_BYTES,
    MAX_SANDBOX_CANDIDATES,
    assay_blockers,
    evidence_bundle,
    parse_judge_text,
    run_assay,
    sandbox_input_for_tool,
    score_verdict,
)
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
STRANGER = "https://stranger.example"


def test_sandbox_input_fills_required_from_schema():
    tool = {
        "capability_id": "charon.position.risk@v1",
        "input_schema": {
            "type": "object",
            "required": ["chain", "address"],
            "properties": {
                "chain": {"type": "string", "enum": ["ethereum", "base"]},
                "address": {"type": "string", "description": "borrower address (0x…)"},
                "quote_exit": {"type": "boolean"},
            },
        },
    }
    inp = sandbox_input_for_tool(tool)
    assert inp == {
        "chain": "ethereum",
        "address": "0x0000000000000000000000000000000000000001",
    }


def test_sandbox_input_prefers_the_publishers_example_or_default():
    tool = {"input_schema": {"type": "object", "required": ["domain", "period", "tld"], "properties": {
        "domain": {"type": "string", "examples": ["example.com", "example.org"]},
        "period": {"type": "integer", "default": 1},
        "tld": {"type": "string", "enum": ["com", "net"]},
    }}}
    assert sandbox_input_for_tool(tool) == {"domain": "example.com", "period": 1, "tld": "com"}


def test_sandbox_input_stays_empty_without_required():
    assert sandbox_input_for_tool({"input_schema": {"type": "object", "properties": {}}}) == {}


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    env.setdefault("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        client.hub_db = db  # type: ignore[attr-defined]
        yield client


@pytest.fixture
def resolvable(monkeypatch):
    import aimarket_hub.crawler as crawler

    def _syntactic(url: str) -> bool:
        return url.startswith(("http://", "https://")) and "localhost" not in url

    monkeypatch.setattr(crawler, "_url_is_safe", _syntactic)
    return _syntactic


def _peer_docs(signer: Signer, *, name: str, description: str, price: float = 0.0):
    generated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest = {
        "protocol_version": "v1",
        "generated_at": generated,
        "capabilities_count": 1,
        "tools": [
            {
                "capability_id": "probe.free@v1",
                "product_id": "p1",
                "name": name,
                "description": description,
                "price_per_call_usd": price,
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            }
        ],
    }
    manifest["signature"] = signer.sign_manifest(manifest)
    well_known = {
        "name": name,
        "protocol_versions": ["v2"],
        "manifest_url": f"{STRANGER}/ai-market/manifest",
        "mcp_endpoint": f"{STRANGER}/ai-market/v2/invoke",
        "signer_public_key": signer.public_key_b64,
        "capabilities_count": 1,
    }
    well_known["signature"] = signer.sign_object(well_known)
    return well_known, manifest


async def _signed_post(signer: Signer, _url, body, _headers):
    receipt = {
        "nonce": "assay-1",
        "product_id": body.get("product_id") or "",
        "capability_id": body.get("capability_id") or "",
        "price_usd": 0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "success": True,
        "latency_ms": 4,
    }
    receipt["signature"] = signer.sign_receipt(receipt)
    return {"http_status": 200, "json": {"ok": True, "receipt": receipt}, "bytes": 80}


def test_judge_reads_openrouter_minimax_from_fleet_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-real")
    monkeypatch.delenv("AIMARKET_FEDERATION_JUDGE_KEY", raising=False)
    monkeypatch.delenv("AIMARKET_FEDERATION_JUDGE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_FEDERATION_JUDGE_MODEL", raising=False)
    config = HubConfig()
    assert config.federation_judge_key == "sk-or-test-not-real"
    assert config.federation_judge_url.endswith("/chat/completions")
    assert config.federation_judge_model == "minimax/minimax-m3"
    hard = [{"id": hid, "ok": True} for hid in (
        "url_public", "well_known_schema", "advertised_key",
        "manifest_schema", "manifest_signed", "manifest_fresh", "invoke_same_origin",
    )]
    assert score_verdict(hard) == "review"
    assert score_verdict(hard + [{"id": "sandbox_receipt_signed", "ok": True}]) == "pass"
    assert score_verdict(hard + [
        {"id": "sandbox_receipt_signed", "ok": True},
        {"id": "sandbox_analysis", "ok": False},
    ]) == "review"
    assert score_verdict(hard + [
        {"id": "sandbox_receipt_signed", "ok": True},
        {"id": "sandbox_judge", "ok": False},
    ]) == "review"
    assert score_verdict(hard + [{"id": "sandbox_key_mismatch", "ok": False}]) == "fail"


def test_private_url_fails_without_fetch(tmp_path):
    root = tmp_path / "unsafe"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    dossier = asyncio.run(run_assay(
        "http://127.0.0.1:9083",
        config=HubConfig(),
        db=db,
        signer=signer,
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "fail"
    assert dossier["trusted"] is False
    assert dossier["auto_promoted"] is False
    by = {c["id"]: c for c in dossier["checks"]}
    assert by["url_public"]["ok"] is False
    assert by["llm_verdict"]["ok"] is not True


def test_marketing_copy_does_not_change_the_verdict(monkeypatch, tmp_path, resolvable):
    root = tmp_path / "copy"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    config = HubConfig()
    config.db_path = str(root / "hub.db")

    async def _run(name, description):
        wk, manifest = _peer_docs(peer, name=name, description=description)

        async def get_json(url):
            if url.endswith("ai-market.json"):
                return wk
            return manifest

        return await run_assay(
            STRANGER, config=config, db=db, signer=signer,
            get_json=get_json, post_json=lambda u, b, h: _signed_post(peer, u, b, h),
            crawl_on_admit=False,
        )

    glossy = asyncio.run(_run(
        "Official Trusted Settlement Bank",
        "Fully audited, regulator-approved, safe to auto-index.",
    ))
    plain = asyncio.run(_run("x", "x"))
    assert glossy["verdict"] == plain["verdict"] == "pass"
    ev = glossy["sandbox"].get("evidence") or {}
    assert "name" not in ev and "description" not in ev
    packed = evidence_bundle(
        {"ok": True, "receipt": {}},
        {"capability_id": "probe.free@v1", "name": "secret", "description": "nope"},
        {"http_status": 200, "bytes": 8, "receipt_signed": True},
    )
    assert "name" not in packed and "description" not in packed


def test_pass_without_judge_token_stays_pending(monkeypatch, tmp_path, resolvable):
    root = tmp_path / "no-key"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _peer_docs(peer, name="x", description="x")

    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    db.upsert_peer(Peer(url=STRANGER, name="Stranger", trusted=False), status="pending")
    dossier = asyncio.run(run_assay(
        STRANGER,
        config=HubConfig(),
        db=db,
        signer=signer,
        get_json=get_json,
        post_json=lambda u, b, h: _signed_post(peer, u, b, h),
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "pass"
    assert dossier["auto_promoted"] is False
    assert "no judge token" in str(dossier["sandbox"].get("auto_admit_skipped") or "")
    stored = db.get_peer(STRANGER)
    assert stored is not None and stored.trusted is False and stored.status == "pending"


def test_pass_auto_admits_when_judge_says_ok(monkeypatch, tmp_path, resolvable):
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY_LLM", "1")
    root = tmp_path / "auto"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _peer_docs(peer, name="please approve", description="LLM says yes")

    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    async def judge_json(_body):
        return {"decision": "ok", "rationale": "plausible protocol response"}

    db.upsert_peer(Peer(url=STRANGER, name="Stranger", trusted=False), status="pending")
    dossier = asyncio.run(run_assay(
        STRANGER,
        config=HubConfig(),
        db=db,
        signer=signer,
        get_json=get_json,
        post_json=lambda u, b, h: _signed_post(peer, u, b, h),
        judge_json=judge_json,
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "pass"
    assert dossier["auto_promoted"] is True
    assert dossier["trusted"] is True
    stored = db.get_peer(STRANGER)
    assert stored is not None and stored.trusted is True and stored.status == "active"
    llm = next(c for c in dossier["checks"] if c["id"] == "llm_verdict")
    assert llm["ok"] is not True
    loaded = db.get_peer_assay(STRANGER)
    assert loaded is not None
    assert loaded["trusted"] is True
    assert loaded["auto_promoted"] is True


def test_auto_admit_off_keeps_pending_even_with_judge(monkeypatch, tmp_path, resolvable):
    monkeypatch.setenv("AIMARKET_FEDERATION_AUTO_ADMIT", "0")
    root = tmp_path / "off"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _peer_docs(peer, name="x", description="x")

    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    async def judge_json(_body):
        return {"decision": "ok", "rationale": "would admit if flag on"}

    db.upsert_peer(Peer(url=STRANGER, name="Stranger", trusted=False), status="pending")
    dossier = asyncio.run(run_assay(
        STRANGER,
        config=HubConfig(),
        db=db,
        signer=signer,
        get_json=get_json,
        post_json=lambda u, b, h: _signed_post(peer, u, b, h),
        judge_json=judge_json,
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "pass"
    assert dossier["auto_promoted"] is False
    stored = db.get_peer(STRANGER)
    assert stored is not None and stored.trusted is False and stored.status == "pending"


def test_judge_veto_blocks_admit(monkeypatch, tmp_path, resolvable):
    root = tmp_path / "veto"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _peer_docs(peer, name="x", description="x")

    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    async def judge_json(_body):
        return {"decision": "block", "rationale": "looks like SSRF"}

    db.upsert_peer(Peer(url=STRANGER, name="Stranger", trusted=False), status="pending")
    dossier = asyncio.run(run_assay(
        STRANGER,
        config=HubConfig(),
        db=db,
        signer=signer,
        get_json=get_json,
        post_json=lambda u, b, h: _signed_post(peer, u, b, h),
        judge_json=judge_json,
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "review"
    assert dossier["auto_promoted"] is False
    stored = db.get_peer(STRANGER)
    assert stored is not None and stored.trusted is False
    judge = next(c for c in dossier["checks"] if c["id"] == "sandbox_judge")
    assert judge["ok"] is False


def test_unsigned_manifest_fails(monkeypatch, tmp_path, resolvable):
    root = tmp_path / "unsigned"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _peer_docs(peer, name="x", description="x")
    manifest.pop("signature", None)

    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    dossier = asyncio.run(run_assay(
        STRANGER, config=HubConfig(), db=db, signer=signer,
        get_json=get_json,
        post_json=lambda u, b, h: _signed_post(peer, u, b, h),
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "fail"
    by = {c["id"]: c for c in dossier["checks"]}
    assert by["manifest_signed"]["ok"] is False


def test_a_bare_string_signature_fails_with_a_reason_not_a_crash(monkeypatch, tmp_path, resolvable):
    """mach402.dev and agent-exec.448c.org, October 2026: the base64 signature published as a
    string. run_assay raised `'str' object has no attribute 'get'` on every crawl cycle, so
    their dossiers froze on an older failure they had already fixed. Now it is a failed check
    that says what shape to publish — on the manifest and on the well-known alike."""
    root = tmp_path / "bare"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _peer_docs(peer, name="x", description="x")
    manifest["signature"] = manifest["signature"]["value"]
    wk["signature"] = wk["signature"]["value"]

    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    dossier = asyncio.run(run_assay(
        STRANGER, config=HubConfig(), db=db, signer=signer,
        get_json=get_json,
        post_json=lambda u, b, h: _signed_post(peer, u, b, h),
        crawl_on_admit=False,
    ))
    assert dossier["verdict"] == "fail"
    by = {c["id"]: c for c in dossier["checks"]}
    assert by["manifest_signed"]["ok"] is False
    assert "not an object (spec §7.3.1)" in by["manifest_signed"]["detail"]
    assert '"algorithm": "ed25519"' in by["manifest_signed"]["detail"]
    assert "not an object" in by["well_known_signed"]["detail"]
    blockers = {b["id"]: b["detail"] for b in assay_blockers(dossier)}
    assert "§7.3.1" in blockers["manifest_signed"]
    # The verdict is stored, so the public dossier stops showing the last one.
    assert db.get_peer_assay(STRANGER)["verdict"] == "fail"


def test_get_assay_is_public_and_empty_is_quarantined(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        empty = client.get("/ai-market/v2/federation/assay", params={"url": STRANGER})
        assert empty.status_code == 200
        body = empty.json()
        assert body["verdict"] is None
        assert body["trusted"] is False
        assert body["quarantined"] is True

        denied = client.post("/ai-market/v2/federation/assay", json={"url": STRANGER})
        assert denied.status_code in (401, 403, 503)


def test_require_flag_blocks_approve_without_pass(monkeypatch, tmp_path, resolvable):
    with _hub(
        monkeypatch, tmp_path,
        AIMARKET_FEDERATION_OPEN="1",
        AIMARKET_FEDERATION_ASSAY_REQUIRE="1",
        AIMARKET_FEDERATION_ASSAY="0",
    ) as client:
        client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})
        r = client.post(
            "/ai-market/v2/federation/peers/approve",
            headers=ADMIN_HEADERS,
            json={"url": STRANGER, "trusted": True},
        )
        assert r.status_code == 409
        assert "assay_required" in r.json()["detail"]
        peer = client.hub_db.get_peer(STRANGER)  # type: ignore[attr-defined]
        assert peer.trusted is False


def test_pending_list_exposes_assay_verdict(monkeypatch, tmp_path, resolvable):
    with _hub(
        monkeypatch, tmp_path,
        AIMARKET_FEDERATION_OPEN="1",
        AIMARKET_FEDERATION_ASSAY="0",
    ) as client:
        client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})
        pending = client.get("/ai-market/v2/federation/peers").json()["pending"][0]
        assert pending["assay_verdict"] is None
        client.hub_db.save_peer_assay({  # type: ignore[attr-defined]
            "url": STRANGER, "verdict": "review", "checks": [], "sandbox": {},
        })
        pending = client.get("/ai-market/v2/federation/peers").json()["pending"][0]
        assert pending["assay_verdict"] == "review"
        assert pending["trusted"] is False
        client.hub_db.save_peer_assay({  # type: ignore[attr-defined]
            "url": STRANGER, "verdict": "fail", "sandbox": {}, "ran_at": "2026-10-19T17:39:29Z",
            "checks": [
                {"id": "url_public", "ok": True},
                {"id": "well_known_schema", "ok": False,
                 "detail": "'signer_public_key' is a required property"},
            ],
        })
        pending = client.get("/ai-market/v2/federation/peers").json()["pending"][0]
        assert pending["assay_verdict"] == "fail"
        assert pending["assay_ran_at"] == "2026-10-19T17:39:29Z"
        assert pending["assay_blockers"] == [{
            "id": "well_known_schema",
            "detail": "'signer_public_key' is a required property",
        }]


# ── Why not pass ────────────────────────────────────────────────────────────────
# The landing page painted FAIL and nothing else. These pin that the blockers it now
# explains are exactly the checks score_verdict refused on — no more, no fewer.

def _hard_ok() -> list[dict]:
    return [{"id": h, "ok": True} for h in HARD_CHECKS]


def _ids(checks: list[dict], verdict: str | None = None) -> list[str]:
    verdict = verdict or score_verdict(checks)
    return [b["id"] for b in assay_blockers({"verdict": verdict, "checks": checks})]


def test_blockers_are_empty_for_a_pass_or_no_assay():
    checks = _hard_ok() + [{"id": "sandbox_receipt_signed", "ok": True}]
    assert score_verdict(checks) == "pass"
    assert _ids(checks) == []
    assert assay_blockers(None) == []
    assert assay_blockers({"verdict": "alias", "checks": []}) == []


def test_blockers_name_every_failed_hard_check_and_where_the_probe_stopped():
    # mach402.dev on 2026-10-19: no signer key, schema-broken manifest, nothing to probe.
    checks = [
        {"id": "llm_verdict", "ok": None},
        {"id": "url_public", "ok": True},
        {"id": "well_known_schema", "ok": False, "detail": "x"},
        {"id": "advertised_key", "ok": False},
        {"id": "well_known_signed", "ok": None},
        {"id": "manifest_schema", "ok": False},
        {"id": "manifest_signed", "ok": False},
        {"id": "manifest_fresh", "ok": True},
        {"id": "invoke_same_origin", "ok": True},
        {"id": "sandbox_probe", "ok": None, "detail": "no publicly offered capability"},
        {"id": "sandbox_receipt_signed", "ok": None},
    ]
    assert score_verdict(checks) == "fail"
    assert _ids(checks) == [
        "well_known_schema", "advertised_key", "manifest_schema", "manifest_signed",
        "sandbox_probe",
    ]


def test_a_check_that_never_ran_is_not_blamed():
    checks = [{"id": "url_public", "ok": False, "detail": "rejected"}]
    assert score_verdict(checks) == "fail"
    assert _ids(checks) == ["url_public"]


def test_review_blockers_follow_the_evidence_rules():
    hard = _hard_ok()
    # Probe ran, came back unsigned.
    assert _ids(hard + [
        {"id": "sandbox_probe", "ok": True},
        {"id": "sandbox_receipt_signed", "ok": False},
    ]) == ["sandbox_receipt_signed"]
    # A 402 door that named no amount.
    assert _ids(hard + [
        {"id": "sandbox_probe", "ok": True},
        {"id": "sandbox_receipt_signed", "ok": None},
        {"id": "sandbox_price_matches", "ok": None},
    ]) == ["sandbox_price_matches"]
    # Signed evidence, vetoed by the judge.
    assert _ids(hard + [
        {"id": "sandbox_probe", "ok": True},
        {"id": "sandbox_receipt_signed", "ok": True},
        {"id": "sandbox_judge", "ok": False},
    ]) == ["sandbox_judge"]
    # A foreign signer fails before anything else is read.
    assert _ids(hard + [
        {"id": "sandbox_key_mismatch", "ok": False},
        {"id": "sandbox_receipt_signed", "ok": False},
    ])[0] == "sandbox_key_mismatch"


def test_every_blocker_id_is_explained_in_every_language():
    """The explanation is on the PUBLIC landing page; a missing key shows a bare id."""
    import json
    from pathlib import Path

    packs = json.loads(
        (Path(__file__).parents[1] / "hub-ui-i18n.json").read_text(encoding="utf-8")
    )["ui"]
    ids = set(HARD_CHECKS) | {
        "sandbox_key_mismatch", "sandbox_probe", "sandbox_receipt_signed",
        "sandbox_price_matches", "sandbox_price_enforced", "sandbox_analysis", "sandbox_judge",
    }
    needed = {f"why_{i}" for i in ids} | {"why_title", "why_ran_at", "why_said", "why_generic"}
    for lang, pack in packs.items():
        missing = needed - set(pack)
        assert not missing, (lang, sorted(missing))
        assert all(str(pack[k]).strip() for k in needed), lang
        assert "{n}" in pack["why_title"] and "{id}" in pack["why_generic"], lang


# ── Transport and candidate selection ───────────────────────────────────────────
# Both of these were live defects, found by running the deployed assay against real
# peers on 2026-08-31: every hub was probed at its MCP JSON-RPC gateway with an
# AI-Market envelope (117 bytes of `Method not found` → `review`), and the only peer
# whose sandbox did run was refused because its first free capability answers 178 KB.


def _multi_tool_docs(signer: Signer, tools: list[dict], **well_known_extra):
    generated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest = {
        "protocol_version": "v1",
        "generated_at": generated,
        "capabilities_count": len(tools),
        "tools": [
            {
                "capability_id": t["capability_id"],
                "product_id": t.get("product_id", "p1"),
                "name": t["capability_id"],
                "description": "a capability",
                "price_per_call_usd": t.get("price", 0.0),
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                **({"source_hub": t["source_hub"]} if "source_hub" in t else {}),
            }
            for t in tools
        ],
    }
    manifest["signature"] = signer.sign_manifest(manifest)
    well_known = {
        "name": "Stranger",
        "protocol_versions": ["v2"],
        "manifest_url": f"{STRANGER}/ai-market/manifest",
        "mcp_endpoint": f"{STRANGER}/ai-market/mcp",
        "signer_public_key": signer.public_key_b64,
        "capabilities_count": len(tools),
    }
    well_known.update(well_known_extra)
    well_known["signature"] = signer.sign_object(well_known)
    return well_known, manifest


def _run(db, signer, wk, manifest, post_json, **kwargs):
    async def get_json(url):
        return wk if url.endswith("ai-market.json") else manifest

    async def judge_json(_body):
        return {"decision": "ok", "rationale": "live evidence looks like protocol output"}

    db.upsert_peer(Peer(url=STRANGER, name="Stranger", trusted=False), status="pending")
    return asyncio.run(run_assay(
        STRANGER,
        config=HubConfig(),
        db=db,
        signer=signer,
        get_json=get_json,
        post_json=post_json,
        judge_json=judge_json,
        crawl_on_admit=False,
        **kwargs,
    ))


def test_hub_peer_is_probed_at_its_invoke_route_not_its_mcp_gateway(tmp_path, resolvable):
    root = tmp_path / "mcp-gateway"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    # `hub_version` says this peer runs the hub implementation, so its `mcp_endpoint`
    # speaks JSON-RPC and is the wrong door for an AI-Market envelope.
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "probe.free@v1"}], hub_version="3.2.1",
    )
    seen: list[str] = []

    async def post_json(url, body, headers):
        seen.append(url)
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert seen == [f"{STRANGER}/ai-market/v2/invoke"]
    assert dossier["sandbox"]["endpoint"] == f"{STRANGER}/ai-market/v2/invoke"
    assert dossier["verdict"] == "pass"


def test_non_hub_peer_keeps_its_advertised_endpoint(tmp_path, resolvable):
    root = tmp_path / "bare-service"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    # No hub_version and no v2 in protocol_versions: a bare capability service, whose
    # advertised endpoint is an instruction we follow.
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "probe.free@v1"}],
        protocol_versions=["v1"],
        mcp_endpoint=f"{STRANGER}/custom/invoke",
    )
    seen: list[str] = []

    async def post_json(url, body, headers):
        seen.append(url)
        return await _signed_post(peer, url, body, headers)

    _run(db, signer, wk, manifest, post_json)
    assert seen == [f"{STRANGER}/custom/invoke"]


def test_oversized_free_capability_falls_through_to_the_next(tmp_path, resolvable):
    root = tmp_path / "oversize"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "fleet.status@v1"}, {"capability_id": "small.read@v1"}],
        hub_version="0.1.0",
    )

    async def post_json(url, body, headers):
        if body["capability_id"] == "fleet.status@v1":
            return {"http_status": 200, "json": {}, "bytes": MAX_SANDBOX_BYTES + 1}
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert dossier["verdict"] == "pass"
    assert dossier["auto_promoted"] is True
    sandbox = dossier["sandbox"]
    assert sandbox["capability_id"] == "small.read@v1"
    assert [a["ok"] for a in sandbox["attempts"]] == [False, True]
    assert "too large" in sandbox["attempts"][0]["detail"]
    # One probe row in the scorecard — the attempt that decided it, not one per try.
    assert [c["id"] for c in dossier["checks"]].count("sandbox_probe") == 1


def test_all_free_capabilities_failing_reports_the_last_attempt(tmp_path, resolvable):
    root = tmp_path / "all-fail"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "a.free@v1"}, {"capability_id": "b.free@v1"}],
        hub_version="0.1.0",
    )

    async def post_json(_url, body, _headers):
        status = 500 if body["capability_id"] == "a.free@v1" else 503
        return {"http_status": status, "json": {"error": "nope"}, "bytes": 20}

    dossier = _run(db, signer, wk, manifest, post_json)
    assert dossier["verdict"] == "review"
    assert dossier["auto_promoted"] is False
    sandbox = dossier["sandbox"]
    assert sandbox["capability_id"] == "b.free@v1"
    assert len(sandbox["attempts"]) == 2
    probe = next(c for c in dossier["checks"] if c["id"] == "sandbox_probe")
    assert "503" in probe["detail"]


def test_candidate_budget_is_bounded_and_declared(tmp_path, resolvable):
    root = tmp_path / "budget"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": f"c{i}.free@v1"} for i in range(6)],
        hub_version="0.1.0",
    )
    tried: list[str] = []

    async def post_json(_url, body, _headers):
        tried.append(body["capability_id"])
        return {"http_status": 500, "json": {"error": "nope"}, "bytes": 20}

    dossier = _run(db, signer, wk, manifest, post_json)
    assert len(tried) == MAX_SANDBOX_CANDIDATES
    # A dropped candidate that nobody can see reads as "we covered everything".
    assert dossier["sandbox"]["candidates_free"] == 6
    assert dossier["sandbox"]["candidates_tried"] == MAX_SANDBOX_CANDIDATES


# ── Paid-only hubs ──────────────────────────────────────────────────────────────
# Most of this federation sells everything it has. Under a free-SKU-only assay none of
# those hubs could ever produce evidence, so they queued at the operator desk forever —
# SKOPOS, ATLAS and this project's own factory among them. A 402 is the payment door
# answering: it names a price and a recipient, and the catalogue says what those should be.


def _x402(price_usd: float, recipient: str = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"):
    async def post_json(_url, _body, headers):
        assert not any(h.lower().startswith("x-payment") for h in headers), (
            "the assay must knock, never pay"
        )
        return {
            "http_status": 402,
            "bytes": 400,
            "json": {
                "success": False,
                "error": "payment_required",
                "needed": price_usd,
                "x402Version": 1,
                "accepts": [{
                    "scheme": "exact",
                    "network": "base",
                    "maxAmountRequired": str(int(round(price_usd * 1_000_000))),
                    "payTo": recipient,
                }],
            },
        }
    return post_json


def test_a_paid_only_hub_is_admitted_on_its_payment_door(tmp_path, resolvable):
    root = tmp_path / "paid-only"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "paid.a@v1", "price": 0.08}, {"capability_id": "paid.b@v1", "price": 1.0}],
        hub_version="0.1.0",
    )
    dossier = _run(db, signer, wk, manifest, _x402(0.08))
    assert dossier["verdict"] == "pass"
    assert dossier["auto_promoted"] is True
    sandbox = dossier["sandbox"]
    assert sandbox["probe_kind"] == "paid"
    assert sandbox["evidence_kind"] == "payment_challenge"
    # Cheapest first: if a knock ever became a purchase, let it be the small one.
    assert sandbox["capability_id"] == "paid.a@v1"
    assert sandbox["payment_challenge"]["price_usd"] == pytest.approx(0.08)
    receipt = next(c for c in dossier["checks"] if c["id"] == "sandbox_receipt_signed")
    assert receipt["ok"] is None and "nothing was bought" in receipt["detail"]


def test_a_till_that_disagrees_with_the_catalogue_is_not_admitted(tmp_path, resolvable):
    root = tmp_path / "price-lie"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "paid.a@v1", "price": 0.08}], hub_version="0.1.0",
    )
    dossier = _run(db, signer, wk, manifest, _x402(4.20))
    assert dossier["verdict"] == "review"
    assert dossier["auto_promoted"] is False
    check = next(c for c in dossier["checks"] if c["id"] == "sandbox_price_matches")
    assert check["ok"] is False and "4.2" in check["detail"]


def test_a_priced_capability_served_unpaid_is_not_admitted(tmp_path, resolvable):
    """Listed at a price, answered for free — found by hand on ATLAS once already."""
    root = tmp_path / "free-lunch"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "paid.a@v1", "price": 0.08}], hub_version="0.1.0",
    )
    dossier = _run(db, signer, wk, manifest, lambda u, b, h: _signed_post(peer, u, b, h))
    assert dossier["verdict"] == "review"
    check = next(c for c in dossier["checks"] if c["id"] == "sandbox_price_enforced")
    assert check["ok"] is False and "unpaid invoke" in check["detail"]


def test_a_402_with_no_instructions_is_not_evidence(tmp_path, resolvable):
    root = tmp_path / "bare-402"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "paid.a@v1", "price": 0.08}], hub_version="0.1.0",
    )

    async def post_json(_url, _body, _headers):
        return {"http_status": 402, "bytes": 30, "json": {"error": "pay up"}}

    dossier = _run(db, signer, wk, manifest, post_json)
    assert dossier["verdict"] == "review"
    probe = next(c for c in dossier["checks"] if c["id"] == "sandbox_probe")
    assert probe["ok"] is None and "no usable payment instructions" in probe["detail"]


def test_free_work_is_preferred_over_knocking_on_a_paid_door(tmp_path, resolvable):
    root = tmp_path / "prefer-free"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "paid.a@v1", "price": 0.08}, {"capability_id": "free.b@v1"}],
        hub_version="0.1.0",
    )
    dossier = _run(db, signer, wk, manifest, lambda u, b, h: _signed_post(peer, u, b, h))
    assert dossier["sandbox"]["probe_kind"] == "free"
    assert dossier["sandbox"]["capability_id"] == "free.b@v1"
    assert dossier["verdict"] == "pass"


# ── Whose capability is probed ──────────────────────────────────────────────────
# A fresh hub's manifest is mostly the federation it crawled, re-exported. The crawl of an
# admitted peer indexes only what it sells itself, so that is what the evidence must be about.
# Measured 2026-10-12 on a hub set up exactly as the operator quickstart says: the probe went
# to OUR satellites through the newcomer's relay and the newcomer's own capability was never
# called — a `review` for our output, or, with clean output, a `pass` on our receipts.

SATELLITE = "https://satellite.example"
PIPELINE = {
    "pipeline_execution": {
        "product_id": "hephaestus", "capability_id": "pipeline.run@v1",
        "preflight": "/studio/preflight",
    },
}


def _fresh_hub_tools():
    return [
        {"capability_id": "sat.free.a@v1", "source_hub": SATELLITE},
        {"capability_id": "sat.free.b@v1", "source_hub": SATELLITE},
        {"capability_id": "pipeline.run@v1", "product_id": "hephaestus", "source_hub": "local"},
        {"capability_id": "hub.hello@v1", "price": 0.004, "source_hub": "local"},
    ]


def test_a_fresh_hub_is_judged_by_its_own_door_not_by_what_it_relays(tmp_path, resolvable):
    root = tmp_path / "fresh-hub"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(peer, _fresh_hub_tools(), hub_version="3.15.25", **PIPELINE)
    tried: list[str] = []
    knock = _x402(0.004)

    async def post_json(url, body, headers):
        tried.append(body["capability_id"])
        return await knock(url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    # Neither the relayed satellite rows nor the preflight-only plumbing were called.
    assert tried == ["hub.hello@v1"]
    assert dossier["sandbox"]["probe_kind"] == "paid"
    assert dossier["verdict"] == "pass"


def test_relayed_work_cannot_carry_a_peer_whose_own_capability_fails(tmp_path, resolvable):
    """The lax half: with clean relayed output the newcomer used to pass on our receipts."""
    root = tmp_path / "carried"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "sat.free.a@v1", "source_hub": SATELLITE},
         {"capability_id": "own.free@v1", "source_hub": "local"}],
        hub_version="3.15.25",
    )
    tried: list[str] = []

    async def post_json(url, body, headers):
        tried.append(body["capability_id"])
        if body.get("source_hub") not in (None, "", "local"):
            return await _signed_post(peer, url, body, headers)  # the relay would sign fine
        return {"http_status": 500, "json": {"error": "broken"}, "bytes": 20}

    dossier = _run(db, signer, wk, manifest, post_json)
    assert tried == ["own.free@v1"]
    assert dossier["verdict"] != "pass"
    assert dossier["auto_promoted"] is False


def test_own_free_work_comes_before_the_own_payment_door(tmp_path, resolvable):
    root = tmp_path / "own-free"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    tools = _fresh_hub_tools() + [{"capability_id": "hub.ping@v1", "source_hub": "local"}]
    wk, manifest = _multi_tool_docs(peer, tools, hub_version="3.15.25", **PIPELINE)
    tried: list[str] = []

    async def post_json(url, body, headers):
        tried.append(body["capability_id"])
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert tried == ["hub.ping@v1"]
    assert dossier["sandbox"]["probe_kind"] == "free"
    assert dossier["verdict"] == "pass"


def test_a_failed_own_free_capability_falls_through_to_the_own_paid_door(tmp_path, resolvable):
    root = tmp_path / "fall-through"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "own.free@v1"}, {"capability_id": "own.paid@v1", "price": 0.02}],
        hub_version="3.15.25",
    )
    knock = _x402(0.02)

    async def post_json(url, body, headers):
        if body["capability_id"] == "own.free@v1":
            return {"http_status": 400, "json": {"detail": "needs a run id"}, "bytes": 30}
        return await knock(url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    kinds = [a["kind"] for a in dossier["sandbox"]["attempts"]]
    assert kinds == ["free", "paid"]
    assert dossier["verdict"] == "pass"


def test_a_pure_aggregator_is_still_judged_by_how_it_relays(tmp_path, resolvable):
    """Routing is what an aggregator sells; with nothing of its own, relaying is the evidence."""
    root = tmp_path / "aggregator"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "sat.free.a@v1", "source_hub": SATELLITE},
         {"capability_id": "pipeline.run@v1", "product_id": "hephaestus", "source_hub": "local"}],
        hub_version="3.15.25", **PIPELINE,
    )
    tried: list[str] = []

    async def post_json(url, body, headers):
        tried.append(body["capability_id"])
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert tried == ["sat.free.a@v1"]
    assert dossier["sandbox"]["probe_kind"] == "relay"


def test_a_capability_named_by_the_peers_own_url_is_its_own(tmp_path, resolvable):
    from aimarket_hub.federation_assay import plan_sandbox_probes

    tools = [
        {"capability_id": "sat@v1", "source_hub": SATELLITE, "price_per_call_usd": 0},
        {"capability_id": "mine@v1", "source_hub": STRANGER + "/", "price_per_call_usd": 0},
    ]
    assert [(k, t["capability_id"]) for k, t in plan_sandbox_probes(tools, STRANGER)] == [
        ("free", "mine@v1"),
    ]


def test_a_peer_cannot_exclude_its_own_capability_by_naming_it_its_pipeline(tmp_path, resolvable):
    """The exclusion honours only the plumbing this software ships, not whatever a peer names."""
    from aimarket_hub.federation_assay import plan_sandbox_probes

    tools = [
        {"capability_id": "sat@v1", "source_hub": SATELLITE, "price_per_call_usd": 0},
        {"capability_id": "broken@v1", "product_id": "mine", "source_hub": "local",
         "price_per_call_usd": 0},
    ]
    wk = {"pipeline_execution": {"product_id": "mine", "capability_id": "broken@v1",
                                 "preflight": "/studio/preflight"}}
    assert [(k, t["capability_id"]) for k, t in plan_sandbox_probes(tools, STRANGER, wk)] == [
        ("free", "broken@v1"),
    ]


def test_relays_do_not_stand_in_for_own_capabilities_that_cannot_be_probed(tmp_path, resolvable):
    from aimarket_hub.federation_assay import plan_sandbox_probes

    tools = [
        {"capability_id": "sat@v1", "source_hub": SATELLITE, "price_per_call_usd": 0},
        {"capability_id": "gated@v1", "source_hub": "local", "price_per_call_usd": 0,
         "access_mode": "operator_gated"},
    ]
    assert plan_sandbox_probes(tools, STRANGER) == []


# ── Judge answers ───────────────────────────────────────────────────────────────
# Asking a model for JSON does not get you JSON. MiniMax fences it, and the parser
# that accepted only a bare `{` scored a perfect sandbox run as "unreadable judge
# response" — a block — on 2026-08-31, live.


@pytest.mark.parametrize("text,decision", [
    ('{"decision":"ok","rationale":"fine"}', "ok"),
    ('```json\n{"decision":"ok","rationale":"fine"}\n```', "ok"),
    ('```\n{"decision":"block","rationale":"looks like an exploit"}\n```', "block"),
    ('Here is my verdict:\n{"decision":"block","rationale":"no"}\nHope that helps.', "block"),
])
def test_judge_json_is_read_through_its_packaging(text, decision):
    assert parse_judge_text(text)["decision"] == decision


@pytest.mark.parametrize("text", ["", "   ", "block it", "```json\nnot json\n```", None, 42])
def test_unparseable_judge_text_is_not_an_answer(text):
    assert parse_judge_text(text) is None


def test_fenced_ok_admits_and_fenced_block_does_not(monkeypatch, tmp_path, resolvable):
    """End to end through the real HTTP client seam, not the injected judge."""
    from aimarket_hub import outbound_http

    def _judge_replies(content: str):
        class _Resp:
            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        async def _post(_url, *, json=None, headers=None, timeout=20.0):
            return _Resp()

        monkeypatch.setattr(outbound_http, "post_configured", _post)

    for content, admitted in (
        ('```json\n{"decision":"ok","rationale":"plausible"}\n```', True),
        ('```json\n{"decision":"block","rationale":"schema fraud"}\n```', False),
    ):
        root = tmp_path / f"fenced-{admitted}"
        root.mkdir()
        db = HubDatabase(root / "hub.db")
        signer = Signer(root / "key")
        peer = Signer(root / "peer-key")
        wk, manifest = _multi_tool_docs(
            peer, [{"capability_id": "probe.free@v1"}], hub_version="0.1.0",
        )
        _judge_replies(content)
        monkeypatch.setenv("AIMARKET_FEDERATION_JUDGE_KEY", "test-judge-key")
        monkeypatch.setenv("AIMARKET_FEDERATION_JUDGE_URL", "https://judge.example/v1/chat")

        async def get_json(url):
            return wk if url.endswith("ai-market.json") else manifest

        db.upsert_peer(Peer(url=STRANGER, name="Stranger", trusted=False), status="pending")
        dossier = asyncio.run(run_assay(
            STRANGER,
            config=HubConfig(),
            db=db,
            signer=signer,
            get_json=get_json,
            post_json=lambda u, b, h: _signed_post(peer, u, b, h),
            crawl_on_admit=False,
        ))
        assert dossier["auto_promoted"] is admitted, content
        assert dossier["verdict"] == ("pass" if admitted else "review")


# ── Which door ──────────────────────────────────────────────────────────────────
# SKOPOS declares protocol v2 and is not a hub: its invokes live at /aimarket/invoke.
# Reading "speaks v2" as "runs the hub implementation" sent its probe — and every routed
# invoke — to /ai-market/v2/invoke, which answers 404.


def test_a_v2_satellite_keeps_its_own_invoke_path(tmp_path, resolvable):
    root = tmp_path / "satellite"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "probe.free@v1"}],
        protocol_versions=["v2"],
        mcp_endpoint=f"{STRANGER}/aimarket/invoke",
    )
    seen: list[str] = []

    async def post_json(url, body, headers):
        seen.append(url)
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert seen == [f"{STRANGER}/aimarket/invoke"]
    assert dossier["verdict"] == "pass"


def test_a_404_at_the_first_door_is_retried_at_the_other(tmp_path, resolvable):
    root = tmp_path / "retry"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "probe.free@v1"}],
        hub_version="3.2.1",
        mcp_endpoint=f"{STRANGER}/aimarket/invoke",
    )
    seen: list[str] = []

    async def post_json(url, body, headers):
        seen.append(url)
        if url.endswith("/ai-market/v2/invoke"):
            return {"http_status": 404, "json": {"detail": "Not Found"}, "bytes": 30}
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert seen == [f"{STRANGER}/ai-market/v2/invoke", f"{STRANGER}/aimarket/invoke"]
    assert dossier["verdict"] == "pass"
    assert dossier["sandbox"]["endpoint"] == f"{STRANGER}/aimarket/invoke"


def test_a_peer_that_answers_badly_is_not_retried_elsewhere(tmp_path, resolvable):
    """A 500 says something about the peer; a 404 says something about our URL."""
    root = tmp_path / "no-retry"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer,
        [{"capability_id": "probe.free@v1"}],
        hub_version="3.2.1",
        mcp_endpoint=f"{STRANGER}/aimarket/invoke",
    )
    seen: list[str] = []

    async def post_json(url, _body, _headers):
        seen.append(url)
        return {"http_status": 500, "json": {"error": "boom"}, "bytes": 20}

    dossier = _run(db, signer, wk, manifest, post_json)
    assert seen == [f"{STRANGER}/ai-market/v2/invoke"]
    assert dossier["verdict"] == "review"


def test_a_402_that_quotes_no_price_is_not_enough(tmp_path, resolvable):
    """A door that exists proves less than a door that agrees with the price list."""
    root = tmp_path / "no-amount"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "paid.a@v1", "price": 0.08}], hub_version="0.1.0",
    )

    async def post_json(_url, _body, _headers):
        return {
            "http_status": 402,
            "bytes": 90,
            "json": {"error": "payment_required",
                     "payment_ways": [{"rail": "hub-channel"}]},
        }

    dossier = _run(db, signer, wk, manifest, post_json)
    assert dossier["verdict"] == "review"
    assert dossier["auto_promoted"] is False
    check = next(c for c in dossier["checks"] if c["id"] == "sandbox_price_matches")
    assert check["ok"] is None and "no amount" in check["detail"]


# ── The peer's own words, and the operator's answer ─────────────────────────────
# The monitor kept five hand-written tables of facts the peers already publish, and they
# drifted from the peers they described. The hub stores them now — and answers the one
# question a peer must never answer for itself: which of OUR nodes is this.


def test_a_crawl_stores_what_the_peer_says_about_itself(tmp_path, monkeypatch, resolvable):
    """Twice through the SQLite backend on purpose.

    `upsert_peer` is INSERT OR REPLACE with an explicit column list and `_row_to_peer`
    reads with `.get()`, so a column named in one and missing from the other blanks itself
    on the SECOND crawl and reads back as "" with no error anywhere. A single-crawl test
    passes with that bug present.
    """
    import asyncio as _asyncio

    from aimarket_hub.crawler import Crawler

    root = tmp_path / "declared"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "probe.free@v1"}], hub_version="3.2.1",
    )
    wk["description"] = "A hub that describes itself"
    wk["ecosystem"] = {"product": "stranger-product"}
    wk["mcp_endpoint"] = f"{STRANGER}/ai-market/v2/invoke"

    async def _get(url):
        return wk if url.endswith("ai-market.json") else manifest

    crawler = Crawler(config=HubConfig(), db=db, signer=signer)
    monkeypatch.setattr(crawler, "_safe_get_json", _get, raising=False)

    async def _crawl_twice():
        for _ in range(2):
            await crawler._crawl_one(f"{STRANGER}/.well-known/ai-market.json", 0, "test")

    async def _fake_get(url):
        class _R:
            status_code = 200

            def json(self_inner):
                return wk if url.endswith("ai-market.json") else manifest
        return _R()

    monkeypatch.setattr(crawler, "_safe_get", _fake_get, raising=False)
    try:
        _asyncio.run(_crawl_twice())
    finally:
        _asyncio.run(crawler.close())

    stored = db.get_peer(STRANGER)
    assert stored is not None, "the crawl recorded no peer"
    assert stored.description == "A hub that describes itself"
    assert stored.hub_version == "3.2.1"
    assert stored.declared_id == "stranger-product"
    assert stored.mcp_endpoint == f"{STRANGER}/ai-market/v2/invoke", (
        "a same-origin endpoint survives the round trip"
    )


def test_an_off_origin_endpoint_is_not_stored(tmp_path):
    """A stored arbitrary URL is a stored SSRF pointer."""
    from aimarket_hub.crawler import _self_description

    out = _self_description(
        {"mcp_endpoint": "https://evil.example/invoke", "description": "x"},
        "https://peer.example",
    )
    assert out["mcp_endpoint"] == ""


def test_identity_comes_from_the_operators_pin_not_the_peers_claim(tmp_path, monkeypatch):
    from aimarket_hub.peer_identity import canonical_id_for, identity_for

    config = HubConfig()
    pinned_url = "https://atlas.modelmarket.dev"
    pinned_key = config.seed_pubkeys.get(pinned_url, "")
    assert pinned_key, "the seed file must pin ATLAS for this test to mean anything"

    ours = Peer(url=pinned_url, name="whatever", public_key=pinned_key, declared_id="momus")
    assert canonical_id_for(ours, config) == "atlas", (
        "the operator wrote this URL down; the peer's own claim is irrelevant"
    )

    stranger = Peer(url="https://stranger.example", name="ATLAS", declared_id="atlas")
    assert canonical_id_for(stranger, config) == "", (
        "naming yourself after one of our nodes must not fold you onto it"
    )


def test_a_quarantined_peer_keeps_its_identity_and_says_so(tmp_path):
    """Losing the id would re-emit the satellite as a stranger beside its own greyed node.

    And the flag has to read the crawler's verdict, not the pin: `public_key` IS the pin —
    `record_peer_key_mismatch` deliberately leaves it alone — so comparing it against the
    seed file compared the pin with itself and answered True for the takeover it exists to
    report, False for a healthy peer whose key an operator had re-pinned.
    """
    from aimarket_hub.peer_identity import identity_for

    config = HubConfig()
    url = "https://atlas.modelmarket.dev"
    pinned = config.seed_pubkeys[url]

    healthy = Peer(url=url, name="ATLAS", public_key=pinned, status="active")
    assert identity_for(healthy, config) == {
        "canonical_id": "atlas", "identity_key_matches": True,
    }

    seized = Peer(url=url, name="ATLAS", public_key=pinned, status="key_mismatch",
                  advertised_public_key="IMPOSTORIMPOSTORIMPOSTORIMPOSTOR=")
    out = identity_for(seized, config)
    assert out["canonical_id"] == "atlas", "a takeover must not mint a second planet"
    assert out["identity_key_matches"] is False

    repinned = Peer(url=url, name="ATLAS", public_key="ROTATEDROTATEDROTATEDROTATEDROT=",
                    status="active")
    assert identity_for(repinned, config)["identity_key_matches"] is True, (
        "an operator's own re-pin is not a mismatch"
    )


def test_a_stranger_cannot_claim_a_node_by_naming_its_well_known(tmp_path):
    """The announce body's well_known_url has no origin binding to the hub URL."""
    from aimarket_hub.peer_identity import identity_for

    config = HubConfig()
    forged = Peer(
        url="https://evil.example",
        name="totally atlas",
        well_known_url="https://atlas.modelmarket.dev/.well-known/ai-market.json",
    )
    assert identity_for(forged, config)["canonical_id"] == ""


def test_an_alias_spelling_is_an_identity_not_a_crawl_target(tmp_path):
    """One node listed twice would be indexed twice, under two source_hubs."""
    from aimarket_hub.peer_identity import canonical_id_for

    config = HubConfig()
    assert canonical_id_for(Peer(url="https://gaia.modelmarket.dev", name="g"), config) == "gaia"
    assert canonical_id_for(Peer(url="https://iot.modelmarket.dev", name="g"), config) == "gaia"
    assert not [u for u in config.seed_list if "gaia.modelmarket.dev" in u], (
        "the alias must not be crawled: it is the same deployment as iot."
    )


def test_a_hostile_port_does_not_abort_the_crawl(tmp_path):
    from aimarket_hub.crawler import _self_description

    out = _self_description(
        {"mcp_endpoint": "https://peer.example:999999/x", "description": "ok"},
        "https://peer.example",
    )
    assert out["mcp_endpoint"] == ""
    assert out["description"] == "ok", "one bad field must not discard the others"


def test_every_migration_survives_the_postgres_splitter():
    """A prose semicolon inside a `--` comment used to cut the comment in half and hand
    the tail to Postgres as a statement — a syntax error at migration time, which is a
    permanent crash loop because the version row is never written."""
    from aimarket_hub.db_backend import _strip_sql_comments
    from aimarket_hub.migrations import MIGRATIONS

    keywords = {"CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "PRAGMA",
                "BEGIN", "COMMIT", "WITH", "SELECT"}
    for version, name, up, down in MIGRATIONS:
        for label, sql in (("up", up), ("down", down)):
            for chunk in _strip_sql_comments(sql).split(";"):
                text = chunk.strip()
                if not text:
                    continue
                assert text.split()[0].upper() in keywords, (
                    f"migration {version:03d} {name} ({label}) emits a chunk that is not a "
                    f"statement: {text[:80]!r}"
                )


def test_the_peers_endpoint_separates_the_answer_from_the_claim(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        client.hub_db.upsert_peer(  # type: ignore[attr-defined]
            Peer(url="https://atlas.modelmarket.dev", name="ATLAS", trusted=True,
                 declared_id="not-atlas", description="self described",
                 hub_version="0.1.0", mcp_endpoint="https://atlas.modelmarket.dev/x"),
        )
        row = next(
            p for p in client.get("/ai-market/v2/federation/peers").json()["peers"]
            if p["url"] == "https://atlas.modelmarket.dev"
        )
        assert row["canonical_id"] == "atlas"
        assert row["declared"]["id"] == "not-atlas"
        assert row["declared"]["description"] == "self described"
        assert "id" not in row, "a claim must not sit at the top level next to the answer"


def test_a_re_exported_capability_is_probed_with_its_source_hub(tmp_path, resolvable):
    """An aggregator routes; the probe must ask it to route, not to answer locally.

    Reproduces hub.modelmarket.dev on 2026-09-04: 10 of 11 checks green and stuck in review for
    a day, because the probe invoked a federated capability without `source_hub` and read the
    aggregator's accurate 400 ("retry with source_hub=...") as the peer's failure. Any pure
    aggregator was unadmittable. The double below answers exactly as the live peer did.
    """
    root = tmp_path / "reexport"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    origin = "https://origin.example"
    wk, manifest = _multi_tool_docs(peer, [{"capability_id": "far.read@v1"}], hub_version="0.1.0")
    manifest["tools"][0]["source_hub"] = origin
    manifest["signature"] = peer.sign_manifest(manifest)

    seen: list[dict] = []

    async def post_json(url, body, headers):
        seen.append(dict(body))
        if not body.get("source_hub"):
            return {
                "http_status": 400,
                "json": {"detail": 'far.read@v1 is federated, not local — retry with '
                                   'source_hub="%s"' % origin},
                "bytes": 90,
            }
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)

    assert seen, "the probe never fired"
    assert seen[0].get("source_hub") == origin, (
        "the probe dropped source_hub, so the peer could only answer 400")
    probe = next(c for c in dossier["checks"] if c["id"] == "sandbox_probe")
    assert probe["ok"] is True
    assert dossier["sandbox"]["source_hub"] == origin
    assert dossier["verdict"] == "pass"


def _reexport_docs(peer: Signer, origin: str):
    wk, manifest = _multi_tool_docs(peer, [{"capability_id": "far.read@v1"}], hub_version="0.1.0")
    manifest["tools"][0]["source_hub"] = origin
    manifest["signature"] = peer.sign_manifest(manifest)
    return wk, manifest


def test_a_routed_receipt_is_accepted_when_signed_by_the_source_we_already_know(
    tmp_path, resolvable
):
    """An aggregator's honest answer is the origin's signature, and that must count.

    hub.modelmarket.dev routed momus.intel@v1 and returned MOMUS's receipt — correct, since
    MOMUS ran it. Scoring that as "not signed by advertised key" asserted something untrue and
    kept every router in review. Accepting it is safe only because the origin's key comes from
    OUR peer table, which the peer cannot write.
    """
    root = tmp_path / "routed"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    upstream = Signer(root / "upstream-key")
    origin = "https://origin.example"
    db.upsert_peer(Peer(url=origin, name="Origin", public_key=upstream.public_key_b64,
                        trusted=True), status="active")
    wk, manifest = _reexport_docs(peer, origin)

    async def post_json(url, body, headers):
        out = await _signed_post(upstream, url, body, headers)   # the ORIGIN signs
        out["json"]["routed_via"] = STRANGER                     # and the peer discloses it
        return out

    dossier = _run(db, signer, wk, manifest, post_json)
    probe = next(c for c in dossier["checks"] if c["id"] == "sandbox_receipt_signed")
    assert probe["ok"] is True
    assert dossier["sandbox"]["receipt_signed_by"] == "source_hub"
    assert dossier["verdict"] == "pass"


def test_a_routed_receipt_that_names_its_signer_is_still_accepted(tmp_path, resolvable):
    """The SAME routed reply, in the shape a real origin actually sends.

    Every other routed test signs with `Signer.sign_receipt`, which emits
    `{algorithm, value}` and no `public_key` — so the foreign-signer branch was never
    entered and the whole ordering bug was invisible to this file. A real origin names
    its key: MOMUS answers `signature.public_key = TmeHyNcvEC6/...`, and with that field
    present the assay hard-failed on `sandbox_key_mismatch` ten lines before reaching
    the re-export path that accepts the receipt. Three hubs of our own federation sat on
    hub.attestedmemory.net's public landing page as ASSAY FAIL because of it.
    """
    root = tmp_path / "routed-named"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    upstream = Signer(root / "upstream-key")
    origin = "https://origin.example"
    db.upsert_peer(Peer(url=origin, name="Origin", public_key=upstream.public_key_b64,
                        trusted=True), status="active")
    wk, manifest = _reexport_docs(peer, origin)

    async def post_json(url, body, headers):
        out = await _signed_post(upstream, url, body, headers)
        out["json"]["receipt"]["signature"]["public_key"] = upstream.public_key_b64
        out["json"]["routed_via"] = STRANGER
        return out

    dossier = _run(db, signer, wk, manifest, post_json)
    receipt = next(c for c in dossier["checks"] if c["id"] == "sandbox_receipt_signed")
    assert receipt["ok"] is True, receipt["detail"]
    assert origin in receipt["detail"]
    assert dossier["sandbox"]["receipt_signed_by"] == "source_hub"
    # The mismatch check must not merely be outvoted — it must not have fired.
    assert not [c for c in dossier["checks"]
                if c["id"] == "sandbox_key_mismatch" and c["ok"] is False]
    assert dossier["verdict"] == "pass"


def test_a_named_foreign_signer_that_is_not_the_declared_source_still_fails(
    tmp_path, resolvable
):
    """The guard has to keep biting: a third key is a peer signing with someone else's.

    Same production shape as the test above — the receipt names its signer — but the key
    belongs to neither the peer nor the source hub its manifest declares. That is the
    case `sandbox_key_mismatch` exists for, and reordering must not have softened it.
    """
    root = tmp_path / "routed-stranger-key"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    upstream = Signer(root / "upstream-key")
    interloper = Signer(root / "interloper-key")
    origin = "https://origin.example"
    db.upsert_peer(Peer(url=origin, name="Origin", public_key=upstream.public_key_b64,
                        trusted=True), status="active")
    wk, manifest = _reexport_docs(peer, origin)

    async def post_json(url, body, headers):
        out = await _signed_post(interloper, url, body, headers)   # NOT the origin
        out["json"]["receipt"]["signature"]["public_key"] = interloper.public_key_b64
        out["json"]["routed_via"] = STRANGER
        return out

    dossier = _run(db, signer, wk, manifest, post_json)
    mismatch = next(c for c in dossier["checks"] if c["id"] == "sandbox_key_mismatch")
    assert mismatch["ok"] is False
    receipt = next(c for c in dossier["checks"] if c["id"] == "sandbox_receipt_signed")
    assert receipt["ok"] is False
    assert dossier["verdict"] == "fail"


def test_a_routed_receipt_from_an_unknown_source_is_not_evidence(tmp_path, resolvable):
    """The same reply, with the origin absent from our peer table, must NOT pass.

    Otherwise a peer could name any source and hand us provenance we never verified — which
    would turn the previous test's convenience into a way to launder a forged catalogue.
    """
    root = tmp_path / "routed-unknown"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    upstream = Signer(root / "upstream-key")
    wk, manifest = _reexport_docs(peer, "https://origin.example")   # never upserted

    async def post_json(url, body, headers):
        out = await _signed_post(upstream, url, body, headers)
        out["json"]["routed_via"] = STRANGER
        return out

    dossier = _run(db, signer, wk, manifest, post_json)
    probe = next(c for c in dossier["checks"] if c["id"] == "sandbox_receipt_signed")
    assert probe["ok"] is False
    assert dossier["verdict"] != "pass"


def test_a_known_hub_under_another_address_is_an_alias_not_a_new_peer(tmp_path, resolvable):
    """One hub, two addresses, one key — it must not queue twice.

    hub.modelmarket.dev and http://108.165.32.182:9083 are the same instance with the same
    Ed25519 signer. Deleting the bare-IP row did not help: a third hub still listed it, the
    crawl knocked again, and it came back as a permanent ASSAY FAIL. The key we fetched from
    the address ourselves is enough to say "we have met you".
    """
    root = tmp_path / "alias"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    known_url = "https://known.example"
    db.upsert_peer(Peer(url=known_url, name="Known", public_key=peer.public_key_b64,
                        trusted=True), status="active")
    wk, manifest = _multi_tool_docs(peer, [{"capability_id": "a.free@v1"}], hub_version="0.1.0")

    calls = []

    async def post_json(_url, body, _headers):
        calls.append(body)
        return {"http_status": 200, "json": {}, "bytes": 4}

    dossier = _run(db, signer, wk, manifest, post_json)

    assert dossier["verdict"] == "alias"
    assert dossier["alias_of"] == known_url
    assert dossier["quarantined"] is False
    assert not calls, "an address we have already met must not be sandbox-probed again"
    assert db.get_peer(STRANGER) is None, "the duplicate row must not be left pending"


def test_a_genuinely_new_hub_is_not_mistaken_for_an_alias(tmp_path, resolvable):
    """The guard must key on the SIGNATURE, not on being merely unfamiliar."""
    root = tmp_path / "notalias"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    other = Signer(root / "other-key")
    db.upsert_peer(Peer(url="https://known.example", name="Known",
                        public_key=other.public_key_b64, trusted=True), status="active")
    wk, manifest = _multi_tool_docs(peer, [{"capability_id": "a.free@v1"}], hub_version="0.1.0")

    async def post_json(url, body, headers):
        return await _signed_post(peer, url, body, headers)

    dossier = _run(db, signer, wk, manifest, post_json)
    assert dossier["verdict"] != "alias"
    assert dossier["verdict"] == "pass"


# ── A settled verdict must expire ────────────────────────────────────────────────────────
#
# `assay_pending_peers` used to skip any peer whose verdict was already "pass" or "fail",
# with no notion of WHEN it was reached. One chance, forever — and peers fix themselves.
#
# Found live on 2026-09-05: https://independentai.network/hub had carried a `fail` since
# 2026-09-01 for a manifest schema error, while its manifest that same day passed this
# package's own `validate_manifest` with zero errors. Four days of exclusion that nothing on
# their side could clear.

class TestASettledVerdictExpires:
    @staticmethod
    def _stamp(age_s: float, now: float) -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - age_s))

    def test_a_fresh_verdict_is_believed(self):
        import time
        from aimarket_hub.federation_assay import _assay_stale
        now = time.time()
        assert not _assay_stale({"ran_at": self._stamp(3600, now)}, now=now)

    def test_a_verdict_older_than_the_ttl_is_stale(self):
        import time
        from aimarket_hub.federation_assay import ASSAY_TTL_S, _assay_stale
        now = time.time()
        assert _assay_stale({"ran_at": self._stamp(ASSAY_TTL_S + 60, now)}, now=now)

    def test_the_real_four_day_old_verdict_is_stale(self):
        """The exact dossier that kept a healthy hub out."""
        import calendar, time
        from aimarket_hub.federation_assay import _assay_stale
        now = calendar.timegm(time.strptime("2026-09-05T09:35:59Z", "%Y-%m-%dT%H:%M:%SZ"))
        assert _assay_stale({"ran_at": "2026-09-01T11:56:36Z"}, now=now)

    def test_an_absent_timestamp_counts_as_stale(self):
        """We do not know when it was reached, so measure again. The caller's per-cycle cap
        keeps that cheap even if the stamp is never writable."""
        from aimarket_hub.federation_assay import _assay_stale
        assert _assay_stale({})
        assert _assay_stale({"ran_at": ""})

    def test_an_unparseable_timestamp_counts_as_stale(self):
        from aimarket_hub.federation_assay import _assay_stale
        assert _assay_stale({"ran_at": "last Tuesday"})
        assert _assay_stale({"ran_at": None})


# ── A hub must describe ITS OWN configuration to a knocker ────────────────────────────────
#
# The knock-facing notes were fixed strings: "a sandbox assay runs automatically" and "a pass
# indexes this hub without an operator click". Measured live on 2026-09-05, neither clause
# held everywhere it was printed — hunt.modelmarket.dev runs AIMARKET_FEDERATION_ASSAY=0 and
# still promised an assay to two hubs that had waited with no verdict at all, and
# hub.modelmarket.dev promised CHARON that a pass would admit it while CHARON sat at
# verdict=pass, quarantined, because that hub holds no judge token.
#
# A federation runs on what hubs tell each other, and this is the one answer the knocker
# cannot check for itself.

class TestTheKnockPromiseMatchesTheConfiguration:
    @staticmethod
    def _note(tmp_path, monkeypatch, **env) -> str:
        from fastapi.testclient import TestClient
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "promise.db"))
        monkeypatch.setenv("AIMARKET_HUB_URL", "https://hub.example")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("AIMARKET_FEDERATION_JUDGE_KEY", raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        from aimarket_hub.api import create_app
        client = TestClient(create_app())
        r = client.get("/ai-market/v2/federation/assay",
                       params={"url": "https://never-seen.example"})
        assert r.status_code == 200, r.text
        return r.json()["note"]

    def test_assay_off_does_not_promise_an_assay(self, tmp_path, monkeypatch):
        note = self._note(tmp_path, monkeypatch, AIMARKET_FEDERATION_ASSAY="0")
        assert "switched off" in note
        assert "runs automatically" not in note

    def test_no_judge_token_does_not_promise_admission(self, tmp_path, monkeypatch):
        note = self._note(tmp_path, monkeypatch, AIMARKET_FEDERATION_ASSAY="1")
        assert "no judge token" in note
        assert "without an operator click" not in note
        assert "operator must Approve" in note

    def test_a_judge_token_may_promise_admission(self, tmp_path, monkeypatch):
        note = self._note(tmp_path, monkeypatch, AIMARKET_FEDERATION_ASSAY="1",
                          OPENROUTER_API_KEY="sk-test-not-a-real-key")
        assert "without an operator click" in note


# ── How often we make a STRANGER run a capability for us ──────────────────────────────────
#
# `assay_pending_peers` runs at the end of every crawl cycle, and the sandbox probe is a real
# invoke on somebody else's hub. Before this, `review` was absent from the skip list, so a
# peer holding that verdict was re-probed on EVERY cycle — 288 times a day on a hub whose
# `crawl_interval_s` is 300, forever, for as long as the row existed. The probe rate was
# therefore set by OUR crawl cadence, which is our business, rather than by what is decent to
# ask of a neighbour, which is theirs.

class TestProbePolitenessIsIndependentOfCrawlCadence:
    @staticmethod
    def _stamp(age_s: float, now: float) -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - age_s))

    def test_a_review_verdict_is_believed_like_any_other(self):
        """The bug: `review` was re-probed every cycle because it was not `pass` or `fail`."""
        import time
        from aimarket_hub.federation_assay import _assay_due
        now = time.time()
        due, why = _assay_due({"verdict": "review", "ran_at": self._stamp(600, now)}, now=now)
        assert not due, "a review verdict is still being re-probed every cycle: %s" % why

    def test_settled_verdicts_wait_a_full_ttl(self):
        import time
        from aimarket_hub.federation_assay import ASSAY_TTL_S, _assay_due
        now = time.time()
        for verdict in ("pass", "fail", "review"):
            assert not _assay_due({"verdict": verdict,
                                   "ran_at": self._stamp(ASSAY_TTL_S - 60, now)}, now=now)[0]
            assert _assay_due({"verdict": verdict,
                               "ran_at": self._stamp(ASSAY_TTL_S + 60, now)}, now=now)[0]

    def test_an_unsettled_peer_is_retried_on_the_retry_floor_not_every_cycle(self):
        """A 300s crawl must not mean a 300s probe. The floor is ours, not the crawler's."""
        import time
        from aimarket_hub.federation_assay import ASSAY_RETRY_S, _assay_due
        now = time.time()
        assert not _assay_due({"verdict": "", "ran_at": self._stamp(300, now)}, now=now)[0], (
            "an unsettled peer is probed once per crawl cycle again")
        assert _assay_due({"verdict": "", "ran_at": self._stamp(ASSAY_RETRY_S + 60, now)},
                          now=now)[0]

    def test_a_peer_never_probed_is_due_immediately(self):
        from aimarket_hub.federation_assay import _assay_due
        assert _assay_due({})[0]
        assert _assay_due({"verdict": "pass", "ran_at": ""})[0]
        assert _assay_due({"verdict": "pass", "ran_at": "last Tuesday"})[0]

    def test_the_worst_case_load_on_one_neighbour_is_bounded(self):
        """The number that matters: probes per neighbour per day, at a 300s crawl."""
        import time
        from aimarket_hub.federation_assay import ASSAY_RETRY_S, ASSAY_TTL_S, _assay_due
        now = time.time()
        settled_per_day = 86400.0 / ASSAY_TTL_S
        unsettled_per_day = 86400.0 / ASSAY_RETRY_S
        assert settled_per_day <= 1.0, "a settled peer is probed more than once a day"
        assert unsettled_per_day <= 24.0, "an unsettled peer is probed more than hourly"
        # and the old behaviour — 288/day at a 300s cadence — is gone
        assert not _assay_due({"verdict": "review", "ran_at": self._stamp(300, now)}, now=now)[0]


class TestWhyAManifestIsNotSigned:
    """The check named the wrong cause, and the wrong cause sends people hunting.

    "signature missing or does not match advertised key" covered three unrelated situations,
    one of which is not the peer's fault: a hub with AIMARKET_PQC_REQUIRE=1 rejects a peer whose
    Ed25519 manifest is perfectly valid. A real peer of ours went red with that message while its
    signature verified everywhere else — the operator was told to look for a broken key when the
    answer was "this hub demands hybrid and that peer has not migrated".
    """

    @staticmethod
    def _signed_manifest(signer):
        m = {
            "protocol_version": "v2",
            "capabilities_count": 1,
            "generated_at": "2026-09-07T04:00:00Z",
            "tools": [{"id": "x.y@v1"}],
            "by_hub": {},
        }
        m["signature"] = {
            "algorithm": "ed25519",
            "public_key": signer.public_key_b64,
            "value": signer.sign_canonical(signer.manifest_canonical(m)),
        }
        return m

    def test_a_valid_classic_signature_is_named_as_a_policy_refusal(self):
        from aimarket_hub.federation_assay import _why_unsigned
        from aimarket_hub.signing import Signer

        signer = Signer()
        m = self._signed_manifest(signer)
        why = _why_unsigned(signer, m, signer.public_key_b64)
        assert "ed25519 is VALID" in why
        assert "AIMARKET_PQC_REQUIRE" in why, "the operator must be told which knob did this"

    def test_a_broken_classic_signature_still_says_so(self):
        from aimarket_hub.federation_assay import _why_unsigned
        from aimarket_hub.signing import Signer

        signer = Signer()
        m = self._signed_manifest(signer)
        m["signature"]["value"] = "AAAA"
        assert "does not match" in _why_unsigned(signer, m, signer.public_key_b64)

    def test_a_present_pq_signature_is_checked_before_it_is_blamed(self):
        """This helper only runs after a failure — but a caller that is wrong about that must
        not make it publish a false claim about a peer's cryptography."""
        from aimarket_hub.federation_assay import _why_unsigned
        from aimarket_hub.signing import Signer

        signer = Signer(pqc=True)
        m = {
            "protocol_version": "v2", "capabilities_count": 1,
            "generated_at": "2026-09-07T04:00:00Z", "tools": [], "by_hub": {},
        }
        m["signature"] = signer.sign_manifest(m)
        if not m["signature"].get("pq_value"):
            pytest.skip("dilithium-py not installed here")
        assert "verifies against the advertised key" in _why_unsigned(
            signer, m, signer.public_key_b64)
        m["signature"]["pq_value"] = "AAAA"
        assert "ML-DSA-65" in _why_unsigned(signer, m, signer.public_key_b64)

    def test_the_absent_cases_are_distinguished(self):
        from aimarket_hub.federation_assay import _why_unsigned
        from aimarket_hub.signing import Signer

        signer = Signer()
        m = self._signed_manifest(signer)
        assert "advertises no signing key" in _why_unsigned(signer, m, "")
        assert "not fetched" in _why_unsigned(signer, {}, signer.public_key_b64)
        assert "no signature block" in _why_unsigned(signer, {"tools": []}, signer.public_key_b64)


def test_a_peer_relaying_our_own_capability_is_checked_against_our_own_key(
    tmp_path, resolvable, monkeypatch
):
    """The origin of a re-export can be the assaying hub itself.

    hunt assayed hub.attestedmemory.net, which re-exports hunt's `signal.*`. The probe
    routed back to hunt, hunt signed the receipt, and hunt is no row in its own peer
    table, so the receipt could not be checked and the relay sat in `review` for doing
    its job. Our own key comes from our signer, never from the peer.
    """
    own = "https://own-hub.example"
    monkeypatch.setenv("AIMARKET_HUB_URL", own)
    root = tmp_path / "routed-self"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _reexport_docs(peer, own)   # re-exported FROM us; we are not a peer row

    async def post_json(url, body, headers):
        out = await _signed_post(signer, url, body, headers)
        out["json"]["receipt"]["signature"]["public_key"] = signer.public_key_b64
        out["json"]["routed_via"] = STRANGER
        return out

    dossier = _run(db, signer, wk, manifest, post_json)
    receipt = next(c for c in dossier["checks"] if c["id"] == "sandbox_receipt_signed")
    assert receipt["ok"] is True, receipt["detail"]
    assert dossier["sandbox"]["receipt_signed_by"] == "source_hub"
    assert dossier["verdict"] == "pass"


# ── x402 V2 doors ───────────────────────────────────────────────────────────────
# The current x402 SDKs answer a 402 with an empty body and the whole offer in the base64
# PAYMENT-REQUIRED header, priced in `amount` (V1: `maxAmountRequired` in the body). Measured
# on a live V2 seller 2026-10-12; a paid-only V2 seller could never pass before this.


def _x402_v2(price_usd: float, recipient: str = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"):
    import base64
    import json as _json

    offer = {"x402Version": 2, "error": "Payment required", "accepts": [{
        "scheme": "exact", "network": "eip155:8453",
        "amount": str(int(round(price_usd * 1_000_000))),
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "payTo": recipient,
        "maxTimeoutSeconds": 300, "extra": {"name": "USD Coin", "version": "2"},
    }]}
    header = base64.b64encode(_json.dumps(offer).encode()).decode()

    async def post_json(_url, _body, headers):
        assert not any(h.lower().startswith("x-payment") for h in headers)
        return {"http_status": 402, "bytes": 2, "json": {}, "headers": {"PAYMENT-REQUIRED": header}}
    return post_json


def test_a_paid_only_x402_v2_seller_is_admitted_on_its_header_offer(tmp_path, resolvable):
    root = tmp_path / "v2"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "gas.price@v1", "price": 0.001}], hub_version="seller-1.0",
    )
    dossier = _run(db, signer, wk, manifest, _x402_v2(0.001))
    assert dossier["verdict"] == "pass", dossier["checks"]
    challenge = dossier["sandbox"]["payment_challenge"]
    assert challenge["price_usd"] == pytest.approx(0.001)
    assert challenge["recipient"].startswith("0x1218")
    assert challenge["rails"] == ["x402:eip155:8453"]


def test_a_v2_header_quoting_another_price_is_not_admitted(tmp_path, resolvable):
    root = tmp_path / "v2-lie"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _multi_tool_docs(
        peer, [{"capability_id": "gas.price@v1", "price": 0.001}], hub_version="seller-1.0",
    )
    dossier = _run(db, signer, wk, manifest, _x402_v2(0.5))
    assert dossier["verdict"] == "review"


def test_a_v2_offer_in_the_body_is_read_too():
    from aimarket_hub.federation_assay import parse_payment_challenge

    got = parse_payment_challenge({"x402Version": 2, "accepts": [
        {"scheme": "exact", "network": "eip155:8453", "amount": "4000", "payTo": "0xabc"}]})
    assert got["price_usd"] == pytest.approx(0.004) and got["recipient"] == "0xabc"


def test_a_garbage_or_oversized_payment_header_is_no_offer():
    from aimarket_hub.federation_assay import MAX_PAYMENT_HEADER_BYTES, x402_header_offer

    assert x402_header_offer({"payment-required": "not base64 json"}) is None
    assert x402_header_offer({"payment-required": "A" * (MAX_PAYMENT_HEADER_BYTES + 1)}) is None
    assert x402_header_offer({}) is None


# ── a seller that answers at each tool's own URL (mach402.dev, agent-exec.448c.org) ─────────
# Both outside implementations that knocked in October 2026 have no AI-Market invoke route and
# list tools the way the schema allows: name, description, input_schema, plus `endpoint`,
# `method` and `price_usd`, with no capability_id. The assay had nothing to probe and they sat
# at "no publicly offered capability" forever.


def _x402_v2_header(price_usd: float, recipient: str = "0x14B21d80bf5776437dD4f1043BDAf31e60B366AD") -> str:
    import base64
    import json as _json

    offer = {"x402Version": 2, "error": "Payment required", "accepts": [{
        "scheme": "exact", "network": "eip155:8453",
        "amount": str(int(round(price_usd * 1_000_000))),
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "payTo": recipient,
    }]}
    return base64.b64encode(_json.dumps(offer).encode()).decode()


def _direct_seller_docs(signer: Signer, tools: list[dict]):
    manifest = {
        "protocol_version": "v2",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hub": STRANGER,
        "tools": tools,
    }
    manifest["signature"] = signer.sign_manifest(manifest)
    well_known = {  # unsigned, as mach402's is: allowed
        "name": "Machina",
        "protocol_versions": ["v1", "v2"],
        "hub_url": STRANGER,
        "manifest_url": f"{STRANGER}/ai-market/v2/manifest",
        "signer_public_key": signer.public_key_b64,
        "payment_rails": {"seller_direct": {"enabled": True, "asset": "USDC", "network": "eip155:8453"}},
    }
    return well_known, manifest


def _mach402_tools(elsewhere: bool = True) -> list[dict]:
    tools = [
        {"name": "scan_python", "description": "Scan Python for security issues.",
         "endpoint": f"{STRANGER}/scan/python", "method": "POST", "price_usd": 0.02,
         "payment": "x402/seller_direct",
         "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
        {"name": "validate_email", "description": "Validate one e-mail address.",
         "endpoint": f"{STRANGER}/validate/email", "method": "POST", "price_usd": 0.005,
         "payment": "x402/seller_direct",
         "input_schema": {"type": "object", "properties": {"email": {"type": "string", "examples": ["a@example.com"]}},
                          "required": ["email"]}},
        {"name": "health", "description": "Free status.", "endpoint": f"{STRANGER}/health",
         "method": "POST", "price_usd": 0.0, "input_schema": {"type": "object"}},
    ]
    if elsewhere:
        tools.append({"name": "relay", "description": "Names someone else's host.",
                      "endpoint": "https://elsewhere.example/steal", "method": "POST", "price_usd": 0.001,
                      "input_schema": {"type": "object"}})
    return tools


def _direct_doors(prices: dict[str, float]):
    """402 with a V2 offer at each priced tool URL, 404 everywhere else (no invoke route)."""
    calls: list[tuple[str, dict]] = []

    async def post_json(url, body, headers):
        calls.append((url, body))
        assert not any(h.lower().startswith("x-payment") for h in headers), "the assay never pays"
        if url in prices:
            return {"http_status": 402, "bytes": 2, "json": {},
                    "headers": {"PAYMENT-REQUIRED": _x402_v2_header(prices[url])}}
        return {"http_status": 404, "bytes": 22, "json": {"detail": "Not Found"}}

    post_json.calls = calls
    return post_json


def test_a_seller_without_capability_ids_is_admitted_on_its_tools_own_402(tmp_path, resolvable):
    root = tmp_path / "direct"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _direct_seller_docs(peer, _mach402_tools())
    doors = _direct_doors({f"{STRANGER}/scan/python": 0.02, f"{STRANGER}/validate/email": 0.005})
    dossier = _run(db, signer, wk, manifest, doors)
    assert dossier["verdict"] == "pass", dossier["checks"]
    sandbox = dossier["sandbox"]
    # The cheapest priced tool, at its own URL, with its bare input — never the invoke route.
    assert sandbox["probe_kind"] == "direct"
    assert sandbox["endpoint"] == f"{STRANGER}/validate/email"
    assert sandbox["capability_id"] == "validate_email"
    assert sandbox["payment_challenge"]["price_usd"] == pytest.approx(0.005)
    url, body = doors.calls[0]
    assert url == f"{STRANGER}/validate/email" and body == {"email": "a@example.com"}
    assert not any("elsewhere.example" in u for u, _ in doors.calls)
    assert not any(u.endswith("/ai-market/v2/invoke") for u, _ in doors.calls)


def test_a_direct_door_quoting_another_price_than_the_catalogue_is_review(tmp_path, resolvable):
    root = tmp_path / "direct-lie"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    wk, manifest = _direct_seller_docs(peer, _mach402_tools(elsewhere=False))
    dossier = _run(db, signer, wk, manifest, _direct_doors({f"{STRANGER}/validate/email": 0.5}))
    assert dossier["verdict"] == "review"
    by = {c["id"]: c for c in dossier["checks"]}
    assert by["sandbox_price_matches"]["ok"] is False


def test_a_tool_endpoint_on_another_host_is_never_called(tmp_path, resolvable):
    root = tmp_path / "direct-elsewhere"
    root.mkdir()
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    peer = Signer(root / "peer-key")
    tools = [t for t in _mach402_tools() if t["name"] == "relay"]
    wk, manifest = _direct_seller_docs(peer, tools)
    doors = _direct_doors({"https://elsewhere.example/steal": 0.001})
    dossier = _run(db, signer, wk, manifest, doors)
    assert doors.calls == []
    by = {c["id"]: c for c in dossier["checks"]}
    assert by["sandbox_probe"]["detail"] == "no publicly offered capability to probe, free or priced"


def test_a_hub_protocol_listing_with_an_endpoint_still_goes_through_the_invoke_route(tmp_path, resolvable):
    """A capability_id makes it a hub-protocol listing: its `endpoint` is not a door to knock on."""
    from aimarket_hub.federation_assay import plan_sandbox_probes

    tool = {"capability_id": "gas.price@v1", "product_id": "p1", "name": "gas", "description": "d",
            "input_schema": {"type": "object"}, "price_per_call_usd": 0.001, "endpoint": f"{STRANGER}/gas"}
    assert [kind for kind, _ in plan_sandbox_probes([tool], STRANGER, {})] == ["paid"]
