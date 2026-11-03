"""A generic root SKU buys an exact graph without accepting a credit grant."""
import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import pipeline_payments, settle
from aimarket_hub.api import create_app
from aimarket_hub.pipeline_provider import CAPABILITY, PRODUCT, PipelineInput
from aimarket_hub.signing import Signer
from tests.test_studio_paid import setup, listing, node

KEY = "0x" + "07" * 32


@pytest.fixture
def client(setup):
    service, db, _ = setup
    with TestClient(create_app(config=service.config, db=db, signer=service.signer)) as client:
        yield client


def plan(client, nodes, wallet=None):
    q = client.post("/studio/preflight", json={"nodes": nodes}).json()
    assert q["ready"], q
    headers = {"X-Studio-Run-Token": q["access_token"]}
    prepared = client.post(f"/studio/paid-runs/{q['run_id']}/prepare-pipeline",
                           json={"wallet": wallet} if wallet else {}, headers=headers)
    assert prepared.status_code == 200, prepared.text
    return q, prepared.json(), headers


def invoke(client, q, payments=None, **kwargs):
    data = {"run_id": q["run_id"], "access_token": q["access_token"]}
    if payments is not None:
        data["transactions"] = payments
    return client.post("/ai-market/v2/invoke", json={"product_id": PRODUCT,
        "capability_id": CAPABILITY, "input": data, **kwargs.pop("body", {})}, **kwargs)


def signed(offer, wallet, nonce=0, **overrides):
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_utils import to_checksum_address
    signature = Account.sign_message(encode_typed_data(full_message=offer["authorization"]), KEY).signature
    tx = pipeline_payments.payment_transaction(offer, wallet, "0x" + signature.hex().removeprefix("0x"))
    tx.pop("from")
    tx["to"] = to_checksum_address(tx["to"])
    tx.update(type=2, chainId=offer["terms"]["chain_id"], nonce=nonce, gas=300000,
              maxFeePerGas=2_000_000_000, maxPriorityFeePerGas=1_000_000_000)
    tx.update(overrides)
    return "0x" + Account.sign_transaction(tx, KEY).raw_transaction.hex().removeprefix("0x")


def payer():
    return pytest.importorskip("eth_account").Account.from_key(KEY).address.lower()


def verified(monkeypatch):
    wallet = payer()
    def verify(**kw):
        t = kw["terms"]
        return dict(tx_hash=kw["tx_hash"], paid_units=t.seller_units, fee_units=t.fee_units,
                    authorizer=wallet, nonce=kw["require_nonce"], pay_to=t.pay_to)
    monkeypatch.setattr(settle, "verify_transfer", verify)


def test_free_graph_needs_no_wallet_and_returns_one_sub1_tree(client, setup):
    _, db, _ = setup
    listing(db, price=0)
    listing(db, cid="demo.end@v1", price=0)
    q, prepared, _ = plan(client, [node(), node("end", "demo.end@v1", depends_on=["read"])])
    assert prepared["offers"] == []
    response = invoke(client, q)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["success"] and out["result"]["final_result"] == {"reading": 7}
    tree = out["subcontracting"]
    assert len(tree["nodes"]) == 3
    assert {n["depth"] for n in tree["nodes"]} == {0, 1}
    assert tree["spent_usd"] == 0
    assert out["bill_of_materials"]["job_id"] == tree["job_id"]
    signer = client.app.state.pipeline_provider.studio.signer
    assert Signer.verify_object_signature(out["receipt"], signer.public_key_b64)
    assert Signer.verify_object_signature(out["bill_of_materials"], signer.public_key_b64)
    for field, value in (("bill_digest", out["bill_of_materials"]), ("result_digest", out["result"])):
        assert out["receipt"][field] == hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert len(out["receipt"]["parents"]) == 2
    assert invoke(client, q).json() == out
    assert client.get(f"/ai-market/v2/jobs/{tree['job_id']}").json()["nodes"] == tree["nodes"]


def test_executor_is_discoverable_with_its_funding_contract(client):
    tools = client.get("/ai-market/v2/manifest").json()["tools"]
    found = [t for t in tools if t["capability_id"] == CAPABILITY]
    assert len(found) == 1 and found[0]["product_id"] == PRODUCT
    declaration = client.get("/.well-known/ai-market.json").json()["pipeline_execution"]
    assert declaration["funding"] == "buyer_signed_transactions"
    assert declaration["credits_allowance"] is False


def test_composite_child_can_subcontract_with_its_own_funding(client, setup, monkeypatch):
    import httpx
    import aimarket_hub.outbound_http as outbound
    from aimarket_hub.supply_security import _bound_response_canonical
    service, db, _ = setup
    listing(db, price=0, invoke_url="https://composer.test/invoke",
            provider_pubkey=service.signer.public_key_b64, trust_score=1)
    listing(db, cid="demo.leaf@v1", price=0)
    async def provider(url, **kwargs):
        assert url == "https://composer.test/invoke"
        assert "X-AIMarket-Job-Grant" not in kwargs["headers"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://hub") as http:
            child = await http.post("/ai-market/v2/invoke", headers={
                "X-AIMarket-Job": kwargs["headers"]["X-AIMarket-Job"]}, json={
                    "product_id": "demo-product", "capability_id": "demo.leaf@v1", "input": {}})
        assert child.status_code == 200, child.text
        result = child.json()["result"]
        canonical = _bound_response_canonical("demo.read@v1", "demo-product", kwargs["json"]["input"], result)
        return httpx.Response(200, json={"result": result},
                              headers={"X-Provider-Signature": service.signer.sign_canonical(canonical)})
    monkeypatch.setattr(outbound, "safe_post", provider)
    q, _, _ = plan(client, [node()])
    out = invoke(client, q).json()
    assert out["success"], out
    assert sorted(n["depth"] for n in out["subcontracting"]["nodes"]) == [0, 1, 2]


@pytest.mark.parametrize("headers,body", [
    ({"X-API-Key": "credit-line"}, {}),
    ({"X-AIMarket-Job-Grant": "grant"}, {}),
    ({"X-AIMarket-Sandbox-Visitor": "trial"}, {}),
    ({}, {"subcontract": {"allowance_usd": 1}}),
])
def test_credit_or_trial_cannot_fund_generic_root(client, setup, headers, body):
    _, db, _ = setup
    listing(db, price=0)
    q, _, _ = plan(client, [node()])
    response = invoke(client, q, headers=headers, body=body)
    assert response.status_code == 400
    assert response.json()["error"] == "pipeline_funding_invalid"
    assert db._conn.execute("SELECT COUNT(*) AS n FROM job_nodes").fetchone()["n"] == 0


def test_paid_root_uses_exact_signed_transfer_and_cache(client, monkeypatch):
    wallet = payer()
    q, prepared, headers = plan(client, [node()], wallet)
    verified(monkeypatch)
    sent = []
    async def broadcast(raw, tx_hash):
        sent.append((raw, tx_hash))
    client.app.state.pipeline_provider.broadcaster = broadcast
    raw = signed(prepared["offers"][0], wallet)
    out = invoke(client, q, {"read": raw}).json()
    assert out["success"], out
    assert len(sent) == 1
    assert out["subcontracting"]["spent_usd"] == 0.004
    assert out["bill_of_materials"]["steps"][0]["job"]["job_id"] == out["subcontracting"]["job_id"]
    assert out["subcontracting"]["nodes"][1]["funded_by"] == "own"
    assert invoke(client, q).json() == out and len(sent) == 1
    assert raw not in json.dumps(out) and q["access_token"] not in json.dumps(out)
    manual = client.post(f"/studio/paid-runs/{q['run_id']}/advance",
                         json={"step_id": "read", "wallet": wallet}, headers=headers)
    assert manual.status_code == 409


@pytest.mark.parametrize("override", [
    {"to": "0x" + "ab" * 20}, {"value": 1}, {"chainId": 1}, {"data": "0x1234"},
])
def test_invalid_bundle_refused_before_any_broadcast(client, override):
    wallet = payer()
    q, prepared, _ = plan(client, [node()], wallet)
    # Account requires checksummed addresses for signing.
    if "to" in override:
        from eth_utils import to_checksum_address
        override = {**override, "to": to_checksum_address(override["to"])}
    response = invoke(client, q, {"read": signed(prepared["offers"][0], wallet, **override)})
    assert response.status_code == 400, response.text
    provider = client.app.state.pipeline_provider
    assert provider._row(q["run_id"]) is None
    state, busy = provider.studio.load(q["run_id"], q["access_token"])
    assert state["status"] == "quoted" and not busy


def test_pending_transaction_resumes_same_job_without_new_payment(client, monkeypatch):
    wallet = payer()
    q, prepared, _ = plan(client, [node()], wallet)
    sent = []
    async def ambiguous(raw, tx_hash):
        sent.append((raw, tx_hash))
        raise TimeoutError("broadcast reply lost")
    client.app.state.pipeline_provider.broadcaster = ambiguous
    monkeypatch.setattr(settle, "verify_transfer", lambda **kw: (_ for _ in ()).throw(settle.PaymentError("not mined")))
    pending = invoke(client, q, {"read": signed(prepared["offers"][0], wallet)})
    assert pending.status_code == 202, pending.text
    job = pending.json()["subcontracting"]["job_id"]
    verified(monkeypatch)
    done = invoke(client, q)
    assert done.status_code == 200 and done.json()["success"], done.text
    assert done.json()["subcontracting"]["job_id"] == job
    assert len(set(sent)) == 1  # exact raw bytes, same chain hash


@pytest.mark.parametrize("raw", ["0x02", "0x0200", "0xdeadbeef"])
def test_malformed_signed_bytes_are_a_client_error(client, raw):
    q, _, _ = plan(client, [node()], payer())
    assert invoke(client, q, {"read": raw}).status_code == 400


def test_failed_child_keeps_payment_and_does_not_broadcast_next(client, setup, monkeypatch):
    wallet = payer()
    _, db, _ = setup
    listing(db, cid="demo.end@v1", price=0.002)
    q, prepared, _ = plan(client, [node(), node("end", "demo.end@v1", depends_on=["read"])], wallet)
    provider = client.app.state.pipeline_provider
    verified(monkeypatch)
    sent = []
    async def broadcast(raw, tx_hash):
        sent.append(tx_hash)
    provider.broadcaster = broadcast
    # Use the normal invoke, including its job wrapper, and an honest provider failure.
    cap = db.get_capability("demo-product", "demo.read@v1", "local")
    cap.prompt_template = '{"success":false,"error":"sensor failed"}'
    db.upsert_capability(cap)
    payments = {s["id"]: signed(s, wallet, i) for i, s in enumerate(prepared["offers"])}
    out = invoke(client, q, payments).json()
    assert out["status"] == "failed" and len(sent) == 1, out
    assert out["subcontracting"]["spent_usd"] == 0.004
    assert out["subcontracting"]["unspent_budget_usd"] == 0.002
    assert sum(n["price_usd"] for n in out["subcontracting"]["nodes"]) == 0.004
    assert invoke(client, q).json() == out and len(sent) == 1


def test_recursion_is_refused_during_preflight(client):
    q = client.post("/studio/preflight", json={"nodes": [
        {"id": "root", "product_id": PRODUCT, "capability_id": CAPABILITY, "input": {}}]}).json()
    assert not q["ready"] and "recursively" in q["blockers"][0]["detail"]


def test_repricing_aborts_before_broadcast(client, setup):
    wallet = payer()
    _, db, _ = setup
    q, prepared, _ = plan(client, [node()], wallet)
    listing(db, price=0.01)
    out = invoke(client, q, {"read": signed(prepared["offers"][0], wallet)}).json()
    assert out["status"] == "failed", out
    assert out["bill_of_materials"]["total_usd"] == 0
    assert "terms changed" in out["bill_of_materials"]["steps"][0]["error"]
    assert "tx_hash" not in out["bill_of_materials"]["steps"][0]


def test_all_bundle_entries_are_checked_before_first_payment(client, setup):
    wallet = payer()
    _, db, _ = setup
    listing(db, cid="demo.end@v1", price=0.002)
    q, prepared, _ = plan(client, [node(), node("end", "demo.end@v1", depends_on=["read"])], wallet)
    first, second = prepared["offers"]
    for payments in ({"read": signed(first, wallet)},
                     {"read": signed(first, wallet), "end": signed(second, wallet, nonce=0)},
                     {"read": signed(first, wallet), "end": signed(second, wallet, nonce=1, value=1)}):
        response = invoke(client, q, payments)
        assert response.status_code == 400, response.text
        assert client.app.state.pipeline_provider._row(q["run_id"]) is None


@pytest.mark.asyncio
async def test_concurrent_roots_and_restart_do_not_repeat_children(client, setup):
    _, db, _ = setup
    listing(db, price=0)
    q, _, _ = plan(client, [node()])
    provider = client.app.state.pipeline_provider
    entered, release = asyncio.Event(), asyncio.Event()
    original = provider.studio.invoke
    calls = []
    async def delayed(*args):
        calls.append(args)
        entered.set()
        await release.wait()
        return await original(*args)
    provider.studio.invoke = delayed
    body = PipelineInput(run_id=q["run_id"], access_token=q["access_token"])
    first = asyncio.create_task(provider.invoke(body, "buyer"))
    await asyncio.wait_for(entered.wait(), 5)
    second = await provider.invoke(body, "buyer")
    assert second["busy"] and len(calls) == 1
    release.set()
    done = await first
    from aimarket_hub.pipeline_provider import PipelineProvider
    restarted = PipelineProvider(provider.studio, provider.jobs)
    assert await restarted.invoke(body, "buyer") == done
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_lost_root_dispatch_stays_locked_for_reconciliation(client, setup):
    _, db, _ = setup
    listing(db, price=0)
    q, _, _ = plan(client, [node()])
    provider = client.app.state.pipeline_provider
    calls = []
    async def lost(*args):
        calls.append(args)
        raise RuntimeError("lost result")
    provider.studio.invoke = lost
    body = PipelineInput(run_id=q["run_id"], access_token=q["access_token"])
    with pytest.raises(RuntimeError):
        await provider.invoke(body, "buyer")
    result = await provider.invoke(body, "buyer")
    assert result["busy"] and result["status"] == "reconciliation_required"
    assert len(calls) == 1


def test_combined_prepare_free_graph_is_two_hub_requests(client, setup):
    _, db, seen = setup
    listing(db, price=0)
    response = client.post('/studio/prepare-pipeline', json={'nodes': [node()], 'max_budget_usd': 0})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    q = response.json()
    assert q['ready'] and q['offers'] == [] and q['access_token']
    assert seen == []
    assert invoke(client, q).json()['success']


def test_combined_prepare_paid_graph_returns_exact_authorizations(client, setup):
    q = client.post('/studio/prepare-pipeline', json={'nodes': [node()], 'wallet': payer(), 'max_budget_usd': .01}).json()
    assert q['ready'] and q['wallet'] == payer()
    offer = q['offers'][0]
    assert offer['authorization'] == pipeline_payments.authorization_data(offer, payer())
    assert offer['terms']['amount_units'] == '4000'
    assert setup[2] == []


def test_combined_prepare_refuses_budget_and_missing_wallet(client):
    denied = client.post('/studio/prepare-pipeline', json={'nodes': [node()], 'wallet': payer(), 'max_budget_usd': 0}).json()
    assert not denied['ready'] and 'access_token' not in denied and 'offers' not in denied
    assert client.post('/studio/prepare-pipeline', json={'nodes': [node()]}).status_code == 400
    assert client.post('/studio/prepare-pipeline', json={'nodes': [node()], 'wallet': 'not-a-wallet'}).status_code == 422


def test_pipeline_status_is_authenticated_read_only_and_returns_root_cache(client, setup):
    service, db, seen = setup
    client.app.state.pipeline_provider.studio.invoke = service.invoke
    listing(db, price=0)
    q = client.post('/studio/prepare-pipeline', json={'nodes': [node()]}).json()
    endpoint = f"/studio/paid-runs/{q['run_id']}/pipeline"
    assert client.get(endpoint).status_code in (403, 404)
    headers = {'X-Studio-Run-Token': q['access_token']}
    before = client.get(endpoint, headers=headers).json()
    assert before['status'] == 'quoted' and not seen
    request = {'product_id': 'hephaestus', 'capability_id': 'pipeline.run@v1',
               'input': {'run_id': q['run_id'], 'access_token': q['access_token']}}
    done = client.post('/ai-market/v2/invoke', json=request).json()
    assert done['success']
    assert client.get(endpoint, headers=headers).json() == done
    assert len(seen) == 1


def test_mcp_free_pipeline_prepare_invoke_status(client, setup):
    import json
    service, db, seen = setup
    client.app.state.pipeline_provider.studio.invoke = service.invoke
    listing(db, price=0)
    def rpc(method, params):
        response = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
        value = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))
        return value['result']
    names = {t['name'] for t in rpc('tools/list', {})['tools']}
    assert {'pipeline_prepare', 'pipeline_invoke', 'pipeline_status'} <= names
    def tool(name, arguments):
        value = rpc('tools/call', {'name': name, 'arguments': arguments})
        assert not value['isError'], value
        return json.loads(value['content'][0]['text'])
    q = tool('pipeline_prepare', {'nodes': [node()], 'max_budget_usd': 0})
    assert q['signature'] and q['ready'] and not seen
    args = {'run_id': q['run_id'], 'access_token': q['access_token']}
    done = tool('pipeline_invoke', args)
    assert done['success'] and done['receipt']['signature']
    assert tool('pipeline_status', args) == done and len(seen) == 1


def test_mcp_paid_pipeline_preserves_authorizations_and_signed_receipts(client, setup, monkeypatch):
    service, _, seen = setup
    provider = client.app.state.pipeline_provider
    provider.studio.invoke = service.invoke
    verified(monkeypatch)
    async def broadcast(raw, tx_hash):
        return None
    provider.broadcaster = broadcast
    def tool(name, arguments):
        response = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}})
        result = json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))['result']
        assert not result['isError'], result
        return json.loads(result['content'][0]['text'])
    q = tool('pipeline_prepare', {'nodes': [node()], 'wallet': payer(), 'max_budget_usd': 1})
    assert not seen and q['ready'] and len(q['offers']) == 1
    assert Signer.verify_object_signature(q, service.signer.public_key_b64)
    raw = signed(q['offers'][0], payer())
    args = {'run_id': q['run_id'], 'access_token': q['access_token'], 'transactions': {'read': raw}}
    result = tool('pipeline_invoke', args)
    assert result['success'] and len(seen) == 1
    assert Signer.verify_object_signature(result['receipt'], service.signer.public_key_b64)
    assert Signer.verify_object_signature(result['bill_of_materials'], service.signer.public_key_b64)
    assert tool('pipeline_invoke', args) == result and len(seen) == 1


def test_seller_operation_id_reaches_provider_only_from_internal_state(client, setup, monkeypatch):
    import httpx
    import aimarket_hub.outbound_http as outbound
    from aimarket_hub.supply_security import _bound_response_canonical
    service, db, _ = setup
    listing(db, price=0, invoke_url='https://provider.test/invoke',
            provider_pubkey=service.signer.public_key_b64, trust_score=1)
    seen=[]
    async def provider(url, **kw):
        seen.append(kw['headers'])
        result={'reading':7}
        canonical=_bound_response_canonical('demo.read@v1','demo-product',kw['json']['input'],result)
        return httpx.Response(200,json={'result':result},headers={
            'X-Provider-Signature':service.signer.sign_canonical(canonical)})
    monkeypatch.setattr(outbound,'safe_post',provider)
    payload={'product_id':'demo-product','capability_id':'demo.read@v1','input':{}}
    r=client.post('/ai-market/v2/invoke',json=payload,headers={
        'Idempotency-Key':'forged','X-AIMarket-Operation-Id':'forged'})
    assert r.json()['success'], r.text
    assert 'Idempotency-Key' not in seen[-1]
    q=client.post('/ai-market/v2/operations/prepare',json={
        'product_id':'demo-product','capability_id':'demo.read@v1','max_price_usd':0}).json()
    op=q['offer']['operation_id']
    r=client.post('/ai-market/v2/operations/'+op+'/invoke',json={'input':{}},
        headers={'X-Operation-Token':q['operation_token']})
    assert r.json()['success'], r.text
    assert seen[-1]['Idempotency-Key']==seen[-1]['X-AIMarket-Operation-Id']==op
