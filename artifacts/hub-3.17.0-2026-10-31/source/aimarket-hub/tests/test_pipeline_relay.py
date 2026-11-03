"""Sponsor isolation, durable authorization reuse, and bounded nonce allocation."""
import asyncio
import json
import time
from copy import deepcopy

import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi import HTTPException

from aimarket_hub.pipeline_client import run_pipeline, PipelineHTTPError
from aimarket_hub.pipeline_provider import PipelineInput, PrepareGraph
from aimarket_hub.pipeline_payments import validate_transaction
from aimarket_hub.pipeline_relay import PipelineRelay, RelayPending
from tests.test_pipeline_client import rig, Transport, KEY, call
from tests.test_studio_paid import setup, listing, node

SPONSOR = Account.from_key('0x' + '09' * 32)


class RelayTransport(Transport):
    def __init__(self, app):
        super().__init__(app)
        self.nonce = 0
        self.receipts = {}
        self.rpc_methods = []
        self.sent = []

    async def handle_async_request(self, request):
        if request.url.host == 'rpc.test':
            payload = json.loads(request.content)
            method = payload['method']
            self.rpc_methods.append(method)
            if method == 'eth_getTransactionCount':
                return httpx.Response(200, json={'result': hex(self.nonce)})
            if method == 'eth_getTransactionReceipt':
                return httpx.Response(200, json={'result': self.receipts.get(payload['params'][0])})
            if method == 'eth_sendRawTransaction':
                from eth_utils import keccak
                self.sent.append(payload['params'][0])
                return httpx.Response(200, json={'result': '0x' + keccak(bytes.fromhex(payload['params'][0][2:])).hex()})
        return await super().handle_async_request(request)


@pytest.fixture
def sponsored(rig):
    base, db, seen = rig
    transport = RelayTransport(base.asgi.app)
    provider = transport.asgi.app.state.pipeline_provider
    relay = PipelineRelay(provider.conn, signer=SPONSOR, rpc_url='https://rpc.test')
    relay.client_factory = lambda: httpx.AsyncClient(transport=transport)
    provider.relay = relay
    return transport, db, seen


async def prepare(transport, nodes=None):
    provider = transport.asgi.app.state.pipeline_provider
    q = await provider.studio.preflight_external(PrepareGraph(nodes=nodes or [node()]))
    q.update(provider.prepare(q['run_id'], q['access_token'], Account.from_key(KEY).address, 'required'))
    state, _ = provider.studio.load(q['run_id'], q['access_token'])
    for step, offer in zip(state['steps'], q['offers']):
        step['relay_authorization'] = '0x' + Account.from_key(KEY).sign_message(
            encode_typed_data(full_message=offer['authorization'])).signature.hex()
    return provider, q, state


def body(q, state):
    return PipelineInput(run_id=q['run_id'], access_token=q['access_token'],
                         authorizations={s['node']['id']: s['relay_authorization'] for s in state['steps']})


@pytest.mark.asyncio
async def test_message_only_signer_no_buyer_rpc_nonce_or_gas(sponsored, tmp_path):
    transport, db, seen = sponsored
    class MessagesOnly:
        address = Account.from_key(KEY).address
        def sign_message(self, message):
            return Account.from_key(KEY).sign_message(message)
    result = await call(transport, tmp_path/'sponsored.json', signer=MessagesOnly(), rpc_url=None, gas_mode='required')
    assert result['success'] and len(seen) == 1
    state = json.loads((tmp_path/'sponsored.json').read_text())
    assert state['budget_check']['buyer_gas_usd'] == '0'
    assert 'transactions' not in state['request']['input']
    assert 'fees' not in state and 'nonce_start' not in state
    assert result['bill_of_materials']['gas_sponsorship']['enabled']
    payment = json.loads(db._conn.execute('SELECT payment_json FROM pipeline_relay_payments').fetchone()['payment_json'])
    validate_transaction(state['quote']['offers'][0], state['wallet'], payment['raw'], gas_payer=SPONSOR.address)
    with pytest.raises(ValueError):
        validate_transaction(state['quote']['offers'][0], state['wallet'], payment['raw'])
    assert 'relay_authorization' not in json.dumps(result) and payment['raw'] not in json.dumps(result)
    transport.rpc_methods.clear()
    async with httpx.AsyncClient(transport=transport) as client:
        assert await run_pipeline(resume=True, state_path=tmp_path/'sponsored.json', client=client) == result
    assert transport.rpc_methods == []


@pytest.mark.asyncio
async def test_required_refused_before_signing_when_disabled(rig, tmp_path):
    transport, db, seen = rig
    with pytest.raises(PipelineHTTPError) as exc:
        await call(transport, tmp_path/'disabled.json', gas_mode='required')
    assert exc.value.status_code == 409 and not transport.invokes and not seen
    assert not db._conn.execute('SELECT * FROM pipeline_relay_payments').fetchone()


@pytest.mark.asyncio
async def test_free_graph_required_still_needs_no_wallet_or_rpc(rig, tmp_path):
    transport, db, seen = rig
    listing(db, price=0)
    result = await call(transport, tmp_path/'free.json', gas_mode='required', signer=None, rpc_url=None, max_total_usd='0')
    assert result['success'] and len(seen) == 1


@pytest.mark.asyncio
async def test_budget_failure_rolls_back_nonce_then_same_order_can_resume(sponsored):
    transport, db, _ = sponsored
    provider, q, state = await prepare(transport)
    provider.relay.daily_wei = 1
    with pytest.raises(RelayPending, match='daily budget'):
        await provider.relay.payment(state, state['steps'][0])
    assert not db._conn.execute('SELECT * FROM pipeline_relay_nonces').fetchone()
    assert not db._conn.execute('SELECT * FROM pipeline_relay_payments').fetchone()
    provider.relay.daily_wei = 10**18
    payment = await provider.relay.payment(state, state['steps'][0])
    assert payment['nonce'] == 0
    transport.rpc_methods.clear()
    assert await provider.relay.payment(state, state['steps'][0]) == payment
    assert not transport.rpc_methods


@pytest.mark.asyncio
async def test_wrong_buyer_signature_never_allocates_gas(sponsored):
    transport, db, seen = sponsored
    provider, q, state = await prepare(transport)
    state['steps'][0]['relay_authorization'] = '0x' + SPONSOR.sign_message(
        encode_typed_data(full_message=q['offers'][0]['authorization'])).signature.hex()
    with pytest.raises(HTTPException) as exc:
        await provider.invoke(body(q, state), 'test')
    assert exc.value.status_code == 400 and not seen
    assert not db._conn.execute('SELECT * FROM pipeline_relay_payments').fetchone()


@pytest.mark.asyncio
async def test_only_one_nonce_in_flight_and_exact_bytes_rebroadcast(sponsored):
    transport, db, _ = sponsored
    provider, q1, s1 = await prepare(transport)
    _, q2, s2 = await prepare(transport)
    first = await provider.relay.payment(s1, s1['steps'][0])
    with pytest.raises(RelayPending, match='awaiting confirmation'):
        await provider.relay.payment(s2, s2['steps'][0])
    assert transport.sent == [first['raw']]
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n'] == 1
    transport.receipts[first['tx_hash']] = {'status': '0x1'}
    transport.nonce = 1
    second = await provider.relay.payment(s2, s2['steps'][0])
    assert second['nonce'] == 1 and first['tx_hash'] != second['tx_hash']


@pytest.mark.asyncio
async def test_cached_relay_payment_recovers_after_worker_loss_and_expiry(sponsored, monkeypatch):
    transport, db, seen = sponsored
    provider, q, state = await prepare(transport)
    real = provider.relay.payment
    committed = []
    async def crash(state, step):
        committed.append(await real(state, step))
        raise asyncio.CancelledError()
    monkeypatch.setattr(provider.relay, 'payment', crash)
    with pytest.raises(asyncio.CancelledError):
        await provider.invoke(body(q, state), 'test')
    assert committed and not seen
    row = provider._row(q['run_id'])
    db._conn.execute('UPDATE studio_pipeline_invocations SET updated_at = ? WHERE run_id = ?',
                     (time.time()-500, q['run_id']))
    db._conn.commit()
    # Advance wall clock beyond expiry; don't alter the signed invoice/typed data.
    now = state['expires_at'] + 1000
    monkeypatch.setattr(time, 'time', lambda: now)
    monkeypatch.setattr(provider.relay, 'payment', real)
    replay = await provider.invoke(body(q, state), 'test')
    assert replay['success'] and len(seen) == 1
    assert replay['bill_of_materials']['steps'][0]['tx_hash'] == committed[0]['tx_hash']
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n'] == 1


@pytest.mark.asyncio
async def test_mode_and_authorizations_immutable_on_replay(sponsored):
    transport, _, _ = sponsored
    provider, q, state = await prepare(transport)
    request = body(q, state)
    result = await provider.invoke(request, 'test')
    assert result['success']
    with pytest.raises(HTTPException) as exc:
        await provider.invoke(PipelineInput(run_id=q['run_id'], access_token=q['access_token'], transactions={}), 'test')
    assert exc.value.status_code == 400
    request.authorizations['read'] = '0x' + '00'*65
    with pytest.raises(HTTPException) as exc:
        await provider.invoke(request, 'test')
    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('same_order', [False, True])
async def test_workers_with_separate_db_connections_cannot_allocate_same_nonce(sponsored, same_order):
    from aimarket_hub.db_backend import SQLiteBackend
    transport, db, _ = sponsored
    provider, _, first = await prepare(transport)
    _, _, second = await prepare(transport)
    if same_order:
        second = deepcopy(first)
    other_db = SQLiteBackend(db.db_path)
    other = PipelineRelay(other_db, signer=SPONSOR, rpc_url='https://rpc.test')
    gate, arrivals = asyncio.Event(), []
    original = transport.handle_async_request
    async def rendezvous(request):
        if request.url.host == 'rpc.test' and json.loads(request.content)['method'] == 'eth_estimateGas':
            arrivals.append(1)
            if len(arrivals) == 2:
                gate.set()
            await gate.wait()
        return await original(request)
    transport.handle_async_request = rendezvous
    other.client_factory = lambda: httpx.AsyncClient(transport=transport)
    try:
        results = await asyncio.gather(provider.relay.payment(first, first['steps'][0]),
                                       other.payment(second, second['steps'][0]), return_exceptions=True)
        if same_order:
            assert results[0] == results[1] and isinstance(results[0], dict)
        else:
            assert sum(isinstance(r, RelayPending) for r in results) == 1
            assert sum(isinstance(r, dict) for r in results) == 1
        assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n'] == 1
        assert db._conn.execute('SELECT next_nonce FROM pipeline_relay_nonces').fetchone()['next_nonce'] == 1
    finally:
        other_db.close()


@pytest.mark.asyncio
async def test_splitter_refused_at_preflight_with_required_sponsor(sponsored, monkeypatch):
    transport, _, seen = sponsored
    monkeypatch.setenv('AIMARKET_MARKET_FEE_BPS', '100')
    monkeypatch.setenv('AIMARKET_MARKET_SPLITTER', '0x' + 'ab' * 20)
    provider, q, state = await prepare(transport)
    # The current settlement policy may not produce split terms without a deployed
    # splitter registry. Explicitly exercise capability eligibility for those terms.
    state['steps'][0]['terms']['fee_units'] = 1
    assert provider.relay.describe(state['steps'])['reason'] == 'gas_sponsor_requires_direct_base_usdc'
    assert not seen


@pytest.mark.asyncio
async def test_sponsorship_is_not_offered_once_todays_budget_cannot_cover_the_plan(sponsored):
    """describe() offered sponsorship whatever was left of the day's budget, so gas_mode="auto"
    picked it and the order could only stall; it now says exhausted and auto uses buyer gas."""
    transport, db, _ = sponsored
    provider, q, state = await prepare(transport)
    step = state['steps'][0]
    assert provider.relay.describe([step])['enabled']
    provider.relay.daily_wei = provider.relay.DEFAULT_FEE_BOUND_WEI - 1
    assert provider.relay.describe([step])['reason'] == 'gas_sponsor_daily_budget_exhausted'


@pytest.mark.asyncio
async def test_an_expired_authorization_ends_even_when_sponsorship_is_off(sponsored, monkeypatch):
    transport, db, _ = sponsored
    provider, q, state = await prepare(transport)
    step = state['steps'][0]
    provider.relay.daily_wei = 1
    import aimarket_hub.pipeline_relay as relay_module
    later = step['invoice']['expires_at'] + 60
    monkeypatch.setattr(relay_module.time, 'time', lambda: later)
    with pytest.raises(ValueError, match='expired'):
        await provider.relay.payment(state, step)
