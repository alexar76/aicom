#!/usr/bin/env python3
"""
Copy bundled pipeline demo recording into the admin demo-replay upload dir
and enable Live Monitor replay.

Prefers ``.mp4`` (Safari / broad browser support); also copies ``.webm`` when present.

Run on the host that mounts ./data → /app/data (or set AIFACTORY_DATA_ROOT).

Example:
  python3 scripts/sync_demo_replay_from_recording.py
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("AIFACTORY_DATA_ROOT", str(ROOT / "data"))

from web.backend.services.pipeline_demo_replay import (  # noqa: E402
    load_raw_config,
    save_config,
    upload_dir,
)


def _pick_source() -> tuple[Path, str]:
    """Return (source_path, dest_basename) — mp4 preferred."""
    candidates = (
        ROOT / "docs" / "gallery" / "recordings" / "pipeline-demo-latest.mp4",
        ROOT / "web" / "frontend" / "public" / "demo" / "pipeline-demo.mp4",
        ROOT / "docs" / "gallery" / "recordings" / "pipeline-demo-latest.webm",
    )
    for p in candidates:
        if p.is_file() and p.suffix.lower() == ".mp4":
            return p, "pipeline-demo-latest.mp4"
    for p in candidates:
        if p.is_file():
            return p, f"pipeline-demo-latest{p.suffix.lower()}"
    raise FileNotFoundError(
        "No demo video found. Expected docs/gallery/recordings/pipeline-demo-latest.mp4 "
        "or web/frontend/public/demo/pipeline-demo.mp4"
    )


def main() -> int:
    src, dest_name = _pick_source()
    dest_dir = upload_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / dest_name
    shutil.copy2(src, dest)

    # Optional second format for operators who want webm in admin media folder
    webm_src = ROOT / "docs" / "gallery" / "recordings" / "pipeline-demo-latest.webm"
    if webm_src.is_file() and dest_name.endswith(".mp4"):
        shutil.copy2(webm_src, dest_dir / "pipeline-demo-latest.webm")

    cfg = load_raw_config()
    cfg["enabled"] = True
    cfg["title"] = cfg.get("title") or "Pipeline demo replay"
    cfg["source"] = "upload"
    cfg["media_filename"] = dest_name
    cfg["video_url"] = None
    cfg["updated_at"] = time.time()
    save_config(cfg)
    print(f"OK — replay enabled using {dest} (source: {src.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
