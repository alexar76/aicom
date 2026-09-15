"""Docker availability and ephemeral DB containers for sandbox previews."""

from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
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


def docker_cli_env(base: dict | None = None) -> dict[str, str]:
    """Env for Docker CLI against the DinD sidecar.

    The DinD TLS cert SAN is ``docker`` (not ``docker-dind``). Rewrite the
    hostname so ``docker info`` / ``docker compose`` verify TLS.
    """
    env = {str(k): str(v) for k, v in (base or os.environ).items()}
    host = (env.get("DOCKER_HOST") or "").strip()
    if "://docker-dind:" in host:
        env["DOCKER_HOST"] = host.replace("://docker-dind:", "://docker:")
    return env


def docker_daemon_host() -> str:
    """Hostname the factory app can use to reach ports published by DinD.

    Unix-socket Docker → loopback. TCP DinD → the rewritten CLI hostname
    (``docker``), whose published ports are on that container, not 127.0.0.1.
    """
    host = (docker_cli_env().get("DOCKER_HOST") or "").strip()
    if host.startswith("tcp://"):
        rest = host[len("tcp://") :]
        if rest.startswith("["):
            end = rest.find("]")
            if end > 0:
                return rest[1:end]
        return rest.rsplit(":", 1)[0]
    return "127.0.0.1"


def docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=12,
            env=docker_cli_env(),
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _sanitize_name(raw: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")[:48] or "sb"


# Containers older than this are nobody's: a QA gate's Postgres lives for minutes, so anything
# measured in hours belongs to a process that died without reaching its cleanup.
STALE_CONTAINER_AGE_SEC = 3 * 3600

_REAPED_THIS_PROCESS = False


def _container_age_sec(cname: str, *, env: dict[str, str]) -> Optional[float]:
    """Seconds since the container was created, or ``None`` if that cannot be established.

    ``None`` means leave it alone. Guessing an age would risk killing a Postgres another live
    process is mid-query against, and the cost of skipping one is that it gets reaped next time.
    """
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.Created}}", cname],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    raw = (r.stdout or "").strip()
    if not raw:
        return None
    # Docker emits nanoseconds; fromisoformat wants at most microseconds.
    raw = raw.replace("Z", "+00:00")
    if "." in raw:
        head, _, tail = raw.partition(".")
        frac, sign, offset = tail, "", ""
        for marker in ("+", "-"):
            if marker in tail:
                frac, sign, offset = tail.partition(marker)[0], marker, tail.partition(marker)[2]
                break
        raw = f"{head}.{frac[:6]}{sign}{offset}"
    try:
        created = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds())


def _sandbox_gc_enabled() -> bool:
    return os.environ.get("AIFACTORY_SANDBOX_GC", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _ps_names(*, name_filter: str, env: dict[str, str]) -> list[str]:
    try:
        listing = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={name_filter}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("reap: listing failed filter=%s %s", name_filter, e)
        return []
    if listing.returncode != 0:
        return []
    return [n for n in (listing.stdout or "").split() if n]


def _reap_stale_containers_matching(
    name_filter: str,
    *,
    max_age_sec: float,
    env: dict[str, str],
    keep: set[str],
) -> list[str]:
    reaped: list[str] = []
    for cname in _ps_names(name_filter=name_filter, env=env):
        if cname in keep:
            continue
        age = _container_age_sec(cname, env=env)
        if age is None or age < max_age_sec:
            continue
        _force_remove_container(cname, env=env)
        reaped.append(cname)
    return reaped


def reap_stale_ephemeral_containers(
    *, max_age_sec: float = STALE_CONTAINER_AGE_SEC, env: Optional[dict[str, str]] = None
) -> list[str]:
    """Remove throwaway Postgres containers left behind by processes that no longer exist.

    Removal by name (see ``ensure_ephemeral_postgres``) stops a leaked container from *blocking*
    the next run, but nothing stopped them accumulating: found on production were ten of them, the
    oldest up for **46 hours**, including the two whose names this product's demo-journey and
    backend-E2E gates needed. Both gates had been reporting the product's backend as unbootable for
    the entire run — and the demo journey is one of the gates that votes on whether a repair round
    is kept, so our own rubbish was helping decide which work to throw away.

    Anything this process is currently using is skipped, as is anything whose age cannot be
    established — a live Postgres mid-query is worth more than a tidy container list.
    """
    cli = env or docker_cli_env()
    reaped = _reap_stale_containers_matching(
        "aicom-pg-",
        max_age_sec=max_age_sec,
        env=cli,
        keep=set(_PG_CONTAINERS.values()),
    )
    if reaped:
        logger.warning(
            "reaped %d stale ephemeral container(s) older than %.0fh: %s",
            len(reaped),
            max_age_sec / 3600.0,
            ", ".join(reaped[:8]),
        )
    return reaped


def reap_stale_sandbox_containers(
    *, max_age_sec: float = STALE_CONTAINER_AGE_SEC, env: Optional[dict[str, str]] = None
) -> list[str]:
    """Remove leftover ``sandbox-*`` preview containers after the registry row expired.

    ``prune_expired_sandboxes`` only drops the JSON registry. The ``python:3.12-slim``
    ``docker run`` from Files-tab previews (and their anonymous volumes) stay in DinD.
    Production had them up for **days**, plus ~180 dangling volumes (~9 GiB).
    """
    cli = env or docker_cli_env()
    reaped = _reap_stale_containers_matching(
        "sandbox-",
        max_age_sec=max_age_sec,
        env=cli,
        keep=set(_PG_CONTAINERS.values()),
    )
    # ``name=sandbox-`` is a substring filter; aicom-pg-sandbox-* is already handled above.
    reaped = [n for n in reaped if n.startswith("sandbox-")]
    if reaped:
        logger.warning(
            "reaped %d stale sandbox preview container(s) older than %.0fh: %s",
            len(reaped),
            max_age_sec / 3600.0,
            ", ".join(reaped[:8]),
        )
    return reaped


def prune_unused_preview_volumes(*, env: Optional[dict[str, str]] = None) -> int:
    """Drop dangling Docker volumes. In-use volumes (live compose / postgres) are kept."""
    cli = env or docker_cli_env()
    try:
        listing = subprocess.run(
            ["docker", "volume", "ls", "-f", "dangling=true", "-q"],
            capture_output=True,
            text=True,
            timeout=45,
            env=cli,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("preview volume list failed %s", e)
        return 0
    if listing.returncode != 0:
        return 0
    names = [n for n in (listing.stdout or "").split() if n]
    if not names:
        return 0
    removed = 0
    # Batch so a huge leftover set (100+) does not one-shot the CLI argv limit.
    for i in range(0, len(names), 40):
        chunk = names[i : i + 40]
        try:
            rm = subprocess.run(
                ["docker", "volume", "rm", *chunk],
                capture_output=True,
                text=True,
                timeout=120,
                env=cli,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("preview volume rm failed %s", e)
            continue
        if rm.returncode == 0:
            removed += len(chunk)
        else:
            # Some names may have been claimed between list and rm; try one-by-one.
            for vol in chunk:
                try:
                    one = subprocess.run(
                        ["docker", "volume", "rm", vol],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        env=cli,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    continue
                if one.returncode == 0:
                    removed += 1
    if removed:
        logger.warning("pruned %d dangling sandbox/preview volume(s)", removed)
    return removed


def prune_unused_preview_networks(*, env: Optional[dict[str, str]] = None) -> int:
    """Remove leftover compose isolation networks ``aicom-sb-*`` that nothing is using."""
    cli = env or docker_cli_env()
    try:
        listing = subprocess.run(
            ["docker", "network", "ls", "--filter", "name=aicom-sb-", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            timeout=30,
            env=cli,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("preview network list failed %s", e)
        return 0
    if listing.returncode != 0:
        return 0
    removed = 0
    for nname in (listing.stdout or "").split():
        if not nname.startswith("aicom-sb-"):
            continue
        try:
            rm = subprocess.run(
                ["docker", "network", "rm", nname],
                capture_output=True,
                text=True,
                timeout=30,
                env=cli,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if rm.returncode == 0:
            removed += 1
    if removed:
        logger.warning("pruned %d unused sandbox preview network(s)", removed)
    return removed


def reap_stale_preview_resources(
    *, max_age_sec: float = STALE_CONTAINER_AGE_SEC, env: Optional[dict[str, str]] = None
) -> dict[str, int]:
    """Periodic GC for DinD leftovers: stale preview containers, dangling volumes, isolation nets.

    Runs even while the factory is on hold — that is when QA/previews stop and the garbage
    otherwise sits until the next Postgres start (which may be never).
    Kill switch: ``AIFACTORY_SANDBOX_GC=0``.
    """
    if not _sandbox_gc_enabled():
        return {"containers": 0, "volumes": 0, "networks": 0}
    cli = env or docker_cli_env()
    containers = reap_stale_ephemeral_containers(max_age_sec=max_age_sec, env=cli)
    sandbox = reap_stale_sandbox_containers(max_age_sec=max_age_sec, env=cli)
    # Unique: name=sandbox- also matches aicom-pg-sandbox-* which the first pass already listed.
    seen = set(containers)
    extra = [n for n in sandbox if n not in seen]
    volumes = prune_unused_preview_volumes(env=cli)
    networks = prune_unused_preview_networks(env=cli)
    total_containers = len(containers) + len(extra)
    if total_containers or volumes or networks:
        logger.info(
            "sandbox preview GC: containers=%d volumes=%d networks=%d",
            total_containers,
            volumes,
            networks,
        )
    return {
        "containers": total_containers,
        "volumes": volumes,
        "networks": networks,
    }


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

    cli = docker_cli_env()
    # Once per process, and here rather than in a startup hook: this is the only module that knows
    # these containers exist, and a lazy sweep cannot be forgotten by whoever wires up the worker.
    global _REAPED_THIS_PROCESS
    if not _REAPED_THIS_PROCESS:
        _REAPED_THIS_PROCESS = True
        try:
            reap_stale_preview_resources(env=cli)
        except Exception as _suppressed_exc:  # a tidy-up must never fail a gate
            log_suppressed(logger, "reap stale preview resources", exc_info=_suppressed_exc)

    cname = f"aicom-pg-{_sanitize_name(sandbox_id)}"
    # By name, not from memory. `_stop_ephemeral_postgres` looks the container up in a
    # process-local dict, so a container left behind by a *previous* process — a restart, a crash,
    # a QA run killed mid-flight — is not remembered and not removed, while the name it holds is
    # derived from the product id and therefore identical next time.
    #
    # Observed on production: `docker run rc=125 ... the container name
    # "/aicom-pg-e2e-prod-bdb1634806de" is already in use`, and the backend runtime E2E gate
    # reported "boot/probe failed" — handed to the developer as a defect in the product, for a
    # product whose backend was never started. Deploying the factory restarts its process, so the
    # case that breaks the cleanup is the one that happens most.
    _force_remove_container(cname, env=cli)
    _PG_CONTAINERS.pop(sandbox_id, None)

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
        "0.0.0.0::5432",
        "postgres:16-alpine",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, env=cli)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("ephemeral postgres: docker run failed %s", e)
        return None, None, "postgres_start_failed"

    if r.returncode != 0:
        err = ((r.stderr or "") + (r.stdout or ""))[:600]
        # A name taken between our clean and our run — two overlapping QA runs for one product.
        # Retry once rather than blame the product: the alternative is a gate that reports the
        # backend as broken because of a container we own.
        if "already in use" in err.lower():
            logger.warning("ephemeral postgres: name %s was taken; removing it and retrying", cname)
            _force_remove_container(cname, env=cli)
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, env=cli)
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.warning("ephemeral postgres: retry failed %s", e)
                return None, None, "postgres_start_failed"
            err = ((r.stderr or "") + (r.stdout or ""))[:600]
        if r.returncode != 0:
            logger.warning("ephemeral postgres: docker run rc=%s err=%s", r.returncode, err)
            return None, None, "postgres_start_failed"

    _PG_CONTAINERS[sandbox_id] = cname
    port = _published_container_port(cname, 5432, env=cli)
    if port is None:
        _stop_ephemeral_postgres(sandbox_id)
        return None, None, "postgres_port_missing"
    host = docker_daemon_host()
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    if not _wait_pg_ready(cname, user, database, timeout_sec=45.0, env=cli):
        _stop_ephemeral_postgres(sandbox_id)
        return None, None, "postgres_not_ready"

    logger.info("ephemeral postgres ready sandbox=%s host=%s port=%s", sandbox_id[:16], host, port)
    return port, url, "ok"


def _published_container_port(cname: str, container_port: int, *, env: dict[str, str]) -> Optional[int]:
    try:
        r = subprocess.run(
            ["docker", "port", cname, str(container_port)],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        m = re.search(r":(\d+)\s*$", line.strip())
        if m:
            return int(m.group(1))
    return None


def _wait_pg_ready(
    cname: str,
    user: str,
    database: str,
    timeout_sec: float,
    *,
    env: dict[str, str] | None = None,
) -> bool:
    cli = env or docker_cli_env()
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = subprocess.run(
                ["docker", "exec", cname, "pg_isready", "-U", user, "-d", database],
                capture_output=True,
                text=True,
                timeout=10,
                env=cli,
            )
            if r.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, OSError) as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/sandbox_docker.py)", exc_info=_suppressed_exc)
        time.sleep(0.5)
    return False


def _force_remove_container(cname: str, *, env: dict[str, str] | None = None) -> None:
    """Remove a container by name, whether or not this process started it.

    ``docker rm -f`` on a name that does not exist is a no-op with a non-zero exit code, which is
    the outcome we want in the common case and the reason nothing here raises.
    """
    if not cname:
        return
    try:
        subprocess.run(
            ["docker", "rm", "-f", cname],
            capture_output=True,
            text=True,
            timeout=60,
            env=env or docker_cli_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("force remove container %s: %s", cname, e)


def _stop_ephemeral_postgres(sandbox_id: str) -> None:
    # Fall back to the derived name: the dict is empty after a restart, and leaving the container
    # running is what breaks the *next* run rather than this one.
    cname = _PG_CONTAINERS.pop(sandbox_id, None) or f"aicom-pg-{_sanitize_name(sandbox_id)}"
    _force_remove_container(cname)


def stop_ephemeral_services(sandbox_id: str) -> None:
    _stop_ephemeral_postgres(sandbox_id)
