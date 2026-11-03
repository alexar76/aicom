"""Seller-authorized cash refunds for direct pipeline payments.

The original seller signs locally. The Hub cannot debit a seller unilaterally;
it sponsors gas, enforces the original buyer/amount, and issues a credit note.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import secrets
import time
from decimal import Decimal
from typing import Annotated

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aimarket_hub import pipeline_payments, settle
from aimarket_hub.db_backend import returning_one, atomic
from aimarket_hub.pipeline_relay import RelayPending
from aimarket_hub.studio_paid import _json


class RefundApproval(BaseModel):
    model_config = ConfigDict(extra='forbid')
    authorization: Annotated[str, Field(pattern=r'^0x[0-9a-fA-F]{130}$')] | None = None


class PipelineRefunds:
    def __init__(self, provider):
        self.provider, self.studio, self.conn = provider, provider.studio, provider.conn

    def load(self, run_id, token, step_id):
        self.studio.load(run_id, token)
        row = self.conn.execute('SELECT * FROM pipeline_refunds WHERE run_id = ? AND step_id = ?', (run_id, step_id)).fetchone()
        if not row:
            raise HTTPException(404, 'refund not prepared')
        return json.loads(row['state_json']), row

    def view(self, state, *, busy=False):
        value = {'protocol': 'SELLER-REFUND/1', 'refund_id': state['refund_id'], 'run_id': state['original_run_id'],
                 'step_id': state['step']['node']['id'], 'status': state['status'], 'busy': bool(busy),
                 'offer': state['offer'], 'tx_hash': state.get('tx_hash'), 'detail': state.get('detail', ''),
                 'credit_note': state.get('credit_note'), 'replacement_payment_allowed': False}
        value['signature'] = self.studio.signer.sign_object(value)
        return value

    def status(self, run_id, token, step_id):
        state, row = self.load(run_id, token, step_id)
        return json.loads(row['response_json']) if row['response_json'] else self.view(state, busy=bool(row['busy'] and time.time()-row['updated_at']<180))

    def prepare(self, run_id, token, step_id):
        run, _ = self.studio.load(run_id, token)
        existing = self.conn.execute('SELECT * FROM pipeline_refunds WHERE run_id = ? AND step_id = ?', (run_id, step_id)).fetchone()
        if existing:
            # An unbroadcast approval may expire while waiting for seller consent
            # or sponsor capacity. Keep the same refund ID and EIP-3009 nonce:
            # even an externally broadcast old approval cannot transfer twice.
            with atomic(self.conn):
                state, row = self.load(run_id, token, step_id)
                step = state['step']
                if (not row['response_json'] and time.time() > step['invoice']['expires_at'] + 30
                        and (not row['busy'] or time.time()-row['updated_at'] > 180)
                        and not (step.get('relay_authorization') and self.provider.relay.cached(state, step))):
                    step['invoice']['expires_at'] = time.time()+900
                    step.pop('relay_authorization', None)
                    state.update(status='awaiting_seller_approval', detail='Previous approval expired before Hub signing; the same refund nonce is retained.')
                    state['offer']['invoice'] = step['invoice']
                    state['offer']['authorization'] = pipeline_payments.authorization_data(step,state['wallet'])
                    state['offer'].pop('signature',None)
                    state['offer']['signature'] = self.studio.signer.sign_object(state['offer'])
                    self.conn.execute("UPDATE pipeline_refunds SET state_json = ?, busy = 0, updated_at = ? WHERE run_id = ? AND step_id = ? AND response_json = ''",
                                      (_json(state),time.time(),run_id,step_id))
            return self.status(run_id, token, step_id)
        if run['status'] not in ('completed', 'failed'):
            raise HTTPException(409, 'reconcile delivery before requesting a refund')
        original = next((s for s in run['steps'] if s['node']['id'] == step_id), None)
        if not original or not original.get('payment') or not original.get('terms'):
            raise HTTPException(409, 'refund requires a verified paid step')
        t, paid = original['terms'], original['payment']
        if not self.provider.relay.describe([original])['enabled']:
            raise HTTPException(409, 'refund gas sponsor requires direct Base USDC')
        if int(t['fee_units']) or int(paid.get('paid_units', 0)) != int(t['amount_units']):
            raise HTTPException(409, 'this refund route requires an exact direct seller payment')
        if str(paid.get('authorizer', '')).lower() != run['wallet'].lower():
            raise HTTPException(409, 'original payment authorizer is not the buyer')
        refund_id = 'refund_' + secrets.token_hex(16)
        terms = {**t, 'pay_to': run['wallet'], 'offer_to': run['wallet'], 'fee_to': '', 'fee_units': 0,
                 'seller_units': int(t['amount_units']), 'amount_units': int(t['amount_units'])}
        step = {'node': {'id': step_id}, 'terms': terms,
                'invoice': {'nonce': '0x'+secrets.token_hex(32), 'expires_at': time.time()+900}}
        wallet = t['pay_to'].lower()
        sponsorship = self.provider.relay.describe([step])
        offer = {'protocol': 'SELLER-REFUND/1', 'refund_id': refund_id, 'run_id': run_id, 'step_id': step_id,
                 'original_tx_hash': original['tx_hash'], 'wallet': wallet, 'buyer_wallet': run['wallet'],
                 'terms': {**terms, **{k:str(terms[k]) for k in ('amount_units','seller_units','fee_units')}},
                 'invoice': step['invoice'], 'authorization': pipeline_payments.authorization_data(step, wallet),
                 'gas_sponsorship': sponsorship, 'seller_approval_required': True}
        offer['signature'] = self.studio.signer.sign_object(offer)
        state = {'run_id': refund_id, 'refund_id': refund_id, 'original_run_id': run_id,
                 'wallet': wallet, 'step': step, 'offer': offer, 'status': 'awaiting_seller_approval'}
        self.conn.execute("INSERT INTO pipeline_refunds (run_id, step_id, original_tx_hash, state_json, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                          (run_id,step_id,original['tx_hash'],_json(state),time.time()))
        self.conn.commit()
        return self.status(run_id, token, step_id)

    def save(self, run_id, step_id, state, *, terminal=False):
        response = self.view(state) if terminal else None
        self.conn.execute("UPDATE pipeline_refunds SET state_json = ?, busy = 0, response_json = ?, updated_at = ? WHERE run_id = ? AND step_id = ? AND response_json = ''",
                          (_json(state),_json(response) if response else '',time.time(),run_id,step_id))
        self.conn.commit()

    async def advance(self, run_id, token, step_id, body):
        state, row = self.load(run_id, token, step_id)
        step = state['step']
        old = step.get('relay_authorization')
        if old and body.authorization and old != body.authorization.lower():
            raise HTTPException(409, 'the refund authorization is immutable')
        if row['response_json']:
            return json.loads(row['response_json'])
        if row['busy'] and time.time()-row['updated_at'] < 180:
            return self.view(state, busy=True)
        if not old:
            if not body.authorization:
                raise HTTPException(400, 'the original seller must sign the refund authorization locally')
            if time.time()+30 >= step['invoice']['expires_at']:
                raise HTTPException(409, 'refund offer expired; no transfer submitted')
            try:
                pipeline_payments.validate_authorization(step,state['wallet'],body.authorization)
            except ValueError as exc:
                raise HTTPException(400,str(exc)) from exc
            step['relay_authorization'] = body.authorization.lower()
        state['status'] = 'pending'
        if not returning_one(self.conn,"UPDATE pipeline_refunds SET busy = 1, state_json = ?, updated_at = ? WHERE run_id = ? AND step_id = ? AND state_json = ? AND updated_at = ? AND response_json = '' RETURNING run_id",
                             (_json(state),time.time(),run_id,step_id,row['state_json'],row['updated_at']),commit=True):
            return self.status(run_id,token,step_id)
        try:
            payment = await self.provider.relay.payment(state,step)
            state['tx_hash'] = payment['tx_hash']
            # Relay DB already committed the bytes before this broadcast.
            try:
                await self.provider.broadcaster(payment['raw'],payment['tx_hash'])
            except Exception:
                pass
            verified = await asyncio.to_thread(settle.verify_transfer,tx_hash=payment['tx_hash'],
                terms=settle.PaymentTerms(**step['terms']),require_nonce=step['invoice']['nonce'])
            if str(verified.get('authorizer','')).lower()!=state['wallet'] or int(verified['paid_units'])!=int(step['terms']['amount_units']):
                raise ValueError('refund transfer does not match the seller authorization')
            note = {'kind':'pipeline.refund/1','refund_id':state['refund_id'],'run_id':run_id,'step_id':step_id,
                    'original_tx_hash':state['offer']['original_tx_hash'],'refund_tx_hash':payment['tx_hash'],
                    'from':state['wallet'],'to':step['terms']['pay_to'],'chain_id':step['terms']['chain_id'],
                    'token_contract':step['terms']['token_contract'],'amount_units':str(step['terms']['amount_units']),
                    'amount_usdc':str(Decimal(step['terms']['amount_units'])/10**6),
                    'gas_payer':payment['gas_payer'],'buyer_gas_fee_units':'0'}
            note['signature'] = self.studio.signer.sign_object(note)
            state.update(status='refunded',credit_note=note,detail='')
            self.save(run_id,step_id,state,terminal=True)
        except settle.PaymentFinal as exc:
            # A relayed refund that REVERTED moved nothing and left its nonce unused. Free the cached
            # bytes and ask the seller to approve again; the same refund nonce is kept, so whatever
            # is broadcast later, the refund can still transfer only once.
            if await self.provider.relay.forget_reverted(state, step):
                step.pop('relay_authorization', None)
                state.pop('tx_hash', None)
                state['reverted'] = [*state.get('reverted', []), payment['tx_hash']]
                state.update(status='awaiting_seller_approval',
                             detail=f'Refund transfer reverted on chain ({str(exc)[:80]}); nothing moved. Approve the refund again.')
            else:
                state['detail'] = 'Refund pending; resume the same refund. Do not create a replacement transfer.'
            self.save(run_id,step_id,state)
        except (RelayPending,settle.PaymentError,ValueError,TimeoutError):
            state['detail'] = 'Refund pending; resume the same refund. Do not create a replacement transfer.'
            self.save(run_id,step_id,state)
        except Exception:
            self.save(run_id,step_id,state)
            raise
        return self.status(run_id,token,step_id)


def attach_routes(app, provider, *, caller, allow_request):
    refunds = PipelineRefunds(provider)
    app.state.pipeline_refunds = refunds
    def check(request):
        if not allow_request('pipeline-refund:'+caller(request)):
            raise HTTPException(429,'slow down',headers={'Retry-After':'2'})
    @app.post('/studio/paid-runs/{run_id}/refunds/{step_id}/prepare')
    async def prepare(run_id:str,step_id:str,request:Request,x_studio_run_token:str=Header(default='')):
        check(request)
        return JSONResponse(refunds.prepare(run_id,x_studio_run_token,step_id),headers={'Cache-Control':'no-store'})
    @app.get('/studio/paid-runs/{run_id}/refunds/{step_id}')
    async def status(run_id:str,step_id:str,request:Request,x_studio_run_token:str=Header(default='')):
        check(request)
        return JSONResponse(refunds.status(run_id,x_studio_run_token,step_id),headers={'Cache-Control':'no-store'})
    @app.post('/studio/paid-runs/{run_id}/refunds/{step_id}')
    async def advance(run_id:str,step_id:str,body:RefundApproval,request:Request,x_studio_run_token:str=Header(default='')):
        check(request)
        value=await refunds.advance(run_id,x_studio_run_token,step_id,body)
        return JSONResponse(value,status_code=200 if value['status']=='refunded' else 202,headers={'Cache-Control':'no-store'})
