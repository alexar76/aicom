"""Bounded, durable gas sponsorship of direct Base USDC authorizations.

One in-flight transaction per relay wallet. Shared DB CAS coordinates processes;
raw transactions are committed before broadcasting and never replaced on retry.
The relay key is the operator's gas-only key, never the buyer's wallet key.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from aimarket_hub import pipeline_payments
from aimarket_hub.db_backend import atomic, returning_one

BASE_USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'


class RelayPending(Exception):
    """No new charge is authorized by a retry; resume the same operation."""


class PipelineRelay:
    def __init__(self, conn, *, signer=None, rpc_url=None, daily_wei=None):
        self.conn = conn
        enabled = os.getenv('AIMARKET_PIPELINE_RELAY_ENABLED', '0') == '1'
        if signer is None and enabled:
            from eth_account import Account
            path = Path(os.environ['AIMARKET_PIPELINE_RELAY_KEY_FILE'])
            if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ValueError('relay key file must be private and not a symlink')
            signer = Account.from_key(path.read_text().strip())
        self.signer = signer
        self.rpc_url = rpc_url or os.getenv('AIMARKET_PIPELINE_RELAY_RPC', 'https://mainnet.base.org')
        self.price_rpc_url = os.getenv('AIMARKET_PIPELINE_RELAY_PRICE_RPC') or None
        self.daily_wei = int(daily_wei if daily_wei is not None else os.getenv('AIMARKET_PIPELINE_RELAY_DAILY_WEI', '20000000000000'))
        if self.daily_wei <= 0:
            raise ValueError('relay daily budget must be positive')
        self.payment_gas_usd = Decimal(os.getenv('AIMARKET_PIPELINE_RELAY_MAX_GAS_USD', '0.10'))
        if not self.payment_gas_usd.is_finite() or self.payment_gas_usd <= 0:
            raise ValueError('relay per-payment gas budget must be positive and finite')
        self.client_factory = lambda: httpx.AsyncClient(timeout=20)

    #: Fee bound assumed for one sponsored payment before any has been made (mainnet evidence:
    #: 6.24e12 wei). Used only to tell whether today's budget still covers one more payment.
    DEFAULT_FEE_BOUND_WEI = 7_000_000_000_000

    def _budget_left(self):
        """Wei left in today's sponsor budget, and the fee bound of the latest sponsored payment."""
        payer = self.signer.address.lower()
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        row = self.conn.execute('SELECT reserved_wei FROM pipeline_relay_budget WHERE payer = ? AND day = ?', (payer, day)).fetchone()
        last = self.conn.execute('SELECT payment_json FROM pipeline_relay_payments WHERE payer = ? ORDER BY created_at DESC LIMIT 1',
                                 (payer,)).fetchone()
        bound = self.DEFAULT_FEE_BOUND_WEI
        if last:
            try:
                bound = int(json.loads(last['payment_json'])['gas_budget']['native_fee_bound_wei'])
            except (KeyError, TypeError, ValueError):
                pass
        return self.daily_wei - (int(row['reserved_wei']) if row else 0), bound

    def describe(self, steps=None):
        reason = '' if self.signer else 'gas_sponsor_not_configured'
        for step in steps or []:
            t = step.get('terms')
            if t and (int(t['chain_id']) != 8453 or t['token_contract'].lower() != BASE_USDC
                      or int(t['fee_units']) != 0 or int(t['decimals']) != 6):
                reason = 'gas_sponsor_requires_direct_base_usdc'
        if not reason and steps:
            # Offer sponsorship only while today's budget covers every payment in this plan, so
            # gas_mode="auto" falls back to buyer gas instead of a quote that can only stall.
            left, bound = self._budget_left()
            if left < bound * sum(1 for step in steps if step.get('terms')):
                reason = 'gas_sponsor_daily_budget_exhausted'
        return {'enabled': not reason, 'protocol': 'GAS-SPONSOR/1', 'buyer_fee_units': '0',
                'gas_payer': self.signer.address.lower() if self.signer else None,
                'reason': reason or None, 'nonce_coordination': 'shared_database',
                'scope': 'direct_base_usdc', 'buyer_private_key_required': False}

    def _existing(self, run_id, step_id, digest):
        row = self.conn.execute('SELECT * FROM pipeline_relay_payments WHERE run_id = ? AND step_id = ?',
                                (run_id, step_id)).fetchone()
        if row:
            if row['request_digest'] != digest:
                raise ValueError('relay operation payment is immutable')
            return json.loads(row['payment_json'])
        return None

    def cached(self, state, step):
        signature, wallet = step['relay_authorization'], state['wallet']
        pipeline_payments.validate_authorization(step, wallet, signature)
        digest = hashlib.sha256(json.dumps({'wallet': wallet, 'terms': step['terms'],
            'authorization': pipeline_payments.authorization_data(step, wallet), 'signature': signature.lower()},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return self._existing(state['run_id'], step['node']['id'], digest)

    async def forget_reverted(self, state, step):
        """Drop this step's relay payment once the chain shows it REVERTED, so the same refund or
        payment can be approved and relayed again. A reverted EIP-3009 call leaves its nonce
        unused, so a fresh authorization with the same nonce still transfers at most once. Returns
        False, and keeps the bytes, unless the receipt is there and failed."""
        from aimarket_hub.pipeline_client import _rpc
        row = self.conn.execute('SELECT payment_json FROM pipeline_relay_payments WHERE run_id = ? AND step_id = ?',
                                (state['run_id'], step['node']['id'])).fetchone()
        if not row:
            return False
        tx_hash = json.loads(row['payment_json'])['tx_hash']
        async with self.client_factory() as client:
            receipt = await _rpc(client, self.rpc_url, 'eth_getTransactionReceipt', [tx_hash])
        if not receipt or str(receipt.get('status', '')).lower() not in ('0x0', '0'):
            return False
        with atomic(self.conn):
            self.conn.execute('DELETE FROM pipeline_relay_payments WHERE run_id = ? AND step_id = ?',
                              (state['run_id'], step['node']['id']))
        return True

    async def payment(self, state, step):
        try:
            return await self._payment(state, step)
        except (httpx.TransportError, TimeoutError) as exc:
            raise RelayPending('Relay RPC unavailable; resume the same order') from exc
        except ValueError as exc:
            if str(exc).startswith(('RPC ', 'invalid JSON')):
                raise RelayPending('Relay RPC or gas estimate unavailable; resume the same order') from exc
            raise

    async def _payment(self, state, step):
        from eth_utils import to_checksum_address
        from aimarket_hub.pipeline_client import _rpc, _budget
        signature, wallet = step['relay_authorization'], state['wallet']
        pipeline_payments.validate_authorization(step, wallet, signature)
        digest = hashlib.sha256(json.dumps({'wallet': wallet, 'terms': step['terms'],
            'authorization': pipeline_payments.authorization_data(step, wallet), 'signature': signature.lower()},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        run_id, step_id = state['run_id'], step['node']['id']
        cached = self._existing(run_id, step_id, digest)
        if cached:
            return cached
        # Expiry first: an authorization past its validity can never be relayed, and a step that
        # only ever answers "pending" (sponsorship switched off meanwhile) would never end.
        if time.time() + 30 >= step['invoice']['expires_at']:
            raise ValueError('authorization expired before relay signing')
        described = self.describe([step])
        if not described['enabled']:
            if described['reason'] == 'gas_sponsor_daily_budget_exhausted':
                raise RelayPending('Gas sponsor daily budget exhausted; retain the same order')
            raise RelayPending('Gas sponsorship is unavailable for this payment; retain the same order')
        payer = self.signer.address.lower()
        async with self.client_factory() as client:
            # Finish the previous wallet nonce first, even across Hub workers/orders.
            head = self.conn.execute('SELECT next_nonce FROM pipeline_relay_nonces WHERE chain_id = 8453 AND payer = ?',
                                     (payer,)).fetchone()
            expected = int(head['next_nonce']) if head else None
            if expected is not None:
                previous = self.conn.execute('SELECT payment_json FROM pipeline_relay_payments WHERE chain_id = 8453 AND payer = ? AND nonce = ?',
                                             (payer, expected - 1)).fetchone()
                if previous:
                    payment = json.loads(previous['payment_json'])
                    receipt = await _rpc(client, self.rpc_url, 'eth_getTransactionReceipt', [payment['tx_hash']])
                    if not receipt:
                        # An interrupted worker may have committed but not sent these bytes.
                        try:
                            await _rpc(client, self.rpc_url, 'eth_sendRawTransaction', [payment['raw']])
                        except ValueError:
                            pass
                        raise RelayPending('Another relay transaction is awaiting confirmation')
            service = Decimal(step['terms']['amount_units']) / 10**6
            budget_state = {'quote': {'offers': [step], 'total_units': str(step['terms']['amount_units'])},
                'rpc_url': self.rpc_url, 'price_rpc_url': self.price_rpc_url,
                # _budget() adds the buyer-side $0.05 reserve; add it back so the per-payment gas cap
                # is exactly AIMARKET_PIPELINE_RELAY_MAX_GAS_USD, not $0.05 less (and 0.05 → none).
                'native_usd_ceiling': None, 'max_total_usd': str(service + self.payment_gas_usd + Decimal('0.05'))}
            try:
                budget = await _budget(client, budget_state)
            except (ValueError, TimeoutError) as exc:
                raise RelayPending('Relay gas budget or price check unavailable; resume this order') from exc
            fee_bound = int(budget['native_fee_bound_wei'])
            pending = int(await _rpc(client, self.rpc_url, 'eth_getTransactionCount', [payer, 'pending']), 16)
            latest = int(await _rpc(client, self.rpc_url, 'eth_getTransactionCount', [payer, 'latest']), 16)
            if pending != latest or (expected is not None and expected != pending):
                raise RelayPending('Relay wallet nonce requires reconciliation')
            balance = int(await _rpc(client, self.rpc_url, 'eth_getBalance', [payer, 'latest']), 16)
            if balance < fee_bound:
                raise RelayPending('Gas sponsor balance is insufficient')
            tx = pipeline_payments.payment_transaction(step, wallet, signature)
            tx['from'] = payer
            gas = int(await _rpc(client, self.rpc_url, 'eth_estimateGas', [
                {k: hex(v) if isinstance(v, int) else v for k, v in tx.items()}]), 16)
            fees = budget_state['fees']
            if gas > fees['gas']:
                raise ValueError('authorization exceeds relay gas limit')
            day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            # No await inside this transaction. CAS and the budget debit are shared
            # by all hosts using this database. A loser rolls back both allocations.
            if time.time() + 10 >= step['invoice']['expires_at']:
                raise ValueError('authorization expired before relay signing')
            with atomic(self.conn):
                if state.get('original_run_id') and state.get('refund_id'):
                    parent = self.conn.execute('SELECT state_json FROM pipeline_refunds WHERE run_id = ? AND step_id = ?',
                                               (state['original_run_id'], step_id)).fetchone()
                    current = json.loads(parent['state_json'])['step'] if parent else {}
                    if current.get('relay_authorization') != signature or current.get('invoice') != step['invoice']:
                        raise RelayPending('Refund approval changed before relay signing; reload the same refund')
                cached = self._existing(run_id, step_id, digest)
                if cached:
                    return cached
                self.conn.execute('INSERT INTO pipeline_relay_nonces (chain_id, payer, next_nonce) VALUES (8453, ?, ?) ON CONFLICT DO NOTHING',
                                  (payer, pending))
                won = returning_one(self.conn, 'UPDATE pipeline_relay_nonces SET next_nonce = next_nonce + 1 WHERE chain_id = 8453 AND payer = ? AND next_nonce = ? RETURNING next_nonce',
                                    (payer, pending))
                if not won:
                    raise RelayPending('Another relay worker allocated this nonce; resume the same order')
                self.conn.execute('INSERT INTO pipeline_relay_budget (payer, day, reserved_wei) VALUES (?, ?, 0) ON CONFLICT DO NOTHING', (payer, day))
                allowed = returning_one(self.conn, 'UPDATE pipeline_relay_budget SET reserved_wei = reserved_wei + ? WHERE payer = ? AND day = ? AND reserved_wei + ? <= ? RETURNING reserved_wei',
                                        (fee_bound, payer, day, fee_bound, self.daily_wei))
                if not allowed:
                    raise RelayPending('Gas sponsor daily budget exhausted')
                tx.pop('from')
                tx.update(to=to_checksum_address(tx['to']), type=2, chainId=8453, nonce=pending,
                          gas=fees['gas'], maxFeePerGas=fees['max_fee'], maxPriorityFeePerGas=fees['priority_fee'])
                raw = '0x' + self.signer.sign_transaction(tx).raw_transaction.hex().removeprefix('0x')
                payment = pipeline_payments.validate_transaction(step, wallet, raw, gas_payer=payer)
                payment.update(gas_payer=payer, sponsored=True, gas_budget=budget)
                self.conn.execute('INSERT INTO pipeline_relay_payments (run_id, step_id, chain_id, payer, nonce, request_digest, payment_json, created_at) VALUES (?, ?, 8453, ?, ?, ?, ?, ?)',
                                  (run_id, step_id, payer, pending, digest, json.dumps(payment), time.time()))
            return payment
