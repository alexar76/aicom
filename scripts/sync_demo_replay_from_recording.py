#!/usr/bin/env python3
"""
Copy docs/gallery/recordings/pipeline-demo-latest.webm into the admin demo-replay upload dir
and enable Live Monitor replay (uses server-local media URL).

Run on the host that mounts ./data → /app/data (or set AIFACTORY_DATA_ROOT).

Example:
  python3 scripts/sync_demo_replay_from_recording.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Host-side runs use repo ./data, not /app/data
import os

os.environ.setdefault("AIFACTORY_DATA_ROOT", str(ROOT / "data"))

from web.backend.services.pipeline_demo_replay import (  # noqa: E402
    load_raw_config,
    save_config,
    upload_dir,
)


def main() -> int:
    src = ROOT / "docs" / "gallery" / "recordings" / "pipeline-demo-latest.webm"
    if not src.is_file():
        print(f"Missing recording: {src}", file=sys.stderr)
        return 1
    dest_dir = upload_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = "pipeline-demo-latest.webm"
    dest = dest_dir / dest_name
    shutil.copy2(src, dest)

    cfg = load_raw_config()
    cfg["enabled"] = True
    cfg["title"] = cfg.get("title") or "Pipeline demo replay"
    cfg["source"] = "upload"
    cfg["media_filename"] = dest_name
    cfg["video_url"] = None
    save_config(cfg)
    print(f"OK — replay enabled using {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
