"""Persistent paths for AI Market Protocol v1 state."""

from __future__ import annotations

from pathlib import Path

from core.paths import data_root, secrets_dir


def ai_market_state_dir() -> Path:
    p = data_root() / "state" / "ai_market"
    p.mkdir(parents=True, exist_ok=True)
    return p


def channels_path() -> Path:
    return ai_market_state_dir() / "channels.json"


def receipts_path() -> Path:
    return ai_market_state_dir() / "receipts.json"


def pipelines_path() -> Path:
    return ai_market_state_dir() / "pipelines.json"


def stats_path() -> Path:
    return ai_market_state_dir() / "stats.jsonl"


def signing_key_path() -> Path:
    return secrets_dir() / "ai_market_signing.key"
