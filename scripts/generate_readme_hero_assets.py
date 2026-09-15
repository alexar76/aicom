#!/usr/bin/env python3
"""
Build README / homepage hero assets from pipeline-demo-latest.webm.

Outputs:
  docs/gallery/hero-demo-preview.gif          — autoplay hook for GitHub README
  docs/gallery/recordings/pipeline-demo-latest.mp4 — GitHub-inline HTML5 video
  web/frontend/public/demo/hero-preview.gif   — same GIF for marketing site
  web/frontend/public/demo/pipeline-demo.mp4    — same MP4 for marketing fallback

Requires: ffmpeg on PATH.

Regenerate after: scripts/record_pipeline_demo_video.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "docs" / "gallery" / "recordings" / "pipeline-demo-latest.webm"
GIF_OUT = REPO / "docs" / "gallery" / "hero-demo-preview.gif"
MP4_OUT = REPO / "docs" / "gallery" / "recordings" / "pipeline-demo-latest.mp4"
PUBLIC_DIR = REPO / "web" / "frontend" / "public" / "demo"


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found — install ffmpeg and retry", file=sys.stderr)
        return 1
    if not SRC.is_file():
        print(f"Missing source video: {SRC}", file=sys.stderr)
        print("Run: python scripts/record_pipeline_demo_video.py", file=sys.stderr)
        return 1

    gif_sec = os.environ.get("DEMO_VIDEO_GIF_SECONDS", "18")
    gif_ss = os.environ.get("DEMO_VIDEO_GIF_START_SEC", "25")
    mp4_sec = os.environ.get("DEMO_VIDEO_MP4_SECONDS", "120")
    mp4_ss = os.environ.get("DEMO_VIDEO_MP4_START_SEC", "0")

    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(mp4_ss),
            "-i",
            str(SRC),
            "-t",
            str(mp4_sec),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-vf",
            "scale=1280:-2",
            "-an",
            str(MP4_OUT),
        ]
    )
    # Build GIF from the MP4 excerpt (much faster / lower memory than palettegen on full webm).
    gif_src = MP4_OUT if MP4_OUT.is_file() else SRC
    gif_input = str(gif_src)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(gif_ss),
            "-i",
            gif_input,
            "-t",
            str(gif_sec),
            "-vf",
            "fps=5,scale=640:-1:flags=lanczos,split[s0][s1];"
            "[s0]palettegen=stats_mode=single:max_colors=96[p];[s1][p]paletteuse=dither=bayer",
            str(GIF_OUT),
        ]
    )

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GIF_OUT, PUBLIC_DIR / "hero-preview.gif")
    shutil.copy2(MP4_OUT, PUBLIC_DIR / "pipeline-demo.mp4")
    print("OK:", GIF_OUT, MP4_OUT, PUBLIC_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
