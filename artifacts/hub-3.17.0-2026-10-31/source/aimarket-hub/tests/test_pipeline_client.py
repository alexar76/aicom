"""Exercise real API preparation and client signatures with a deterministic RPC."""
import json
import os
import time

from aimarket_hub.native_price import ETH_USD, SEQUENCER

import httpx
import pytest
from eth_account import Account

from aimarket_hub.api import create_app
from aimarket_hub.pipeline_client import PipelineBudgetError, PipelinePending, run_pipeline
from aimarket_hub.pipeline_payments import validate_transaction
from tests.test_studio_paid import setup, listing, node

KEY = '0x' + '07' * 32


class Transport(httpx.AsyncBaseTransport):
    def __init__(self, app):
        self.asgi = httpx.ASGITransport(app=app)
        self.hub_calls = []
        self.invokes = []
        self.lose_first = False
        self.pending = 0
        self.gas_price = 6_000_000
        self.chain = 8453
        self.budget_bad = False
        self.nonmatching_auth = False
        self.eth_usd = 3000
        self.price_age = 10
        self.price_reads = 0

    async def handle_async_request(self, request):
        payload = json.loads(request.content) if request.content else {}
        if request.url.host in ('rpc.test', 'base-rpc.publicnode.com'):
            method = payload['method']
            values = {'eth_chainId': self.chain, 'eth_gasPrice': self.gas_price,
                      'eth_getTransactionCount': 0, 'eth_getBalance': 10**18, 'eth_estimateGas': 90000}
            if method == 'eth_getBlockByNumber':
                return httpx.Response(200, json={'result': {'number': hex(12345), 'timestamp': hex(int(time.time()))}})
            if method == 'eth_call' and payload['params'][0]['to'] in (ETH_USD, SEQUENCER):
                args = payload['params'][0]
                now = int(time.time())
                if args['data'] == '0x313ce567':
                    words = [8]
                elif args['to'] == SEQUENCER:
                    words = [1, 0, now - 7200, now - 7200, 1]
                else:
                    self.price_reads += 1
                    words = [1, self.eth_usd * 10**8, now - self.price_age, now - self.price_age, 1]
                return httpx.Response(200, json={'result': '0x' + ''.join(format(w, '064x') for w in words)})
            if method == 'eth_call':
                value = 10**8 if payload['params'][0]['data'].startswith('0x70a08231') else 1000
            else:
                value = values[method]
            return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': hex(value)})
        self.hub_calls.append(request.url.path)
        if request.url.path.endswith('/invoke'):
            self.invokes.append(payload)
            if self.pending:
                self.pending -= 1
                return httpx.Response(202, json=self.asgi.app.state.pipeline_provider.status(
                    payload['input']['run_id'], payload['input']['access_token']))
        response = await self.asgi.handle_async_request(request)
        await response.aread()
        if request.url.path == '/studio/prepare-pipeline' and self.nonmatching_auth:
            q = response.json();q['offers'][0]['authorization']['message']['value'] = '999999'
            return httpx.Response(200, json=q)
        if request.url.path.endswith('/invoke') and self.lose_first:
            self.lose_first = False
            raise httpx.ReadTimeout('lost completed response')
        return response


@pytest.fixture
def rig(setup, monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_WALLET_STATE_DIR", str(tmp_path / "wallets"))
    service, db, seen = setup
    app = create_app(config=service.config, db=db, signer=service.signer)
    # Keep the production orchestration, replacing only child delivery and chain confirmation.
    app.state.pipeline_provider.studio.invoke = service.invoke
    async def broadcast(raw, tx_hash):
        pass
    app.state.pipeline_provider.broadcaster = broadcast
    from aimarket_hub import settle
    def verify(**kw):
        t = kw['terms']
        return {'tx_hash': kw['tx_hash'], 'paid_units': t.seller_units, 'fee_units': t.fee_units,
                'authorizer': Account.from_key(KEY).address.lower(), 'nonce': kw['require_nonce'], 'pay_to': t.pay_to}
    monkeypatch.setattr(settle, 'verify_transfer', verify)
    return Transport(app), db, seen


async def call(transport, path, **kw):
    options = dict(hub='https://hub.test', signer=Account.from_key(KEY), max_total_usd='1',
                   rpc_url='https://rpc.test', state_path=path,
                   poll_interval_s=.001, timeout_s=.1)
    options.update(kw)
    async with httpx.AsyncClient(transport=transport) as client:
        return await run_pipeline({'nodes': [node()]}, client=client, **options)


@pytest.mark.asyncio
async def test_paid_one_call_two_requests_and_local_recovery(rig, tmp_path):
    transport, _, seen = rig
    path = tmp_path/'state.json'
    result = await call(transport, path)
    assert result['success'] and len(seen) == 1
    assert transport.hub_calls == ['/studio/prepare-pipeline', '/ai-market/v2/invoke']
    state = json.loads(path.read_text())
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert KEY not in path.read_text()
    assert float(state['budget_check']['conservative_total_usd']) < 1
    validate_transaction(state['quote']['offers'][0], state['wallet'], state['request']['input']['transactions']['read'])
    async with httpx.AsyncClient(transport=transport) as client:
        replay = await run_pipeline(resume=True, state_path=path, client=client)
    assert replay == result and len(transport.hub_calls) == 2


@pytest.mark.asyncio
async def test_free_graph_needs_no_signer_rpc_or_price(rig, tmp_path):
    transport, db, _ = rig
    listing(db, price=0)
    result = await call(transport, tmp_path/'free', signer=None, rpc_url=None, native_usd_ceiling=None, max_total_usd=0)
    assert result['success']
    assert transport.invokes[0]['input']['transactions'] == {}


@pytest.mark.asyncio
async def test_pending_automatically_resumes_same_order(rig, tmp_path):
    transport, _, seen = rig
    transport.pending = 2
    result = await call(transport, tmp_path/'pending')
    assert result['success'] and len(seen) == 1
    assert len(transport.invokes) == 3 and all(r == transport.invokes[0] for r in transport.invokes)
    assert transport.hub_calls.count('/studio/prepare-pipeline') == 1


@pytest.mark.asyncio
async def test_lost_response_returns_cached_server_order_without_rebuy(rig, tmp_path):
    transport, _, seen = rig
    transport.lose_first = True
    result = await call(transport, tmp_path/'lost')
    assert result['success'] and len(seen) == 1 and len(transport.invokes) == 1
    assert transport.hub_calls[-1].endswith('/pipeline')


@pytest.mark.asyncio
async def test_timeout_then_resume_without_key(rig, tmp_path):
    transport, _, seen = rig
    transport.pending = 100
    path = tmp_path/'timeout'
    with pytest.raises(PipelinePending):
        await call(transport, path, timeout_s=.002)
    original = json.loads(path.read_text())['request']
    transport.pending = 0
    async with httpx.AsyncClient(transport=transport) as client:
        result = await run_pipeline(resume=True, state_path=path, client=client)
    assert result['success'] and len(seen) == 1
    assert all(r == original for r in transport.invokes)


@pytest.mark.asyncio
async def test_budget_refuses_before_root_or_any_payment(rig, tmp_path):
    transport, _, seen = rig
    with pytest.raises(PipelineBudgetError):
        await call(transport, tmp_path/'budget', max_total_usd='.005')
    assert not transport.invokes and not seen


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['chain', 'authorization', 'stale_price'])
async def test_refuse_untrusted_payment_details(rig, tmp_path, change):
    transport, _, seen = rig
    kwargs = {}
    if change == 'chain': transport.chain = 1
    if change == 'authorization': transport.nonmatching_auth = True
    if change == 'stale_price': transport.price_age = 1600
    with pytest.raises(ValueError):
        await call(transport, tmp_path/'reject', **kwargs)
    assert not transport.invokes and not seen


@pytest.mark.asyncio
async def test_existing_file_never_starts_a_second_order(rig, tmp_path):
    transport, _, seen = rig
    path = tmp_path/'existing'
    await call(transport, path)
    with pytest.raises(ValueError, match='resume'):
        await call(transport, path)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_failed_child_is_terminal_not_retried(rig, tmp_path):
    transport, _, seen = rig
    async def fail(payload, headers, caller):
        seen.append(payload)
        return 503, {'success': False, 'error': 'seller offline'}
    transport.asgi.app.state.pipeline_provider.studio.invoke = fail
    result = await call(transport, tmp_path/'failed')
    assert result['status'] == 'failed' and len(seen) == 1 and len(transport.invokes) == 1


@pytest.mark.asyncio
async def test_lock_rejects_concurrent_client_before_preparation(rig, tmp_path):
    import fcntl
    transport, _, _ = rig
    path = tmp_path/'locked'
    with open(str(path)+'.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='another client'):
            await call(transport, path)
    assert not transport.hub_calls


@pytest.mark.asyncio
async def test_resume_rechecks_network_budget_without_replacement(rig, tmp_path):
    transport, _, seen = rig
    transport.pending = 1
    path = tmp_path/'repriced'
    await call(transport, path, wait=False)
    original = json.loads(path.read_text())['request']
    real_handle = transport.handle_async_request
    async def high_l1(request):
        data = json.loads(request.content) if request.content else {}
        if (request.url.host == 'rpc.test' and data.get('method') == 'eth_call'
                and data['params'][0]['to'].lower() == '0x420000000000000000000000000000000000000f'):
            return httpx.Response(200, json={'result': hex(10**18)})
        return await real_handle(request)
    transport.handle_async_request = high_l1
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(PipelineBudgetError):
            await run_pipeline(resume=True, state_path=path, client=client)
    assert len(transport.invokes) == 1 and not seen
    assert json.loads(path.read_text())['request'] == original


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['receipt', 'final_result', 'bill_of_materials'])
async def test_tampered_terminal_result_is_not_accepted(rig, tmp_path, target):
    transport, _, _ = rig
    original = transport.handle_async_request
    async def tamper(request):
        response = await original(request)
        if request.url.path.endswith('/invoke') and response.status_code == 200:
            body = response.json()
            if target == 'receipt':
                body['receipt']['signature']['value'] = 'invalid'
            elif target == 'bill_of_materials':
                body[target]['total_usd'] = 999
            else:
                body[target] = {'altered': True}
            return httpx.Response(200, json=body)
        return response
    transport.handle_async_request = tamper
    with pytest.raises(ValueError, match='signature|signed result'):
        await call(transport, tmp_path/'tampered')
    assert json.loads((tmp_path/'tampered').read_text())['phase'] == 'submitted'


@pytest.mark.asyncio
async def test_lost_success_is_recovered_without_rpc(rig, tmp_path):
    transport, _, seen = rig
    original = transport.handle_async_request
    lost = False
    async def lose_then_rpc_down(request):
        nonlocal lost
        if lost and request.url.host == 'rpc.test':
            raise AssertionError('reading completed result must not need RPC')
        response = await original(request)
        if request.url.path.endswith('/invoke') and response.status_code == 200:
            lost = True
            raise httpx.ReadTimeout('completed response lost')
        return response
    transport.handle_async_request = lose_then_rpc_down
    result = await call(transport, tmp_path/'lost-without-rpc')
    assert result['success'] and len(seen) == 1 and len(transport.invokes) == 1


@pytest.mark.asyncio
async def test_wallet_reservation_spans_separate_state_directories(rig, tmp_path):
    transport, _, seen = rig
    transport.pending = 1
    first = tmp_path/'a'/'state'
    await call(transport, first, wait=False)
    original = json.loads(first.read_text())['request']
    with pytest.raises(ValueError, match='wallet reserved by another order'):
        await call(transport, tmp_path/'b'/'state')
    assert not seen and len(transport.invokes) == 1
    async with httpx.AsyncClient(transport=transport) as client:
        assert (await run_pipeline(resume=True, state_path=first, client=client))['success']
    assert transport.invokes[-1] == original
    assert (await call(transport, tmp_path/'c'/'state'))['success']


@pytest.mark.asyncio
async def test_wrong_pinned_key_refused_before_signing(rig, tmp_path):
    transport, _, seen = rig
    with pytest.raises(ValueError, match='signature'):
        await call(transport, tmp_path/'wrong-pin-state', trusted_hub_key='wrong')
    assert not transport.invokes and not seen


@pytest.mark.asyncio
async def test_corrupt_local_cache_is_verified(rig, tmp_path):
    transport, _, _ = rig
    path = tmp_path/'cache'
    await call(transport, path)
    state = json.loads(path.read_text())
    state['result']['final_result'] = {'corrupt': True}
    path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match='signed result'):
        await run_pipeline(resume=True, state_path=path)


@pytest.mark.asyncio
async def test_failed_wallet_lease_released_only_after_authorizations_expire(rig, tmp_path):
    transport, _, seen = rig
    original = transport.asgi.app.state.pipeline_provider.studio.invoke
    async def fail(payload, headers, caller):
        return 503, {'success': False, 'error': 'seller unavailable'}
    transport.asgi.app.state.pipeline_provider.studio.invoke = fail
    path = tmp_path/'failed-reservation'
    assert (await call(transport, path))['status'] == 'failed'
    with pytest.raises(ValueError, match='wallet reserved'):
        await call(transport, tmp_path/'before-expiry')
    state = json.loads(path.read_text())
    for offer in state['quote']['offers']:
        offer['invoice']['expires_at'] = 0
    path.write_text(json.dumps(state))
    transport.asgi.app.state.pipeline_provider.studio.invoke = original
    assert (await call(transport, tmp_path/'after-expiry'))['success']


@pytest.mark.asyncio
async def test_eth_rise_to_20000_rechecks_budget_and_preserves_original_order(rig, tmp_path):
    transport, _, seen = rig
    transport.pending = 1
    path = tmp_path/'price-rise'
    await call(transport, path, wait=False, max_total_usd='.10', native_usd_ceiling='6000')
    original = json.loads(path.read_text())['request']
    transport.eth_usd = 20000
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(PipelineBudgetError):
            await run_pipeline(resume=True, state_path=path, client=client)
    assert len(transport.invokes) == 1 and not seen
    assert json.loads(path.read_text())['request'] == original


@pytest.mark.asyncio
async def test_live_oracle_default_without_manual_ceiling(rig, tmp_path):
    transport, _, _ = rig
    path = tmp_path/'oracle-default'
    result = await call(transport, path)
    state = json.loads(path.read_text())
    assert result['success'] and state['native_usd_ceiling'] is None
    assert state['budget_check']['native_usd_ceiling'] == '3750.00'
    assert len(state['budget_check']['native_price']['observations']) == 2
    assert transport.price_reads == 4  # Before signing and again before the root POST.


@pytest.mark.asyncio
async def test_a_submitted_order_that_never_finished_frees_the_wallet_after_expiry(rig, tmp_path):
    """A submit the Hub refused (quote or invoice expired) left the order in "submitted" forever,
    and only a completed order was ever checked for expiry: the wallet stayed reserved for good."""
    transport, _, _ = rig
    transport.pending = 1
    stuck = tmp_path/'stuck'/'state'
    await call(transport, stuck, wait=False)
    state = json.loads(stuck.read_text())
    assert state['phase'] == 'submitted'
    with pytest.raises(ValueError, match='wallet reserved'):
        await call(transport, tmp_path/'blocked'/'state')
    for offer in state['quote']['offers']:
        offer['invoice']['expires_at'] = 0
    stuck.write_text(json.dumps(state))
    transport.pending = 0
    assert (await call(transport, tmp_path/'next'/'state'))['success']


@pytest.mark.asyncio
async def test_a_paid_order_saved_without_an_rpc_can_be_resumed_with_one(rig, tmp_path):
    """The rpc_url check ran after the recovery file was saved, and resume refused every
    override, so a paid buyer-gas order prepared without an RPC could never continue."""
    transport, _, seen = rig
    path = tmp_path/'no-rpc'
    with pytest.raises(ValueError, match='requires rpc_url'):
        await call(transport, path, rpc_url=None, gas_mode='buyer')
    assert json.loads(path.read_text())['phase'] == 'prepared'
    async with httpx.AsyncClient(transport=transport) as client:
        result = await run_pipeline(resume=True, state_path=path, client=client, signer=Account.from_key(KEY),
                                    rpc_url='https://rpc.test', poll_interval_s=.001, timeout_s=.1)
    assert result['success'] and len(seen) == 1
    with pytest.raises(ValueError, match='saved RPC'):
        async with httpx.AsyncClient(transport=transport) as client:
            await run_pipeline(resume=True, state_path=path, client=client, rpc_url='https://other.test')
