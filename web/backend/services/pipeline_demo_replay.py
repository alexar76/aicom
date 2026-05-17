"""Persisted demo replay video for Live Monitor (external URL or uploaded file)."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from core.paths import data_root

import logging
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)
CONFIG_REL = Path("config/pipeline_demo_replay.json")
UPLOAD_DIR_REL = Path("public/pipeline_demo_replay")

_MAX_MB = int(os.environ.get("AIFACTORY_PIPELINE_DEMO_MAX_MB", "120"))
MAX_UPLOAD_BYTES = max(1, _MAX_MB) * 1024 * 1024

ALLOWED_EXT = frozenset({".webm", ".mp4", ".mov"})
FILENAME_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def config_file() -> Path:
    return data_root() / CONFIG_REL


def upload_dir() -> Path:
    return data_root() / UPLOAD_DIR_REL


def default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "title": "Pipeline demo replay",
        "source": "none",
        "video_url": None,
        "media_filename": None,
        "updated_at": None,
    }


def load_raw_config() -> dict[str, Any]:
    path = config_file()
    if not path.is_file():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_config()
    if not isinstance(data, dict):
        return default_config()
    base = default_config()
    for k in base:
        if k in data:
            base[k] = data[k]
    return base


def save_config(cfg: dict[str, Any]) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    out = dict(cfg)
    out["updated_at"] = time.time()
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def validate_external_url(url: str) -> bool:
    u = url.strip()
    if len(u) > 2048:
        return False
    if u.startswith(("https://", "http://")):
        return True
    if u.startswith("/") and not u.startswith("//"):
        return True
    return False


def play_url_for_metrics(cfg: dict[str, Any]) -> str | None:
    if not cfg.get("enabled"):
        return None
    src = cfg.get("source") or "none"
    if src == "upload":
        fn = cfg.get("media_filename")
        if isinstance(fn, str) and fn and FILENAME_SAFE.match(fn):
            # Public URL: <video> cannot send Bearer auth (admin media route would 401).
            return "/api/public/pipeline-demo-replay"
        return None
    if src == "external_url":
        vu = cfg.get("video_url")
        if isinstance(vu, str) and vu.strip():
            return vu.strip()
    return None


def metrics_demo_replay_slice(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg if cfg is not None else load_raw_config()
    pu = play_url_for_metrics(cfg)
    if not pu:
        return {
            "enabled": False,
            "title": str(cfg.get("title") or "Pipeline demo replay")[:200],
            "play_url": None,
        }
    return {
        "enabled": True,
        "title": str(cfg.get("title") or "Pipeline demo replay")[:200],
        "play_url": pu,
    }


def admin_public_config() -> dict[str, Any]:
    dr = load_raw_config()
    return {
        "enabled": bool(dr.get("enabled")),
        "title": str(dr.get("title") or "Pipeline demo replay")[:200],
        "source": dr.get("source") or "none",
        "video_url": dr.get("video_url"),
        "media_filename": dr.get("media_filename"),
        "updated_at": dr.get("updated_at"),
        "play_url": play_url_for_metrics(dr),
    }


def safe_remove_media(filename: str) -> None:
    if not isinstance(filename, str) or not FILENAME_SAFE.match(filename):
        return
    p = upload_dir() / filename
    try:
        if p.is_file():
            p.unlink()
    except OSError as _suppressed_exc:
        log_suppressed(logger, "non-fatal (web/backend/services/pipeline_demo_replay.py)", exc_info=_suppressed_exc)
