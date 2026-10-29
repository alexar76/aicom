"""Small persistent last-good snapshots for cache-first dashboards.

Streamlit's function cache only returns an exact cache key.  Relative periods
move over time, so an exact-key miss must not turn the page into a blank loading
screen.  This store keeps one trusted, locally-produced presentation snapshot
per semantic dashboard/filter/period key.  The UI paints it first and replaces
it only after the fresh queries complete successfully.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import pickle
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from plotly.utils import PlotlyJSONEncoder

from .config_paths import project_root

SNAPSHOT_VERSION = 1
_MAX_SNAPSHOTS = 128
_LOCK = threading.RLock()


def _cache_dir(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override)
    configured = os.environ.get("SKOPOS_DASHBOARD_CACHE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return project_root() / "data" / "dashboard_cache"


def _snapshot_path(namespace: str, signature: str, cache_dir: str | Path | None = None) -> Path:
    digest = hashlib.sha256(f"{namespace}\0{signature}".encode("utf-8")).hexdigest()
    return _cache_dir(cache_dir) / f"{digest}.snapshot"


def load_dashboard_snapshot(
    namespace: str,
    signature: str,
    *,
    cache_dir: str | Path | None = None,
    db_target: str | None = None,
) -> dict[str, Any] | None:
    """Return the last complete snapshot, never failing the dashboard.

    The database is authoritative so snapshots survive container restarts and
    are shared by every web worker.  The local file remains a fast fallback for
    single-process/dev deployments.
    """
    cache_key = _cache_key(namespace, signature)
    if db_target:
        payload = _load_from_db(db_target, cache_key)
        if payload is not None:
            return payload
    path = _snapshot_path(namespace, signature, cache_dir)
    try:
        with _LOCK, path.open("rb") as fh:
            envelope = pickle.load(fh)  # trusted local file at a hashed, fixed path
        if not isinstance(envelope, dict) or envelope.get("version") != SNAPSHOT_VERSION:
            return None
        payload = envelope.get("payload")
        return payload if isinstance(payload, dict) else None
    except (OSError, EOFError, pickle.PickleError, AttributeError, ValueError):
        return None


def save_dashboard_snapshot(
    namespace: str,
    signature: str,
    payload: dict[str, Any],
    *,
    cache_dir: str | Path | None = None,
    db_target: str | None = None,
) -> None:
    """Atomically replace a last-good snapshot after all queries succeeded."""
    directory = _cache_dir(cache_dir)
    path = _snapshot_path(namespace, signature, cache_dir)
    envelope = {
        "version": SNAPSHOT_VERSION,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    if db_target:
        _save_to_db(db_target, _cache_key(namespace, signature), envelope)
    tmp_path: Path | None = None
    try:
        with _LOCK:
            directory.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".snapshot-", dir=str(directory))
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "wb") as fh:
                pickle.dump(envelope, fh, protocol=pickle.HIGHEST_PROTOCOL)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, path)
            _trim(directory)
    except (OSError, pickle.PickleError, TypeError, ValueError):
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _cache_key(namespace: str, signature: str) -> str:
    return hashlib.sha256(f"{namespace}\0{signature}".encode("utf-8")).hexdigest()


_TYPE_KEY = "__skopos_snapshot_type__"


def should_refresh_snapshot(payload: dict[str, Any] | None, requested: bool) -> bool:
    """A snapshot refreshes only when absent or explicitly requested now."""
    return payload is None or requested


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {
            _TYPE_KEY: "dataframe",
            "value": value.to_json(orient="table", date_format="iso"),
        }
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _restore_json(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get(_TYPE_KEY) == "dataframe" and isinstance(value.get("value"), str):
            return pd.read_json(io.StringIO(value["value"]), orient="table")
        return {key: _restore_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_json(item) for item in value]
    return value


def _decode_envelope(raw: str) -> dict[str, Any] | None:
    try:
        decoded = base64.b64decode(raw.encode("ascii")).decode("utf-8")
        envelope = _restore_json(json.loads(decoded))
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        AttributeError,
    ):
        return None
    if not isinstance(envelope, dict) or envelope.get("version") != SNAPSHOT_VERSION:
        return None
    payload = envelope.get("payload")
    return payload if isinstance(payload, dict) else None


def _load_from_db(db_target: str, cache_key: str) -> dict[str, Any] | None:
    from .db_connection import connect

    con = None
    try:
        con = connect(db_target)
        row = con.execute(
            "SELECT payload_b64 FROM dashboard_ui_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        raw = row["payload_b64"] if hasattr(row, "keys") else row[0]
        return _decode_envelope(str(raw))
    except Exception:  # cache failure must never take down analytics
        return None
    finally:
        if con is not None:
            con.close()


def _save_to_db(db_target: str, cache_key: str, envelope: dict[str, Any]) -> None:
    from .db_connection import connect

    con = None
    try:
        serialized = json.dumps(
            _json_safe(envelope),
            cls=PlotlyJSONEncoder,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.b64encode(serialized).decode("ascii")
        con = connect(db_target)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_ui_cache (
              cache_key TEXT PRIMARY KEY,
              payload_b64 TEXT NOT NULL,
              updated_at_utc TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            INSERT INTO dashboard_ui_cache(cache_key, payload_b64, updated_at_utc)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
              payload_b64 = excluded.payload_b64,
              updated_at_utc = excluded.updated_at_utc
            """,
            (cache_key, encoded, str(envelope["captured_at_utc"])),
        )
        con.commit()
    except Exception:  # local file fallback below remains available
        pass
    finally:
        if con is not None:
            con.close()


def _trim(directory: Path) -> None:
    try:
        files = sorted(
            directory.glob("*.snapshot"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old in files[_MAX_SNAPSHOTS:]:
            old.unlink(missing_ok=True)
    except OSError:
        pass
