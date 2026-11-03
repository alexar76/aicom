"""Two companies, one job: Independent AI's claim.audit@v1 hires Attested Memory on Attested's own hub.

examples/cross-company-check/server.py is loaded as it ships. Two REAL hub apps run in-process:

* Independent's hub (the `hub` kit fixture) lists the auditor and holds a credit account AT
  Attested's hub (AIMARKET_PEER_API_KEYS), so it can resell Attested's checks;
* Attested's hub sells claim.check@v1 ($0.022) and contradiction.scan@v1 ($0.009) as local packs.

The buyer opens a job on Independent's hub with an allowance; the auditor buys both checks back
through Independent's hub inside that job; Independent's hub pays Attested's hub from its account
there and carves price + routing fee out of the allowance. Only the network is replaced.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests._mandate_kit import ADMIN_TOKEN, HUB, balance, funded_account, hub
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "cross-company-check"
ATTESTED = "https://attested.test"
AUDIT_URL = "http://127.0.0.1:9476/invoke"
CHECK_PRICE, SCAN_PRICE = 0.022, 0.009
FEE_BPS = 100


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit_server = _load("cross_company_audit_server", EXAMPLE_DIR / "server.py")


class _Resp:
    def __init__(self, status, headers, body):
        import httpx

        self.status_code = status
        self.headers = httpx.Headers(headers)
        self.content = body
        self.text = body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)


def _attested_hub(tmp_path, scan_answer: dict):
    root = tmp_path / "attested"
    root.mkdir()
    config = HubConfig()
    config.hub_url = ATTESTED
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    for product, cap, price, answer in (
        ("claim-check", "claim.check@v1", CHECK_PRICE,
         {"status": "contested", "confidence": 0.6, "method": "submitted-evidence-weight-v1"}),
        ("contradiction-scan", "contradiction.scan@v1", SCAN_PRICE, scan_answer),
    ):
        db.upsert_capability(Capability(
            capability_id=cap, product_id=product, name=cap, description="Attested check",
            price_per_call_usd=price, source_hub="local", invoke_url="", prompt_template=json.dumps(answer)))
    client = TestClient(create_app(config=config, db=db, signer=Signer(root / "key")), base_url=ATTESTED)
    client.__enter__()
    return client, db


def _world(monkeypatch, tmp_path, *, scan_answer=None, fund_independent_at_attested=1.0):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0")
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    attested, attested_db = _attested_hub(
        tmp_path, scan_answer if scan_answer is not None else {"contradictions": [], "method": "lexical-negation-v1"})
    # Independent's own account AT Attested's hub, funded by Independent (here: an operator grant).
    acct, key = funded_account(attested, attested_db, fund_independent_at_attested)
    return attested, attested_db, acct, key


@pytest.fixture()
def two_companies(monkeypatch, tmp_path):
    attested, attested_db, indep_acct_at_attested, key = _world(monkeypatch, tmp_path)
    yield from _independent(monkeypatch, tmp_path, attested, attested_db, indep_acct_at_attested, key)


def _independent(monkeypatch, tmp_path, attested, attested_db, indep_acct_at_attested, key):
    env = {
        "AIMARKET_PEER_API_KEYS": f"{ATTESTED}={key}",
        "AIMARKET_ROUTING_FEE_BPS": str(FEE_BPS),
        "AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG": "1",
        "AIMARKET_SUPPLY_OPERATOR_PUBLISHERS": "independent-claim-audit",
        "AIMARKET_ALLOW_LOCAL_PUBLISH": "1",
        "AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE": "off",
    }
    with hub(monkeypatch, tmp_path, **env) as (client, db):
        import aimarket_hub.api as api_mod
        import aimarket_hub.peer_routing as peer_routing
        import aimarket_hub.outbound_http as outbound

        def transport(method, url, headers, body, timeout):
            r = client.request(method, url, headers=dict(headers), content=body)
            return r.status_code, dict(r.headers), r.content

        cfg = audit_server.Config(hub_url=HUB, key_path=tmp_path / "audit" / "provider_key",
                                  state_path=tmp_path / "audit" / "daily_spend.json",
                                  child_source_hub=ATTESTED)
        auditor = audit_server.Auditor(cfg, transport=transport)
        to_attested: list[dict] = []

        async def safe_post(url, *, json=None, headers=None, timeout=30.0, invoke=False, oracle_paid=False):
            sent = {k: v for k, v in (headers or {}).items() if v}
            if url == AUDIT_URL:
                raw = __import__("json").dumps(json or {}).encode()
                status, out_headers, out = await asyncio.to_thread(auditor.handle, sent, raw)
                return _Resp(status, out_headers, out)
            if url.startswith(ATTESTED):
                to_attested.append(sent)
                r = await asyncio.to_thread(attested.post, url.replace(ATTESTED, ""), json=json, headers=sent)
                return _Resp(r.status_code, dict(r.headers), r.content)
            raise AssertionError(f"unexpected outbound POST {url}")

        async def safe_get(url, *, timeout=10.0):
            r = attested.get(url.replace(ATTESTED, ""))
            return _Resp(r.status_code, dict(r.headers), r.content)

        monkeypatch.setattr(outbound, "safe_post", safe_post)
        monkeypatch.setattr(outbound, "safe_get", safe_get)
        monkeypatch.setattr(peer_routing, "_peer_endpoint_cache", {})
        db.upsert_peer(Peer(url=ATTESTED, name="Attested Memory", capabilities_count=2, trust_score=0.9,
                            well_known_url=f"{ATTESTED}/.well-known/ai-market.json", trusted=True))
        for product, cap, price in (("claim-check", "claim.check@v1", CHECK_PRICE),
                                    ("contradiction-scan", "contradiction.scan@v1", SCAN_PRICE)):
            db.upsert_capability(Capability(
                capability_id=cap, product_id=product, name=cap, price_per_call_usd=price,
                source_hub=ATTESTED, source_hub_name="Attested Memory", trust_score=0.9,
                routed_price_usd=round(price * (1 + FEE_BPS / 10000), 6), routing_fee_bps=FEE_BPS))
        manifest = json.loads((EXAMPLE_DIR / "capability.json").read_text(encoding="utf-8"))
        manifest.update(invoke_url=AUDIT_URL, provider_pubkey=auditor.pubkey_b64)
        r = client.post("/ai-market/v2/supply/register", json=manifest,
                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        assert r.status_code == 200, r.text
        try:
            yield client, db, attested, attested_db, indep_acct_at_attested, to_attested
        finally:
            attested.__exit__(None, None, None)


def _audit(client, api_key, *, allowance=0.05, statements=None):
    return client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json={
        "product_id": "independent-claim-audit", "capability_id": "claim.audit@v1",
        "input": {"claim": "The vault holds 3 BTC",
                  "evidence": [{"source_uri": "https://a.example", "excerpt_hash": "sha256:" + "a" * 64,
                                "stance": "supports", "quality": 0.8}],
                  "statements": statements or ["The vault holds 3 BTC", "The audit found 3 BTC"]},
        **({"subcontract": {"allowance_usd": allowance, "max_depth": 1}} if allowance else {}),
    })


def test_independent_hires_attested_and_every_ledger_balances(two_companies):
    client, db, attested, attested_db, indep_at_attested, to_attested = two_companies
    buyer, buyer_key = funded_account(client, db, 1.0)
    r = _audit(client, buyer_key)
    assert r.status_code == 200, r.text
    body = r.json()
    result, sub = body["result"], body["subcontracting"]
    assert result["verdict"] == "contested" and result["funding"] == "cost-plus"
    assert result["subcontractor"]["hub"] == ATTESTED
    assert sorted((n["capability_id"], n["status"], n["funded_by"]) for n in sub["nodes"]) == [
        ("claim.check@v1", "captured", "allowance"), ("contradiction.scan@v1", "captured", "allowance")]
    # The allowance paid Attested's prices plus Independent's 1% routing fee.
    children = (CHECK_PRICE + SCAN_PRICE) * (1 + FEE_BPS / 10000)
    assert sub["spent_usd"] == pytest.approx(children, abs=2e-5)
    assert balance(db, buyer) == pytest.approx(1.0 - 0.003 - children, abs=2e-5)
    # Independent's hub paid Attested's hub out of its own account there — real money on two ledgers.
    assert balance(attested_db, indep_at_attested) == pytest.approx(1.0 - CHECK_PRICE - SCAN_PRICE)
    # Attested saw Independent's key and nothing of the buyer's job.
    for sent in to_attested:
        assert "X-API-Key" in sent and "X-AIMarket-Job" not in sent and "X-AIMarket-Job-Grant" not in sent


def test_contradictions_make_the_audit_inconsistent(monkeypatch, tmp_path):
    attested, attested_db, acct, key = _world(monkeypatch, tmp_path, scan_answer={
        "contradictions": [{"left_index": 0, "right_index": 1, "confidence": 1.0}],
        "method": "lexical-negation-v1"})
    gen = _independent(monkeypatch, tmp_path, attested, attested_db, acct, key)
    client, db, *_ = next(gen)
    try:
        _, buyer_key = funded_account(client, db, 1.0)
        r = _audit(client, buyer_key, statements=["The bridge is open", "The bridge is not open"])
        assert r.status_code == 200, r.text
        assert r.json()["result"]["verdict"] == "inconsistent"
    finally:
        gen.close()


def test_an_empty_account_at_attested_costs_the_buyer_only_the_failed_audit_nothing(monkeypatch, tmp_path):
    """Independent did not prepay Attested: the checks cannot be bought, the audit fails, and
    the buyer pays nothing for children that were never delivered."""
    attested, attested_db, acct, key = _world(monkeypatch, tmp_path, fund_independent_at_attested=0.0)
    gen = _independent(monkeypatch, tmp_path, attested, attested_db, acct, key)
    client, db, *_ = next(gen)
    try:
        buyer, buyer_key = funded_account(client, db, 1.0)
        r = _audit(client, buyer_key)
        assert r.status_code == 502, r.text
        assert balance(db, buyer) == pytest.approx(1.0)
    finally:
        gen.close()


def test_without_an_allowance_the_auditor_does_not_spend_its_own_money(two_companies):
    client, db, *_ = two_companies
    buyer, buyer_key = funded_account(client, db, 1.0)
    r = _audit(client, buyer_key, allowance=None)
    assert r.status_code in (402, 502), r.text
    assert "allowance" in r.text
