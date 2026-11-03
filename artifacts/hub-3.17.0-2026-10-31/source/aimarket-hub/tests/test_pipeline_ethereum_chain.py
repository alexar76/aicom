"""Real local chain-id 1 EIP-3009 purchase through the SDK and Hub."""
import asyncio,json
import httpx
import pytest
from eth_account import Account
from tests import test_topup_chain as kit
from tests._mandate_kit import hub
from tests.test_studio_paid import listing,node
from aimarket_hub.pipeline_client import run_pipeline
pytestmark=kit.pytestmark


def test_sdk_ethereum_transaction_and_exact_seller_payment(monkeypatch,tmp_path):
    monkeypatch.setattr(kit,'BASE_CHAIN_ID',1)
    generator=kit.chain.__wrapped__();chain=next(generator)
    try:
        rpc,token=chain['rpc'],chain['token']
        monkeypatch.setenv('AIMARKET_X402_CHAIN','ethereum')
        monkeypatch.setenv('AIMARKET_X402_ASSET',token)
        monkeypatch.setenv('AIMARKET_X402_ENABLED','1')
        monkeypatch.setenv('AIMARKET_X402_ACCEPT','1')
        monkeypatch.setenv('AIMARKET_SETTLE_RPC_URL',rpc)
        monkeypatch.setenv('AIMARKET_MARKET_FEE_BPS','0')
        monkeypatch.setenv('AIMARKET_WALLET_STATE_DIR',str(tmp_path/'wallets'))
        async def local_budget(client,state):
            state['fees']={'gas':300000,'max_fee':2_000_000_000,'priority_fee':1_000_000_000}
            return {'native_fee_bound_wei':str(300000*2_000_000_000)}
        monkeypatch.setattr('aimarket_hub.pipeline_client._budget',local_budget)
        before=kit._usdc_balance(rpc,token,kit._DEPLOYER[0])
        with hub(monkeypatch,tmp_path) as (h,db):
            listing(db,payout=kit._DEPLOYER[0])
            class Routed(httpx.AsyncBaseTransport):
                def __init__(self):self.asgi=httpx.ASGITransport(app=h.app);self.net=httpx.AsyncHTTPTransport()
                async def handle_async_request(self,request):
                    if request.url.host=='hub.test':
                        if request.url.path.endswith('/invoke'):
                            async with httpx.AsyncClient() as c:
                                await c.post(rpc,json={'jsonrpc':'2.0','id':1,'method':'anvil_mine','params':['0x1']})
                        return await self.asgi.handle_async_request(request)
                    return await self.net.handle_async_request(request)
                async def aclose(self):await self.net.aclose()
            async def run():
                async with httpx.AsyncClient(transport=Routed()) as c:
                    profile=dict(chain_id=1,token_contract=token,decimals=6,eip712_name='USD Coin',eip712_version='2',usd_pegged=True,authorization='EIP-3009')
                    return await run_pipeline({'nodes':[node()]},hub='https://hub.test',signer=Account.from_key(kit._STRANGER[1]),rpc_url=rpc,gas_mode='buyer',max_total_usd='1',state_path=tmp_path/'eth.json',accepted_assets=[profile],client=c,poll_interval_s=.05,timeout_s=15)
            result=asyncio.run(run());assert result['success'],result
            assert result['bill_of_materials']['steps'][0]['terms']['chain_id']==1
        assert kit._usdc_balance(rpc,token,kit._DEPLOYER[0])-before==4000
    finally:generator.close()
