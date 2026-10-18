"""Adapter failure boundaries; n8n is mocked here, unlike run.py check."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from aimarket_hub.signing import Signer
from aimarket_hub.supply_security import _bound_response_canonical
from adapter import create_app

BODY = json.loads((Path(__file__).parent / "request.json").read_text())
TOKEN = "test-hub-token"
HEADERS = {"X-AIMarket-Internal-Token": TOKEN}


def client(tmp_path):
    return TestClient(create_app(state_dir=tmp_path, hub_token=TOKEN, webhook_token="test-webhook"))


def mock_n8n(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler)))


def test_authentication_input_and_body_limit(tmp_path):
    with client(tmp_path) as c:
        assert c.post("/invoke", json=BODY).status_code == 401
        assert c.post("/invoke", json={**BODY, "input": {"items": []}}, headers=HEADERS).status_code == 422
        assert c.post("/invoke", json={**BODY, "capability_id": "other@v1"}, headers=HEADERS).status_code == 422
        assert c.post("/invoke", content="x" * 17000, headers=HEADERS).status_code == 413


@pytest.mark.parametrize("upstream_status,payload,expected", [
    (200, {"message": "Workflow was started"}, 502),
    (401, {"error": "unauthorised"}, 502),
    (500, {"error": "broken"}, 502),
    (422, {"error": "invalid_input"}, 422),
    (302, {}, 502),
])
def test_n8n_failures_do_not_become_signed_success(tmp_path, monkeypatch, upstream_status, payload, expected):
    mock_n8n(monkeypatch, lambda request: httpx.Response(upstream_status, json=payload))
    with client(tmp_path) as c:
        response = c.post("/invoke", json=BODY, headers=HEADERS)
        assert response.status_code == expected
        assert "X-Provider-Signature" not in response.headers


def test_timeout(tmp_path, monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("simulated", request=request)
    mock_n8n(monkeypatch, timeout)
    with client(tmp_path) as c:
        assert c.post("/invoke", json=BODY, headers=HEADERS).status_code == 504


def test_signature_binding_and_private_upstream_credential(tmp_path, monkeypatch):
    result = {"kind": "order_check", "schema_version": 1, "demo": True,
              "reservation_created": False, "order_created": False, "subtotal_minor": 3430}
    def handler(request):
        assert request.headers["X-Workshop-Key"] == "test-webhook"
        assert "X-AIMarket-Internal-Token" not in request.headers
        assert json.loads(request.content) == BODY["input"]
        return httpx.Response(200, json=result)
    mock_n8n(monkeypatch, handler)
    with client(tmp_path) as c:
        response = c.post("/invoke", json=BODY, headers=HEADERS)
        assert response.status_code == 200
        pubkey = c.get("/healthz").json()["provider_pubkey"]
        sig = response.headers["X-Provider-Signature"]
        assert Signer.verify(pubkey, sig, _bound_response_canonical(
            BODY["capability_id"], BODY["product_id"], BODY["input"], result))
        assert not Signer.verify(pubkey, sig, _bound_response_canonical(
            BODY["capability_id"], BODY["product_id"], {"items": []}, result))
