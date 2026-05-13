"""Small helpers shared by pipeline worker modules."""

from __future__ import annotations

import os


def env_truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")
