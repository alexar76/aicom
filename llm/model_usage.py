"""Provider-reported, per-request usage. The budget ledger remains separate."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

from core.paths import logs_dir

logger = logging.getLogger(__name__)


def _count(value):
    return value if type(value) is int and value >= 0 else None


class ModelUsage:
    """Record one attempted provider dispatch, including partial streams and errors."""

    def __init__(self, provider, base_url, model, config, *, wire="openai", stream=False):
        self.host = urlsplit(base_url).hostname
        self.wire = wire
        self.usage = {}
        self.started = monotonic()
        self.provider_error = False
        self.row = {
            "schema_version": 1,
            "call_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "factory",
            "provider": provider,
            "provider_host": self.host,
            "model": model,
            "task_type": config.task_type,
            "agent_type": config.agent_type,
            "product_id": config.product_id,
            "stream": stream,
            # Factory sends messages (or an Ollama prompt), without MCP tool definitions.
            "mcp_servers": [],
            "provider_model": None,
            "provider_request_id": None,
            "provider_generation_id": None,
            "http_status": None,
        }

    def __enter__(self):
        return self

    def sent(self, response):
        headers = getattr(response, "headers", {})
        self.row["http_status"] = getattr(response, "status_code", None)
        self.row["provider_request_id"] = headers.get("request-id") or headers.get("x-request-id")
        status = self.row["http_status"]
        self.provider_error |= isinstance(status, int) and not 200 <= status < 300

    def observe(self, body):
        if not isinstance(body, dict):
            return
        self.provider_error |= bool(body.get("error"))
        if isinstance(body.get("id"), str):
            self.row["provider_generation_id"] = body["id"]
        if isinstance(body.get("model"), str):
            self.row["provider_model"] = body["model"]
        usage = body if self.wire == "ollama" else body.get("usage")
        if isinstance(usage, dict):
            # Anthropic sends cumulative counters across message_start/message_delta.
            # Streaming chunks without usage must leave the latest sample intact.
            if self.wire == "ollama":
                usage = {key: usage[key] for key in ("prompt_eval_count", "eval_count") if key in usage}
            self.usage.update({key: value for key, value in usage.items() if value is not None})

    def __exit__(self, exc_type, exc, tb):
        usage = self.usage
        details = usage.get("prompt_tokens_details")
        if not isinstance(details, dict):
            details = {}
        read = _count(details.get("cached_tokens"))
        if read is None:
            read = _count(usage.get("prompt_cache_hit_tokens"))
        write = _count(details.get("cache_write_tokens"))
        misses = _count(usage.get("prompt_cache_miss_tokens"))
        input_tokens = _count(usage.get("prompt_tokens"))
        output_tokens = _count(usage.get("completion_tokens"))
        if self.wire == "anthropic":
            read = _count(usage.get("cache_read_input_tokens"))
            write = _count(usage.get("cache_creation_input_tokens"))
            misses = _count(usage.get("input_tokens"))
            input_tokens = sum(n or 0 for n in (misses, read, write)) if misses is not None else None
            output_tokens = _count(usage.get("output_tokens"))
        elif self.wire == "ollama":
            input_tokens = _count(usage.get("prompt_eval_count"))
            output_tokens = _count(usage.get("eval_count"))

        cost = usage.get("cost") if self.host == "openrouter.ai" else None
        if type(cost) not in (int, float) or not 0 <= cost <= 1e100:
            cost = None
        outcome = "ok"
        if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
            outcome = "cancelled"
        elif exc_type or self.provider_error:
            outcome = "error"
        self.row.update(
            outcome=outcome,
            latency_ms=round((monotonic() - self.started) * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=read,
            cache_write_input_tokens=write,
            cache_miss_input_tokens=misses,
            provider_cost_usd=cost,
        )
        try:
            directory = logs_dir()
            directory.mkdir(parents=True, exist_ok=True)
            line = (json.dumps(self.row, separators=(",", ":")) + "\n").encode()
            fd = os.open(directory / "model_usage.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
        except (OSError, ValueError):
            logger.warning("Could not append Factory model usage")
