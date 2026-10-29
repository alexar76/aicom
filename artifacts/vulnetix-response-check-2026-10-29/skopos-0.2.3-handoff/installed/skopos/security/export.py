"""What SKOPOS publishes about its own findings, read-only.

MOMUS runs on another machine, binds to loopback, and its public edge refuses every
route that makes it act — `/scan`, `/retest`, `/remediate`, `/a2a/tasks` all return 404
there by design, as a second layer behind the operator token. `/skopos/report` is one
of those routes. So SKOPOS cannot post its findings across; it publishes them instead,
and the host that can reach MOMUS pulls and posts over its own loopback.

Reads leave here. Writes stay there. Neither machine gains a shell or a credential on
the other, and nothing that changes MOMUS becomes reachable from the internet.

The token is its OWN, not MOMUS's operator token: this endpoint may only be used to
read what a scan already found, so a leak of it discloses posture — bad, but bounded —
rather than granting the ability to file findings against any host MOMUS knows.
"""
from __future__ import annotations

import hmac
import os
from typing import Any

from ..db_connection import DbConnection
from .momus_push import build_document
from .store import latest_snapshots

TOKEN_ENV = "SKOPOS_EXPORT_TOKEN"
HEADER = "X-Skopos-Export-Token"


def export_enabled() -> bool:
    """Off until a token is set. An export with no token is an open posture report."""
    return bool((os.environ.get(TOKEN_ENV) or "").strip())


def token_ok(presented: str | None) -> bool:
    expected = (os.environ.get(TOKEN_ENV) or "").strip()
    supplied = (presented or "").strip()
    if not expected or not supplied:
        return False
    # compare_digest, not ==: a byte-at-a-time comparison on a public endpoint is a
    # prefix oracle for the token itself.
    return hmac.compare_digest(supplied, expected)


def build_export(con: DbConnection, server_names: list[str] | None = None) -> dict[str, Any]:
    """The newest snapshot of each server, in the shape MOMUS's bridge reads."""
    from .store import latest_disks

    documents = [build_document(con, snap) for snap in latest_snapshots(con, server_names)]
    # The newest disk usage each host reported (every ~5 min), beside the hourly findings: what an
    # alerter needs to page before a disk is full rather than an hour after.
    disks = latest_disks(con)
    for doc in documents:
        if doc.get("server") in disks:
            doc["disks_observed_at"], doc["disks"] = disks[doc["server"]]
    return {"documents": documents, "count": len(documents), "agents": _agents(con)}


def _agents(con: DbConnection) -> list[dict[str, Any]]:
    """Every enrolled agent and when its last report was ACCEPTED — a name and a time, no key id
    or address. On 2026-10-13 a deploy dropped four hosts from servers.yaml: their reports came
    back 400 for two hours, so they had no snapshot and no disk row, and an alerter that only
    reads documents never saw them go quiet."""
    from ..node_store import list_credentials

    try:
        creds = list_credentials(con)
    except Exception:
        return []
    return [{"server": c["server_name"], "last_seen_at": c.get("last_seen_at_utc")}
            for c in creds if not c.get("revoked_at_utc")]
