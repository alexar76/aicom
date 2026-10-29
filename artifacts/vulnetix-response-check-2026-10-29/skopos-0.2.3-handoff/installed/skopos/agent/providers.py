from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, replace
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import AgentConfig, ProviderConfig, get_provider
from .rate_limit import wait_before_llm_call

_OPENROUTER_HOST = "openrouter.ai"
_CONNECT_TIMEOUT = 12
_READ_TIMEOUT = 90


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class LLMProviderError(RuntimeError):
    pass


class LLMEmptyResponseError(LLMProviderError):
    """The provider answered, but with no usable text — e.g. finish_reason=length
    with the whole budget spent on hidden reasoning. Unlike an auth or bad-request
    error, this is worth trying the next provider for: a different model may return
    content where this one produced none."""

    pass


def is_transient_llm_error(exc: BaseException) -> bool:
    """True for network blips and retryable upstream errors."""
    if isinstance(exc, (requests.ConnectionError, requests.Timeout, OSError)):
        return True
    msg = str(exc).lower()
    if "httpconnectionpool" in msg or "connection aborted" in msg or "timed out" in msg:
        return True
    if isinstance(exc, LLMProviderError):
        if any(code in msg for code in ("http 429", "http 502", "http 503", "http 504")):
            return True
        if "connection" in msg or "timeout" in msg:
            return True
    return False


def _http_session() -> requests.Session:
    """Direct local HTTP — no Cursor/IDE proxy."""
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}
    retry = Retry(
        total=2,
        connect=2,
        read=1,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_HTTP = _http_session()


def _warm_dns(host: str = _OPENROUTER_HOST) -> None:
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        pass


def _request_timeout() -> tuple[int, int]:
    return (_CONNECT_TIMEOUT, _READ_TIMEOUT)


def _headers(prov: ProviderConfig) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if prov.extra_headers:
        h.update(prov.extra_headers)
    if prov.kind == "anthropic_compatible":
        if prov.api_key:
            h["x-api-key"] = prov.api_key
            h["anthropic-version"] = h.get("anthropic-version", "2023-06-01")
    elif prov.api_key:
        h["Authorization"] = f"Bearer {prov.api_key}"
    return h


def _resolve_provider(cfg: AgentConfig, provider_id: str | None, *, model: str | None) -> ProviderConfig:
    prov = get_provider(cfg, provider_id)
    if model and model != prov.model:
        return replace(prov, model=model)
    return prov


def chat_completion(
    cfg: AgentConfig,
    messages: list[ChatMessage],
    *,
    provider_id: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    prov = _resolve_provider(cfg, provider_id, model=model)
    if prov.kind in ("openai_compatible", "ollama", "lmstudio"):
        return _openai_chat(prov, messages, temperature=temperature, max_tokens=max_tokens)
    if prov.kind == "anthropic_compatible":
        return _anthropic_chat(prov, messages, temperature=temperature, max_tokens=max_tokens)
    raise LLMProviderError(f"Unsupported provider kind: {prov.kind}")


def chat_completion_with_fallback(
    cfg: AgentConfig,
    messages: list[ChatMessage],
    attempts: list[tuple[str | None, str | None]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> tuple[str, str, str]:
    """Try providers in order; return (text, provider_id, model)."""
    last_err: BaseException | None = None
    for provider_id, model in attempts:
        if not provider_id:
            continue
        try:
            prov = get_provider(cfg, provider_id)
        except KeyError:
            continue
        if prov.kind in ("openai_compatible", "anthropic_compatible") and not prov.api_key:
            continue
        effective_model = model or prov.model
        try:
            text = chat_completion(
                cfg,
                messages,
                provider_id=provider_id,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return text, provider_id, effective_model
        except BaseException as exc:
            last_err = exc
            # A transient blip, or a provider that answered with no usable text
            # (finish_reason=length / empty content), is worth trying the next
            # provider for. A real error (auth, bad request) is not — fail fast.
            if is_transient_llm_error(exc) or isinstance(exc, LLMEmptyResponseError):
                continue
            raise
    if last_err:
        raise LLMProviderError(str(last_err)) from last_err
    raise LLMProviderError("no LLM provider available")


def chat_completion_stream(
    cfg: AgentConfig,
    messages: list[ChatMessage],
    *,
    provider_id: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> Iterator[str]:
    prov = get_provider(cfg, provider_id)
    if prov.kind not in ("openai_compatible", "ollama", "lmstudio"):
        yield chat_completion(cfg, messages, provider_id=provider_id, temperature=temperature, max_tokens=max_tokens)
        return
    url = prov.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": prov.model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    wait_before_llm_call()
    with _HTTP.post(
        url,
        headers=_headers(prov),
        json=payload,
        stream=True,
        timeout=120,
    ) as resp:
        if resp.status_code >= 400:
            raise LLMProviderError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:]
            if chunk.strip() == "[DONE]":
                break
            try:
                data = json.loads(chunk)
                delta = data["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _is_reasoning_model(model: str) -> bool:
    m = model.lower()
    return any(x in m for x in ("minimax", "deepseek-r", "/o1", "/o3", "qwq"))


def _openrouter_reasoning_payload(prov: ProviderConfig) -> dict:
    """MiniMax M3 etc. burn max_tokens on hidden reasoning — reserve budget for content."""
    if "openrouter.ai" not in (prov.base_url or "") or not _is_reasoning_model(prov.model):
        return {}
    return {"reasoning": {"effort": "low", "exclude": True}}


def _extract_openai_message_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise LLMEmptyResponseError("Model returned no choices")
    choice = choices[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    if content:
        text = str(content).strip()
        if text:
            return text
    finish = choice.get("finish_reason") or "unknown"
    raise LLMEmptyResponseError(
        f"Model returned no text (finish_reason={finish}). "
        "The token budget may have been used by hidden reasoning."
    )


def _openai_chat(
    prov: ProviderConfig,
    messages: list[ChatMessage],
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    url = prov.base_url.rstrip("/") + "/chat/completions"
    reasoning = _openrouter_reasoning_payload(prov)
    budgets = [max_tokens]
    if max_tokens < 4096 and reasoning:
        budgets.append(min(max_tokens * 3, 4096))

    last_err: LLMProviderError | None = None
    for budget in budgets:
        payload = {
            "model": prov.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": budget,
            **reasoning,
        }
        wait_before_llm_call()
        _warm_dns()
        last_req_err: Exception | None = None
        resp = None
        for attempt in range(3):
            try:
                resp = _HTTP.post(
                    url,
                    headers=_headers(prov),
                    json=payload,
                    timeout=_request_timeout(),
                )
                break
            except requests.RequestException as e:
                last_req_err = e
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
                    _warm_dns()
                    continue
                raise LLMProviderError(f"LLM request failed: {e}") from e
        if resp is None:
            raise LLMProviderError(f"LLM request failed: {last_req_err}") from last_req_err
        if resp.status_code >= 400:
            raise LLMProviderError(f"LLM HTTP {resp.status_code}: {resp.text[:800]}")
        data = resp.json()
        try:
            return _extract_openai_message_content(data)
        except LLMProviderError as e:
            last_err = e
            if budget != budgets[-1]:
                continue
            raise
    if last_err:
        raise last_err
    raise LLMProviderError("LLM request failed")


def verify_openrouter_key(api_key: str) -> dict:
    """Check OpenRouter key via GET /auth/key. Returns parsed JSON data."""
    wait_before_llm_call()
    try:
        resp = _HTTP.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except requests.RequestException as e:
        raise LLMProviderError(f"OpenRouter key check failed: {e}") from e
    if resp.status_code >= 400:
        raise LLMProviderError(f"OpenRouter key HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise LLMProviderError(f"Unexpected OpenRouter key response: {data!r}")
    return data


def openrouter_credits(api_key: str) -> dict:
    """Fetch OpenRouter account credits."""
    wait_before_llm_call()
    try:
        resp = _HTTP.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
    except requests.RequestException as e:
        raise LLMProviderError(f"OpenRouter credits check failed: {e}") from e
    if resp.status_code >= 400:
        raise LLMProviderError(f"OpenRouter credits HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise LLMProviderError(f"Unexpected OpenRouter credits response: {data!r}")
    return data


def _anthropic_chat(
    prov: ProviderConfig,
    messages: list[ChatMessage],
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    url = prov.base_url.rstrip("/") + "/messages"
    system = ""
    conv: list[dict] = []
    for m in messages:
        if m.role == "system":
            system = m.content
        else:
            conv.append({"role": m.role, "content": m.content})
    payload = {
        "model": prov.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": conv,
    }
    if system:
        payload["system"] = system
    wait_before_llm_call()
    try:
        resp = _HTTP.post(
            url,
            headers=_headers(prov),
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        raise LLMProviderError(f"Anthropic request failed: {e}") from e
    if resp.status_code >= 400:
        raise LLMProviderError(f"Anthropic HTTP {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    try:
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except (TypeError, KeyError) as e:
        raise LLMProviderError(f"Unexpected Anthropic response: {data!r}") from e
    if not text.strip():
        # Same "answered but empty" case as the OpenAI path — let the fallback try
        # the next provider instead of returning an empty briefing as success.
        stop = data.get("stop_reason") or "unknown"
        raise LLMEmptyResponseError(f"Model returned no text (stop_reason={stop}).")
    return text
