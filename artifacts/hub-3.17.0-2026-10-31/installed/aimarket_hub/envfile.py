"""The operator's settings file: ``data/aimarket.env``, beside the database and the keys.

`aimarket quickstart` writes it and every `aimarket` command reads it, so a hub keeps the
settings it was set up with across restarts and shells. Before it existed the quickstart
printed five `export` lines; the first `serve` from a new terminal then ran without them —
credits off, so every priced capability was served free, and no admin token, so the
operator could not approve a peer or top up a buyer. Measured 2026-10-12 by following the
operator quickstart from a clean machine.

The real environment always wins: a value already set in the process (systemd
``EnvironmentFile``, ``docker run -e``, an ``export``) is never replaced by the file.

The file holds the admin token, so it is written 0600, like the signing keys next to it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

FILE_NAME = "aimarket.env"
_HEADER = (
    "# Written by `aimarket quickstart`. Read by every `aimarket` command;",
    "# a variable already set in the environment wins over this file.",
    "# Holds the admin token: keep it 0600 and back it up with the keys.",
)
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def candidates() -> list[Path]:
    """Where the file may be, first match wins."""
    explicit = os.environ.get("AIMARKET_ENV_FILE", "").strip()
    if explicit:
        return [Path(explicit)]
    out: list[Path] = []
    db_path = os.environ.get("AIMARKET_DB_PATH", "").strip()
    if db_path:
        out.append(Path(db_path).parent / FILE_NAME)
    out.append(Path("data") / FILE_NAME)
    return out


def default_path(db_path: str | os.PathLike[str]) -> Path:
    """Where quickstart writes it: next to the database the hub actually uses."""
    explicit = os.environ.get("AIMARKET_ENV_FILE", "").strip()
    if explicit:
        return Path(explicit)
    return Path(db_path).parent / FILE_NAME


def parse(text: str) -> dict[str, str]:
    """``KEY=value`` lines; ``#`` comments, blank lines and an optional ``export`` ignored."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _KEY.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def read(path: Path) -> dict[str, str]:
    try:
        return parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def load() -> Path | None:
    """Apply the first settings file found to ``os.environ``. Returns its path or None."""
    for path in candidates():
        if path.is_file():
            for key, value in read(path).items():
                os.environ.setdefault(key, value)
            return path
    return None


def merge(path: Path, values: dict[str, str]) -> dict[str, str]:
    """Add the keys the file does not have yet; never change one it already has.

    Returns what was added. Idempotent: running quickstart again keeps the same admin
    token and the same name, so nothing an operator already relies on moves under them.
    """
    existing = read(path)
    added = {k: v for k, v in values.items() if k not in existing and v != ""}
    if not added and path.exists():
        return {}
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        current = path.read_bytes()
        if current and not current.endswith(b"\n"):
            lines.append("")  # an operator's last line without a newline stays its own line
    else:
        lines.extend(_HEADER)
    lines += [f"{k}={v}" for k, v in added.items()]
    body = "\n".join(lines) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, body.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return added


def update(path: Path, values: dict[str, str]) -> None:
    """Set these keys, replacing a line the file already has. For an explicit operator choice
    (`quickstart --name …`), which must win over the value saved last time."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else list(_HEADER)
    pending = dict(values)
    out: list[str] = []
    for raw in lines:
        key = raw.strip().removeprefix("export ").partition("=")[0].strip()
        if key in pending:
            out.append(f"{key}={pending.pop(key)}")
        else:
            out.append(raw)
    out += [f"{k}={v}" for k, v in pending.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, ("\n".join(out) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
