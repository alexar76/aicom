"""Auto product showcase — Playwright clip + gallery card on DEPLOYED/COMPLETED."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from core.paths import data_root

logger = logging.getLogger(__name__)

GALLERY_DIR = Path(__file__).resolve().parents[3] / "docs" / "gallery"
RECORDINGS_DIR = GALLERY_DIR / "recordings"
QUEUE_FILE = "state/product_showcase_queue.jsonl"
INDEX_FILE = "state/product_showcase_index.json"


def _queue_path() -> Path:
    p = data_root() / QUEUE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _index_path() -> Path:
    p = data_root() / INDEX_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_showcase_capture_base_url(explicit: str | None = None) -> str:
    """URL Playwright uses to open sandbox preview (must be reachable from this process)."""
    if explicit and str(explicit).strip():
        url = str(explicit).strip().rstrip("/")
    else:
        url = (
            os.environ.get("AIFACTORY_SHOWCASE_BASE_URL", "").strip()
            or os.environ.get("AIFACTORY_PUBLIC_URL", "").strip()
            or os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip()
            or "http://127.0.0.1:8080"
        ).rstrip("/")
    # In Docker the app listens on 8080; host-mapped 9080 is not open inside the container.
    if Path("/.dockerenv").is_file():
        for host in ("127.0.0.1", "localhost"):
            url = url.replace(f"http://{host}:9080", f"http://{host}:8080")
            url = url.replace(f"https://{host}:9080", f"https://{host}:8080")
    return url


def _pending_showcase_queued(pid: str, *, within_sec: float = 120.0) -> bool:
    q = _queue_path()
    if not q.is_file():
        return False
    cutoff = time.time() - within_sec
    for line in reversed(q.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("product_id") or "") != pid:
            continue
        if row.get("status") == "queued" and float(row.get("queued_at") or 0) >= cutoff:
            return True
    return False


def get_product_showcase_status(product_id: str) -> dict:
    """Last queue row for a product (queued / done / failed)."""
    pid = str(product_id or "").strip()
    if not pid:
        raise ValueError("product_id required")
    q = _queue_path()
    if not q.is_file():
        return {"product_id": pid, "status": "none"}
    last: dict | None = None
    for line in reversed(q.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("product_id") or "") == pid:
            last = row
            break
    if not last:
        return {"product_id": pid, "status": "none"}
    return {
        "product_id": pid,
        "status": str(last.get("status") or "unknown"),
        "queued_at": last.get("queued_at"),
        "completed_at": last.get("completed_at"),
        "error": last.get("error"),
        "base_url": last.get("base_url"),
    }


def enqueue_product_showcase(product_id: str, *, base_url: str | None = None) -> dict:
    """Queue a showcase capture job (deduped while a recent queued row exists)."""
    pid = str(product_id or "").strip()
    if not pid:
        raise ValueError("product_id required")
    capture_url = _resolve_showcase_capture_base_url(base_url)
    if _pending_showcase_queued(pid):
        return {"status": "already_queued", "product_id": pid, "base_url": capture_url}
    row = {
        "product_id": pid,
        "queued_at": time.time(),
        "base_url": capture_url,
        "status": "queued",
    }
    q = _queue_path()
    with q.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _spawn_worker_once()
    return {"status": "queued", "product_id": pid, "base_url": capture_url}


def _spawn_worker_once() -> None:
    if os.environ.get("AIFACTORY_SHOWCASE_WORKER_DISABLED", "").lower() in ("1", "true", "yes"):
        return
    t = threading.Thread(target=_process_queue, name="product-showcase", daemon=True)
    t.start()


def _process_queue() -> None:
    q = _queue_path()
    if not q.is_file():
        return
    lines = q.read_text(encoding="utf-8", errors="replace").splitlines()
    pending: list[dict] = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") == "queued":
            pending.append(row)
    for row in pending[:3]:
        pid = str(row.get("product_id") or "")
        if not pid:
            continue
        try:
            _capture_showcase(pid, base_url=str(row.get("base_url") or "http://127.0.0.1:9080"))
            row["status"] = "done"
            row["completed_at"] = time.time()
        except Exception as exc:
            logger.warning("showcase capture failed for %s: %s", pid, exc)
            row["status"] = "failed"
            row["error"] = str(exc)[:500]
    # Rewrite queue tail (keep last 200 rows)
    kept = []
    for line in lines[-200:]:
        try:
            kept.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    for row in pending:
        for i, k in enumerate(kept):
            if k.get("product_id") == row.get("product_id") and k.get("queued_at") == row.get("queued_at"):
                kept[i] = row
    q.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + ("\n" if kept else ""), encoding="utf-8")


def _capture_showcase(product_id: str, *, base_url: str) -> None:
    """Record sandbox preview clip via existing demo script helper."""
    repo = Path(__file__).resolve().parents[3]
    script = repo / "scripts" / "record_product_showcase.py"
    if not script.is_file():
        _write_gallery_stub(product_id, base_url)
        return
    env = os.environ.copy()
    env["DEMO_VIDEO_BASE_URL"] = base_url
    env["DEMO_VIDEO_SANDBOX_PRODUCT_ID"] = product_id
    env["DEMO_VIDEO_OUT"] = str(RECORDINGS_DIR)
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo),
        env=env,
        timeout=int(os.environ.get("AIFACTORY_SHOWCASE_TIMEOUT_SEC", "300")),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        raise RuntimeError(err or f"record_product_showcase exited {proc.returncode}")
    _register_gallery_entry(product_id, base_url)


def _write_gallery_stub(product_id: str, base_url: str) -> None:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "product_id": product_id,
        "preview_url": f"{base_url}/api/sandbox/preview/{product_id}/",
        "captured_at": time.time(),
        "kind": "stub",
    }
    stub = RECORDINGS_DIR / f"showcase-{product_id}.json"
    stub.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _register_gallery_entry(product_id, base_url, media=f"showcase-{product_id}.json")


def _register_gallery_entry(product_id: str, base_url: str, media: str | None = None) -> None:
    idx_path = _index_path()
    idx: dict = {}
    if idx_path.is_file():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            idx = {}
    entries = idx.get("entries") if isinstance(idx.get("entries"), list) else []
    clip = media or f"showcase-{product_id}.webm"
    entries = [e for e in entries if e.get("product_id") != product_id]
    entries.insert(
        0,
        {
            "product_id": product_id,
            "clip": clip,
            "preview_url": f"{base_url}/api/sandbox/preview/{product_id}/",
            "updated_at": time.time(),
        },
    )
    idx["entries"] = entries[:48]
    idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")


def _clip_path(clip: str) -> Path:
    name = Path(str(clip or "")).name
    return RECORDINGS_DIR / name


def _entry_has_playable_clip(entry: dict) -> bool:
    clip = str(entry.get("clip") or "")
    if not (clip.endswith(".webm") or clip.endswith(".mp4")):
        return bool(clip)
    path = _clip_path(clip)
    try:
        return path.is_file() and path.stat().st_size > 1024
    except OSError:
        return False


def list_showcase_gallery() -> dict:
    idx_path = _index_path()
    if not idx_path.is_file():
        return {"entries": [], "count": 0}
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"entries": [], "count": 0}
    entries = idx.get("entries") if isinstance(idx.get("entries"), list) else []
    playable = [e for e in entries if isinstance(e, dict) and _entry_has_playable_clip(e)]
    if len(playable) != len(entries):
        idx["entries"] = playable
        idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"entries": playable, "count": len(playable)}


def maybe_enqueue_on_deploy(product_id: str, new_state: str) -> None:
    st = str(new_state or "").upper()
    if st not in ("DEPLOYED_PRODUCTION", "COMPLETED"):
        return
    if os.environ.get("AIFACTORY_AUTO_SHOWCASE", "1").lower() in ("0", "false", "no"):
        return
    try:
        enqueue_product_showcase(product_id)
    except Exception:
        logger.debug("auto showcase enqueue skipped", exc_info=True)
