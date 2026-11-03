"""SELLER-OP/1: signed seller offers and durable, scoped, at-most-once operations.

Uses the existing seller-direct EIP-3009 settlement path. This is an extension for
compatible sellers, not a claim that every x402 endpoint supports durable results.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time

import httpx

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field

from aimarket_hub import settle, provider_recovery
from aimarket_hub.db_backend import returning_one
from aimarket_hub.studio_paid import _json, check_input

PROTOCOL = 'SELLER-OP/1'
ZERO_WALLET = '0x' + '00' * 20
BASE = '/ai-market/v2/operations'


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    wallet: str = Field(ZERO_WALLET, pattern=r'^0x[0-9a-fA-F]{40}$')
    max_price_usd: float = Field(ge=0, le=100000, allow_inf_nan=False)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input: dict
    wallet: str = Field(ZERO_WALLET, pattern=r'^0x[0-9a-fA-F]{40}$')
    tx_hash: str | None = Field(None, pattern=r'^0x[0-9a-fA-F]{64}$')


class SellerOperations:
    def __init__(self, studio, invoke):
        self.studio, self.conn, self.signer, self.invoke = studio, studio.conn, studio.signer, invoke
        self.provider_status = provider_recovery.request_status

    def quote(self, body: QuoteRequest):
        # First release sells local capabilities only: never recursively broker an operation.
        node = {'id': 'work', 'product_id': body.product_id, 'capability_id': body.capability_id,
                'source_hub': 'local', 'input': {}}
        cap = self.studio.db.get_capability(body.product_id, body.capability_id, 'local')
        if cap is None or not self.studio.route_ok(cap) or body.capability_id == 'pipeline.run@v1':
            raise HTTPException(404, 'seller operation requires an available local listing')
        # Describe terms without demanding real inputs before the buyer's graph has resolved them.
        try:
            description = self.studio.describe(node, validate_input=False)
        except (ValueError, SchemaError) as exc:
            raise HTTPException(409, {'code': 'settlement_route_unsupported', 'detail': str(exc)[:300]}) from exc
        terms, schema = description['terms'], description['input_schema']
        price = terms['amount_usd'] if terms else 0
        if price > body.max_price_usd:
            raise HTTPException(409, 'seller price exceeds the approved maximum')
        operation_id, token = 'op_' + secrets.token_hex(16), secrets.token_urlsafe(32)
        invoice, secret = None, ''
        if terms:
            secret = settle.mint_secret()
            invoice = self.studio.invoices.mint(nonce=settle.nonce_for_secret(secret),
                capability_id=body.capability_id, pay_to=terms['pay_to'], amount_units=terms['amount_units'],
                ttl_s=settle.invoice_ttl_s(), secret=secret)
        offer = {'protocol': PROTOCOL, 'operation_id': operation_id, 'product_id': body.product_id,
                 'capability_id': body.capability_id, 'wallet': body.wallet.lower(),
                 'terms': terms, 'input_schema': schema,
                 'invoice': {k: invoice[k] for k in ('nonce', 'expires_at')} if invoice else None,
                 'expires_at': invoice['expires_at'] if invoice else time.time() + 900,
                 'recovery': 'durable_result_at_most_once_dispatch'}
        recovery = provider_recovery.descriptor(cap)
        offer['provider_recovery'] = provider_recovery.PROTOCOL if recovery else None
        offer['signature'] = self.signer.sign_object(offer)
        state = {'offer': offer, 'status': 'quoted', 'node': node, 'secret': secret, 'request': None, 'provider_recovery': recovery}
        self.conn.execute('INSERT INTO seller_operations (operation_id, token_hash, state_json, updated_at) VALUES (?, ?, ?, ?)',
            (operation_id, hashlib.sha256(token.encode()).hexdigest(), _json(state), time.time()))
        self.conn.commit()
        return {'offer': offer, 'operation_token': token}

    def load(self, operation_id, token):
        row = self.conn.execute('SELECT * FROM seller_operations WHERE operation_id = ?', (operation_id,)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(404, 'operation not found')
        return json.loads(row['state_json']), row

    def save(self, operation_id, state, *, busy=False, response=None):
        self.conn.execute('UPDATE seller_operations SET state_json = ?, busy = ?, response_json = ?, updated_at = ? WHERE operation_id = ? AND response_json = \'\'',
            (_json(state), int(busy), _json(response) if response else '', time.time(), operation_id))
        self.conn.commit()

    def view(self, state, busy=False):
        offer = state['offer']
        result = {'protocol': PROTOCOL, 'operation_id': offer['operation_id'],
                  'product_id': offer['product_id'], 'capability_id': offer['capability_id'],
                  'offer_digest': hashlib.sha256(_json(offer).encode()).hexdigest(),
                  'status': state['status'], 'busy': bool(busy),
                  'input_digest': state.get('input_digest'),
                  'wallet': state.get('payer') or (state.get('request') or {}).get('wallet', offer['wallet']),
                  'tx_hash': (state.get('request') or {}).get('tx_hash'),
                  'success': state['status'] == 'completed', 'result': state.get('result', {}),
                  'receipt': state.get('receipt'), 'detail': state.get('detail', ''),
                  'recovery': {'action': 'resume_same_operation' if (state['status'] == 'reconciliation_required' and state.get('provider_recovery') and not state.get('provider_requires_operator')) else
                               'contact_operator' if state['status'] == 'reconciliation_required' else
                               'wait' if busy else 'read_result' if state['status'] in ('completed', 'failed') else 'resume_same_operation',
                               'replacement_payment_allowed': False}}
        result['signature'] = self.signer.sign_object(result)
        return result

    def status(self, operation_id, token):
        state, row = self.load(operation_id, token)
        if row['response_json']:
            return json.loads(row['response_json'])
        if row['busy'] and time.time() - row['updated_at'] > 180:
            # Never unlock a possibly dispatched non-idempotent provider on a timer.
            state.update(status='reconciliation_required', detail='Stale execution claim; verify provider outcome before any further action.')
        return self.view(state, row['busy'])

    async def recover(self, operation_id, token):
        state, row = self.load(operation_id, token)
        if row['response_json'] or not state.get('provider_recovery') or not state.get('request'):
            return self.status(operation_id, token)
        if state['status'] not in ('running', 'reconciliation_required'):
            return self.status(operation_id, token)
        if row['busy'] and time.time() - row['updated_at'] <= 180:
            return self.status(operation_id, token)
        # Paid work may be recovered only after the original transfer was verified.
        # Old operations without that durable evidence remain operator-reconciled.
        if state['offer']['terms'] and not state.get('verified_payment'):
            return self.status(operation_id, token)
        try:
            doc = await self.provider_status(state['provider_recovery'], operation_id)
            provider_recovery.verify(doc, state['provider_recovery'], operation_id, state['node'], state['request']['input'])
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            return self.status(operation_id, token)
        original = _json(state)
        if doc['status'] == 'completed':
            state.update(status='completed', result=doc['result'], receipt=doc,
                         detail='Recovered the signed provider result without a second dispatch.')
        elif doc['status'] == 'reconciliation_required':
            state.update(status='reconciliation_required', provider_requires_operator=True,
                         detail='Provider has no durable outcome; manual reconciliation is required.')
        else:
            return self.status(operation_id, token)
        response = self.view(state)
        returning_one(self.conn,
            "UPDATE seller_operations SET state_json = ?, busy = 0, response_json = ?, updated_at = ? "
            "WHERE operation_id = ? AND state_json = ? AND response_json = '' RETURNING operation_id",
            (_json(state), _json(response) if state['status'] == 'completed' else '', time.time(), operation_id, original), commit=True)
        return self.status(operation_id, token)

    async def execute(self, operation_id, token, body: ExecuteRequest, caller):
        state, row = self.load(operation_id, token)
        request = body.model_dump()
        request['wallet'] = request['wallet'].lower()
        if request['tx_hash']:
            request['tx_hash'] = request['tx_hash'].lower()
        if state['request'] is not None and state['request'] != request:
            raise HTTPException(409, 'operation input, buyer and payment are immutable')
        if row['response_json'] or row['busy'] or state['status'] == 'reconciliation_required':
            return await self.recover(operation_id, token)
        offer = state['offer']
        if offer['wallet'] != ZERO_WALLET and offer['wallet'] != request['wallet']:
            raise HTTPException(409, 'operation belongs to a different wallet')
        try:
            check_input(request['input'], offer['input_schema'], dynamic=False)
        except (ValueError, SchemaError) as exc:
            raise HTTPException(422, str(exc)) from exc
        if offer['terms'] and not request['tx_hash']:
            raise HTTPException(402, 'pay the prepared invoice and submit its transaction hash')
        if not offer['terms'] and request['tx_hash']:
            raise HTTPException(400, 'free operations accept no payment')
        if state['request'] is None and not request['tx_hash'] and time.time() >= offer['expires_at']:
            raise HTTPException(409, 'unstarted operation offer expired')
        original_state = _json(state)
        state['request'], state['input_digest'] = request, hashlib.sha256(_json(request['input']).encode()).hexdigest()
        state['status'] = 'payment_pending' if offer['terms'] else 'ready'
        if not returning_one(self.conn,
            'UPDATE seller_operations SET state_json = ?, busy = 1, updated_at = ? WHERE operation_id = ? AND busy = 0 AND state_json = ? RETURNING operation_id',
            (_json(state), time.time(), operation_id, original_state), commit=True):
            return self.status(operation_id, token)
        dispatched = False
        try:
            if offer['terms']:
                try:
                    payment = await asyncio.to_thread(settle.verify_transfer, tx_hash=request['tx_hash'],
                        terms=settle.PaymentTerms(**offer['terms']), require_nonce=offer['invoice']['nonce'],
                        paid_before=offer['invoice']['expires_at'] if time.time() >= offer['expires_at'] else None)
                except Exception:
                    state['detail'] = 'Payment confirmation unavailable; retain the same operation and transaction.'
                    self.save(operation_id, state)
                    return self.view(state)
                authorizer = str(payment.get('authorizer', '')).lower()
                if request['wallet'] != ZERO_WALLET and authorizer != request['wallet']:
                    if offer['wallet'] != ZERO_WALLET:
                        # The offer was made for one wallet and another paid it: nothing to correct,
                        # and nothing was dispatched. The verified payment stays on record for a refund.
                        state['verified_payment'] = payment
                        state.update(status='failed', detail='Paid by a wallet other than the one this offer was made for; no provider dispatch. Ask the operator for a refund of the recorded payment.')
                        response = self.view(state)
                        self.save(operation_id, state, response=response)
                        return self.status(operation_id, token)
                    # Open offer, wrong wallet declared: undo the claim so the same payment can be
                    # submitted again with the paying wallet (or none).
                    self.save(operation_id, json.loads(original_state))
                    raise HTTPException(409, 'payment authorizer differs from the declared wallet; nothing was dispatched — '
                                             'invoke again with the paying wallet, or without one')
                # With no declared wallet, whoever paid this invoice is the buyer. The request itself
                # stays as submitted, so the same body replayed later still matches it.
                state['verified_payment'], state['payer'] = payment, authorizer
            # Every revalidation precedes dispatch. The outer operation never renews the invoice.
            try:
                current = self.studio.describe(state['node'], validate_input=False)
            except (ValueError, SchemaError):
                current = None  # the listing is gone or its route is no longer usable
            if current != {'terms': offer['terms'], 'input_schema': offer['input_schema']}:
                state.update(status='failed', detail='Listing changed after the offer; no provider dispatch.')
            else:
                state['status'] = 'running'
                self.save(operation_id, state, busy=True)  # durable BEFORE provider dispatch
                headers = {}
                if offer['terms']:
                    headers = {'X-Payment': request['tx_hash'], 'X-Payment-Nonce': offer['invoice']['nonce'],
                               'X-Payment-Secret': state['secret']}
                payload = {k: state['node'][k] for k in ('product_id', 'capability_id', 'source_hub')}
                payload.update(input=request['input'], max_price_usd=offer['terms']['amount_usd'] if offer['terms'] else 0)
                dispatched = True
                code, answer = await self.invoke(payload, headers, caller, operation_id=operation_id)
                if code >= 500:
                    state.update(status='reconciliation_required', detail='Provider outcome uncertain; no automatic second dispatch.')
                else:
                    success = 200 <= code < 300 and answer.get('success', answer.get('ok')) is True
                    state.update(status='completed' if success else 'failed', result=answer.get('result', {}),
                                 receipt=answer.get('receipt'), detail='' if success else str(answer.get('error', 'provider refused'))[:300])
        except HTTPException:
            raise
        except BaseException:
            if dispatched:
                state.update(status='reconciliation_required', detail='Interrupted execution; inspect the same operation, never repurchase.')
                self.save(operation_id, state)
            else:
                # Nothing reached the provider: release the claim as it was, so the same request
                # can simply run again. Marking it "reconciliation" stranded paid operations forever.
                self.save(operation_id, json.loads(original_state))
            raise
        response = self.view(state)
        self.save(operation_id, state, response=response if state['status'] in ('completed', 'failed') else None)
        return self.status(operation_id, token)


def attach_routes(app, operations, *, caller, allow_request):
    def check(request):
        if not allow_request('seller-operation:' + caller(request)):
            raise HTTPException(429, 'slow down', headers={'Retry-After': '2'})

    @app.post(BASE + '/prepare')
    async def quote(body: QuoteRequest, request: Request):
        check(request)
        return JSONResponse(operations.quote(body), headers={'Cache-Control': 'no-store'})

    @app.get(BASE + '/{operation_id}')
    async def status(operation_id: str, request: Request, x_operation_token: str = Header(default='')):
        check(request)
        return JSONResponse(await operations.recover(operation_id, x_operation_token), headers={'Cache-Control': 'no-store'})

    @app.post(BASE + '/{operation_id}/invoke')
    async def execute(operation_id: str, body: ExecuteRequest, request: Request, x_operation_token: str = Header(default='')):
        check(request)
        response = await operations.execute(operation_id, x_operation_token, body, caller(request))
        return JSONResponse(response, status_code=200 if response['status'] in ('completed', 'failed') else 202,
                            headers={'Cache-Control': 'no-store'})
