"""Redis wake queue unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_redis_url_builds_authenticated_url_and_escapes_password(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "p@ss:/ word")
    monkeypatch.setenv("AIFACTORY_REDIS_HOST", "redis.internal")
    monkeypatch.setenv("AIFACTORY_REDIS_PORT", "6380")
    monkeypatch.setenv("AIFACTORY_REDIS_DB", "2")
    monkeypatch.setenv("AIFACTORY_REDIS_URL", "redis://stale-without-auth:6379/0")

    from orchestrator.redis_wake import redis_url

    assert redis_url() == "redis://:p%40ss%3A%2F%20word@redis.internal:6380/2"


def test_publish_wake_noop_when_inline(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PIPELINE_QUEUE_BACKEND", raising=False)
    from orchestrator.redis_wake import publish_wake

    assert publish_wake() is False


def test_publish_wake_pushes_when_redis(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PIPELINE_QUEUE_BACKEND", "redis")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("AIFACTORY_REDIS_URL", "redis://127.0.0.1:6379/0")
    mock_client = MagicMock()
    with patch("redis.from_url", return_value=mock_client):
        from orchestrator.redis_wake import publish_wake

        assert publish_wake("test") is True
        mock_client.lpush.assert_called_once()
