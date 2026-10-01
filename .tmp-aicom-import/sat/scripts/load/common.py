"""Shared helpers for ecosystem load tests (Locust)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load repo ``.env`` when keys are not already in the process environment."""
    env_file = os.environ.get("ENV_FILE", str(ROOT / ".env"))
    if not os.path.isfile(env_file):
        return
    with open(env_file, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")


def service_url(name: str, default: str) -> str:
    return (os.environ.get(name) or default).rstrip("/")


def bearer_header(env_key: str) -> dict[str, str]:
    token = (os.environ.get(env_key) or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}
