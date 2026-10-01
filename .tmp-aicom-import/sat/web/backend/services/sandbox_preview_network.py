"""Internal Docker bridge networks for compose sandbox previews (egress isolation)."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from web.backend.services.ai_market_protocol.config import _is_production_env

logger = logging.getLogger(__name__)


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def preview_network_isolation_enabled() -> bool:
    """Whether compose preview stacks run on an ``--internal`` (no-egress) network.

    Default-on. Disabling it lets untrusted generated code reach the internet (and,
    via the Docker host, potentially internal services), so:
      * a clear WARNING is logged whenever it is turned off, and
      * in production (``AIFACTORY_ENV``/``AIFACTORY_PROD``/``AIFACTORY_PRODUCTION``)
        the disable is REFUSED unless the operator also sets the explicit override
        ``AIFACTORY_SANDBOX_ALLOW_INSECURE_NETWORK=1`` — otherwise isolation is forced
        back on (fail-safe). (S6)
    """
    v = (os.environ.get("AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION") or "1").strip().lower()
    if v not in ("0", "false", "no", "off"):
        return True

    # Operator is asking to disable egress isolation.
    if _is_production_env() and not _env_truthy("AIFACTORY_SANDBOX_ALLOW_INSECURE_NETWORK"):
        logger.error(
            "sandbox network: refusing to disable preview network isolation in production "
            "(AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION=%s). Set "
            "AIFACTORY_SANDBOX_ALLOW_INSECURE_NETWORK=1 to override. Forcing isolation ON.",
            v,
        )
        return True

    logger.warning(
        "sandbox network: preview network isolation is DISABLED — untrusted compose "
        "stacks can reach the network/internet. This is unsafe for production."
    )
    return False


def _sanitize_net_name(raw: str, max_len: int = 63) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "sb"
    if len(s) > max_len:
        s = s[:max_len]
    return s


def preview_isolation_network_name(project: str) -> str:
    """Docker network name for a compose project (63-char limit)."""
    return _sanitize_net_name(f"aicom-sb-{project}")


def ensure_internal_bridge_network(network_name: str) -> bool:
    """
    Create an ``--internal`` bridge network if missing.
    Returns False if Docker is unavailable or create failed (caller may fall back to no isolation).
    """
    try:
        ins = subprocess.run(
            ["docker", "network", "inspect", network_name],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if ins.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("sandbox network: inspect unavailable (%s)", e)
        return False

    try:
        cr = subprocess.run(
            ["docker", "network", "create", "--driver", "bridge", "--internal", network_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if cr.returncode == 0:
            logger.info("sandbox network: created internal network %s", network_name)
            return True
        err = (cr.stderr or cr.stdout or "").strip()
        if "already exists" in err.lower():
            return True
        logger.warning("sandbox network: create failed name=%s err=%s", network_name, err[:400])
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("sandbox network: create unavailable (%s)", e)
        return False


def write_default_external_network_override(path: Path, network_name: str) -> None:
    """Compose fragment: attach project default network to our pre-created external network."""
    path.write_text(
        "networks:\n"
        "  default:\n"
        "    external: true\n"
        f"    name: {network_name}\n",
        encoding="utf-8",
    )


def remove_internal_network(network_name: str) -> None:
    try:
        rm = subprocess.run(
            ["docker", "network", "rm", network_name],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if rm.returncode == 0:
            logger.info("sandbox network: removed %s", network_name)
        else:
            err = (rm.stderr or rm.stdout or "").strip()
            if err and "not found" not in err.lower():
                logger.debug("sandbox network: rm %s: %s", network_name, err[:300])
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug("sandbox network: rm skipped (%s)", e)


def prepare_isolation_for_compose(project: str) -> Tuple[Optional[str], Optional[str]]:
    """
    If isolation is enabled and Docker works, create internal network and a temp override compose file.
    Returns (override_file_path, network_name) or (None, None) on skip/failure.
    """
    if not preview_network_isolation_enabled():
        return None, None
    net = preview_isolation_network_name(project)
    if not ensure_internal_bridge_network(net):
        return None, None
    try:
        fd, name = tempfile.mkstemp(prefix="aicom-net-", suffix=".yml")
        os.close(fd)
        p = Path(name)
        write_default_external_network_override(p, net)
        return str(p), net
    except OSError as e:
        logger.warning("sandbox network: temp override failed (%s)", e)
        remove_internal_network(net)
        return None, None
