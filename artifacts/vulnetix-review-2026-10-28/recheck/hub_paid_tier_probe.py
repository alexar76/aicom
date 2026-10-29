"""Offline reproduction of the sixth goal in the current Vulnetix comment.
Run from repo root: PYTHONPATH=aimarket-hub:oracles/core .venv/bin/python <this file>
Only synthetic credentials and temporary databases; no external calls.
"""
import importlib.util
import json
from pathlib import Path
import tempfile

from pytest import MonkeyPatch
from fastapi.testclient import TestClient
from oracle_core import Capability, OracleSpec, create_app
from oracle_core.price_gate import PriceGate, HubRequestVerifier
from oracle_core.tiers import PaidTierPolicy

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('provider_channel_test_helpers', ROOT/'aimarket-hub/tests/test_provider_channel_ref.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

with tempfile.TemporaryDirectory(prefix='aicom-paid-tier-recheck-') as temporary, MonkeyPatch.context() as patch:
    base = Path(temporary)
    for key, value in {
        'AIMARKET_AUTO_CRAWL':'0', 'AIMARKET_UPDATE_CHECK':'0',
        'AIMARKET_DEPOSIT_CLAIMS_DIR':str(base/'claims'),
        'AIMARKET_SIGN_PROVIDER_REQUESTS':'1',
    }.items():
        patch.setenv(key, value)
    seen = helpers._capture_provider(patch)
    with helpers._hub(patch, base, helpers._cap(invoke_url='https://provider.example/ai-market/v2/invoke')) as hub:
        channel = helpers._open(hub)
        response = helpers._invoke(hub, channel['channel_id'], channel['channel_secret'], input={'T':101})
        assert response.status_code == 200, response.text
    assert len(seen) == 1
    headers = seen[0]
    assert 'X-AIMarket-Hub-Signature' in headers
    assert not any(k.lower() == 'x-aimarket-paid-tier' for k in headers)
    signer = helpers.Signer(base/'hub/key')
    hub_url = headers['X-AIMarket-Hub-Signer']
    audience = headers['X-AIMarket-Hub-Audience']
    verifier = HubRequestVerifier({hub_url:[signer.public_key_b64]}, [audience])
    # Use a synthetic oracle that costs no CPU, but has a real free-tier ceiling.
    oracle = OracleSpec(name='Audit oracle', product_id='prod-prov', description='audit',
        public_url=audience, categories=['oracle'], signing_key_path=str(base/'oracle-key'),
        capabilities=[Capability(capability_id='prov.echo@v1', product_id='prod-prov',
            description='audit', price_per_call_usd=0.25, free_tier_max={'T':100},
            input_schema={'type':'object','properties':{'T':{'type':'integer'}}},
            handler=lambda data:{'T':data['T']})])
    policy = PaidTierPolicy.from_env({'ORACLE_PAID_TIER_SECRET':'audit-only-synthetic-tier-grant'})
    gate = PriceGate('enforce', verifier)
    body = {'capability_id':'prov.echo@v1','product_id':'prod-prov','input':{'T':101}}
    with TestClient(create_app(oracle, paid_tier=policy, price_gate=gate, call_log=False)) as client:
        denied = client.post('/ai-market/v2/invoke',json=body,headers=headers)
        assert denied.status_code == 402, denied.text
        assert denied.json()['free_tier']['max'] == 100, denied.text
        # The same oracle serves the request when explicitly given the tier grant.
        allowed = client.post('/ai-market/v2/invoke',json=body,
            headers={'X-AIMarket-Paid-Tier':'audit-only-synthetic-tier-grant'})
        assert allowed.status_code == 200, allowed.text
    result = {'goal':6, 'status':'open_reproduced',
        'hub_version':'3.16.0', 'actual_hub_request_signed':True,
        'actual_hub_request_has_paid_tier_header':False,
        'oracle_with_trusted_hub_signature_http_status':denied.status_code,
        'oracle_with_explicit_tier_grant_http_status':allowed.status_code,
        'credentials':'synthetic only', 'external_requests':0}
    (Path(__file__).parent/'hub-paid-tier-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
