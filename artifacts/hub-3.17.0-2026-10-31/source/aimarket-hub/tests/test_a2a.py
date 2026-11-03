"""A2A 1.0 discovery facade: conformance-shaped responses and abuse boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.delenv("AIMARKET_SKIP_SEED", raising=False)
    config = HubConfig()
    config.hub_name = "Independent AI Hub"
    config.hub_url = "https://independent.example/hub"
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "hub-key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    with TestClient(app) as test_client:
        yield test_client


def _request(*, request_id=1, method="SendMessage", params=None):
    if params is None:
        params = {
            "message": {
                "messageId": "msg-1",
                "role": "ROLE_USER",
                "parts": [{"text": "Find translation tools"}],
            }
        }
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _post(client, payload):
    return client.post("/a2a", json=payload, headers={"A2A-Version": "1.0"})


class TestAgentCard:
    def test_card_declares_only_the_live_jsonrpc_skills(self, client):
        response = client.get("/.well-known/agent-card.json")
        assert response.status_code == 200
        card = response.json()
        assert card["supportedInterfaces"] == [{
            "url": "https://independent.example/hub/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }]
        capabilities = dict(card["capabilities"])
        extensions = capabilities.pop("extensions")
        assert capabilities == {
            "streaming": False,
            "pushNotifications": True,
            "extendedAgentCard": False,
        }
        # x402 is offered, never demanded: credits, mandates and the trial work without it.
        assert extensions == [{
            "uri": "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2",
            "description": extensions[0]["description"],
            "required": False,
        }]
        assert "txHash" in extensions[0]["description"]
        assert [skill["id"] for skill in card["skills"]] == ["marketplace-search", "marketplace-invoke"]
        assert card["securitySchemes"]["aimarketApiKey"] == {"apiKeySecurityScheme": {
            "location": "header", "name": "X-API-Key",
            "description": card["securitySchemes"]["aimarketApiKey"]["apiKeySecurityScheme"]["description"],
        }}
        assert card["securitySchemes"]["aimarketMandate"]["apiKeySecurityScheme"]["name"] == "X-AIMarket-Mandate"
        # Optional credentials: no securityRequirements, or a trial/x402 buyer would be told
        # it cannot call at all.
        assert "securityRequirements" not in card
        assert response.headers["cache-control"] == "public, max-age=300"
        assert response.headers["etag"].startswith('"')

    def test_invoke_can_be_switched_off_and_the_card_then_says_so(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIMARKET_A2A_INVOKE", "0")
        config = HubConfig()
        config.hub_url = "https://independent.example/hub"
        config.db_path = str(tmp_path / "off.db")
        config.signing_key_path = str(tmp_path / "off-key")
        app = create_app(config=config, db=HubDatabase(config.db_path), signer=Signer(config.signing_key_path))
        with TestClient(app) as off:
            card = off.get("/.well-known/agent-card.json").json()
            assert [skill["id"] for skill in card["skills"]] == ["marketplace-search"]
            assert "extensions" not in card["capabilities"] and "securitySchemes" not in card
            invoke = _request(params={"message": {
                "messageId": "m-off", "role": "ROLE_USER",
                "parts": [{"data": {"invoke": {"product_id": "x-1", "capability_id": "x.y@v1"}}}],
            }})
            # Without the bridge an invoke block is just an unknown search option.
            assert _post(off, invoke).json()["error"]["code"] == -32602
            assert _post(off, _request(method="GetTask", params={"id": "a2at_" + "0" * 24})).json()["error"]["code"] == -32001

    def test_card_supports_head_and_conditional_get(self, client):
        first = client.get("/.well-known/agent-card.json")
        head = client.head("/.well-known/agent-card.json")
        cached = client.get(
            "/.well-known/agent-card.json",
            headers={"If-None-Match": first.headers["etag"]},
        )
        assert head.status_code == 200
        assert head.content == b""
        assert cached.status_code == 304
        assert cached.content == b""

    def test_native_manifest_binds_a2a_urls_inside_its_signature(self, client):
        manifest = client.get("/.well-known/ai-market.json").json()
        assert manifest["a2a_endpoint"] == "https://independent.example/hub/a2a"
        assert manifest["a2a_agent_card_url"].endswith("/.well-known/agent-card.json")
        assert manifest["signature"]["algorithm"] == "ed25519"


class TestA2AJsonRpc:
    def test_text_query_returns_a_direct_message_with_structured_offers(self, client):
        response = _post(client, _request())
        assert response.status_code == 200
        assert response.headers["a2a-version"] == "1.0"
        body = response.json()
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == 1
        message = body["result"]["message"]
        assert message["role"] == "ROLE_AGENT"
        assert message["contextId"]
        assert message["parts"][0]["mediaType"] == "text/plain"
        data = message["parts"][1]["data"]
        assert data["query"] == "Find translation tools"
        assert isinstance(data["matches"], list)
        assert data["search"]["query_stays_local"] is True
        assert message["metadata"]["invokeEndpoint"].endswith("/ai-market/v2/invoke")

    def test_structured_query_maps_only_bounded_public_filters(self, client):
        payload = _request(params={
            "message": {
                "messageId": "msg-json",
                "contextId": "ctx-kept",
                "role": "ROLE_USER",
                "parts": [{"data": {
                    "intent": "security audit",
                    "budget": 0.1,
                    "maxLatencyMs": 5000,
                    "minTrust": 0.0,
                    "limit": 2,
                }}],
            }
        })
        body = _post(client, payload).json()
        assert body["result"]["message"]["contextId"] == "ctx-kept"
        data = body["result"]["message"]["parts"][1]["data"]
        assert data["query"] == "security audit"
        assert len(data["matches"]) <= 2

    @pytest.mark.parametrize(
        ("method", "params", "code"),
        [
            ("GetTask", {"id": "a2at_" + "0" * 24}, -32001),
            ("CancelTask", {"id": "a2at_" + "0" * 24}, -32001),
            ("GetTask", {}, -32602),
            ("SendStreamingMessage", {}, -32004),
            ("SubscribeToTask", {}, -32004),
            ("GetExtendedAgentCard", {}, -32004),
            ("CreateTaskPushNotificationConfig", {}, -32602),
            ("CreateTaskPushNotificationConfig",
             {"taskId": "a2at_" + "0" * 24, "url": "https://client.example/hook"}, -32001),
            ("ListTaskPushNotificationConfigs", {"taskId": "a2at_" + "0" * 24}, -32001),
            ("UnknownMethod", {}, -32601),
        ],
    )
    def test_unavailable_operations_fail_with_standard_codes(self, client, method, params, code):
        assert _post(client, _request(method=method, params=params)).json()["error"]["code"] == code

    def test_list_tasks_is_empty_for_a_caller_nobody_authenticated(self, client):
        # Search answers with a Message and creates no task; an anonymous caller lists nothing
        # even when tasks exist (test_a2a_invoke pins the scoping).
        _post(client, _request())
        body = _post(client, _request(method="ListTasks", params={})).json()
        assert body["result"] == {"tasks": [], "nextPageToken": "", "pageSize": 50, "totalSize": 0}

    def test_version_is_mandatory_and_downgrade_fails_closed(self, client):
        missing = client.post("/a2a", json=_request())
        old = client.post("/a2a", json=_request(), headers={"A2A-Version": "0.3"})
        assert missing.json()["error"]["code"] == -32009
        assert old.json()["error"]["code"] == -32009

    def test_files_and_push_callbacks_are_not_silently_accepted(self, client):
        file_request = _request(params={
            "message": {
                "messageId": "msg-file",
                "role": "ROLE_USER",
                "parts": [{"url": "https://attacker.example/payload"}],
            }
        })
        assert _post(client, file_request).json()["error"]["code"] == -32005

        # A search creates no task, so a webhook for it could never fire: refused, not ignored.
        push_request = _request()
        push_request["params"]["configuration"] = {
            "taskPushNotificationConfig": {"url": "https://attacker.example/callback"}
        }
        error = _post(client, push_request).json()["error"]
        assert error["code"] == -32602 and "for tasks" in error["message"]

    def test_push_switched_off_says_so(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIMARKET_A2A_PUSH_ENABLED", "0")
        config = HubConfig()
        config.hub_url = "https://independent.example/hub"
        config.db_path = str(tmp_path / "off.db")
        config.signing_key_path = str(tmp_path / "off-key")
        app = create_app(config=config, db=HubDatabase(config.db_path), signer=Signer(config.signing_key_path))
        with TestClient(app) as off:
            assert off.get("/.well-known/agent-card.json").json()["capabilities"]["pushNotifications"] is False
            body = _post(off, _request(method="CreateTaskPushNotificationConfig", params={})).json()
            assert body["error"]["code"] == -32003

    @pytest.mark.parametrize(
        "options",
        [
            {"intent": "x", "limit": 21},
            {"intent": "x", "budget": True},
            {"intent": "x", "minTrust": 1.1},
            {"intent": "x", "includeStale": True},
        ],
    )
    def test_search_options_are_finite_bounded_and_allowlisted(self, client, options):
        payload = _request(params={
            "message": {
                "messageId": "msg-bounds",
                "role": "ROLE_USER",
                "parts": [{"data": options}],
            }
        })
        assert _post(client, payload).json()["error"]["code"] == -32602

    def test_non_finite_json_number_is_rejected_even_if_a_lax_client_sends_it(self, client):
        # RFC 8259 forbids Infinity, while CPython's decoder accepts it by default. Keep
        # the application-level finite check: a hand-written client can still send this.
        raw = b'''{"jsonrpc":"2.0","id":1,"method":"SendMessage","params":{"message":{"messageId":"m","role":"ROLE_USER","parts":[{"data":{"intent":"x","budget":Infinity}}]}}}'''
        response = client.post(
            "/a2a", content=raw,
            headers={"Content-Type": "application/json", "A2A-Version": "1.0"},
        )
        assert response.json()["error"]["code"] == -32602

    def test_body_is_capped_before_json_processing(self, client):
        response = client.post(
            "/a2a",
            content=b"{" + b"x" * (128 * 1024) + b"}",
            headers={"Content-Type": "application/json", "A2A-Version": "1.0"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["data"][0]["reason"] == "REQUEST_TOO_LARGE"


class TestTrafficIsCounted:
    """Whether A2A clients exist, and whether they pay, is read off this counter. Before it
    /a2a was the one surface with no metric at all. Invoke tasks are counted by the state
    they reach (test_a2a_invoke)."""

    @staticmethod
    def _value(method: str, result: str) -> float:
        from aimarket_hub.metrics import REGISTRY

        return REGISTRY.get_sample_value(
            "aimarket_hub_a2a_requests_total", {"method": method, "result": result},
        ) or 0.0

    def test_card_reads_and_calls_land_in_the_counter_by_method_and_outcome(self, client):
        before = {k: self._value(*k) for k in [
            ("agent-card", "ok"), ("SendMessage", "ok"), ("SendMessage", "version_not_supported"),
            ("other", "method_not_found"), ("other", "ok"),
        ]}
        client.get("/.well-known/agent-card.json")
        _post(client, _request())
        client.post("/a2a", json=_request(), headers={"A2A-Version": "0.3"})
        _post(client, _request(method="Mint\nNew{Series}"))
        after = {k: self._value(*k) for k in before}
        assert after[("agent-card", "ok")] == before[("agent-card", "ok")] + 1
        assert after[("SendMessage", "ok")] == before[("SendMessage", "ok")] + 1
        assert after[("SendMessage", "version_not_supported")] == before[("SendMessage", "version_not_supported")] + 1
        # an invented method cannot mint a new series: it is counted as "other"
        grew = sum(after[k] - before[k] for k in [("other", "method_not_found"), ("other", "ok")])
        assert grew == 1
