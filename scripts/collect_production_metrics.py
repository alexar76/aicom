#!/usr/bin/env python3
"""Fetch live production metrics and refresh docs/production-metrics.snapshot.json."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "production-metrics.snapshot.json"
DEFAULT_URL = "https://magic-ai-factory.com/api/public/ecosystem-status"


def fetch(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="ecosystem-status URL")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--stdout", action="store_true", help="print JSON only")
    args = parser.parse_args()

    try:
        payload = fetch(args.url, args.timeout)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} from {args.url}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    payload.setdefault(
        "snapshot_generated_at",
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    if args.stdout:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    SNAPSHOT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
