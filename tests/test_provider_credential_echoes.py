"""Provider errors and streamed text must not expose the configured credential."""

from __future__ import annotations

import json
import traceback
from types import SimpleNamespace

import httpx
import pytest

from llm.anthropic_provider import AnthropicProvider
from llm.credential_redaction import CredentialStreamRedactor
from llm.openai_compatible import OpenAICompatibleProvider


CANARY = "disposable-provider-secret-echo-canary"


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_SECRETS_BACKEND", "env")
    monkeypatch.setattr("llm.usage_guard.record_llm_call_spend", lambda entry: None)
    return tmp_path / "logs" / "llm_calls.jsonl"


async def _provider(kind, handler):
    provider_class = AnthropicProvider if kind == "anthropic" else OpenAICompatibleProvider
    options = {"api_key_env": None} if kind == "anthropic" else {}
    provider = provider_class(name="synthetic-echo-review", api_key=CANARY, **options)
    await provider._client.aclose()
    provider._client = httpx.AsyncClient(
        base_url="https://provider.example/v1", transport=httpx.MockTransport(handler),
    )
    return provider


def _frame(kind, *, text=None, error=None):
    if error is not None:
        payload = {"type": "error", "error": {"message": error}}
    elif kind == "anthropic":
        payload = {"type": "content_block_delta", "delta": {"text": text}}
    else:
        payload = {"choices": [{"delta": {"content": text}}]}
    return "data: " + json.dumps(payload) + "\n\n"


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
@pytest.mark.asyncio
async def test_sse_error_redacts_exception_health_and_actual_durable_log(kind, isolated_logs, caplog):
    body = _frame(kind, error="upstream rejected " + CANARY)
    provider = await _provider(kind, lambda request: httpx.Response(
        200, text=body, headers={"Content-Type": "text/event-stream"},
    ))
    try:
        with pytest.raises(RuntimeError) as error:
            async for _ in provider.stream("synthetic prompt " + CANARY):
                pass
        rendered = "".join(traceback.format_exception(error.type, error.value, error.tb))
        assert CANARY not in rendered
        assert CANARY not in provider.health.error_message
        assert CANARY not in caplog.text
        assert CANARY not in isolated_logs.read_text()
        row = json.loads(isolated_logs.read_text().splitlines()[-1])
        assert row["success"] is False and "[redacted]" in row["error"]
    finally:
        await provider._client.aclose()


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
@pytest.mark.asyncio
async def test_http_exception_redacts_generate_stream_and_health(kind, isolated_logs, caplog):
    def handler(request):
        raise httpx.ConnectError("transport diagnostic " + CANARY, request=request)

    provider = await _provider(kind, handler)
    try:
        with pytest.raises(RuntimeError) as error:
            await provider.generate("synthetic prompt " + CANARY)
        assert CANARY not in "".join(traceback.format_exception(error.type, error.value, error.tb))
        with pytest.raises(RuntimeError):
            async for _ in provider.stream("synthetic prompt"):
                pass
        await provider.check_health()
        assert CANARY not in provider.health.error_message
        assert CANARY not in caplog.text
        assert CANARY not in isolated_logs.read_text()
    finally:
        await provider._client.aclose()


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
@pytest.mark.parametrize("split", [1, 5, len(CANARY) - 1])
@pytest.mark.asyncio
async def test_stream_key_split_across_chunks_is_redacted(kind, split, isolated_logs):
    body = (_frame(kind, text="ordinary prefix ") +
            _frame(kind, text=CANARY[:split]) + _frame(kind, text=CANARY[split:]) +
            _frame(kind, text=" ordinary suffix"))
    provider = await _provider(kind, lambda request: httpx.Response(
        200, text=body, headers={"Content-Type": "text/event-stream"},
    ))
    try:
        chunks = [part async for part in provider.stream("synthetic prompt " + CANARY)]
        assert "".join(chunks) == "ordinary prefix [redacted] ordinary suffix"
        assert chunks[0] == "ordinary prefix "  # Ordinary text flushes immediately.
        assert CANARY not in isolated_logs.read_text()
    finally:
        await provider._client.aclose()


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
@pytest.mark.asyncio
async def test_normal_response_echo_is_redacted_before_return_and_log(kind, isolated_logs):
    payload = {"content": [{"type": "text", "text": "echo " + CANARY}]} if kind == "anthropic" else {
        "choices": [{"message": {"content": "echo " + CANARY}, "finish_reason": "stop"}],
    }
    provider = await _provider(kind, lambda request: httpx.Response(200, json=payload))
    try:
        assert await provider.generate("synthetic prompt " + CANARY) == "echo [redacted]"
        assert CANARY not in isolated_logs.read_text()
    finally:
        await provider._client.aclose()


def test_redactor_preserves_nonsecret_partial_prefix_at_normal_end():
    redactor = CredentialStreamRedactor("secret-canary")
    assert redactor.feed("ordinary prose") == "ordinary pro"
    assert redactor.finish() == "se"
    assert redactor.feed("ordinary output") == "ordinary output"


@pytest.mark.parametrize("field", ["id", "name"])
def test_dashboard_model_ids_redact_credential_echo(field, monkeypatch):
    from web.backend.api.admin.dashboard import routes_providers as routes

    monkeypatch.setattr(routes, "_assert_url_safe_for_outbound", lambda url: None)
    payload = {"data" if field == "id" else "models": [{field: "echo-" + CANARY}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: payload))
    result = routes._provider_models_probe(base_url="https://provider.example/v1", health_path="/v1/models", api_key=CANARY)
    assert result == ["echo-[redacted]"]


def test_dashboard_probe_error_log_redacts_credential_without_traceback(monkeypatch, caplog):
    from web.backend.api.admin.dashboard import routes_providers as routes

    monkeypatch.setattr(routes, "_assert_url_safe_for_outbound", lambda url: None)
    def reject(*args, **kwargs):
        raise httpx.ConnectError("upstream diagnostic " + CANARY)
    monkeypatch.setattr(httpx, "get", reject)
    assert routes._provider_models_probe(base_url="https://provider.example/v1", health_path="/v1/models", api_key=CANARY) == []
    assert "[redacted]" in caplog.text
    assert CANARY not in caplog.text
