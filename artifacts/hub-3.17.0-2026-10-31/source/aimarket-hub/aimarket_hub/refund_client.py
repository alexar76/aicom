"""Prepare or resume a seller-approved cash refund without sharing either wallet key."""
from __future__ import annotations
import asyncio
import json
import math
import time
from pathlib import Path
from urllib.parse import quote as urlquote
import httpx

from aimarket_hub.pipeline_client import _save, _http_ok
from aimarket_hub.pipeline_lock import FileLock
from aimarket_hub.pipeline_payments import authorization_data, validate_authorization
from aimarket_hub.pipeline_verification import verify_document, verify_result


class RefundPending(RuntimeError):
    def __init__(self, state_path, step_id, result):
        self.state_path,self.step_id,self.result=str(state_path),step_id,result
        super().__init__('Refund pending; repeat refund_pipeline with the same state_path and step_id')


def verify_refund(answer, state, step_id):
    key,pq=state['trusted_hub_key'],state.get('trusted_hub_pq_key')
    verify_document(answer,key,pq)
    offer=answer['offer'];verify_document(offer,key,pq)
    original=next(s for s in state['result']['bill_of_materials']['steps'] if s['id']==step_id)
    t=original['terms']
    if (offer['run_id']!=state['quote']['run_id'] or offer['step_id']!=step_id
            or offer['original_tx_hash']!=original['tx_hash'] or offer['buyer_wallet'].lower()!=state['wallet'].lower()
            or offer['wallet'].lower()!=t['pay_to'].lower() or int(offer['terms']['amount_units'])!=int(t['amount_units'])
            or any(offer['terms'][k]!=t[k] for k in ('chain_id','token_contract','decimals','eip712_name','eip712_version'))
            or int(t['fee_units'])!=0 or int(offer['terms']['fee_units'])!=0
            or offer['terms']['pay_to'].lower()!=state['wallet'].lower()
            or offer['terms']['offer_to'].lower()!=state['wallet'].lower()
            or offer['authorization']!=authorization_data(offer,offer['wallet'])
            or not offer['gas_sponsorship']['enabled'] or offer['gas_sponsorship']['buyer_fee_units']!='0'):
        raise ValueError('refund differs from the original paid order')
    if answer['refund_id']!=offer['refund_id'] or answer['run_id']!=offer['run_id'] or answer['step_id']!=step_id:
        raise ValueError('refund response identity mismatch')
    if answer['status']=='refunded':
        note=answer['credit_note'];verify_document(note,key,pq)
        expected={'kind':'pipeline.refund/1','refund_id':offer['refund_id'],'run_id':offer['run_id'],
                  'step_id':step_id,'original_tx_hash':offer['original_tx_hash'],'refund_tx_hash':answer['tx_hash'],
                  'from':offer['wallet'],'to':offer['buyer_wallet'],'amount_units':str(t['amount_units']),
                  'chain_id':t['chain_id'],'token_contract':t['token_contract'],'buyer_gas_fee_units':'0'}
        if any(note.get(k)!=v for k,v in expected.items()):
            raise ValueError('refund credit note differs from the approved transfer')
    return offer


async def refund_pipeline(*, state_path, step_id, seller_signer=None, authorization=None,
                          wait=True, timeout_s=180, poll_interval_s=2, client=None):
    """No signer/signature: return the seller approval offer without moving money.

    With seller authorization: persist the exact signature before submitting,
    sponsor gas, and recover the same refund. The original bill stays unchanged.
    """
    if not math.isfinite(timeout_s) or not math.isfinite(poll_interval_s) or timeout_s<=0 or poll_interval_s<=0:
        raise ValueError('positive timeout and polling interval required')
    path=Path(state_path).absolute();lock=FileLock(str(path)+'.lock')
    owned=client is None
    client=client or httpx.AsyncClient(timeout=120)
    try:
        if path.is_symlink():raise ValueError('recovery file cannot be a symlink')
        state=json.loads(path.read_text());verify_result(state['result'],state)
        if state['result']['status'] not in ('completed','failed'):
            raise ValueError('reconcile the pipeline before requesting a refund')
        saved=state.setdefault('refunds',{}).setdefault(step_id,{})
        if saved.get('result',{}).get('status')=='refunded':
            verify_refund(saved['result'],state,step_id)
            return saved['result']
        base=state['hub']+'/studio/paid-runs/'+state['quote']['run_id']+'/refunds/'+urlquote(step_id,safe='')
        headers={'X-Studio-Run-Token':state['quote']['access_token']}
        expired = saved.get('result') and time.time() > saved['result']['offer']['invoice']['expires_at'] + 30
        if not saved.get('result') or expired:
            response=await client.post(base+'/prepare',headers=headers)
            _http_ok(response,path);answer=response.json();verify_refund(answer,state,step_id)
            if expired and answer['status']=='awaiting_seller_approval':
                old_offer=saved['result']['offer']
                if any(answer['offer'][k]!=old_offer[k] for k in ('refund_id','original_tx_hash','wallet','buyer_wallet','terms')) or answer['offer']['invoice']['nonce']!=old_offer['invoice']['nonce']:
                    raise ValueError('refresh must preserve the original refund and nonce')
                saved.pop('authorization',None);saved.pop('submitted',None)
            saved['result']=answer;_save(path,state)
        offer=verify_refund(saved['result'],state,step_id)
        if seller_signer is not None and authorization is not None:
            raise ValueError('provide seller_signer or authorization, not both')
        if seller_signer is not None:
            from eth_account.messages import encode_typed_data
            if seller_signer.address.lower()!=offer['wallet'].lower():
                raise ValueError('refund requires the original seller signer')
            authorization='0x'+seller_signer.sign_message(encode_typed_data(full_message=offer['authorization'])).signature.hex().removeprefix('0x')
        if authorization is not None:
            validate_authorization(offer,offer['wallet'],authorization)
            if saved.get('authorization') and saved['authorization']!=authorization.lower():
                raise ValueError('saved refund authorization cannot change')
            saved['authorization']=authorization.lower();_save(path,state)
        if not saved.get('authorization'):
            return saved['result']
        deadline=time.monotonic()+timeout_s
        read_first=bool(saved.get('submitted'))
        while True:
            try:
                if read_first:
                    response=await client.get(base,headers=headers)
                else:
                    saved['submitted']=True;_save(path,state)
                    response=await client.post(base,headers=headers,json={'authorization':saved['authorization']})
                if response.status_code==429 or response.status_code>=500:
                    raise httpx.TransportError('temporary refund response failure')
                _http_ok(response,path);answer=response.json();verify_refund(answer,state,step_id)
                saved['result']=answer;_save(path,state)
                if answer['status']=='refunded':return answer
                read_first=bool(answer.get('busy'))
            except httpx.TransportError:
                read_first=True
            if not wait:return saved['result']
            left=deadline-time.monotonic()
            if left<=0:raise RefundPending(path,step_id,saved['result'])
            await asyncio.sleep(min(left,poll_interval_s))
    finally:
        if owned:await client.aclose()
        lock.close()


def sign_refund_offer(offer, *, seller_signer, buyer_wallet, original_tx_hash,
                      max_usdc, trusted_hub_key, trusted_hub_pq_key=None):
    """Seller-side approval: needs only the signed offer, never buyer recovery tokens.

    The seller supplies the approved buyer, original payment hash and refund cap.
    This helper validates those bindings; its caller decides whether a refund is owed.
    """
    from decimal import Decimal
    from eth_account.messages import encode_typed_data
    from aimarket_hub.pipeline_client import BASE_USDC, _positive
    verify_document(offer,trusted_hub_key,trusted_hub_pq_key)
    t=offer['terms'];amount=Decimal(t['amount_units'])/10**6
    if (offer.get('protocol')!='SELLER-REFUND/1' or offer['wallet'].lower()!=seller_signer.address.lower()
            or offer['buyer_wallet'].lower()!=buyer_wallet.lower() or t['pay_to'].lower()!=buyer_wallet.lower()
            or t['offer_to'].lower()!=buyer_wallet.lower() or offer['original_tx_hash'].lower()!=original_tx_hash.lower()
            or t['chain_id']!=8453 or t['token_contract'].lower()!=BASE_USDC or t['decimals']!=6
            or t['eip712_name']!='USD Coin' or t['eip712_version']!='2' or int(t['fee_units'])!=0
            or amount<=0 or amount>_positive(max_usdc,'max_usdc')
            or offer['authorization']!=authorization_data(offer,offer['wallet'])
            or time.time()+30>=offer['invoice']['expires_at']):
        raise ValueError('refund offer differs from seller approval')
    signature='0x'+seller_signer.sign_message(encode_typed_data(full_message=offer['authorization'])).signature.hex().removeprefix('0x')
    validate_authorization(offer,offer['wallet'],signature)
    return signature
