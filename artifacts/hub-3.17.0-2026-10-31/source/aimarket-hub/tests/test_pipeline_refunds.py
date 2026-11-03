import json
from copy import deepcopy
import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi import HTTPException

from aimarket_hub import settle
from aimarket_hub.refund_client import refund_pipeline
from aimarket_hub.pipeline_refunds import RefundApproval
from tests.test_pipeline_relay import sponsored, SPONSOR
from tests.test_pipeline_client import rig, KEY, call
from tests.test_studio_paid import setup, listing


async def bought(sponsored, tmp_path):
    transport,db,seen=sponsored
    listing(db,payout=SPONSOR.address)
    path=tmp_path/'buyer.json'
    result=await call(transport,path,gas_mode='required',rpc_url=None)
    tx=result['bill_of_materials']['steps'][0]['tx_hash']
    transport.receipts[tx]={'status':'0x1'};transport.nonce=1
    return transport,db,seen,path,result


def refund_verified(monkeypatch):
    def verify(**kw):
        t=kw['terms']
        return {'tx_hash':kw['tx_hash'],'paid_units':t.amount_units,'fee_units':0,
                'authorizer':SPONSOR.address.lower(),'nonce':kw['require_nonce'],'pay_to':t.pay_to}
    monkeypatch.setattr(settle,'verify_transfer',verify)


@pytest.mark.asyncio
async def test_refund_requires_seller_and_returns_cash_credit_note_once(sponsored,tmp_path,monkeypatch):
    transport,db,seen,path,original=await bought(sponsored,tmp_path)
    async with httpx.AsyncClient(transport=transport) as client:
        offer=await refund_pipeline(state_path=path,step_id='read',client=client)
        assert offer['status']=='awaiting_seller_approval'
        assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==1
        with pytest.raises(ValueError,match='original seller'):
            await refund_pipeline(state_path=path,step_id='read',seller_signer=Account.from_key(KEY),client=client)
        refund_verified(monkeypatch)
        done=await refund_pipeline(state_path=path,step_id='read',seller_signer=SPONSOR,client=client,poll_interval_s=.001)
        assert done['status']=='refunded'
        note=done['credit_note']
        assert note['from']==SPONSOR.address.lower() and note['to']==Account.from_key(KEY).address.lower()
        assert note['amount_units']=='4000' and note['buyer_gas_fee_units']=='0'
        assert await refund_pipeline(state_path=path,step_id='read',client=client)==done
        assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==2
        state=json.loads(path.read_text())
        assert state['result']==original and len(seen)==1
        manager=transport.asgi.app.state.pipeline_refunds
        assert manager.status(state['quote']['run_id'],state['quote']['access_token'],'read')==done
        with pytest.raises(HTTPException) as exc:
            manager.status(state['quote']['run_id'],'wrong-token','read')
        assert exc.value.status_code==404


@pytest.mark.asyncio
async def test_amount_or_destination_tampering_refused_before_refund_gas(sponsored,tmp_path):
    transport,db,_,path,_=await bought(sponsored,tmp_path)
    s=json.loads(path.read_text());manager=transport.asgi.app.state.pipeline_refunds
    args=(s['quote']['run_id'],s['quote']['access_token'],'read')
    q=manager.prepare(*args)
    typed=deepcopy(q['offer']['authorization']);typed['message']['value']='9999999'
    sig='0x'+SPONSOR.sign_message(encode_typed_data(full_message=typed)).signature.hex()
    with pytest.raises(HTTPException) as exc:
        await manager.advance(*args,RefundApproval(authorization=sig))
    assert exc.value.status_code==400
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==1


@pytest.mark.asyncio
async def test_lost_refund_response_resumes_same_signature_and_transaction(sponsored,tmp_path,monkeypatch):
    transport,db,_,path,_=await bought(sponsored,tmp_path)
    refund_verified(monkeypatch)
    original=transport.handle_async_request
    lost=[]
    async def lose(request):
        response=await original(request)
        if request.method=='POST' and request.url.path.endswith('/refunds/read') and not lost:
            await response.aread();lost.append(1)
            raise httpx.ReadTimeout('refund committed but reply lost')
        return response
    transport.handle_async_request=lose
    async with httpx.AsyncClient(transport=transport) as client:
        done=await refund_pipeline(state_path=path,step_id='read',seller_signer=SPONSOR,client=client,poll_interval_s=.001)
    assert done['status']=='refunded' and lost==[1]
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==2
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_refunds').fetchone()['n']==1


@pytest.mark.asyncio
async def test_expired_unbroadcast_refund_refresh_keeps_identity_and_nonce(sponsored,tmp_path,monkeypatch):
    import time
    transport,db,_,path,_=await bought(sponsored,tmp_path)
    state=json.loads(path.read_text());manager=transport.asgi.app.state.pipeline_refunds
    args=(state['quote']['run_id'],state['quote']['access_token'],'read')
    initial=manager.prepare(*args)
    now=initial['offer']['invoice']['expires_at']+40
    monkeypatch.setattr(time,'time',lambda:now)
    refreshed=manager.prepare(*args)
    assert refreshed['refund_id']==initial['refund_id']
    assert refreshed['offer']['invoice']['nonce']==initial['offer']['invoice']['nonce']
    assert refreshed['offer']['invoice']['expires_at']>initial['offer']['invoice']['expires_at']
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_refunds').fetchone()['n']==1


@pytest.mark.asyncio
async def test_committed_refund_bytes_never_replaced_after_expiry(sponsored,tmp_path,monkeypatch):
    import time
    transport,db,_,path,_=await bought(sponsored,tmp_path)
    state=json.loads(path.read_text());manager=transport.asgi.app.state.pipeline_refunds
    args=(state['quote']['run_id'],state['quote']['access_token'],'read')
    initial=manager.prepare(*args)
    sig='0x'+SPONSOR.sign_message(encode_typed_data(full_message=initial['offer']['authorization'])).signature.hex()
    monkeypatch.setattr(settle,'verify_transfer',lambda **k:(_ for _ in ()).throw(settle.PaymentError('pending')))
    pending=await manager.advance(*args,RefundApproval(authorization=sig))
    assert pending['tx_hash']
    now=initial['offer']['invoice']['expires_at']+40
    monkeypatch.setattr(time,'time',lambda:now)
    q=manager.prepare(*args)
    assert q['offer']==initial['offer'] and q['tx_hash']==pending['tx_hash']
    refund_verified(monkeypatch)
    done=await manager.advance(*args,RefundApproval())
    assert done['status']=='refunded' and done['tx_hash']==pending['tx_hash']


@pytest.mark.asyncio
async def test_refund_mcp_uses_same_authorized_ledger(sponsored,tmp_path,monkeypatch):
    transport,db,_,path,_=await bought(sponsored,tmp_path)
    s=json.loads(path.read_text());args={'run_id':s['quote']['run_id'],'access_token':s['quote']['access_token'],'step_id':'read'}
    async with httpx.AsyncClient(transport=transport) as client:
        async def tool(name, arguments):
            r=await client.post('https://hub.test/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}})
            message=json.loads(next(line[6:] for line in r.text.splitlines() if line.startswith('data: ')))['result']
            return message,json.loads(message['content'][0]['text'])
        msg,q=await tool('pipeline_refund_prepare',args)
        assert not msg['isError'] and q['status']=='awaiting_seller_approval'
        sig='0x'+SPONSOR.sign_message(encode_typed_data(full_message=q['offer']['authorization'])).signature.hex()
        refund_verified(monkeypatch)
        msg,done=await tool('pipeline_refund',{**args,'authorization':sig})
        assert not msg['isError'] and done['status']=='refunded'
        msg,status=await tool('pipeline_refund_status',args)
        assert not msg['isError'] and status==done
        assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==2


@pytest.mark.asyncio
async def test_seller_can_approve_without_buyers_private_recovery_file(sponsored,tmp_path):
    from aimarket_hub.refund_client import sign_refund_offer
    transport,_,_,path,original=await bought(sponsored,tmp_path)
    s=json.loads(path.read_text());manager=transport.asgi.app.state.pipeline_refunds
    q=manager.prepare(s['quote']['run_id'],s['quote']['access_token'],'read')['offer']
    args=dict(seller_signer=SPONSOR,buyer_wallet=s['wallet'],original_tx_hash=original['bill_of_materials']['steps'][0]['tx_hash'],
              max_usdc='.004',trusted_hub_key=s['trusted_hub_key'],trusted_hub_pq_key=s.get('trusted_hub_pq_key'))
    signature=sign_refund_offer(q,**args)
    assert len(signature)==132
    with pytest.raises(ValueError,match='seller approval'):
        sign_refund_offer(q,**{**args,'max_usdc':'.003'})
    assert not any(k in q for k in ('access_token','operation_token','private_key'))


@pytest.mark.asyncio
async def test_a_reverted_refund_transfer_is_offered_again_not_pending_forever(sponsored,tmp_path,monkeypatch):
    """A relayed refund that reverted used to stay 'pending' for good: every advance re-verified the
    same cached bytes and prepare() refused to refresh while they were cached."""
    transport,db,_,path,_=await bought(sponsored,tmp_path)
    s=json.loads(path.read_text());manager=transport.asgi.app.state.pipeline_refunds
    args=(s['quote']['run_id'],s['quote']['access_token'],'read')
    def sign(q):
        return '0x'+SPONSOR.sign_message(encode_typed_data(full_message=q['offer']['authorization'])).signature.hex()
    def reverted(**kw):
        transport.receipts[kw['tx_hash']]={'status':'0x0'}
        raise settle.PaymentFinal('transaction reverted')
    monkeypatch.setattr(settle,'verify_transfer',reverted)
    q=manager.prepare(*args)
    out=await manager.advance(*args,RefundApproval(authorization=sign(q)))
    assert out['status']=='awaiting_seller_approval' and 'reverted' in out['detail']
    assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==1  # the purchase only
    transport.nonce=2  # a reverted transaction still consumes the sponsor's account nonce
    refund_verified(monkeypatch)
    q=manager.prepare(*args)
    done=await manager.advance(*args,RefundApproval(authorization=sign(q)))
    assert done['status']=='refunded'
