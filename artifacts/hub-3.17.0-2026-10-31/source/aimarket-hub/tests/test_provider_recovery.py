import hashlib
import json
import time
from copy import deepcopy

import pytest
from eth_account import Account

from aimarket_hub import provider_recovery
from aimarket_hub.seller_operations import QuoteRequest, ExecuteRequest
from aimarket_hub.supply_security import _bound_response_canonical
from tests.test_peer_operations import hubs
from tests.test_studio_paid import setup, listing
from tests.test_pipeline_client import KEY


def document(signer, original_id, payload, result, **changes):
    d={'protocol': 'PROVIDER-OP/1', 'operation_id': original_id, 'product_id': 'demo-product',
       'capability_id': 'demo.read@v1', 'input_sha256': hashlib.sha256(provider_recovery.canonical(payload).encode()).hexdigest(),
       'status': 'completed', 'result': result,
       'result_signature': signer.sign_canonical(_bound_response_canonical('demo.read@v1','demo-product',payload,result))}
    d.update(changes)
    return {**d, 'signature': signer.sign_canonical(provider_recovery.canonical(d))}


@pytest.mark.asyncio
async def test_lost_provider_reply_recovers_signed_result_once(hubs, monkeypatch):
    _, seller, _, _, delivered, _ = hubs
    ops=seller.state.seller_operations
    monkeypatch.setenv('AIMARKET_PROVIDER_OPERATION_PRODUCTS','demo-product')
    listing(ops.studio.db, invoke_url='https://provider.test/invoke', provider_pubkey=ops.signer.public_key_b64)
    wallet=Account.from_key(KEY).address.lower()
    q=ops.quote(QuoteRequest(product_id='demo-product',capability_id='demo.read@v1',wallet=wallet,max_price_usd=1))
    assert q['offer']['provider_recovery']=='PROVIDER-OP/1'
    original={}
    async def lost(payload, headers, caller, *, operation_id):
        delivered.append(operation_id)
        original.update(document(ops.signer,operation_id,payload['input'],{'reading':91}))
        return 503, {'error':'response lost after provider saved its result'}
    ops.invoke=lost
    args=(q['offer']['operation_id'],q['operation_token'])
    request=ExecuteRequest(input={'city':'Москва'},wallet=wallet,tx_hash='0x'+'45'*32)
    assert (await ops.execute(*args,request,'buyer'))['status']=='reconciliation_required'
    status_reads=[]
    async def read(spec, operation_id):
        status_reads.append(operation_id)
        return original
    ops.provider_status=read
    recovered=await ops.recover(*args)
    assert recovered['success'] and recovered['result']=={'reading':91}
    assert len(delivered)==1 and status_reads==[args[0]]
    assert await ops.execute(*args,request,'buyer')==recovered
    assert await ops.recover(*args)==recovered
    # A late worker cannot overwrite the first immutable terminal response.
    state,_=ops.load(*args);state['status']='reconciliation_required'
    ops.save(args[0],state)
    assert ops.status(*args)==recovered


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper', ['operation_id','input_sha256','result_signature','signature'])
async def test_untrusted_recovery_never_accepts_another_result(hubs, monkeypatch, tamper):
    _, seller, _, _, delivered, _=hubs
    ops=seller.state.seller_operations
    monkeypatch.setenv('AIMARKET_PROVIDER_OPERATION_PRODUCTS','demo-product')
    listing(ops.studio.db, price=0, invoke_url='https://provider.test/invoke',provider_pubkey=ops.signer.public_key_b64)
    q=ops.quote(QuoteRequest(product_id='demo-product',capability_id='demo.read@v1',max_price_usd=0))
    async def lost(*args, **kwargs):
        delivered.append(1);return 503,{}
    ops.invoke=lost
    args=(q['offer']['operation_id'],q['operation_token'])
    await ops.execute(*args,ExecuteRequest(input={}), 'buyer')
    d=document(ops.signer,args[0],{}, {'reading':99}, **({tamper:'wrong'} if tamper!='signature' else {}))
    if tamper=='signature':d['signature']='invalid'
    async def read(*_):return d
    ops.provider_status=read
    out=await ops.recover(*args)
    assert out['status']=='reconciliation_required' and not out['success'] and delivered==[1]


@pytest.mark.asyncio
async def test_provider_unknown_requires_operator_and_never_redispatches(hubs, monkeypatch):
    _,seller,_,_,delivered,_=hubs;ops=seller.state.seller_operations
    monkeypatch.setenv('AIMARKET_PROVIDER_OPERATION_PRODUCTS','demo-product')
    listing(ops.studio.db, price=0, invoke_url='https://provider.test/invoke',provider_pubkey=ops.signer.public_key_b64)
    q=ops.quote(QuoteRequest(product_id='demo-product',capability_id='demo.read@v1',max_price_usd=0))
    args=(q['offer']['operation_id'],q['operation_token'])
    async def lost(*a,**kw):delivered.append(1);return 503,{}
    ops.invoke=lost
    await ops.execute(*args,ExecuteRequest(input={}), 'buyer')
    async def read(*_):return document(ops.signer,args[0],{}, {},status='reconciliation_required')
    ops.provider_status=read
    out=await ops.recover(*args)
    assert out['recovery']['action']=='contact_operator'
    assert (await ops.execute(*args,ExecuteRequest(input={}), 'buyer'))['recovery']['action']=='contact_operator'
    assert delivered==[1]


@pytest.mark.asyncio
async def test_pipeline_recovers_provider_failure_across_two_hubs_without_new_payment(hubs, monkeypatch, tmp_path):
    from tests.test_peer_operations import buy
    _, seller, _, _, delivered, broadcasts=hubs
    ops=seller.state.seller_operations
    monkeypatch.setenv('AIMARKET_PROVIDER_OPERATION_PRODUCTS','demo-product')
    listing(ops.studio.db, invoke_url='https://provider.test/invoke',provider_pubkey=ops.signer.public_key_b64)
    saved={}
    async def lost(payload, headers, caller, *, operation_id):
        delivered.append(operation_id)
        saved[operation_id]=document(ops.signer,operation_id,payload['input'],{'recovered':True})
        return 503, {'error':'provider reply lost'}
    async def read(spec,operation_id):return saved[operation_id]
    ops.invoke, ops.provider_status=lost,read
    result=await buy(hubs,tmp_path/'state.json')
    assert result['success'] and result['final_result']=={'recovered':True}
    assert len(delivered)==1 and len(set(broadcasts))==1
    assert result['bill_of_materials']['total_usd']==.004
    assert 'grant_secret' not in json.dumps(result)
