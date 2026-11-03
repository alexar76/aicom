"""Buyer-owned PostgreSQL coordination across hosts, without storing wallet keys.

The private signed recovery state is durable in the buyer's database. Session
advisory locks serialize active clients; ownership survives process failure.
"""
from __future__ import annotations
import hashlib
import json
import os
import time

from aimarket_hub.pipeline_verification import verify_result, verify_document


class WalletCoordinator:
    def __init__(self,conn,identity,owner,state):
        self.conn,self.identity,self.owner,self.state=conn,identity,owner,state

    @classmethod
    async def acquire(cls,state,client,rpc):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise ValueError('shared wallet coordination requires aimarket-hub[postgres]') from None
        dsn=os.environ.get('AIMARKET_WALLET_DATABASE_URL','')
        if not dsn:raise ValueError('this order requires AIMARKET_WALLET_DATABASE_URL on every host')
        chain=state['quote']['offers'][0]['terms']['chain_id']
        identity=str(chain)+':'+state['wallet'].lower()
        owner=hashlib.sha256((state['hub']+':'+state['quote']['run_id']).encode()).hexdigest()
        lock_id=int.from_bytes(hashlib.sha256(('aimarket-wallet:'+identity).encode()).digest()[:8],'big',signed=True)
        conn=None
        try:
            conn=await psycopg.AsyncConnection.connect(dsn,autocommit=True,row_factory=dict_row,connect_timeout=10,client_encoding="UTF8")
            await conn.execute('CREATE TABLE IF NOT EXISTS aimarket_buyer_wallets (identity TEXT PRIMARY KEY, owner TEXT NOT NULL, state_json TEXT NOT NULL)')
            row=await (await conn.execute('SELECT pg_try_advisory_lock(%s) AS locked',(lock_id,))).fetchone()
            if not row['locked']:raise ValueError('another host is using this wallet; retry the same order')
            row=await (await conn.execute('SELECT * FROM aimarket_buyer_wallets WHERE identity=%s',(identity,))).fetchone()
            if row:
                saved=json.loads(row['state_json'])
                if row['owner']!=owner:
                    if not await releasable(saved,client,rpc):
                        raise ValueError('wallet reserved by another order; resume its original run on any cooperating host')
                else:
                    if saved['wallet']!=state['wallet'] or saved['hub']!=state['hub'] or saved['quote']['run_id']!=state['quote']['run_id']:
                        raise ValueError('shared wallet recovery identity mismatch')
                    for key in ('trusted_hub_key','trusted_hub_pq_key','accepted_assets','nodes','max_total_usd'):
                        if saved.get(key)!=state.get(key):raise ValueError('shared wallet policy differs from the original approval')
                    if state.get('trusted_hub_key'):
                        verify_document(saved['quote'],state['trusted_hub_key'],state.get('trusted_hub_pq_key'))
                    # A stale copy on a second host must reuse the committed bytes.
                    state.clear();state.update(saved)
            obj=cls(conn,identity,owner,state)
            await conn.execute('INSERT INTO aimarket_buyer_wallets(identity,owner,state_json) VALUES (%s,%s,%s) ON CONFLICT(identity) DO UPDATE SET owner=excluded.owner,state_json=excluded.state_json',
                               (identity,owner,json.dumps(state,sort_keys=True,separators=(',',':'))))
            return obj
        except ValueError:
            if conn:await conn.close()
            raise
        except Exception:
            if conn:await conn.close()
            # PostgreSQL errors can contain the password-bearing connection string.
            raise ValueError('shared wallet database unavailable; retain and resume the same order') from None

    async def checkpoint(self,state):
        try:
            cur=await self.conn.execute('UPDATE aimarket_buyer_wallets SET state_json=%s WHERE identity=%s AND owner=%s',
                (json.dumps(state,sort_keys=True,separators=(',',':')),self.identity,self.owner))
            if cur.rowcount!=1:raise ValueError('wallet ownership lost')
        except Exception:
            raise ValueError('shared wallet checkpoint failed; no new submission allowed; resume the same order') from None

    async def close(self,state):
        try:
            # Never replace committed signed bytes with a stale local snapshot.
            if (state.get('phase') in ('preparing','prepared') or
                    (state.get('verified') and state.get('result',{}).get('success'))):
                if state.get('result'):verify_result(state['result'],state)
                await self.conn.execute('DELETE FROM aimarket_buyer_wallets WHERE identity=%s AND owner=%s',(self.identity,self.owner))
        except Exception:
            pass  # Retaining the durable reservation is the safe failure.
        finally:
            await self.conn.close()


async def releasable(state,client,rpc):
    if state.get('phase')!='completed' or not state.get('verified'):return False
    verify_result(state['result'],state)
    if state['result'].get('success'):return True
    offers=state['quote']['offers'];chain=offers[0]['terms']['chain_id']
    if int(await rpc(client,state['rpc_url'],'eth_chainId',[]),16)!=chain:
        raise ValueError('wallet release RPC differs from the approved chain')
    pending=int(await rpc(client,state['rpc_url'],'eth_getTransactionCount',[state['wallet'],'pending']),16)
    latest=int(await rpc(client,state['rpc_url'],'eth_getTransactionCount',[state['wallet'],'latest']),16)
    consumed=state.get('nonce_start') is not None and latest>=state['nonce_start']+len(offers)
    expired=all(time.time()>o['invoice']['expires_at']+30 for o in offers)
    return pending==latest and (consumed or expired)


async def record_completed(state):
    """Best-effort cleanup after a lost DB connection at terminal response time.

    Cached results stay available offline. A subsequent successful resume can
    publish the verified terminal state without touching another order's lease.
    """
    conn=None
    try:
        import psycopg
        verify_result(state['result'],state)
        offers=state['quote']['offers']
        if not offers or state['quote'].get('gas_sponsorship',{}).get('enabled'):return
        identity=str(offers[0]['terms']['chain_id'])+':'+state['wallet'].lower()
        owner=hashlib.sha256((state['hub']+':'+state['quote']['run_id']).encode()).hexdigest()
        lock_id=int.from_bytes(hashlib.sha256(('aimarket-wallet:'+identity).encode()).digest()[:8],'big',signed=True)
        conn=await psycopg.AsyncConnection.connect(os.environ['AIMARKET_WALLET_DATABASE_URL'],autocommit=True,connect_timeout=5,client_encoding='UTF8')
        row=await (await conn.execute('SELECT pg_try_advisory_lock(%s)',(lock_id,))).fetchone()
        if not row[0]:return
        if state['result'].get('success'):
            await conn.execute('DELETE FROM aimarket_buyer_wallets WHERE identity=%s AND owner=%s',(identity,owner))
        else:
            await conn.execute('UPDATE aimarket_buyer_wallets SET state_json=%s WHERE identity=%s AND owner=%s',(json.dumps(state,sort_keys=True),identity,owner))
    except Exception:
        pass
    finally:
        if conn:await conn.close()
