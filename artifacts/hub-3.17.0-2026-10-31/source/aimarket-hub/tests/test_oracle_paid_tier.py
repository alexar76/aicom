"""Paid-tier grants must follow actual funding and the exact destination.

The route tests use the real hub ledger and safe_post; only DNS/HTTP is local.
"""
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub import oracle_paid_tier as tier, outbound_http as outbound
from tests.test_provider_channel_ref import _cap, _hub, _open, _invoke, _balance
from tests.test_provider_request_auth import _sold_peer, _paid_invoke

URL = 'https://oracle.example/ai-market/v2/invoke'
SECRET_ENV = 'TEST_ORACLE_TIER_GRANT'
SECRET = 'test-only-tier-' + 'grant-value'
REAL_CLIENT = httpx.AsyncClient


def configure(monkeypatch, url=URL, **options):
    monkeypatch.setenv(tier.CONFIG_ENV, json.dumps({url: {'secret_env': SECRET_ENV, **options}}))
    monkeypatch.setenv(SECRET_ENV, SECRET)


def test_default_and_unfunded_do_not_read_a_credential(monkeypatch):
    monkeypatch.delenv(tier.CONFIG_ENV, raising=False)
    assert tier.headers_for(URL, transport_url=URL, admitted=True) == {}
    configure(monkeypatch)
    assert tier.headers_for(URL, transport_url=URL, admitted=False) == {}


@pytest.mark.parametrize('url', [
    URL+'/', URL+'?x=1', URL+'#frag', URL.replace('oracle.', 'other.'),
    URL.replace('oracle.example', 'oracle.example.evil.test'),
    URL.replace('oracle.example', 'oracle.example@evil.test'),
    URL.replace('https:', 'http:'), URL.replace('/ai-market/', '/other/../ai-market/'),
    URL.replace('/ai-market/', '/%61i-market/'), URL+'\n',
])
def test_no_scope_widening(monkeypatch, url):
    configure(monkeypatch)
    assert tier.headers_for(url, transport_url=url, admitted=True) == {}


@pytest.mark.parametrize('raw', ['bad json', '[]', 'null', '"value"', '{"x":1,"x":2}'])
def test_malformed_config_fails_closed(monkeypatch, raw):
    monkeypatch.setenv(tier.CONFIG_ENV, raw)
    assert tier.headers_for(URL, transport_url=URL, admitted=True) == {}


@pytest.mark.parametrize('secret', ['', 'a\rb', 'a\nb', 'a\tb', 'nonascii-€'])
def test_missing_or_invalid_secret_fails_closed(monkeypatch, secret):
    configure(monkeypatch)
    monkeypatch.setenv(SECRET_ENV, secret)
    assert tier.headers_for(URL, transport_url=URL, admitted=True) == {}


def test_each_oracle_gets_only_its_own_credential(monkeypatch):
    second = 'https://second.example/ai-market/v2/invoke'
    configure(monkeypatch)
    monkeypatch.setenv('TEST_SECOND_TIER', SECRET+'-second')
    monkeypatch.setenv(tier.CONFIG_ENV, json.dumps({
        URL:{'secret_env':SECRET_ENV}, second:{'secret_env':'TEST_SECOND_TIER'}}))
    assert tier.headers_for(URL, transport_url=URL, admitted=True) == {tier.HEADER:SECRET}
    assert tier.headers_for(second, transport_url=second, admitted=True) == {tier.HEADER:SECRET+'-second'}
    assert tier.headers_for(URL, transport_url=second, admitted=True) == {}


def test_rewrite_requires_both_endpoints_and_http_requires_opt_in(monkeypatch):
    local = 'http://127.0.0.1:9000/ai-market/v2/invoke'
    docker = 'http://oracle:9000/ai-market/v2/invoke'
    config = {local:{'secret_env':SECRET_ENV}}
    monkeypatch.setenv(SECRET_ENV, SECRET)
    monkeypatch.setenv(tier.CONFIG_ENV, json.dumps(config))
    assert tier.headers_for(local, transport_url=docker, admitted=True) == {}
    config[docker] = {'secret_env':SECRET_ENV}
    monkeypatch.setenv(tier.CONFIG_ENV, json.dumps(config))
    assert tier.headers_for(local, transport_url=docker, admitted=True) == {}
    config[docker]['allow_http'] = True
    monkeypatch.setenv(tier.CONFIG_ENV, json.dumps(config))
    assert tier.headers_for(local, transport_url=docker, admitted=True) == {tier.HEADER:SECRET}


@pytest.mark.parametrize('overrides,expected', [
    ({}, True), ({'reserved':False}, False), ({'hold_rail':'routing_fee'}, False),
    ({'price':0}, False), ({'price':float('nan')}, False), ({'sandbox':True}, False),
    ({'hold_rail':'credits'}, True),
    ({'reserved':False,'x402_accepted':{'ok':True}}, True),
    ({'reserved':False,'x402_accepted':{'ok':False}}, False),
])
def test_only_funded_work_gets_a_grant(overrides, expected):
    args = dict(price=0.25, sandbox=False, reserved=True, hold_rail='channel', x402_accepted=None)
    args.update(overrides)
    assert tier.funded(**args) is expected


def transport(monkeypatch, backend):
    options = []
    async def prepare(url, *, invoke=False):
        # DNS only: real safe_post still selects auth and controls redirects/proxies.
        return outbound.resolve_invoke_url(url) if invoke else url, {}, {}
    def client(**kwargs):
        options.append(kwargs)
        return REAL_CLIENT(transport=backend, **kwargs)
    monkeypatch.setattr(outbound, 'prepare_safe_request_async', prepare)
    monkeypatch.setattr(outbound.httpx, 'AsyncClient', client)
    return options


@pytest.mark.asyncio
async def test_grant_is_not_forwarded_on_redirect_and_ignores_proxy_env(monkeypatch):
    configure(monkeypatch)
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(302, headers={'Location':'https://other.example/steal'})
    options = transport(monkeypatch, httpx.MockTransport(receive))
    response = await outbound.safe_post(URL, json={}, oracle_paid=True)
    assert response.status_code == 302 and len(seen) == 1
    assert seen[0].headers[tier.HEADER] == SECRET
    assert options == [{'timeout':30.0, 'follow_redirects':False, 'trust_env':False}]


@pytest.mark.asyncio
async def test_unadmitted_supplied_header_is_stripped(monkeypatch):
    configure(monkeypatch)
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={})
    transport(monkeypatch, httpx.MockTransport(receive))
    await outbound.safe_post(URL, headers={'x-AImarket-paid-tier':'buyer-forged'})
    assert tier.HEADER not in seen[0].headers


def test_paid_hub_to_real_oracle_lifts_ceiling_without_ip_trust(monkeypatch, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'oracles/core'))
    pytest.importorskip('oracle_core')
    from oracle_core import OracleSpec, Capability, create_app
    from oracle_core.tiers import PaidTierPolicy
    from oracle_core.price_gate import PriceGate
    configure(monkeypatch)
    calls = []
    spec = OracleSpec(name='Tier test', product_id='prod-prov', description='test', public_url=URL,
        categories=['oracle'], signing_key_path=str(tmp_path/'oracle.key'), capabilities=[
            Capability(capability_id='prov.echo@v1', product_id='prod-prov', description='test',
                price_per_call_usd=0.25, free_tier_max={'T':100},
                input_schema={'type':'object','properties':{'T':{'type':'integer'}}},
                handler=lambda data: calls.append(data) or {'did':data['T']})])
    oracle = create_app(spec, paid_tier=PaidTierPolicy.from_env({'ORACLE_PAID_TIER_SECRET':SECRET}),
                        price_gate=PriceGate.from_env(URL, {'ORACLE_PRICE_GATE':'enforce'}), call_log=False)
    transport(monkeypatch, httpx.ASGITransport(app=oracle))
    with _hub(monkeypatch, tmp_path, _cap(invoke_url=URL)) as hub:
        channel = _open(hub)
        response = _invoke(hub, channel['channel_id'], channel['channel_secret'], input={'T':101})
        assert response.status_code == 200, response.text
        assert calls == [{'T':101}]
        assert _balance(channel['channel_id']) == pytest.approx(4.75)
        assert SECRET not in response.text
        # A broken oracle credential fails the call and returns its reservation.
        monkeypatch.setenv(SECRET_ENV, SECRET+'-wrong')
        refused = _invoke(hub, channel['channel_id'], channel['channel_secret'], input={'T':102})
        assert refused.status_code != 200
        assert _balance(channel['channel_id']) == pytest.approx(4.75)
        assert calls == [{'T':101}]


def test_bad_payment_cannot_reach_oracle(monkeypatch, tmp_path):
    configure(monkeypatch)
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'success':True, 'result':{}})
    transport(monkeypatch, httpx.MockTransport(receive))
    with _hub(monkeypatch, tmp_path, _cap(invoke_url=URL)) as hub:
        channel = _open(hub)
        assert _invoke(hub, channel['channel_id'], 'wrong-secret').status_code == 402
    assert seen == []


def test_free_local_call_does_not_get_grant_even_with_buyer_header(monkeypatch, tmp_path):
    configure(monkeypatch)
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'success':True, 'result':{}})
    transport(monkeypatch, httpx.MockTransport(receive))
    with _hub(monkeypatch, tmp_path, _cap(invoke_url=URL, price_per_call_usd=0)) as hub:
        response = hub.post('/ai-market/v2/invoke', headers={tier.HEADER:'forged'}, json={
            'product_id':'prod-prov','capability_id':'prov.echo@v1','source_hub':'local','input':{}})
        assert response.status_code == 200, response.text
    assert tier.HEADER not in seen[0].headers


@pytest.mark.parametrize('sells,price,expected', [(True,0.02,True), (False,0.02,False), (True,0,False)])
def test_federated_grant_requires_selling_and_funded_price(tmp_path, monkeypatch, sells, price, expected):
    app, _, out = _sold_peer(tmp_path, monkeypatch, sells=sells, price=price)
    with TestClient(app) as client:
        response = _paid_invoke(client)
    assert response.status_code == 200, response.text
    assert out.post_oracle_paid == [expected]


def test_sandbox_trial_keeps_the_free_tier(monkeypatch, tmp_path):
    from aimarket_hub import sandbox_trials
    configure(monkeypatch)
    monkeypatch.setattr(sandbox_trials, '_ledger', sandbox_trials.SandboxTrialLedger(str(tmp_path/'trials.db')))
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'success':True, 'result':{}})
    transport(monkeypatch, httpx.MockTransport(receive))
    with _hub(monkeypatch, tmp_path, _cap(invoke_url=URL)) as hub:
        response = hub.post('/ai-market/v2/invoke', headers={'X-AIMarket-Sandbox-Visitor':'vis_tier_trial'}, json={
            'product_id':'prod-prov','capability_id':'prov.echo@v1','source_hub':'local','input':{}})
        assert response.status_code == 200, response.text
    assert tier.HEADER not in seen[0].headers


def test_credit_hold_authorizes_grant(monkeypatch, tmp_path):
    from tests.test_credits_invoke import _hub as credit_hub
    configure(monkeypatch)
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'success':True, 'result':{}})
    transport(monkeypatch, httpx.MockTransport(receive))
    with credit_hub(monkeypatch, tmp_path, AIMARKET_CREDITS_ENABLED='1',
                    AIMARKET_CREDITS_OPEN_SIGNUP='1', AIMARKET_CREDITS_FREE_GRANT_USD='1') as (hub, db):
        db.upsert_capability(_cap(invoke_url=URL, trust_score=0.8))
        key = hub.post('/ai-market/v2/accounts', json={'label':'tier-test'}).json()['api_key']
        response = hub.post('/ai-market/v2/invoke', headers={'X-API-Key':key}, json={
            'product_id':'prod-prov','capability_id':'prov.echo@v1','source_hub':'local','input':{}})
        assert response.status_code == 200, response.text
        account = hub.get('/ai-market/v2/account', headers={'X-API-Key':key}).json()
        assert account['spent_usd'] == pytest.approx(0.25)
    assert seen[0].headers[tier.HEADER] == SECRET


def test_verified_x402_authorizes_grant(monkeypatch, tmp_path):
    from tests.test_provider_payer_statement import _local_hub, _x402_settled, _invoke as invoke_x402, OTHER
    configure(monkeypatch, url='https://iot.example/ai-market/v2/invoke')
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'ok':True, 'output':{'switched':True}})
    transport(monkeypatch, httpx.MockTransport(receive))
    with _local_hub(monkeypatch, tmp_path, payout='0x'+'5e'*20, AIMARKET_X402_ACCEPT='1',
                    AIMARKET_CREDITS_ENABLED='0', AIMARKET_PAYMENT_RECIPIENT='0x'+'cd'*20) as (hub, _, _):
        _x402_settled(monkeypatch, price=0.05, authorizer=OTHER)
        quote = invoke_x402(hub, {})
        assert quote.status_code == 402 and not seen
        response = invoke_x402(hub, {'X-Payment':'0x'+'11'*32, 'X-Payment-Nonce':quote.json()['nonce'],
                                    'X-Payment-Secret':quote.json()['payment_secret']})
        assert response.status_code == 200, response.text
    assert seen[0].headers[tier.HEADER] == SECRET


@pytest.mark.asyncio
async def test_paid_transport_keeps_checked_ip_host_and_tls_name(monkeypatch):
    import socket
    configure(monkeypatch)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda host, port, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))])
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'ok':True})
    monkeypatch.setattr(outbound.httpx, 'AsyncClient', lambda **kw:
        REAL_CLIENT(transport=httpx.MockTransport(receive), **kw))
    await outbound.safe_post(URL, json={}, oracle_paid=True, invoke=True)
    request = seen[0]
    assert request.url.host == '93.184.216.34'
    assert request.headers['Host'] == 'oracle.example'
    assert request.extensions['sni_hostname'] == 'oracle.example'
    assert request.headers[tier.HEADER] == SECRET
