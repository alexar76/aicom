#!/usr/bin/env python3
"""Backfill launch blog posts for products with marketing_content.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Local dev: default to repo data/ when AIFACTORY_DATA_ROOT is unset.
if not os.environ.get("AIFACTORY_DATA_ROOT"):
    local_data = REPO_ROOT / "data"
    if local_data.is_dir():
        os.environ["AIFACTORY_DATA_ROOT"] = str(local_data)

from web.backend.services.product_blog import backfill_launch_posts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Marketing launch blog posts")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing non-admin posts")
    parser.add_argument("--capture-screenshots", action="store_true", help="Capture sandbox hero images")
    parser.add_argument("--base-url", default="", help="App base URL for sandbox capture")
    parser.add_argument("--all", dest="only_missing", action="store_false", help="Re-process all products")
    args = parser.parse_args()

    result = backfill_launch_posts(
        only_missing=args.only_missing,
        capture_screenshots=args.capture_screenshots,
        base_url=args.base_url or None,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        sys.exit(1)


if __name__ == "__main__":
    main()
