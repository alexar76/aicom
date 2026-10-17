import copy
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.procurement_contract import CONTRACT, digest
from services import diagnosis_provider as provider


@pytest.fixture
def packet():
    finding = {'file': 'app/main.py', 'title': 'Division by zero', 'severity': 'high'}
    p = {'contract': CONTRACT, 'issue': digest({'file': finding['file'], 'title': finding['title']}),
         'finding': finding, 'files': {'app/main.py': 'def divide(x):\n    return 1 / x\n'},
         'acceptance': 'Return a diagnosis.'}
    p['fingerprint'] = digest(p)
    return p


def test_auth_and_packet_binding(monkeypatch, packet):
    monkeypatch.setenv('DIAGNOSIS_HUB_TOKEN', 'test-token')
    client = TestClient(provider.app)
    body = {'product_id': 'aicom-diagnostics', 'capability_id': 'aicom.diagnose@v1', 'input': packet}
    assert client.post('/diagnose', json=body).status_code == 403
    packet['files']['app/main.py'] = 'altered source'
    assert client.post('/diagnose', json=body, headers={'X-AIMarket-Internal-Token': 'test-token'}).status_code == 422


def test_reservation_survives_failure_and_enforces_budget(tmp_path, monkeypatch, packet):
    monkeypatch.setenv('DIAGNOSIS_STATE', str(tmp_path / 'budget.db'))
    monkeypatch.setenv('DIAGNOSIS_DAILY_USD', '0.05')
    assert provider.reserve(packet, Decimal('0.03')) is None
    with pytest.raises(HTTPException) as error:
        provider.reserve(packet, Decimal('0.03'))
    assert error.value.status_code == 409
    different = copy.deepcopy(packet)
    different['fingerprint'] = 'different'
    with pytest.raises(HTTPException) as error:
        provider.reserve(different, Decimal('0.03'))
    assert error.value.status_code == 429


def test_accepts_valid_packet_and_rejects_oversize(packet):
    provider.validate_packet(packet)
    packet['files']['app/main.py'] = 'x' * 16001
    packet['fingerprint'] = digest({k: v for k, v in packet.items() if k != 'fingerprint'})
    with pytest.raises(ValueError, match='source too large'):
        provider.validate_packet(packet)


@pytest.mark.asyncio
async def test_service_binds_model_report_and_caches_without_second_inference(tmp_path, monkeypatch, packet):
    monkeypatch.setenv('DIAGNOSIS_STATE', str(tmp_path / 'budget.db'))
    monkeypatch.setenv('DIAGNOSIS_MODEL', 'test/model')
    monkeypatch.setenv('DIAGNOSIS_MODEL_KEY', 'test-key')
    calls = []
    class Response:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self): return self.body
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url):
            return Response({'data': [{'id': 'test/model', 'pricing': {'prompt': '0.000001', 'completion': '0.000001'}}]})
        async def post(self, url, **kwargs):
            import json
            calls.append(url)
            report = {'fingerprint': 'model-hallucinated-hash', 'diagnosis': [{
                'file': 'app/main.py', 'line': 2, 'evidence': 'return 1 / x',
                'explanation': 'Zero input divides by zero.', 'suggest_check': 'Test divide(0).'}]}
            return Response({'choices': [{'finish_reason': 'stop', 'message': {'content': '```json\n' + json.dumps(report) + '\n```'}}]})
    monkeypatch.setattr(provider.httpx, 'AsyncClient', lambda **kwargs: Client())
    result = await provider.diagnose(packet)
    assert result['result']['fingerprint'] == packet['fingerprint']
    assert result['result']['diagnosis'][0]['suggested_check'] == 'Test divide(0).'
    assert await provider.diagnose(packet) == result
    assert len(calls) == 1


def test_response_signature_is_bound_to_request(tmp_path, monkeypatch, packet):
    import base64
    import json
    from aimarket_hub.supply_security import _bound_response_canonical
    monkeypatch.setenv('DIAGNOSIS_SIGNING_KEY', str(tmp_path / 'provider.key'))
    body = {'result': {'diagnosis': [{'explanation': 'Source-bound diagnosis.'}]}}
    response = provider.signed_response(packet, body)
    signature = base64.b64decode(response.headers['X-Provider-Signature'])
    canonical = _bound_response_canonical('aicom.diagnose@v1', 'aicom-diagnostics', packet, body['result'])
    provider.signing_key().public_key().verify(signature, canonical.encode())
    changed = dict(packet, fingerprint='changed')
    from cryptography.exceptions import InvalidSignature
    with pytest.raises(InvalidSignature):
        provider.signing_key().public_key().verify(signature, _bound_response_canonical(
            'aicom.diagnose@v1', 'aicom-diagnostics', changed, body['result']).encode())
