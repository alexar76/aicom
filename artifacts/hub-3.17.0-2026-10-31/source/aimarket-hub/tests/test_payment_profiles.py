import json,time
from copy import deepcopy
import httpx
import pytest
from aimarket_hub.payment_profiles import asset_policy,USDC
from aimarket_hub.native_price import ETHEREUM_ETH_USD,native_price
from aimarket_hub.pipeline_client import _rpc
from tests.test_pipeline_client import rig,call
from tests.test_studio_paid import setup


class EthereumTransport(httpx.AsyncBaseTransport):
    def __init__(self,inner):self.inner=inner;self.calls=[]
    async def handle_async_request(self,request):
        if request.url.host in ('rpc.test','eth.drpc.org','ethereum-rpc.publicnode.com'):
            p=json.loads(request.content);m=p['method'];self.calls.append(p)
            if m=='eth_chainId':value=hex(1)
            elif m=='eth_getBlockByNumber':value={'number':'0x12345','timestamp':hex(int(time.time()))}
            elif m=='eth_call' and p['params'][0]['to']==ETHEREUM_ETH_USD:
                now=int(time.time())
                words=[8] if p['params'][0]['data']=='0x313ce567' else [1,3000*10**8,now-5,now-5,1]
                value='0x'+''.join(format(w,'064x') for w in words)
            elif m=='eth_call':value=hex(10**23)
            else:value=hex({'eth_gasPrice':100000000,'eth_getTransactionCount':0,'eth_getBalance':10**18,'eth_estimateGas':90000}[m])
            return httpx.Response(200,json={'result':value})
        return await self.inner.handle_async_request(request)


@pytest.mark.asyncio
async def test_ethereum_usdc_uses_ethereum_price_and_no_l2_fee(rig,tmp_path,monkeypatch):
    t,_,seen=rig;monkeypatch.setenv('AIMARKET_X402_CHAIN','ethereum')
    wrapper=EthereumTransport(t);path=tmp_path/'eth.json'
    result=await call(wrapper,path,max_total_usd='1')
    s=json.loads(path.read_text())
    assert result['success'] and len(seen)==1
    assert s['quote']['offers'][0]['terms']['chain_id']==1
    assert s['quote']['offers'][0]['terms']['token_contract'].lower()==USDC[1]
    assert s['budget_check']['l1_upper_bound_wei']=='0'
    assert s['budget_check']['native_price']['feed']==ETHEREUM_ETH_USD
    assert s['budget_check']['native_price']['sequencer_feed'] is None
    assert all(p.get('params',[{}])[0].get('to')!='0x420000000000000000000000000000000000000F' for p in wrapper.calls if p['method']=='eth_call')


@pytest.mark.asyncio
async def test_explicit_custom_usd_token_and_decimals(rig,tmp_path,monkeypatch):
    t,_,_=rig
    token='0x'+'ab'*20
    monkeypatch.setenv('AIMARKET_X402_CHAIN','ethereum')
    monkeypatch.setenv('AIMARKET_X402_ASSET_SYMBOL','TESTUSD')
    monkeypatch.setenv('AIMARKET_X402_ASSET',token)
    monkeypatch.setenv('AIMARKET_X402_ASSET_DECIMALS','18')
    monkeypatch.setenv('AIMARKET_X402_EIP712_NAME','Test Dollar')
    monkeypatch.setenv('AIMARKET_X402_EIP712_VERSION','1')
    wrapper=EthereumTransport(t)
    with pytest.raises(ValueError,match='allowlist'):
        await call(wrapper,tmp_path/'refused.json')
    assert not t.invokes
    profile=dict(chain_id=1,token_contract=token,decimals=18,eip712_name='Test Dollar',eip712_version='1',usd_pegged=True,authorization='EIP-3009')
    p=tmp_path/'allowed.json';result=await call(wrapper,p,accepted_assets=[profile])
    s=json.loads(p.read_text());assert result['success']
    assert s['budget_check']['service_usd']=='0.004'
    assert 'service_usdc' not in s['budget_check']
    assert s['quote']['offers'][0]['authorization']['domain']['name']=='Test Dollar'


@pytest.mark.parametrize('change',[{'usd_pegged':False},{'authorization':'approve'},{'chain_id':137},{'decimals':True}])
def test_custom_policy_requires_explicit_supported_usd_authorization(change):
    p=asset_policy()[0];p.update(change)
    with pytest.raises(ValueError):asset_policy([p])
