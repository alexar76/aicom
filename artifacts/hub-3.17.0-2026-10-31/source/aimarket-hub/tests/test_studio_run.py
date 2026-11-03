"""The studio's run path is a forwarder, and forwarders are where SSRF lives.

The studio is served by the hub because the manifest it composes from is here and the hub's
CORS is fail-closed. The pipeline executor, though, is a different service, and a browser
cannot reach it cross-origin — so the hub forwards one specific request to one specific
place.

Every test below exists to keep it *that* narrow:

  * the destination comes from the hub's own environment, never from the request body. A
    forwarder that takes its target from the caller is an SSRF gadget whatever it is named,
    and this one would be reachable unauthenticated from any browser.
  * unconfigured is a refusal with a reason, not a default guess at some localhost port.
  * the body is shape- and size-checked here as well as by the executor, so the route
    cannot be repurposed into a general-purpose poster.
"""

from __future__ import annotations

import json as json_module
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer

EXECUTOR = "https://executor.example.com"
NODE = {"product_id": "prod-platon", "capability_id": "platon.state@v1", "input": {}}


@contextmanager
def _client(tmp_path, monkeypatch, *, executor: str | None = None):
    if executor is None:
        monkeypatch.delenv("AIMARKET_PIPELINE_EXECUTOR_URL", raising=False)
    else:
        monkeypatch.setenv("AIMARKET_PIPELINE_EXECUTOR_URL", executor)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = create_app(
        config=config,
        db=HubDatabase(tmp_path / "hub.db"),
        signer=Signer(config.signing_key_path),
    )
    with TestClient(app) as client:
        yield client


class _Resp:
    def __init__(self, payload, status_code=200, *, text=""):
        self._payload = payload
        self.status_code = status_code
        self._text = text

    def json(self):
        if self._payload is _BROKEN:
            raise ValueError("not json")
        return self._payload


_BROKEN = object()


def _capture(monkeypatch, response):
    """Replace the outbound call and record exactly what it was asked to do."""
    seen: dict = {}

    async def fake_post(url, *, json=None, timeout=None, headers=None):
        seen.update({"url": url, "json": json, "timeout": timeout, "headers": headers})
        if isinstance(response, Exception):
            raise response
        return response

    import aimarket_hub.outbound_http as outbound

    monkeypatch.setattr(outbound, "post_configured", fake_post)
    return seen


class TestFailsClosed:
    def test_no_executor_configured_is_a_refusal_with_a_reason(self, tmp_path, monkeypatch):
        with _client(tmp_path, monkeypatch) as client:
            resp = client.post("/studio/run", json={"nodes": [NODE]})
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "executor_not_configured"
        # The message has to name the env var; "run failed" costs an hour of guessing.
        assert "AIMARKET_PIPELINE_EXECUTOR_URL" in body["detail"]

    def test_the_body_cannot_supply_a_destination(self, tmp_path, monkeypatch):
        """The defect this route is written to not have."""
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_x"}))
        with _client(tmp_path, monkeypatch) as client:
            resp = client.post("/studio/run", json={
                "nodes": [NODE],
                "executor": "http://169.254.169.254/latest/meta-data",
                "url": "http://169.254.169.254/",
                "base_url": "http://localhost:22",
            })
        # Unknown fields are dropped by the model and the target is still unset, so the
        # request is refused rather than sent anywhere.
        assert resp.status_code == 503
        assert seen == {}


class TestBodyIsValidatedHere:
    @pytest.mark.parametrize("body", [
        {"nodes": []},
        {"nodes": [{"capability_id": "c@v1"}]},           # no product_id
        {"nodes": [{"product_id": "p"}]},                  # no capability_id
        {"nodes": [dict(NODE) for _ in range(17)]},        # over the executor's limit
        {},
    ])
    def test_a_malformed_blueprint_never_leaves_the_hub(self, tmp_path, monkeypatch, body):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_x"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            resp = client.post("/studio/run", json=body)
        assert resp.status_code == 422
        assert seen == {}

    def test_sixteen_nodes_is_accepted(self, tmp_path, monkeypatch):
        """The cap must match the executor's, not be stricter than it."""
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_x"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            resp = client.post("/studio/run", json={"nodes": [dict(NODE) for _ in range(16)]})
        assert resp.status_code == 200
        assert len(seen["json"]["nodes"]) == 16


class TestForwarding:
    def test_independent_check_policy_and_private_evidence_survive_forwarding(self, tmp_path, monkeypatch):
        evidence = {"company": {"result": {"found": True}, "receipt": {"signature": {"value": "signed"}}}}
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_checks", "step_results": evidence}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            response = client.post("/studio/run", json={"nodes": [NODE], "continue_on_error": True})
            invalid = client.post("/studio/run", json={"nodes": [NODE], "continue_on_error": "true"})
        assert response.status_code == 200
        assert seen["json"]["continue_on_error"] is True
        assert response.json()["step_results"] == evidence
        assert invalid.status_code == 422

    def test_it_posts_the_blueprint_to_the_configured_executor(self, tmp_path, monkeypatch):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc", "bill_of_materials": {}}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR + "/") as client:
            resp = client.post("/studio/run", json={
                "nodes": [{**NODE, "id": "a", "input_from": "z", "depends_on": ["z"]}],
                "channel_id": "ch_1",
            })
        assert resp.status_code == 200
        assert seen["url"] == f"{EXECUTOR}/ai-market/pipelines"   # trailing slash normalised
        assert seen["json"]["channel_id"] == "ch_1"
        assert seen["json"]["nodes"][0]["input_from"] == "z"

    def test_it_carries_no_caller_credentials(self, tmp_path, monkeypatch):
        """The studio's run path is the free/sandbox one; paid runs go direct.

        The forwarder takes a URL and a body and nothing else — there is no parameter
        through which a caller's Authorization header could reach the executor.
        """
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post(
                "/studio/run",
                json={"nodes": [NODE]},
                headers={"Authorization": "Bearer secret", "Cookie": "session=abc"},
            )
        assert "secret" not in json_module.dumps(seen["json"])
        assert "secret" not in json_module.dumps(seen["headers"] or {})
        assert "Cookie" not in (seen["headers"] or {})

    def test_an_absent_field_is_not_forwarded_as_null(self, tmp_path, monkeypatch):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post("/studio/run", json={"nodes": [NODE]})
        assert "channel_id" not in seen["json"]
        assert "input_from" not in seen["json"]["nodes"][0]

    def test_the_reply_names_where_the_signed_original_lives(self, tmp_path, monkeypatch):
        """The page must be able to link to the verifiable BoM, not just show a summary."""
        _capture(monkeypatch, _Resp({"trace_id": "tr_abc", "bill_of_materials": {"steps": []}}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            body = client.post("/studio/run", json={"nodes": [NODE]}).json()
        assert body["trace_url"] == "/studio/trace/tr_abc"

    def test_no_trace_id_means_no_invented_link(self, tmp_path, monkeypatch):
        _capture(monkeypatch, _Resp({"error": "invalid_channel"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            body = client.post("/studio/run", json={"nodes": [NODE]}).json()
        assert "trace_url" not in body

    def test_the_executors_status_code_is_passed_through(self, tmp_path, monkeypatch):
        _capture(monkeypatch, _Resp({"error": "nope"}, status_code=402))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            resp = client.post("/studio/run", json={"nodes": [NODE]})
        assert resp.status_code == 402


class TestExecutorFailures:
    def test_unreachable_is_502_not_500(self, tmp_path, monkeypatch):
        _capture(monkeypatch, RuntimeError("connect timeout"))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            resp = client.post("/studio/run", json={"nodes": [NODE]})
        assert resp.status_code == 502
        assert resp.json()["error"] == "executor_unreachable"

    def test_a_non_json_reply_is_reported_as_such(self, tmp_path, monkeypatch):
        _capture(monkeypatch, _Resp(_BROKEN, status_code=200))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            resp = client.post("/studio/run", json={"nodes": [NODE]})
        assert resp.status_code == 502
        assert resp.json()["error"] == "executor_returned_non_json"


class TestThePageItself:
    def test_the_studio_is_served_from_the_same_origin_as_the_manifest(self, tmp_path, monkeypatch):
        """Same-origin is the whole reason it lives on the hub: CORS is fail-closed."""
        with _client(tmp_path, monkeypatch) as client:
            resp = client.get("/studio/")
        # 200 with the built bundle, or the 503 "not built" page in a checkout without it.
        assert resp.status_code in (200, 503)
        assert "HEPHAESTUS" in resp.text


class TestTheConfiguredDestinationIsStillValidated:
    """`post_configured` drops the private-host refusal on purpose — not every check."""

    @pytest.mark.parametrize("bad", [
        "file:///etc/passwd",
        "gopher://internal/",
        "ftp://internal/",
        "//no-scheme/",
        "",
    ])
    def test_post_configured_refuses_a_non_http_destination(self, bad):
        import asyncio

        from aimarket_hub.outbound_http import post_configured

        with pytest.raises(ValueError):
            asyncio.run(post_configured(bad, json={}))

    @pytest.mark.parametrize("bad", [
        "http://host/x\r\nX-Injected: 1",
        "http://host/x\nHost: elsewhere",
        "http://host/\tx",
    ])
    def test_post_configured_refuses_header_injection(self, bad):
        import asyncio

        from aimarket_hub.outbound_http import post_configured

        with pytest.raises(ValueError):
            asyncio.run(post_configured(bad, json={}))


class TestTheVisitorIsMeteredAsThemselves:
    """The hub's free trial is per visitor. Whose id reaches the executor decides whether
    a stranger gets their own allowance or shares — and exhausts — one belonging to this
    service."""

    def test_the_visitor_header_is_forwarded(self, tmp_path, monkeypatch):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post(
                "/studio/run",
                json={"nodes": [NODE]},
                headers={"X-AIMarket-Sandbox-Visitor": "visitor-42"},
            )
        assert seen["headers"] == {"X-AIMarket-Sandbox-Visitor": "visitor-42"}

    def test_nothing_is_forwarded_when_the_caller_sends_no_id(self, tmp_path, monkeypatch):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post("/studio/run", json={"nodes": [NODE]})
        assert not seen["headers"]

    def test_no_other_caller_header_is_relayed(self, tmp_path, monkeypatch):
        """Only the trial id — never the caller's own credentials."""
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post(
                "/studio/run",
                json={"nodes": [NODE]},
                headers={
                    "X-AIMarket-Sandbox-Visitor": "visitor-42",
                    "Authorization": "Bearer secret",
                    "X-Payment-Channel": "ch_someone_else",
                },
            )
        assert set(seen["headers"]) == {"X-AIMarket-Sandbox-Visitor"}


class TestNoFieldTheStudioNeedsIsDropped:
    """A forwarder deletes every field its model does not declare, silently.

    `source_hub` says which peer sells a row. Dropping it sent every federated hop to the
    executor with no idea where to look, and the studio's Run button could only fail.
    """

    def test_source_hub_reaches_the_executor(self, tmp_path, monkeypatch):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post("/studio/run", json={"nodes": [
                {**NODE, "source_hub": "https://iot.modelmarket.dev"},
            ]})
        assert seen["json"]["nodes"][0]["source_hub"] == "https://iot.modelmarket.dev"

    def test_a_row_the_executor_hosts_carries_no_source_hub(self, tmp_path, monkeypatch):
        seen = _capture(monkeypatch, _Resp({"trace_id": "tr_abc"}))
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            client.post("/studio/run", json={"nodes": [NODE]})
        assert "source_hub" not in seen["json"]["nodes"][0]


class TestTheTraceLinkStaysOnThisOrigin:
    """The executor is typically an internal name like `http://aicom-app-1:8080`.

    Publishing it in a public response both leaks infrastructure — the same class of defect
    as an IP in a signed manifest — and hands the browser a link it cannot follow.
    """

    def test_the_reply_links_to_a_path_here_not_to_the_executor(self, tmp_path, monkeypatch):
        _capture(monkeypatch, _Resp({"trace_id": "tr_abc123", "bill_of_materials": {}}))
        with _client(tmp_path, monkeypatch, executor="http://aicom-app-1:8080") as client:
            body = client.post("/studio/run", json={"nodes": [NODE]}).json()
        assert body["trace_url"] == "/studio/trace/tr_abc123"
        assert "aicom-app-1" not in json_module.dumps(body)

    # `..` is absent on purpose: the URL is normalised before routing, so it never
    # reaches this handler and asserting on it would test the ASGI server.
    @pytest.mark.parametrize("bad", ["tr_ZZZ", "tr_", "x" * 80, "tr_abc%2F..%2Fx"])
    def test_only_the_executor_s_own_id_format_travels(self, tmp_path, monkeypatch, bad):
        """The id lands in a URL on another service; it must not be steerable."""
        with _client(tmp_path, monkeypatch, executor=EXECUTOR) as client:
            resp = client.get(f"/studio/trace/{bad}")
        assert resp.status_code in (400, 404)

    def test_unconfigured_is_a_refusal_not_a_guess(self, tmp_path, monkeypatch):
        with _client(tmp_path, monkeypatch) as client:
            resp = client.get("/studio/trace/tr_abc123")
        assert resp.status_code == 503
        assert resp.json()["error"] == "executor_not_configured"
