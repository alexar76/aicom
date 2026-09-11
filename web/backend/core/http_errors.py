"""Client-facing HTTP error helpers — avoid leaking host paths / stack noise."""

from __future__ import annotations

_PATH_MARKERS = ("/Users/", "/home/", "/root/", "/opt/", "/var/", "/tmp/", "C:\\", "\\\\")


def client_error_detail(
    exc: BaseException,
    *,
    fallback: str = "Bad request",
    max_len: int = 240,
) -> str:
    """Return a short, path-scrubbed message for intentional validation errors.

    Use for ``except ValueError`` (and similar) admin 400s. Never pass raw
    ``Exception`` / ``OSError`` strings — those become ``fallback``.
    """
    if not isinstance(exc, (ValueError, LookupError, KeyError)):
        return fallback
    msg = " ".join(str(exc).strip().split())
    if not msg or len(msg) > max_len:
        return fallback
    lower = msg.lower()
    if any(m.lower() in lower or m in msg for m in _PATH_MARKERS):
        return fallback
    return msg
