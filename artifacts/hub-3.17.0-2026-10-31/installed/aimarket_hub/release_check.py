"""Does a newer aimarket-hub exist? One read of PyPI's public JSON, said once, never blocking long.

A hub nobody tells about releases drifts out of the federation without noticing: rules
tighten (on 2026-10-12 every hub began refusing small-order Ed25519 keys), and an operator who
installed once and never looked again finds peers refusing them with no hint why. `doctor`
and `serve` say so when they start. Nothing is sent but the GET a `pip install` would make;
`AIMARKET_UPDATE_CHECK=0` turns it off.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

from aimarket_hub import __version__

PYPI_URL = "https://pypi.org/pypi/aimarket-hub/json"


def _key(version: str) -> tuple[int, ...]:
    """Numeric release parts; a pre-release or local suffix sorts as its release."""
    return tuple(int(p) for p in re.findall(r"\d+", version.split("+", 1)[0])[:4])


def enabled() -> bool:
    return os.environ.get("AIMARKET_UPDATE_CHECK", "1").strip().lower() not in ("0", "false", "no", "off")


def latest(timeout: float = 2.5, url: str = PYPI_URL) -> str | None:
    """The newest version on PyPI, or None when it cannot be read (offline is not an error)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"aimarket-hub/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(2_000_000))
        version = str((data.get("info") or {}).get("version") or "").strip()
        return version or None
    except Exception:  # noqa: BLE001 - a release check never breaks a command
        return None


def notice(current: str = __version__, newest: str | None = None) -> str | None:
    """A one-line notice when `newest` is ahead of `current`, else None."""
    if not newest:
        return None
    try:
        ahead = _key(newest) > _key(current)
    except ValueError:
        return None
    if not ahead:
        return None
    return (f"aimarket-hub {newest} is out (this hub runs {current}): "
            f"pip install -U \"aimarket-hub[pqc]\" — or pull the new image — and restart.")
