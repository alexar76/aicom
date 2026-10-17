"""Real journal + HTTP transport + Hub signatures; no live purchases."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from cryptography.exceptions import InvalidSignature

from core import pipeline_cost_guard as costs
from core.procurement_contract import PurchasePolicy, accept_report, build_requests, source_file
from core.procurement_receipt import checked_charge
from core.procurement_store import PurchaseStore, micros
from orchestrator.procurement import prepare_diagnosis, record_diagnosis_outcome

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("_procurement_hub_signing", REPO / "aimarket-hub/aimarket_hub/signing.py")
signing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signing)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_MAX_PIPELINE_COST_USD", "5")
    monkeypatch.setenv("AIFACTORY_PROCUREMENT_API_KEY", "private-purchaser-key")
    monkeypatch.delenv("AIFACTORY_FACTORY_ON_HOLD", raising=False)
    monkeypatch.setattr(costs, "_STATE_PATH", tmp_path / "state/llm_cost.json")
    costs.reset_pipeline_cost_state_for_tests()
    signer = signing.Signer(tmp_path / "signer", pqc=False)
    config = {"enabled": True, "hub_url": "https://hub.example", "hub_public_key": signer.public_key_b64,
              "providers": [{"product_id": "doctor", "capability_id": "diagnose@v1"}],
              "share_globs": ["app/*.py"]}
    (tmp_path / "config").mkdir()
    (tmp_path / "config/procurement.json").write_text(json.dumps(config))
    code = tmp_path / "code/prod/app/main.py"
    code.parent.mkdir(parents=True)
    code.write_text("def divide(x):\n    return 1 / x\n")
    findings = [{"file": "app/main.py", "title": "Division by zero", "severity": "high"}]
    state = {"root": tmp_path, "product": {"id": "prod"}, "task_queue": [],
             "task": {"id": "repair", "product_id": "prod"}, "input_data": {"qa_findings": findings}}
    yield state, signer, config
    costs.reset_pipeline_cost_state_for_tests()


def complete_internal(state, number):
    state["task_queue"].append({"id": f"dev-{number}", "product_id": "prod", "agent_type": "developer",
                                "status": "completed", "completed_at": number})


class Hub:
    def __init__(self, signer, mode="ok"):
        self.signer, self.mode = signer, mode
        self.posts = []

    def handle(self, request):
        if request.url.path == "/.well-known/ai-market.json":
            body = {"signer_public_key": self.signer.public_key_b64}
            body["signature"] = self.signer.sign_object(body)
            if self.mode == "wrong_key":
                body["signer_public_key"] = "tampered"
            return httpx.Response(200, json=body)
        if request.url.path.endswith("/search"):
            assert "x-api-key" not in request.headers
            return httpx.Response(200, json={"matches": [{"product_id": "doctor", "capability_id": "diagnose@v1",
                "source_hub": "local", "demo": self.mode == "demo", "offerable": True,
                "credits_eligible": self.mode != "seller_direct",
                "routed_price_usd": .1, "input_required": ["contract", "files", "fingerprint"]}]})
        assert request.url.path.endswith("/invoke")
        assert request.headers["x-api-key"] == "private-purchaser-key"
        body = json.loads(request.content)
        self.posts.append(body)
        assert body["max_price_usd"] == .1
        assert "subcontract" not in body and "verify" not in body
        if self.mode == "timeout":
            raise httpx.ReadTimeout("lost after seller received the request")
        if self.mode == "http_error":
            return httpx.Response(502, json={"error": "failed"})
        packet = body["input"]
        result = {k: packet[k] for k in ("contract", "issue", "fingerprint")}
        result["diagnosis"] = [{"file": "app/main.py", "line": 2, "evidence": "return 1 / x",
                                 "explanation": "Zero input divides by zero.",
                                 "suggested_check": "Test divide(0) against the required error contract."}]
        receipt = {"nonce": f"rcpt_{len(self.posts)}", "product_id": "doctor", "capability_id": "diagnose@v1",
                   "price_usd": .1, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "success": True, "latency_ms": 10}
        receipt["signature"] = self.signer.sign_receipt(receipt)
        if self.mode == "bad_report":
            result["diagnosis"][0]["evidence"] = "not in source"
        if self.mode == "bad_receipt":
            receipt["price_usd"] = .01
        return httpx.Response(200, json={"success": True, "receipt": receipt, "result": result})


async def attempt(state, hub):
    async with httpx.AsyncClient(transport=httpx.MockTransport(hub.handle)) as client:
        return await prepare_diagnosis(**state, client=client)


@pytest.mark.asyncio
async def test_third_repair_buys_once_and_delivers_source_bound_advice(world):
    state, signer, _ = world
    hub = Hub(signer)
    for n in (1, 2):
        complete_internal(state, n)
        assert await attempt(state, hub) is None
    complete_internal(state, 3)
    result = await attempt(state, hub)
    assert result["report"]["diagnosis"][0]["line"] == 2
    assert len(hub.posts) == 1
    assert await attempt(state, hub) == result  # crash before local execution: replay saved advice, not purchase
    store = PurchaseStore(state["root"])
    assert store.exposure("prod") == 100_000
    assert costs.total_product_spend_usd("prod") == costs.Decimal("0.1")
    store.mark_applied(result["order_id"])
    assert await attempt(state, hub) is None
    record_diagnosis_outcome(state["root"], "prod", {"bugs_found": []}, gates_passed=True)
    assert json.loads(store.orders()[0]["outcome"])["gates_passed"] is True
    assert len(hub.posts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["timeout", "http_error", "bad_receipt"])
async def test_uncertain_payment_survives_restart_and_blocks_repurchase(world, mode):
    state, signer, _ = world
    hub = Hub(signer, mode)
    for n in (1, 2, 3):
        complete_internal(state, n)
        assert await attempt(state, hub) is None
    row = PurchaseStore(state["root"]).orders()[0]
    assert row["payment"] == "unknown" and row["reserved"] == 100_000
    complete_internal(state, 4)
    await attempt(state, Hub(signer))
    assert len(hub.posts) == 1
    assert len(PurchaseStore(state["root"]).orders()) == 1


@pytest.mark.asyncio
async def test_rejected_advice_is_still_billed_and_no_refund_is_invented(world):
    state, signer, _ = world
    hub = Hub(signer, "bad_report")
    for n in (1, 2, 3):
        complete_internal(state, n)
        assert await attempt(state, hub) is None
    row = PurchaseStore(state["root"]).orders()[0]
    assert row["status"] == "rejected" and row["payment"] == "paid" and row["charged"] == 100_000
    assert row["observation"] == "dev-3"
    def forbidden(request):
        pytest.fail("replaying this repair must not search for another paid supplier")
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        assert await prepare_diagnosis(**state, client=client) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["demo", "wrong_key", "seller_direct"])
async def test_unusable_offers_and_wrong_hub_key_do_not_spend(world, mode):
    state, signer, _ = world
    hub = Hub(signer, mode)
    for n in (1, 2, 3):
        complete_internal(state, n)
        assert await attempt(state, hub) is None
    assert not hub.posts and not PurchaseStore(state["root"]).orders()


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["disabled", "product", "hold", "stuck", "locked", "no_output"])
async def test_policy_stops_do_not_contact_hub(world, monkeypatch, switch):
    state, signer, config = world
    if switch == "disabled":
        config["enabled"] = False
        (state["root"] / "config/procurement.json").write_text(json.dumps(config))
    elif switch == "product":
        state["product"]["external_diagnostics_allowed"] = False
    elif switch == "hold":
        monkeypatch.setenv("AIFACTORY_FACTORY_ON_HOLD", "1")
    elif switch == "stuck":
        state["product"]["pipeline_stuck_reason"] = "operator review required"
    elif switch == "locked":
        state["product"]["operator_locked"] = True
    else:
        state["product"]["last_round_generated"] = False
    def forbidden(request):
        pytest.fail("policy-disabled procurement made an HTTP request")
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        for n in (1, 2, 3, 4):
            complete_internal(state, n)
            assert await prepare_diagnosis(**state, client=client) is None


def test_source_scope_blocks_secrets_symlinks_traversal_and_large_files(world):
    state, _, _ = world
    root = state["root"] / "code/prod"
    for path in ("../signer", "/etc/passwd", "app/../../signer", ".env", "app/key.pem"):
        with pytest.raises(ValueError):
            source_file(root, path, ("*",))
    (root / "app/link.py").symlink_to(root / "app/main.py")
    with pytest.raises(ValueError):
        source_file(root, "app/link.py", ("*",))
    for content in ("password = 'a-private-value'", "a" * 16_001):
        (root / "app/main.py").write_text(content)
        with pytest.raises(ValueError):
            source_file(root, "app/main.py", ("*",))


def test_qa_path_formats_share_one_identity_without_expanding_scope(world):
    state, _, _ = world
    root = state["root"] / "code/prod"
    policy = PurchasePolicy.load(state["root"])
    finding = state["input_data"]["qa_findings"][0]
    expected = build_requests(root, [finding], policy)
    for path in ("code/prod/app/main.py", "data/code/prod/app/main.py", str(root / "app/main.py")):
        assert build_requests(root, [{**finding, "file": path}], policy) == expected
    for path in ("code/other/app/main.py", "data/code/prod/../app/main.py",
                 str(state["root"] / "code/other/app/main.py")):
        assert build_requests(root, [{**finding, "file": path}], policy) == []


def test_report_cannot_change_scope_revision_or_claim_unseen_evidence(world):
    state, _, _ = world
    policy = PurchasePolicy.load(state["root"])
    packet = build_requests(state["root"] / "code/prod", state["input_data"]["qa_findings"], policy)[0]
    for report in ({}, {**packet, "diagnosis": []}, {**packet, "fingerprint": "other", "diagnosis": [{}]},
                   {**packet, "diagnosis": [{"file": "../../x", "line": 1}]},
                   {**packet, "diagnosis": [{"file": [], "line": 1}]}):
        with pytest.raises(ValueError):
            accept_report(packet, report)


def test_company_budget_serializes_concurrent_products_and_preserves_unknown_holds(tmp_path):
    store = PurchaseStore(tmp_path)
    def buy(n):
        return PurchaseStore(tmp_path).reserve(
            order={"id": str(n), "product": str(n), "issue": "same", "fingerprint": "rev", "supplier": "doctor",
                   "request": {}}, amount=100_000, llm_spent=0, total_cap=1_000_000,
            external_cap=500_000, daily_cap=100_000, completion_reserve=100_000, max_attempts=2)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(buy, range(8))) == 1
    assert sum(row["reserved"] for row in store.orders()) == 100_000
    assert len(PurchaseStore(tmp_path).orders()) == 1


@pytest.mark.asyncio
async def test_total_budget_leaves_money_for_completion(world):
    state, signer, _ = world
    costs.record_product_llm_spend("prod", 4.5)
    hub = Hub(signer)
    for n in (1, 2, 3):
        complete_internal(state, n)
        assert await attempt(state, hub) is None
    assert not hub.posts


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("hybrid", [False, True])
def test_billing_verifier_matches_real_hub_signer_and_rejects_tampering(tmp_path, version, hybrid):
    signer = signing.Signer(tmp_path / "hub", pqc=hybrid)
    request = {"product_id": "doctor", "capability_id": "diagnose@v1"}
    receipt = {**request, "nonce": "rcpt_test", "price_usd": .1, "success": True, "latency_ms": 1,
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    receipt["signature"] = signer.sign_receipt(receipt, version=version)
    assert checked_charge(receipt, signer.public_key_b64, request, time.time(), signer.pq_public_key_b64) == 100_000
    receipt["price_usd"] = .01
    with pytest.raises(InvalidSignature):
        checked_charge(receipt, signer.public_key_b64, request, time.time(), signer.pq_public_key_b64)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "-Infinity"])
def test_money_rejects_nonfinite_or_negative_values(value):
    with pytest.raises((ValueError, ArithmeticError)):
        micros(value)


@pytest.mark.asyncio
async def test_real_executor_hands_paid_diagnosis_to_internal_developer(world, monkeypatch):
    from types import SimpleNamespace

    import orchestrator.procurement as procurement
    from orchestrator.task_executor_agent import run_agent_task

    state, signer, _ = world
    hub = Hub(signer)
    for n in (1, 2):
        complete_internal(state, n)
        await attempt(state, hub)
    complete_internal(state, 3)
    original = procurement.prepare_diagnosis
    async def with_transport(**kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(hub.handle)) as client:
            return await original(**kwargs, client=client)
    monkeypatch.setattr(procurement, "prepare_diagnosis", with_transport)
    seen = {}
    class ReachedDeveloper(BaseException):
        pass
    class Developer:
        async def execute(self, agent_input):
            seen.update(agent_input.data)
            raise ReachedDeveloper()
    task = {**state["task"], "status": "running", "agent_type": "developer", "state": "DEV_FIXING",
            "input_data": state["input_data"]}
    product = state["product"]
    product["state"] = "BUG_FOUND"
    host = SimpleNamespace(data_root=state["root"], _load_spec=lambda pid: {}, _load_arch=lambda pid: {})
    with pytest.raises(ReachedDeveloper):
        await run_agent_task(host, agent_type="developer", agent=Developer(), task=task,
                             products={"prod": product}, task_queue=state["task_queue"],
                             product=product, pid="prod", task_id=task["id"])
    assert seen["external_diagnosis"]["report"]["diagnosis"][0]["file"] == "app/main.py"
    assert len(hub.posts) == 1
    assert product["state"] == "BUG_FOUND"  # advice does not advance or waive QA
    assert PurchaseStore(state["root"]).orders()[0]["applied"] == 0


@pytest.mark.asyncio
async def test_source_changed_during_purchase_is_billed_but_not_applied(world):
    state, signer, _ = world
    hub = Hub(signer)
    handler = hub.handle
    def mutate(request):
        response = handler(request)
        if request.method == "POST":
            (state["root"] / "code/prod/app/main.py").write_text("def divide(x):\n    return 0\n")
        return response
    hub.handle = mutate
    for n in (1, 2, 3):
        complete_internal(state, n)
        assert await attempt(state, hub) is None
    row = PurchaseStore(state["root"]).orders()[0]
    assert row["status"] == "rejected" and row["charged"] == 100_000
    assert "source changed" in row["reason"]


@pytest.mark.asyncio
async def test_replayed_local_attempts_do_not_qualify_as_two_repairs(world):
    state, signer, _ = world
    complete_internal(state, 1)
    hub = Hub(signer)
    for _ in range(5):
        assert await attempt(state, hub) is None
    assert not hub.posts


@pytest.mark.asyncio
async def test_external_costs_block_later_llm_admission(world, monkeypatch):
    state, signer, _ = world
    hub = Hub(signer)
    for n in (1, 2, 3):
        complete_internal(state, n)
        await attempt(state, hub)
    monkeypatch.setenv("AIFACTORY_MAX_PIPELINE_COST_USD", "0.1")
    with pytest.raises(costs.PipelineCostBudgetExceeded):
        costs.assert_product_within_budget("prod")


def test_order_attempt_budget_survives_new_task_ids_and_source_versions(tmp_path):
    store = PurchaseStore(tmp_path)
    def reserve(n):
        return store.reserve(order={"id": str(n), "product": "p", "issue": "same",
                    "fingerprint": str(n), "supplier": str(n), "request": {}},
                    amount=10, llm_spent=0, total_cap=1000, external_cap=100, daily_cap=100,
                    completion_reserve=1, max_attempts=2)
    assert reserve(1)
    store.finish("1", status="rejected", charged=10)
    assert reserve(2)
    store.finish("2", status="rejected", charged=10)
    assert not reserve(3)


def test_one_purchase_per_internal_repair_even_for_another_supplier_and_issue(tmp_path):
    store = PurchaseStore(tmp_path)
    def reserve(n, observation):
        return store.reserve(order={"id": str(n), "product": "p", "issue": str(n),
                             "fingerprint": str(n), "supplier": str(n), "request": {},
                             "observation": observation},
                             amount=10, llm_spent=0, total_cap=1000, external_cap=100, daily_cap=100,
                             completion_reserve=1, max_attempts=2)
    assert reserve(1, "dev-3")
    store.finish("1", status="rejected", charged=10)
    assert not reserve(2, "dev-3")
    assert reserve(2, "dev-4")


def test_unknown_payment_can_only_be_released_by_explicit_reconciliation(tmp_path):
    import subprocess
    import sys

    store = PurchaseStore(tmp_path)
    assert store.reserve(order={"id": "p1", "product": "p", "issue": "i", "fingerprint": "v",
                                  "supplier": "doctor", "request": {}},
                         amount=100_000, llm_spent=0, total_cap=1_000_000,
                         external_cap=500_000, daily_cap=500_000, completion_reserve=1, max_attempts=2)
    result = subprocess.run([sys.executable, str(REPO / "scripts/procurement_orders.py"),
                             "--data-root", str(tmp_path), "reconcile", "--order", "p1",
                             "--charged-usd", "0.07", "--evidence", "Hub ledger reference 123"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    row = store.orders()[0]
    assert row["charged"] == 70_000 and row["reserved"] == 0 and row["payment"] == "paid"
    assert row["status"] == "rejected"  # reconciliation never fabricates useful work


def test_late_settlement_still_counts_against_todays_company_cap(tmp_path, monkeypatch):
    import core.procurement_store as module

    clock = [86400.0]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    store = PurchaseStore(tmp_path)
    def reserve(order_id):
        return store.reserve(order={"id": order_id, "product": order_id, "issue": "i", "fingerprint": "v",
                                  "supplier": "doctor", "request": {}}, amount=100, llm_spent=0,
                             total_cap=1000, external_cap=1000, daily_cap=100, completion_reserve=1, max_attempts=2)
    assert reserve("yesterday")
    clock[0] += 86400
    assert not reserve("today")  # yesterday's unknown money is still reserved
    store.finish("yesterday", status="rejected", charged=100)
    assert not reserve("today")  # a newly confirmed charge does not disappear at midnight
