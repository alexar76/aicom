"""Buyer adapter for pinned peers advertising SELLER-OP/1.

Only fixed same-peer endpoints are called. No buyer key, credit credential or local
SUB/1 token crosses the federation boundary. HTTP redirects are never followed.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal

import httpx

from aimarket_hub import settle, x402
from aimarket_hub.outbound_http import prepare_safe_request_async
from aimarket_hub.signing import Signer
from aimarket_hub.studio_paid import _json

BASE = '/ai-market/v2/operations'
PROTOCOL = 'SELLER-OP/1'


class RemotePending(Exception):
    def __init__(self, message, *, reconciliation=False):
        super().__init__(message)
        self.reconciliation = reconciliation


async def request_json(method, url, *, body=None, token=None):
    target, headers, ext = await prepare_safe_request_async(url)
    if token:
        headers['X-Operation-Token'] = token
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        async with client.stream(method, target, json=body, headers=headers, extensions=ext) as response:
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError('peer operation response exceeds 2 MB')
                chunks.append(chunk)
    value = json.loads(b''.join(chunks))
    if not isinstance(value, dict):
        raise ValueError('peer operation response must be an object')
    return value


class PeerOperations:
    def __init__(self, db):
        self.db = db
        self.request = request_json

    def peer(self, node):
        peer = self.db.get_peer(node['source_hub'])
        if not peer or not peer.trusted or peer.status != 'active' or not peer.public_key:
            raise ValueError('independent seller requires an active, pinned trusted peer')
        return peer

    @staticmethod
    def verify(value, peer):
        if not Signer.verify_object_signature(value, peer.public_key,
            pq_public_key_b64=peer.pq_public_key or None, require_pq=bool(peer.pq_public_key)):
            raise ValueError('invalid independent seller signature')

    def validate(self, node, remote, *, wallet=None):
        peer = self.peer(node)
        offer = remote['offer']
        self.verify(offer, peer)
        if (offer.get('protocol') != PROTOCOL or not re.fullmatch(r'op_[0-9a-f]{32}', offer.get('operation_id', ''))
                or any(offer.get(k) != node[k] for k in ('product_id', 'capability_id'))):
            raise ValueError('independent seller offer differs from the requested capability')
        if wallet is not None and offer.get('wallet') != wallet.lower():
            raise ValueError('independent seller offer belongs to a different buyer')
        cap = self.db.get_capability(node['product_id'], node['capability_id'], node['source_hub'])
        if not cap:
            raise ValueError('independent seller listing disappeared')
        terms = offer.get('terms')
        if not terms:
            if cap.price_per_call_usd != 0:
                raise ValueError('independent seller price differs from the catalogue')
            return {'terms': None, 'input_schema': offer['input_schema']}
        if not (x402.enabled() and x402.accept_enabled() and settle.rpc_urls()):
            raise ValueError('seller-direct payment verification is unavailable on this hub')
        payment = settle.PaymentTerms(**terms)
        profile = x402.asset_profile() or {}
        if (payment.chain_id != x402.chain_id() or payment.token_contract.lower() != str(profile.get('address', '')).lower()
                or payment.decimals != int(profile.get('decimals', 6))
                or payment.amount_units != settle.to_units(cap.price_per_call_usd, payment.decimals)
                or Decimal(str(payment.amount_usd)) != Decimal(str(cap.price_per_call_usd))
                or payment.seller_units + payment.fee_units != payment.amount_units
                or payment.amount_units <= 0 or min(payment.seller_units, payment.fee_units) < 0
                or (payment.fee_units and not settle.is_address(payment.fee_to))
                or not settle.is_address(payment.pay_to) or not settle.is_address(payment.offer_to)
                or (cap.payout_address and cap.payout_address.lower() != payment.pay_to.lower())):
            raise ValueError('independent seller payment terms differ from the supported quoted asset/price/payee')
        invoice = offer.get('invoice') or {}
        if not settle.is_nonce(invoice.get('nonce', '')) or invoice.get('expires_at') != offer.get('expires_at'):
            raise ValueError('invalid independent seller invoice')
        return {'terms': terms, 'input_schema': offer['input_schema']}

    async def prepare(self, node, wallet):
        peer = self.peer(node)
        manifest = await self.request('GET', peer.url.rstrip('/') + '/.well-known/ai-market.json')
        self.verify(manifest, peer)
        if (manifest.get('seller_operations') or {}).get('protocol') != PROTOCOL:
            raise ValueError('peer bills independently and does not advertise SELLER-OP/1')
        cap = self.db.get_capability(node['product_id'], node['capability_id'], node['source_hub'])
        envelope = await self.request('POST', peer.url.rstrip('/') + BASE + '/prepare', body={
            'product_id': node['product_id'], 'capability_id': node['capability_id'],
            'wallet': wallet, 'max_price_usd': cap.price_per_call_usd})
        token = envelope.get('operation_token')
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            raise ValueError('independent seller returned an invalid scoped token')
        self.validate(node, envelope, wallet=wallet)
        if time.time() + 30 >= envelope['offer']['expires_at']:
            raise ValueError('independent seller offer is too close to expiry')
        return envelope

    async def advance(self, step, wallet):
        remote, node = step['remote'], step['node']
        peer = self.peer(node)
        offer = remote['offer']
        url = peer.url.rstrip('/') + BASE + '/' + offer['operation_id']
        body = {'input': step['resolved_input'], 'wallet': wallet, 'tx_hash': step.get('tx_hash')}
        try:
            status = await self.request('GET', url, token=remote['operation_token'])
            self._verify_status(status, peer, offer, body, allow_unbound=True)
            if status['status'] in ('quoted', 'ready', 'payment_pending') and not status.get('busy'):
                status = await self.request('POST', url + '/invoke', body=body, token=remote['operation_token'])
            self._verify_status(status, peer, offer, body)
            if status['status'] == 'reconciliation_required':
                raise RemotePending('Recover the same seller operation; never repurchase.',
                    reconciliation=status.get('recovery', {}).get('action') != 'resume_same_operation')
            if status['status'] not in ('completed', 'failed'):
                raise RemotePending('Seller operation pending; recover the same operation, never replace its payment.')
            return 200, {'success': status['success'], 'result': status['result'], 'receipt': status,
                         'detail': status.get('detail', '')}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # An HTTP error or an untrusted result does not prove non-execution.
            raise RemotePending('Seller outcome unavailable or unverifiable; read the same operation again.') from exc

    def _verify_status(self, status, peer, offer, body, *, allow_unbound=False):
        self.verify(status, peer)
        if any(status.get(k) != offer[k] for k in ('operation_id', 'product_id', 'capability_id')):
            raise ValueError('seller returned a different operation')
        if status.get('status') in ('completed', 'failed') and status.get('success') is not (status['status'] == 'completed'):
            raise ValueError('seller outcome is inconsistent')
        if status.get('protocol') != PROTOCOL or status.get('offer_digest') != hashlib.sha256(_json(offer).encode()).hexdigest():
            raise ValueError('seller status is not bound to its signed offer')
        if allow_unbound and status.get('status') == 'quoted' and status.get('input_digest') is None:
            return
        if (status.get('input_digest') != hashlib.sha256(_json(body['input']).encode()).hexdigest()
                or status.get('wallet') != body['wallet'].lower() or status.get('tx_hash') != body['tx_hash']):
            raise ValueError('seller operation is bound to different input or payment')
