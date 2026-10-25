"""Package deliverable source without credentials, runtime state or filesystem links."""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path


_PRIVATE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".ssh", ".aws", ".codex", ".agents",
    ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".aicom_sandbox", ".next",
    "secrets", "private", "credentials", "state", "logs", "uploads", "backups",
    "runtime", "sandbox_previews",
})
_PRIVATE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".keystore", ".db", ".sqlite", ".sqlite3", ".pyc", ".log")
_ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template"})


def _deliverable_name(name: str) -> bool:
    lower = name.lower()
    if lower in _PRIVATE_DIRS or lower in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc", ".envrc"}:
        return False
    if lower.startswith(".env") and lower not in _ENV_TEMPLATES:
        return False
    if lower.endswith(_PRIVATE_SUFFIXES) or lower.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")):
        return False
    if lower.endswith(".json") and lower.startswith(("credentials", "secrets", "service-account", "service_account")):
        return False
    return True


def write_product_source(archive: zipfile.ZipFile, source: Path) -> None:
    """Use directory descriptors and O_NOFOLLOW so links never become ZIP contents.

    fwalk does not follow directory links. Relative descriptor opens keep a file
    inside the directory already traversed even if a parent path is renamed.
    """
    root = source.resolve(strict=True)
    for directory, dirs, files, directory_fd in os.fwalk(source, follow_symlinks=False):
        dirs[:] = sorted(name for name in dirs if _deliverable_name(name)
                         and stat.S_ISDIR(os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode))
        for name in sorted(files):
            if not _deliverable_name(name):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
                continue
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    continue
                entry = zipfile.ZipInfo(path.relative_to(source).as_posix())
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = (stat.S_IFREG | (stat.S_IMODE(info.st_mode) & 0o755)) << 16
                with archive.open(entry, "w") as output:
                    shutil.copyfileobj(handle, output)
