import json

import httpx
import pytest

from llm.anthropic_provider import AnthropicProvider
from llm.openai_compatible import OpenAICompatibleProvider


def sse(*events):
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events)


@pytest.mark.asyncio
async def test_openrouter_stream_records_terminal_usage(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_LOGS_DIR", str(tmp_path))

    def handler(request):
        assert json.loads(request.content)["usage"] == {"include": True}
        return httpx.Response(200, headers={"x-request-id": "req-fixture"}, text=sse(
            {"id": "gen-fixture", "choices": [{"delta": {"content": "private reply"}}]},
            {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 3, "cost": 0,
                                       "prompt_tokens_details": {"cached_tokens": 60, "cache_write_tokens": 12}}},
        ) + "data: [DONE]\n\n")

    provider = OpenAICompatibleProvider(base_url="https://openrouter.ai/api/v1", api_key="fixture-key")
    await provider._client.aclose()
    async with httpx.AsyncClient(base_url=provider.base_url, transport=httpx.MockTransport(handler)) as client:
        provider._client = client
        assert "".join([part async for part in provider.stream("private prompt")]) == "private reply"
    raw = (tmp_path / "model_usage.jsonl").read_text()
    usage = json.loads(raw)
    assert (usage["input_tokens"], usage["output_tokens"]) == (100, 3)
    assert (usage["cache_read_input_tokens"], usage["cache_write_input_tokens"]) == (60, 12)
    assert usage["provider_cost_usd"] == 0
    assert usage["provider_request_id"] == "req-fixture" and usage["provider_generation_id"] == "gen-fixture"
    assert usage["mcp_servers"] == [] and "private" not in raw and "fixture-key" not in raw


@pytest.mark.asyncio
async def test_anthropic_stream_merges_start_and_delta_usage(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_LOGS_DIR", str(tmp_path))
    response = sse(
        {"type": "message_start", "message": {"id": "msg-fixture", "usage": {
            "input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 20, "output_tokens": 1,
        }}},
        {"type": "content_block_delta", "delta": {"text": "done"}},
        {"type": "message_delta", "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    )
    provider = AnthropicProvider(api_key="fixture-key")
    await provider._client.aclose()
    async with httpx.AsyncClient(base_url=provider.base_url, transport=httpx.MockTransport(
        lambda _: httpx.Response(200, text=response)
    )) as client:
        provider._client = client
        assert "".join([part async for part in provider.stream("private prompt")]) == "done"
    usage = json.loads((tmp_path / "model_usage.jsonl").read_text())
    assert (usage["input_tokens"], usage["output_tokens"]) == (130, 5)
    assert (usage["cache_read_input_tokens"], usage["cache_write_input_tokens"]) == (100, 20)
    assert usage["provider_cost_usd"] is None
