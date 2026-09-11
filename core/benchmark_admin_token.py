"""
Optional admin JWT for autonomous benchmark scripts (Director / benchmark_pass_rate).

Set ``AIFACTORY_BENCHMARK_ADMIN_TOKEN`` or a one-line file path in
``AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE`` (e.g. under ``data/secrets/``, mode 0600).
Without a token, Director skips emitting ``benchmark_now`` and skips league runs
so the API is not hammered with unauthenticated admin calls.
"""

from __future__ import annotations

import os
from pathlib import Path


def read_benchmark_admin_token() -> str | None:
    t = (os.environ.get("AIFACTORY_BENCHMARK_ADMIN_TOKEN") or "").strip()
    if t:
        return t
    fp = (os.environ.get("AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE") or "").strip()
    if not fp:
        return None
    try:
        raw = Path(fp).expanduser().read_text(encoding="utf-8").strip()
        return raw or None
    except OSError:
        return None
