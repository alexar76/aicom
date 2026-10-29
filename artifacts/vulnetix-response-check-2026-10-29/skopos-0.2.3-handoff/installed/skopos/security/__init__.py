"""SKOPOS security: probe a host, audit the snapshot, store and read the findings.

Imports are LAZY on purpose. Eagerly importing the probe pulled in paramiko through
`remote_ops`, so `skopos.security.momus_push` — which only reads a table and posts JSON —
could not be imported at all on a host with no SSH stack installed. That is not a
hypothetical: the conductor host is exactly such a host, and the failure surfaced as the
autopilot silently doing nothing.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers only, never at runtime
    from .audit import audit_snapshot
    from .collector import scan_all_servers, scan_server
    from .probe import ServerSnapshot, probe_server

__all__ = [
    "ServerSnapshot",
    "audit_snapshot",
    "probe_server",
    "scan_server",
    "scan_all_servers",
]

_LAZY = {
    "audit_snapshot": ".audit",
    "scan_all_servers": ".collector",
    "scan_server": ".collector",
    "ServerSnapshot": ".probe",
    "probe_server": ".probe",
}


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module, __name__), name)
