"""
Full factory data backup (ZIP of AIFACTORY_DATA_ROOT).

Used by Admin → Settings → Factory backup (admin+ only).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.logging_utils import log_suppressed
from core.paths import config_path, data_root, pipeline_db_path, workspace_id

logger = logging.getLogger(__name__)

_RESTORE_UPLOADS_DIR = "_restore_uploads"
_RESTORE_LOCK = Path("state") / ".factory_restore_lock"
_PRESERVE_TOP_LEVEL = frozenset({"backups", _RESTORE_UPLOADS_DIR})

_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
        "target",
        ".cargo",
        ".eggs",
        "site-packages",
    }
)

# Optional top-level dirs under data/ (heavy ephemeral previews).
_DEFAULT_SKIP_TOP_LEVEL = frozenset({"sandboxes"})

_MAX_FILES = 200_000
_MAX_FILE_BYTES = 512 * 1024 * 1024


def _should_skip_dir(name: str, *, include_sandboxes: bool) -> bool:
    if name in _SKIP_DIR_NAMES:
        return True
    if not include_sandboxes and name in _DEFAULT_SKIP_TOP_LEVEL:
        return True
    return False


def build_factory_backup_zip(*, include_sandboxes: bool = False) -> tuple[Path, str]:
    """
    Write a temporary ZIP and return (path, suggested_download_filename).

    Caller must delete ``path`` after streaming (BackgroundTasks).
    """
    root = data_root().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Data root not found: {root}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    ws = workspace_id().replace("/", "_")[:64]
    filename = f"aicom-factory-backup-{ws}-{ts}.zip"

    fd, tmp_path = tempfile.mkstemp(prefix="aicom-factory-backup-", suffix=".zip")
    os.close(fd)

    file_count = 0
    skipped_large: list[dict[str, Any]] = []
    skipped_top_level: list[str] = []

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for dirpath, dirnames, filenames, dir_fd in os.fwalk(root, topdown=True, follow_symlinks=False):
                rel_dir = Path(dirpath).relative_to(root)
                pruned: list[str] = []
                for d in sorted(dirnames):
                    if len(rel_dir.parts) == 0 and (
                        d in _PRESERVE_TOP_LEVEL
                        or (not include_sandboxes and d in _DEFAULT_SKIP_TOP_LEVEL)
                    ):
                        skipped_top_level.append(d)
                        continue
                    if _should_skip_dir(d, include_sandboxes=include_sandboxes):
                        continue
                    pruned.append(d)
                dirnames[:] = pruned
                for name in sorted(filenames):
                    if file_count >= _MAX_FILES:
                        skipped_large.append(
                            {
                                "reason": f"backup capped at {_MAX_FILES} files",
                                "last_path": str(Path(dirpath) / name),
                            }
                        )
                        break
                    fpath = Path(dirpath) / name
                    # Generated code can contain symlinks. Open relative to the
                    # walked directory descriptor so a path swap cannot redirect
                    # the read outside data/. O_NONBLOCK also avoids blocking on
                    # a FIFO before fstat rejects non-regular files.
                    try:
                        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
                    except OSError:
                        continue
                    with os.fdopen(fd, "rb") as source:
                        source_stat = os.fstat(source.fileno())
                        if not stat.S_ISREG(source_stat.st_mode):
                            continue
                        size_bytes = source_stat.st_size
                        if size_bytes > _MAX_FILE_BYTES:
                            skipped_large.append(
                                {
                                    "path": str(fpath.relative_to(root)),
                                    "size_bytes": size_bytes,
                                    "reason": f"file larger than {_MAX_FILE_BYTES} bytes",
                                }
                            )
                            continue
                        arc = fpath.relative_to(root).as_posix()
                        date_time = datetime.fromtimestamp(source_stat.st_mtime).timetuple()[:6]
                        if not 1980 <= date_time[0] <= 2107:
                            date_time = (1980, 1, 1, 0, 0, 0)
                        info = zipfile.ZipInfo(arc, date_time=date_time)
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = source_stat.st_mode << 16
                        with zf.open(info, "w", force_zip64=True) as target:
                            shutil.copyfileobj(source, target)
                        file_count += 1
                if file_count >= _MAX_FILES:
                    break

            manifest: dict[str, Any] = {
                "backup_type": "aicom_factory_full",
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "workspace_id": workspace_id(),
                "data_root": str(root),
                "pipeline_db": str(pipeline_db_path()),
                "include_sandboxes": include_sandboxes,
                "files_in_zip": file_count,
                "skipped_top_level_dirs": sorted(set(skipped_top_level)) or None,
                "skipped_large_or_truncated": skipped_large or None,
                "restore_hint": (
                    "Stop the app, extract this ZIP over your data bind mount "
                    "(e.g. ./data), preserving permissions. Restart containers."
                ),
            }
            zf.writestr(
                "_BACKUP_MANIFEST.json",
                (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
            )
            readme = (
                "AI-Factory — full instance backup (data volume).\n"
                "Contains pipeline DB, configs, secrets, product code/specs, logs, discovery, etc.\n"
                "Open _BACKUP_MANIFEST.json for caps and skipped paths.\n"
                "This is NOT a per-product export (see Admin → Files → Download product ZIP).\n\n"
                "Respaldo completo del volumen data/ de la fábrica.\n"
                "Резервная копия всего каталога data/ фабрики.\n"
            )
            zf.writestr("_BACKUP_README.txt", readme.encode("utf-8"))
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            log_suppressed(logger, "factory backup: temp zip cleanup failed", exc_info=True)
        raise

    return Path(tmp_path), filename


def factory_backups_dir() -> Path:
    d = data_root() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def persist_factory_backup_to_disk(*, include_sandboxes: bool = False) -> dict[str, Any]:
    """
    Build a factory ZIP and move it into ``data/backups/`` (scheduled / on-disk backups).
    """
    zip_path, filename = build_factory_backup_zip(include_sandboxes=include_sandboxes)
    dest = factory_backups_dir() / filename
    try:
        shutil.move(str(zip_path), str(dest))
    except Exception:
        zip_path.unlink(missing_ok=True)
        raise
    size = dest.stat().st_size
    return {
        "filename": filename,
        "relative_path": f"backups/{filename}",
        "size_bytes": size,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def list_on_disk_factory_backups(*, limit: int = 20) -> list[dict[str, Any]]:
    """Newest-first ZIPs in data/backups/ matching factory backup naming."""
    out: list[dict[str, Any]] = []
    bdir = factory_backups_dir()
    files = sorted(
        (p for p in bdir.glob("aicom-factory-backup-*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in files[: max(1, limit)]:
        st = p.stat()
        out.append(
            {
                "filename": p.name,
                "relative_path": f"backups/{p.name}",
                "size_bytes": st.st_size,
                "modified_at_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return out


def prune_factory_backups_on_disk(*, retention: int) -> list[str]:
    """Keep the newest ``retention`` scheduled backups; delete older aicom-factory-backup-*.zip."""
    keep = max(1, min(int(retention), 365))
    bdir = factory_backups_dir()
    files = sorted(
        (p for p in bdir.glob("aicom-factory-backup-*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed: list[str] = []
    for p in files[keep:]:
        try:
            p.unlink(missing_ok=True)
            removed.append(p.name)
        except OSError:
            log_suppressed(logger, f"factory backup prune failed for {p.name}", exc_info=True)
    return removed


def _restore_uploads_dir() -> Path:
    d = data_root() / _RESTORE_UPLOADS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _restore_upload_path(token: str) -> Path:
    # Only tokens minted by save_restore_upload may select a ZIP. In particular,
    # reject traversal before restore's finally block can delete that path.
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise ValueError("Invalid restore token")
    return _restore_uploads_dir() / f"{token}.zip"


def _read_backup_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = zf.read("_BACKUP_MANIFEST.json")
    except KeyError as e:
        raise ValueError("Not an AI-Factory backup ZIP (_BACKUP_MANIFEST.json missing)") from e
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid backup manifest")
    if data.get("backup_type") != "aicom_factory_full":
        raise ValueError("ZIP is not a full factory backup (backup_type mismatch)")
    return data


def _validate_zip_member(dest_real: Path, info: zipfile.ZipInfo) -> None:
    """Reject ZipSlip, absolute paths, and symlink entries before extraction."""
    name = info.filename
    if not name or name.endswith("/"):
        # Directory entries still must not escape the staging root.
        if name:
            _validate_zip_member_path(dest_real, name)
        return
    _validate_zip_member_path(dest_real, name)
    mode = (info.external_attr >> 16) & 0xFFFF
    if info.create_system == 3 and stat.S_ISLNK(mode):
        raise ValueError(f"Refusing symlink in backup: {name!r}")


def _validate_zip_member_path(dest_real: Path, name: str) -> None:
    if name.startswith(("/", "\\")) or os.path.isabs(name):
        raise ValueError(f"Absolute path in backup: {name!r}")
    if ".." in Path(name.replace("\\", "/")).parts:
        raise ValueError(f"Path traversal in backup: {name!r}")
    target = (dest_real / name).resolve()
    try:
        target.relative_to(dest_real)
    except ValueError as exc:
        raise ValueError(f"Path traversal in backup: {name!r}") from exc


def safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a validated backup and preserve ordinary Unix permission bits."""
    dest_real = dest.resolve()
    dest_real.mkdir(parents=True, exist_ok=True)
    members = zf.infolist()
    for info in members:
        _validate_zip_member(dest_real, info)
    zf.extractall(dest_real)
    # ZipFile does not restore stored permissions. Without this a 0600 secret
    # becomes 0644 (under a normal umask), and executable product scripts stop
    # working. Apply directory modes last so a read-only parent cannot block
    # extraction or a child's chmod. Never restore setuid/setgid/sticky bits.
    for info in sorted(members, key=lambda item: (item.is_dir(), -len(Path(item.filename).parts))):
        mode = (info.external_attr >> 16) & 0xFFFF
        if info.create_system == 3 and mode:
            (dest_real / info.filename).chmod(stat.S_IMODE(mode) & 0o777)


def inspect_backup_zip(zip_path: Path) -> dict[str, Any]:
    """Read manifest and file stats from an uploaded backup ZIP."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest = _read_backup_manifest(zf)
        files = [info for info in zf.infolist() if not info.is_dir()]
        total_uncompressed = sum(info.file_size for info in files)
    return {
        "backup_manifest": manifest,
        "archive_files": len(files),
        "archive_bytes_uncompressed": total_uncompressed,
    }


def scan_current_factory_state() -> dict[str, Any]:
    """Snapshot of live data/ for restore warnings."""
    root = data_root().resolve()
    out: dict[str, Any] = {
        "data_root": str(root),
        "workspace_id": workspace_id(),
        "has_config_overlay": config_path().is_file(),
        "config_path": str(config_path()),
        "pipeline_db_path": str(pipeline_db_path()),
        "pipeline_db_exists": pipeline_db_path().is_file(),
        "top_level_dirs": [],
        "data_total_bytes": 0,
        "products_total": 0,
        "products_by_state": {},
        "has_secrets_dir": (root / "secrets").is_dir(),
        "has_code_dir": (root / "code").is_dir(),
    }
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir():
                out["top_level_dirs"].append(child.name)
            try:
                if child.is_file():
                    out["data_total_bytes"] += child.stat().st_size
                elif child.is_dir() and child.name not in _PRESERVE_TOP_LEVEL:
                    for dirpath, _dn, filenames in os.walk(child, followlinks=False):
                        for fn in filenames:
                            try:
                                out["data_total_bytes"] += (Path(dirpath) / fn).stat().st_size
                            except OSError:
                                pass
            except OSError:
                pass
    db = pipeline_db_path()
    if db.is_file():
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            wid = workspace_id()
            row = conn.execute(
                "SELECT COUNT(*) FROM products WHERE workspace_id = ?",
                (wid,),
            ).fetchone()
            out["products_total"] = int(row[0]) if row else 0
            rows = conn.execute(
                "SELECT state, COUNT(*) FROM products WHERE workspace_id = ? GROUP BY state",
                (wid,),
            ).fetchall()
            out["products_by_state"] = {str(s or "unknown"): int(c) for s, c in rows}
            conn.close()
        except sqlite3.Error as e:
            out["pipeline_db_error"] = str(e)
    return out


def save_restore_upload(content: bytes) -> tuple[str, Path]:
    """Persist uploaded ZIP; return (token, path)."""
    if len(content) < 32:
        raise ValueError("Upload is empty or too small")
    max_mb = int(os.environ.get("AIFACTORY_FACTORY_RESTORE_MAX_MB", "2048") or 2048)
    max_bytes = max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(f"Backup ZIP exceeds limit ({max_mb} MB)")
    token = uuid.uuid4().hex
    dest = _restore_uploads_dir() / f"{token}.zip"
    dest.write_bytes(content)
    return token, dest


def preview_restore(token: str) -> dict[str, Any]:
    path = _restore_upload_path(token)
    if not path.is_file():
        raise FileNotFoundError("Upload expired or not found — upload the ZIP again")
    backup = inspect_backup_zip(path)
    current = scan_current_factory_state()
    warnings: list[str] = []
    # Baseline warning intrinsic to the mode: a full snapshot replaces the entire data/
    # directory (not a merge), even when the current data dir looks empty.
    warnings.append(
        "Full snapshot restore will REPLACE the entire data/ directory — this is not a merge."
    )
    if current.get("products_total", 0) > 0:
        warnings.append(
            f"Current pipeline has {current['products_total']} product(s) — restore will REPLACE them."
        )
    if current.get("has_config_overlay"):
        warnings.append("Platform settings overlay on disk will be replaced by the backup.")
    if current.get("has_secrets_dir"):
        warnings.append("Secrets (JWT, LLM keys, bootstrap) will be replaced — ensure the backup is trusted.")
    bws = backup.get("backup_manifest", {}).get("workspace_id")
    if bws and bws != workspace_id():
        warnings.append(
            f"Backup workspace_id={bws!r} differs from current {workspace_id()!r}."
        )
    return {
        "restore_token": token,
        "restore_mode": "full_snapshot_replace",
        "backup": backup,
        "current": current,
        "warnings": warnings,
    }


def _clear_data_root_for_restore(root: Path) -> list[str]:
    removed: list[str] = []
    for child in list(root.iterdir()):
        if child.name in _PRESERVE_TOP_LEVEL:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=False)
        else:
            child.unlink(missing_ok=True)
        removed.append(child.name)
    return removed


def restore_factory_from_upload(
    token: str,
    *,
    create_pre_restore_backup: bool = True,
) -> dict[str, Any]:
    """
    Full snapshot restore: replace data/ contents from uploaded ZIP (not a merge).

    Leaves ``data/backups/`` and ``data/_restore_uploads/`` intact; writes a pre-restore
    ZIP into ``data/backups/`` when requested.
    """
    upload_path = _restore_upload_path(token)
    if not upload_path.is_file():
        raise FileNotFoundError("Upload expired or not found — upload the ZIP again")

    root = data_root().resolve()
    lock_path = root / _RESTORE_LOCK
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    pre_backup_name: str | None = None
    try:
        lock_path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

        with zipfile.ZipFile(upload_path, "r") as zf:
            _read_backup_manifest(zf)

        if create_pre_restore_backup:
            pre_path, pre_backup_name = build_factory_backup_zip(include_sandboxes=False)
            try:
                backups_dir = root / "backups"
                backups_dir.mkdir(parents=True, exist_ok=True)
                dest = backups_dir / (pre_backup_name or "pre-restore.zip")
                shutil.move(str(pre_path), str(dest))
            except Exception:
                pre_path.unlink(missing_ok=True)
                raise

        staging = Path(tempfile.mkdtemp(prefix="aicom-restore-staging-"))
        try:
            with zipfile.ZipFile(upload_path, "r") as zf:
                safe_extract_zip(zf, staging)
            removed = _clear_data_root_for_restore(root)
            copied = 0
            for item in staging.iterdir():
                if item.name.startswith("_BACKUP_") or item.name in _PRESERVE_TOP_LEVEL:
                    continue
                dest = root / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, symlinks=True, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest, follow_symlinks=False)
                copied += 1
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        try:
            from core.pipeline_state_writer import notify_pipeline_worker_wake

            notify_pipeline_worker_wake()
        except Exception:
            log_suppressed(logger, "restore: pipeline wake notify failed", exc_info=True)

        return {
            "ok": True,
            "restore_mode": "full_snapshot_replace",
            "removed_top_level": removed,
            "restored_entries": copied,
            "pre_restore_backup_file": (
                f"backups/{pre_backup_name}" if pre_backup_name else None
            ),
            "restart_recommended": True,
            "message": (
                "Full factory restore completed. Restart the app container (docker compose restart app) "
                "so API and pipeline worker reload pipeline.db and secrets."
            ),
        }
    finally:
        lock_path.unlink(missing_ok=True)
        try:
            upload_path.unlink(missing_ok=True)
        except OSError:
            log_suppressed(logger, "restore: upload cleanup failed", exc_info=True)
