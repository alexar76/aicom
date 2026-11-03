"""Two separately keyed hubs, seller-owned invoices and durable remote results."""
import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
import pytest
from eth_account import Account

from aimarket_hub import settle
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.seller_operations import SellerOperations
from aimarket_hub.signing import Signer
from tests.test_studio_paid import setup, listing, node
from tests.test_pipeline_client import Transport, KEY
from aimarket_hub.pipeline_client import run_pipeline

SELLER_URL = 'https://seller.test'


@pytest.fixture
def hubs(setup, tmp_path, monkeypatch):
    buyer, buyer_db, seen = setup
    buyer.config.hub_url = 'https://buyer.test'
    app = create_app(config=buyer.config, db=buyer_db, signer=buyer.signer)
    buyer_studio = app.state.pipeline_provider.studio
    buyer_studio.route_ok = lambda cap: True
    buyer_studio.invoke = buyer.invoke
    config = HubConfig()
    config.hub_url = SELLER_URL
    config.db_path = str(tmp_path/'seller.db')
    config.signing_key_path = str(tmp_path/'seller-key')
    seller_db = HubDatabase(config.db_path)
    seller_signer = Signer(config.signing_key_path)
    listing(seller_db)
    seller = create_app(config=config, db=seller_db, signer=seller_signer)
    seller.state.pipeline_provider.studio.route_ok = lambda cap: True
    delivered, requests, broadcasts = [], [], []
    async def deliver(payload, headers, caller, *, operation_id):
        delivered.append((payload, headers, operation_id))
        return 200, {'success': True, 'result': {'remote_reading': 42}, 'receipt': {'work': operation_id}}
    seller.state.seller_operations.invoke = deliver
    async def request(method, url, *, body=None, token=None):
        assert urlsplit(url).netloc == 'seller.test'
        requests.append((method, urlsplit(url).path))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=seller), base_url=SELLER_URL) as c:
            r = await c.request(method, url, json=body, headers={'X-Operation-Token': token} if token else {})
            r.raise_for_status()
            return r.json()
    buyer_studio.remote.request = request
    buyer_db.upsert_peer(Peer(url=SELLER_URL, name='Independent seller', trusted=True, trust_score=1,
        public_key=seller_signer.public_key_b64, pq_public_key=seller_signer.pq_public_key_b64,
        last_crawl=datetime.now(timezone.utc).isoformat()))
    listing(buyer_db, source=SELLER_URL)
    assert not buyer.config.sells_on_behalf_of(SELLER_URL) and not buyer.config.peer_api_key(SELLER_URL)
    async def broadcast(raw, tx_hash):
        broadcasts.append(tx_hash)
    app.state.pipeline_provider.broadcaster = broadcast
    def verify(**kw):
        t = kw['terms']
        return {'tx_hash': kw['tx_hash'], 'paid_units': t.seller_units, 'fee_units': t.fee_units,
                'authorizer': Account.from_key(KEY).address.lower(), 'nonce': kw['require_nonce'], 'pay_to': t.pay_to}
    monkeypatch.setattr(settle, 'verify_transfer', verify)
    monkeypatch.setenv('AIMARKET_WALLET_STATE_DIR', str(tmp_path/'wallets'))
    return app, seller, Transport(app), requests, delivered, broadcasts


async def buy(hubs, path, nodes=None):
    _, _, transport, _, _, _ = hubs
    remote = node();remote['source_hub'] = SELLER_URL
    async with httpx.AsyncClient(transport=transport) as c:
        return await run_pipeline({'nodes': nodes or [remote]}, hub='https://buyer.test',
            signer=Account.from_key(KEY), max_total_usd='1', native_usd_ceiling='6000',
            rpc_url='https://rpc.test', state_path=path, client=c, poll_interval_s=.001, timeout_s=1)


@pytest.mark.asyncio
async def test_independent_seller_owns_invoice_payment_and_receipt(hubs, tmp_path):
    buyer, seller, _, requests, delivered, broadcasts = hubs
    result = await buy(hubs, tmp_path/'order')
    assert result['success'] and result['final_result'] == {'remote_reading': 42}
    assert len(delivered) == 1 and len(set(broadcasts)) == 1
    bill = result['bill_of_materials']
    step = bill['steps'][0]
    assert step['payment_rail'] == 'independent_seller' and step['source_hub'] == SELLER_URL
    offer = step['seller_operation']
    nonce = offer['invoice']['nonce']
    assert seller.state.seller_operations.studio.invoices.get(nonce)
    assert buyer.state.pipeline_provider.studio.invoices.get(nonce) is None
    assert offer['operation_id'] == delivered[0][2]
    assert bill['total_usd'] == .004 and len(result['subcontracting']['nodes']) == 2
    assert len(result['receipt']['parents']) == 1
    assert all(n['funded_by'] == 'own' for n in result['subcontracting']['nodes'])
    assert 'operation_token' not in json.dumps(result)
    assert 'X-AIMarket-Job' not in delivered[0][1]
    assert [m for m,p in requests if p.endswith('/invoke')] == ['POST']


@pytest.mark.asyncio
async def test_lost_seller_response_recovers_by_get_without_redispatch(hubs, tmp_path):
    buyer, seller, _, requests, delivered, _ = hubs
    original = buyer.state.pipeline_provider.studio.remote.request
    lost = False
    async def flaky(method, url, **kw):
        nonlocal lost
        result = await original(method, url, **kw)
        if url.endswith('/invoke') and not lost:
            lost = True
            # Simulate reopening the operation store after a seller process restart.
            old = seller.state.seller_operations
            reopened = SellerOperations(old.studio, old.invoke)
            state = json.loads((tmp_path/'order').read_text())
            offer = state['quote']['offers'][0]['seller_operation']
            assert reopened.conn.execute('SELECT response_json FROM seller_operations WHERE operation_id = ?',
                (offer['operation_id'],)).fetchone()['response_json']
            raise httpx.ReadTimeout('lost seller response')
        return result
    buyer.state.pipeline_provider.studio.remote.request = flaky
    result = await buy(hubs, tmp_path/'order')
    assert result['success'] and len(delivered) == 1
    assert len([p for m,p in requests if p.endswith('/invoke')]) == 1
    assert len(result['subcontracting']['nodes']) == 2


@pytest.mark.asyncio
async def test_remote_input_from_previous_step_is_resolved_before_payment(hubs, tmp_path):
    buyer, seller, _, _, delivered, _ = hubs
    local_db = buyer.state.pipeline_provider.studio.db
    listing(local_db, cid='seed.read@v1', price=0)
    schema = {'type': 'object', 'properties': {'number': {'type': 'integer'}}, 'required': ['number']}
    listing(seller.state.seller_operations.studio.db, input_schema=schema)
    listing(local_db, source=SELLER_URL, input_schema=schema)
    first = node('seed', 'seed.read@v1')
    remote = node('read', depends_on=['seed']);remote.update(source_hub=SELLER_URL, input={'number': '${seed.reading}'})
    result = await buy(hubs, tmp_path/'graph', [first, remote])
    assert result['success'] and delivered[0][0]['input'] == {'number': 7}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['signature', 'price', 'payee', 'protocol'])
async def test_untrusted_or_incompatible_offers_refuse_before_signing(hubs, tmp_path, change):
    buyer, seller, transport, _, delivered, broadcasts = hubs
    adapter = buyer.state.pipeline_provider.studio.remote
    original = adapter.request
    async def changed(method, url, **kw):
        result = await original(method, url, **kw)
        if url.endswith('/prepare'):
            if change == 'signature':
                result['offer']['signature']['value'] = 'invalid'
            else:
                offer = result['offer']
                if change == 'price': offer['terms']['amount_units'] += 1
                if change == 'payee': offer['terms']['pay_to'] = '0x' + 'aa'*20
                if change == 'protocol': offer['protocol'] = 'unknown'
                offer['signature'] = seller.state.seller_operations.signer.sign_object(offer)
        return result
    adapter.request = changed
    with pytest.raises(ValueError, match='Graph refused'):
        await buy(hubs, tmp_path/'rejected')
    assert not delivered and not broadcasts and not transport.invokes


@pytest.mark.asyncio
async def test_seller_binds_input_and_payment_and_authenticates_status(hubs):
    _, seller, _, _, delivered, _ = hubs
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=seller), base_url=SELLER_URL) as c:
        q=(await c.post('/ai-market/v2/operations/prepare',json={'product_id':'demo-product',
           'capability_id':'demo.read@v1','wallet':Account.from_key(KEY).address,'max_price_usd':1})).json()
        url='/ai-market/v2/operations/'+q['offer']['operation_id']
        assert (await c.get(url)).status_code == 404
        headers={'X-Operation-Token':q['operation_token']}
        body={'input':{},'wallet':Account.from_key(KEY).address,'tx_hash':'0x'+'ab'*32}
        result=(await c.post(url+'/invoke',json=body,headers=headers)).json()
        assert result['success']
        assert (await c.post(url+'/invoke',json=body,headers=headers)).json() == result
        assert (await c.get(url,headers=headers)).json() == result
        for modified in ({**body,'input':{'changed':True}}, {**body,'tx_hash':'0x'+'cd'*32},
                         {**body,'wallet':'0x'+'ab'*20}):
            assert (await c.post(url+'/invoke',json=modified,headers=headers)).status_code == 409
        assert len(delivered)==1


@pytest.mark.asyncio
async def test_stale_buyer_worker_recovers_remote_result_and_is_fenced(hubs, tmp_path):
    from aimarket_hub.pipeline_provider import PipelineInput
    from aimarket_hub.pipeline_leases import LeaseLost
    buyer, seller, _, _, delivered, broadcasts = hubs
    provider = buyer.state.pipeline_provider
    original = provider.studio.remote.request
    arrived, release = asyncio.Event(), asyncio.Event()
    async def stalled(method, url, **kw):
        result = await original(method, url, **kw)
        if url.endswith('/invoke'):
            arrived.set()
            await release.wait()
        return result
    provider.studio.remote.request = stalled
    task = asyncio.create_task(buy(hubs, tmp_path/'stale'))
    await asyncio.wait_for(arrived.wait(), 10)
    persisted = json.loads((tmp_path/'stale').read_text())
    q = persisted['quote']
    provider.conn.execute('UPDATE studio_pipeline_invocations SET updated_at = 0 WHERE run_id = ?', (q['run_id'],))
    provider.conn.commit()
    status = provider.status(q['run_id'], q['access_token'])
    assert not status['busy'] and status['recovery']['action'] == 'resume_same_run'
    result = await provider.invoke(PipelineInput(**persisted['request']['input']), 'restarted-buyer')
    assert result['success'] and len(delivered) == 1 and len(set(broadcasts)) == 1
    release.set()
    with pytest.raises(LeaseLost):
        await task
    assert provider.status(q['run_id'], q['access_token']) == result
    assert len(result['subcontracting']['nodes']) == 2


@pytest.mark.asyncio
async def test_seller_concurrent_invoke_dispatches_once_and_unknown_is_not_retried(hubs):
    _, seller, _, _, delivered, _ = hubs
    from aimarket_hub.seller_operations import QuoteRequest, ExecuteRequest
    ops = seller.state.seller_operations
    listing(ops.studio.db, price=0)
    quote = ops.quote(QuoteRequest(product_id='demo-product',capability_id='demo.read@v1',max_price_usd=0))
    args=(quote['offer']['operation_id'],quote['operation_token'],ExecuteRequest(input={}), 'buyer')
    arrived, release = asyncio.Event(), asyncio.Event()
    async def uncertain(*a, **kw):
        delivered.append(kw['operation_id'])
        arrived.set()
        await release.wait()
        return 503, {'error':'lost provider reply'}
    ops.invoke = uncertain
    task = asyncio.create_task(ops.execute(*args))
    await arrived.wait()
    assert (await ops.execute(*args))['busy']
    release.set()
    result = await task
    assert result['status'] == 'reconciliation_required'
    assert (await ops.execute(*args))['recovery']['action'] == 'contact_operator'
    assert len(delivered) == 1


@pytest.mark.asyncio
async def test_input_from_context_works_for_independent_seller(hubs, tmp_path):
    buyer, seller, _, _, delivered, _ = hubs
    db = buyer.state.pipeline_provider.studio.db
    listing(db, cid='seed.read@v1', price=0)
    schema = {'type':'object','required':['context'],'properties':{'context':{'type':'object'}}}
    listing(db, source=SELLER_URL, input_schema=schema)
    listing(seller.state.seller_operations.studio.db, input_schema=schema)
    remote=node('read', depends_on=['seed'], input_from='seed');remote['source_hub']=SELLER_URL
    result=await buy(hubs,tmp_path/'context',[node('seed','seed.read@v1'),remote])
    assert result['success'] and delivered[0][0]['input']=={'context':{'reading':7}}


@pytest.mark.asyncio
async def test_sdk_resumes_cancelled_buyer_after_lease_expiry(hubs, tmp_path):
    buyer, _, transport, _, delivered, _ = hubs
    provider=buyer.state.pipeline_provider
    original=provider.studio.remote.request
    arrived=asyncio.Event()
    async def cancelled_response(method, url, **kw):
        result=await original(method,url,**kw)
        if url.endswith('/invoke'):
            arrived.set()
            await asyncio.Event().wait()
        return result
    provider.studio.remote.request=cancelled_response
    path=tmp_path/'cancelled'
    task=asyncio.create_task(buy(hubs,path))
    await asyncio.wait_for(arrived.wait(),10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    saved=json.loads(path.read_text())
    q=saved['quote']
    provider.conn.execute('UPDATE studio_pipeline_invocations SET updated_at = 0 WHERE run_id = ?', (q['run_id'],))
    provider.conn.commit()
    assert provider.status(q['run_id'],q['access_token'])['recovery']['action']=='resume_same_run'
    async with httpx.AsyncClient(transport=transport) as c:
        result=await run_pipeline(resume=True,state_path=path,client=c,poll_interval_s=.001,timeout_s=1)
    assert result['success'] and len(delivered)==1


@pytest.mark.asyncio
async def test_unknown_seller_outcome_stops_sdk_without_repurchase(hubs, tmp_path):
    from aimarket_hub.pipeline_client import PipelinePending
    _, seller, _, _, delivered, _ = hubs
    async def unknown(*args, **kw):
        delivered.append(kw['operation_id'])
        return 503, {'error':'unknown delivery'}
    seller.state.seller_operations.invoke=unknown
    path=tmp_path/'unknown'
    with pytest.raises(PipelinePending):
        await buy(hubs,path)
    state=json.loads(path.read_text())
    assert state['result']['status']=='reconciliation_required'
    assert len(delivered)==1


@pytest.mark.asyncio
async def test_seller_without_payment_route_returns_preflight_blocker(hubs, monkeypatch):
    _, seller, _, _, delivered, _=hubs
    monkeypatch.setattr(settle,'terms_for',lambda *a,**kw:None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=seller),base_url=SELLER_URL) as c:
        r=await c.post('/ai-market/v2/operations/prepare',json={
            'product_id':'demo-product','capability_id':'demo.read@v1','max_price_usd':1})
    assert r.status_code==409
    assert r.json()['detail']['code']=='settlement_route_unsupported'
    assert not delivered
    assert seller.state.seller_operations.conn.execute('SELECT COUNT(*) AS n FROM seller_operations').fetchone()['n']==0
