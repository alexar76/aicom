"""Docker availability and ephemeral DB containers for sandbox previews."""

from __future__ import annotations

import logging
import re
import socket
import subprocess
import time
from typing import Optional
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


def pick_loopback_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    _, port = s.getsockname()
    s.close()
    return int(port)

_PG_CONTAINERS: dict[str, str] = {}


def docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=12,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _sanitize_name(raw: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")[:48] or "sb"


def ensure_ephemeral_postgres(
    sandbox_id: str,
    *,
    user: str = "sandbox",
    password: str = "sandbox",
    database: str = "sandbox",
) -> tuple[Optional[int], Optional[str], str]:
    """
    Start a throwaway Postgres 16 on loopback via ``docker run``.
    Returns (host_port, DATABASE_URL for asyncpg/sync, status).
    """
    if not docker_available():
        return None, None, "docker_unavailable"

    port = pick_loopback_port()
    cname = f"aicom-pg-{_sanitize_name(sandbox_id)}"
    _stop_ephemeral_postgres(sandbox_id)

    cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        cname,
        "-e",
        f"POSTGRES_USER={user}",
        "-e",
        f"POSTGRES_PASSWORD={password}",
        "-e",
        f"POSTGRES_DB={database}",
        "-p",
        f"127.0.0.1:{port}:5432",
        "postgres:16-alpine",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("ephemeral postgres: docker run failed %s", e)
        return None, None, "postgres_start_failed"

    if r.returncode != 0:
        err = ((r.stderr or "") + (r.stdout or ""))[:600]
        logger.warning("ephemeral postgres: docker run rc=%s err=%s", r.returncode, err)
        return None, None, "postgres_start_failed"

    _PG_CONTAINERS[sandbox_id] = cname
    url = f"postgresql://{user}:{password}@127.0.0.1:{port}/{database}"
    if not _wait_pg_ready(cname, user, database, timeout_sec=45.0):
        _stop_ephemeral_postgres(sandbox_id)
        return None, None, "postgres_not_ready"

    logger.info("ephemeral postgres ready sandbox=%s port=%s", sandbox_id[:16], port)
    return port, url, "ok"


def _wait_pg_ready(cname: str, user: str, database: str, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = subprocess.run(
                ["docker", "exec", cname, "pg_isready", "-U", user, "-d", database],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, OSError) as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/sandbox_docker.py)", exc_info=_suppressed_exc)
        time.sleep(0.5)
    return False


def _stop_ephemeral_postgres(sandbox_id: str) -> None:
    cname = _PG_CONTAINERS.pop(sandbox_id, None)
    if not cname:
        return
    try:
        subprocess.run(["docker", "stop", cname], capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("stop ephemeral postgres %s: %s", cname, e)


def stop_ephemeral_services(sandbox_id: str) -> None:
    _stop_ephemeral_postgres(sandbox_id)
