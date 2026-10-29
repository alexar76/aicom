"""The files SKOPOS installs on a monitored host.

``skopos_node.py`` is checked in rather than generated so that its behaviour can
be tested directly and so SKOPOS can verify, by hash, that the copy running on a
host is the copy it shipped. Only the privileged dumper is generated, because it
embeds the collection scripts from :mod:`skopos.remote_scripts` and those must
never drift from what the SSH path runs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
AGENT_SOURCE_PATH = AGENT_DIR / "skopos_node.py"


def agent_source() -> str:
    return AGENT_SOURCE_PATH.read_text(encoding="utf-8")


def agent_sha256() -> str:
    """Hash of the agent SKOPOS would install.

    Compared against what a host reports so a swapped agent is a finding rather
    than a silent change in what the fleet is telling us.
    """
    return hashlib.sha256(agent_source().encode("utf-8")).hexdigest()


def agent_version() -> str:
    for line in agent_source().splitlines():
        if line.startswith("AGENT_VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0"
