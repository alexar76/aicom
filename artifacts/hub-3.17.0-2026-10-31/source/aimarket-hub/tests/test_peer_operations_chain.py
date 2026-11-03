"""Independent seller settlement on local Anvil: actual contracts, signatures and receipts."""
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
import pytest
from eth_account import Account

from aimarket_hub import pipeline_payments
from aimarket_hub.models import Peer
from tests._mandate_kit import hub
from tests.test_studio_paid import listing, node
from tests.test_studio_paid_chain import send
from tests.test_topup_chain import chain, wired, pytestmark, _STRANGER, _DEPLOYER, _usdc_balance, _mine


@pytest.mark.parametrize('lost_reply', [False, True])
def test_two_independent_hubs_settle_once_on_chain(wired, monkeypatch, tmp_path, lost_reply):
    monkeypatch.setenv('AIMARKET_AUTO_CRAWL', '0')
    monkeypatch.setenv('AIMARKET_X402_ENABLED', '1')
    monkeypatch.setenv('AIMARKET_X402_ACCEPT', '1')
    monkeypatch.setenv('AIMARKET_MARKET_FEE_BPS', '0')
    rpc, token = wired['rpc'], wired['token']
    seller_url = 'https://seller.test'
    seller_before = _usdc_balance(rpc, token, _DEPLOYER[0])
    buyer_before = _usdc_balance(rpc, token, _STRANGER[0])
    with hub(monkeypatch, tmp_path) as (buyer, bdb), hub(monkeypatch, tmp_path) as (seller, sdb):
        seller_ops = seller.app.state.seller_operations
        listing(sdb, payout=_DEPLOYER[0])
        listing(bdb, source=seller_url, payout=_DEPLOYER[0])
        provider = buyer.app.state.pipeline_provider
        provider.studio.route_ok = lambda cap: True
        bdb.upsert_peer(Peer(url=seller_url, name='seller', trusted=True, trust_score=1,
            public_key=seller_ops.signer.public_key_b64, pq_public_key=seller_ops.signer.pq_public_key_b64,
            last_crawl=datetime.now(timezone.utc).isoformat()))
        assert not provider.studio.config.sells_on_behalf_of(seller_url)
        assert not provider.studio.config.peer_api_key(seller_url)
        calls=[]
        async def peer_http(method, url, *, body=None, token=None):
            calls.append((method, urlsplit(url).path))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=seller.app),base_url=seller_url) as c:
                r=await c.request(method,url,json=body,headers={'X-Operation-Token':token} if token else {})
                r.raise_for_status()
                if lost_reply and url.endswith('/invoke') and r.json().get('success'):
                    raise httpx.ReadTimeout('seller completed but HTTP reply lost')
                return r.json()
        provider.studio.remote.request=peer_http
        graph=[{**node(), 'source_hub':seller_url}]
        q=buyer.post('/studio/prepare-pipeline',json={'nodes':graph,'wallet':_STRANGER[0],'max_budget_usd':1}).json()
        assert q['ready'], q
        offer=q['offers'][0]
        signature=Account.sign_typed_data(_STRANGER[1],full_message=offer['authorization']).signature
        tx=pipeline_payments.payment_transaction(offer,_STRANGER[0],'0x'+signature.hex().removeprefix('0x'))
        tx.pop('from',None)
        raw=send(rpc,tx,broadcast=False)
        request={'product_id':'hephaestus','capability_id':'pipeline.run@v1','input':{
            'run_id':q['run_id'],'access_token':q['access_token'],'transactions':{'read':raw}}}
        for _ in range(10):
            result=buyer.post('/ai-market/v2/invoke',json=request).json()
            if result['status'] in ('completed','failed'): break
            _mine(rpc)
        assert result['success'], result
        assert result['final_result']=={'reading':7}
        assert result['bill_of_materials']['total_usd']==.004
        assert len(result['subcontracting']['nodes'])==2
        assert buyer.post('/ai-market/v2/invoke',json=request).json()==result
        assert len([p for m,p in calls if p.endswith('/invoke')])==1
        nonce=offer['seller_operation']['invoice']['nonce']
        assert seller_ops.studio.invoices.get(nonce)['consumed_at']
        assert provider.studio.invoices.get(nonce) is None
    assert _usdc_balance(rpc,token,_DEPLOYER[0])-seller_before==4000
    assert buyer_before-_usdc_balance(rpc,token,_STRANGER[0])==4000
