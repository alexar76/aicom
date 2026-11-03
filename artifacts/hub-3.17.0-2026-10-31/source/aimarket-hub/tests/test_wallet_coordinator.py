"""Run with AIMARKET_TEST_WALLET_POSTGRES pointing only at a disposable test DB."""
import json,os,uuid
from copy import deepcopy
import httpx
import pytest
from aimarket_hub.wallet_coordinator import WalletCoordinator
from aimarket_hub.pipeline_client import run_pipeline
from tests.test_pipeline_client import rig,call
from tests.test_studio_paid import setup


@pytest.fixture
def shared(monkeypatch):
    dsn=os.environ.get('AIMARKET_TEST_WALLET_POSTGRES')
    if not dsn:pytest.skip('requires disposable PostgreSQL')
    import psycopg
    from psycopg.conninfo import make_conninfo
    schema='wallet_test_'+uuid.uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as c:c.execute('CREATE SCHEMA '+schema)
    target=make_conninfo(dsn,options='-csearch_path='+schema)
    monkeypatch.setenv('AIMARKET_WALLET_DATABASE_URL',target)
    yield target
    with psycopg.connect(dsn,autocommit=True) as c:c.execute('DROP SCHEMA '+schema+' CASCADE')


def stub():
    return dict(hub='https://hub.test',wallet='0x'+'ab'*20,phase='prepared',quote={'run_id':'run_one','offers':[{'terms':{'chain_id':8453}}]})


@pytest.mark.asyncio
async def test_separate_connections_lock_and_recover_committed_bundle(shared):
    a=stub();stale=deepcopy(a)
    first=await WalletCoordinator.acquire(a,None,None)
    with pytest.raises(ValueError,match='another host'):
        await WalletCoordinator.acquire(deepcopy(a),None,None)
    a.update(phase='submitted',request={'signed_bundle':'same bytes'})
    await first.checkpoint(a)
    await first.conn.close() # Simulated client crash: ownership remains.
    other=stub();other['quote']['run_id']='run_two'
    with pytest.raises(ValueError,match='reserved'):
        await WalletCoordinator.acquire(other,None,None)
    resumed=await WalletCoordinator.acquire(stale,None,None)
    assert stale['request']==a['request'] and stale['phase']=='submitted'
    await resumed.conn.close()
    with pytest.raises(ValueError,match='checkpoint failed'):
        await resumed.checkpoint(stale)


@pytest.mark.asyncio
async def test_sdk_second_host_stale_file_reuses_bundle_without_signer(shared,rig,tmp_path):
    t,_,seen=rig;t.pending=1
    path=tmp_path/'host_a.json'
    pending=await call(t,path,wait=False)
    assert not pending.get('success')
    original=json.loads(path.read_text());assert original['wallet_coordination']=='postgres'
    stale=deepcopy(original);stale['phase']='prepared';stale.pop('request');stale.pop('nonce_start')
    second=tmp_path/'host_b.json';second.write_text(json.dumps(stale))
    async with httpx.AsyncClient(transport=t) as c:
        result=await run_pipeline(resume=True,state_path=second,client=c,poll_interval_s=.001)
    assert result['success'] and len(seen)==1
    assert json.loads(second.read_text())['request']==original['request']
    # Even after the shared row was released, a stale pre-signing copy reads the
    # immutable result before requiring a signer or touching a new nonce.
    third=tmp_path/'host_c.json';third.write_text(json.dumps(stale))
    async with httpx.AsyncClient(transport=t) as c:
        assert await run_pipeline(resume=True,state_path=third,client=c)==result
    assert len(seen)==1
    import psycopg
    with psycopg.connect(shared) as c:
        assert c.execute('SELECT count(*) FROM aimarket_buyer_wallets').fetchone()[0]==0


@pytest.mark.asyncio
async def test_shared_checkpoint_failure_prevents_submission(shared,rig,tmp_path,monkeypatch):
    t,_,_=rig
    async def fail(self,state):raise ValueError('checkpoint failed')
    monkeypatch.setattr(WalletCoordinator,'checkpoint',fail)
    with pytest.raises(ValueError,match='checkpoint failed'):
        await call(t,tmp_path/'no-submit.json')
    assert not t.invokes
