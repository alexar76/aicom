"""Real EIP-3009 transfer with a buyer that has zero ETH; Anvil gas sponsor."""
import pytest
from eth_account import Account
from tests.test_topup_chain import chain, wired, pytestmark, _STRANGER, _DEPLOYER, _OPERATOR, _usdc_balance, _mine, _rpc
from tests._mandate_kit import hub
from tests.test_studio_paid import listing, node


@pytest.mark.parametrize("with_refund", [False, True])
def test_sponsor_pays_real_chain_gas_and_buyer_only_usdc(wired, monkeypatch, tmp_path, with_refund):
    from aimarket_hub import pipeline_relay
    from aimarket_hub.pipeline_relay import PipelineRelay
    rpc, token = wired['rpc'], wired['token']
    monkeypatch.setattr(pipeline_relay, 'BASE_USDC', token.lower())
    monkeypatch.setenv('AIMARKET_X402_ENABLED', '1')
    monkeypatch.setenv('AIMARKET_X402_ACCEPT', '1')
    monkeypatch.setenv('AIMARKET_MARKET_FEE_BPS', '0')
    # The local chain has no Chainlink/L1 fee oracle. Those are tested separately;
    # all token signatures, broadcasts, authorizer logs and receipt checks are real.
    async def local_budget(client, state):
        state['fees'] = {'gas': 300000, 'max_fee': 2_000_000_000, 'priority_fee': 1_000_000_000}
        return {'native_fee_bound_wei': str(300000*2_000_000_000)}
    monkeypatch.setattr('aimarket_hub.pipeline_client._budget', local_budget)
    _rpc(rpc, 'anvil_setBalance', [_STRANGER[0], '0x0'])
    buyer_nonce = _rpc(rpc, 'eth_getTransactionCount', [_STRANGER[0], 'latest'])
    seller_before = _usdc_balance(rpc, token, _DEPLOYER[0])
    buyer_before = _usdc_balance(rpc, token, _STRANGER[0])
    sponsor_before = int(_rpc(rpc, 'eth_getBalance', [_OPERATOR[0], 'latest']), 16)
    with hub(monkeypatch, tmp_path) as (client, db):
        listing(db, payout=_DEPLOYER[0])
        provider = client.app.state.pipeline_provider
        provider.relay = PipelineRelay(provider.conn, signer=Account.from_key(_OPERATOR[1]), rpc_url=rpc, daily_wei=10**18)
        q = client.post('/studio/prepare-pipeline', json={'nodes': [node()], 'wallet': _STRANGER[0],
                                                        'gas_mode': 'required', 'max_budget_usd': 1}).json()
        assert q['gas_sponsorship']['enabled'], q
        sig = Account.sign_typed_data(_STRANGER[1], full_message=q['offers'][0]['authorization']).signature
        request = {'product_id': 'hephaestus', 'capability_id': 'pipeline.run@v1', 'input': {
            'run_id': q['run_id'], 'access_token': q['access_token'], 'authorizations': {'read': '0x'+sig.hex()}}}
        for _ in range(10):
            result = client.post('/ai-market/v2/invoke', json=request).json()
            if result['status'] in ('completed', 'failed'):
                break
            _mine(rpc)
        assert result['success'], result
        assert client.post('/ai-market/v2/invoke', json=request).json() == result
        assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n'] == 1
        if with_refund:
            url='/studio/paid-runs/'+q['run_id']+'/refunds/read'
            headers={'X-Studio-Run-Token':q['access_token']}
            quote=client.post(url+'/prepare',headers=headers).json()
            auth=Account.sign_typed_data(_DEPLOYER[1],full_message=quote['offer']['authorization']).signature
            approval={'authorization':'0x'+auth.hex()}
            for _ in range(10):
                refunded=client.post(url,headers=headers,json=approval).json()
                if refunded['status']=='refunded':break
                _mine(rpc)
            assert refunded['status']=='refunded',refunded
            assert client.post(url,headers=headers,json=approval).json()==refunded
            assert client.post('/ai-market/v2/invoke',json=request).json()==result
            assert db._conn.execute('SELECT COUNT(*) AS n FROM pipeline_relay_payments').fetchone()['n']==2
    assert _usdc_balance(rpc, token, _DEPLOYER[0])-seller_before == (0 if with_refund else 4000)
    assert buyer_before-_usdc_balance(rpc, token, _STRANGER[0]) == (0 if with_refund else 4000)
    assert _rpc(rpc, 'eth_getBalance', [_STRANGER[0], 'latest']) == '0x0'
    assert _rpc(rpc, 'eth_getTransactionCount', [_STRANGER[0], 'latest']) == buyer_nonce
    assert int(_rpc(rpc, 'eth_getBalance', [_OPERATOR[0], 'latest']), 16) < sponsor_before
