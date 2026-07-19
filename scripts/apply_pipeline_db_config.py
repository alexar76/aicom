#!/usr/bin/env python3
"""Apply Admin → Settings pipeline DB fields to process environment (entrypoint)."""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from core.pipeline_database import apply_pipeline_db_config_from_app_config
from web.backend.core.config import AppConfig


def main() -> int:
    config = AppConfig()
    result = apply_pipeline_db_config_from_app_config(config)
    print(
        f"pipeline_db_backend={result['backend']} "
        f"database_url_set={result['database_url_set']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
