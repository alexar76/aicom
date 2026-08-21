#!/usr/bin/env python3
"""Migrate legacy provider ids in data/logs/llm_calls.jsonl (e.g. deep-seek → deepseek_api)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from llm.pricing_estimate import migrate_llm_calls_provider_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize legacy LLM provider ids in JSONL logs")
    parser.add_argument(
        "--path",
        default=os.environ.get(
            "AIFACTORY_LLM_CALLS_JSONL",
            str(Path(os.environ.get("AIFACTORY_DATA_ROOT", "/app/data")) / "logs" / "llm_calls.jsonl"),
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    parser.add_argument(
        "--no-re-enrich",
        action="store_true",
        help="Do not recompute estimated_cost_usd after id change",
    )
    args = parser.parse_args()
    path = Path(args.path)
    stats = migrate_llm_calls_provider_ids(
        path,
        dry_run=args.dry_run,
        re_enrich_cost=not args.no_re_enrich,
    )
    print(f"path={path} dry_run={args.dry_run} stats={stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
