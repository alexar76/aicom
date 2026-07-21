"""Redis wake queue unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_publish_wake_noop_when_inline(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PIPELINE_QUEUE_BACKEND", raising=False)
    from orchestrator.redis_wake import publish_wake

    assert publish_wake() is False


def test_publish_wake_pushes_when_redis(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PIPELINE_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("AIFACTORY_REDIS_URL", "redis://127.0.0.1:6379/0")
    mock_client = MagicMock()
    with patch("redis.from_url", return_value=mock_client):
        from orchestrator.redis_wake import publish_wake

        assert publish_wake("test") is True
        mock_client.lpush.assert_called_once()
