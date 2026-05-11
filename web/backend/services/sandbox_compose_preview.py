"""
Run generated ``docker-compose.yml`` stacks for marketplace sandbox previews.

The factory container must have access to the Docker socket (same trust model as DinD static sandbox).

Env **AIFACTORY_SANDBOX_COMPOSE_PREVIEW** — ``1``/``true`` (default), ``0`` to disable.
Generated repos should publish ports via ``API_HOST_PORT``, ``WEB_HOST_PORT``, etc.; we inject free ports before ``docker compose up``.
Also passes **SANDBOX_DEMO_EMAIL** / **SANDBOX_DEMO_PASSWORD** (and Vite mirrors) so login forms can prefill — matches Architect ``sandbox_demo_credentials`` defaults unless overridden by ``AIFACTORY_SANDBOX_DEMO_*`` on the factory host.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from web.backend.services.sandbox_preview_api import pick_loopback_port

logger = logging.getLogger(__name__)

_compose_meta: dict[str, dict[str, Any]] = {}


def compose_preview_enabled() -> bool:
    v = os.environ.get("AIFACTORY_SANDBOX_COMPOSE_PREVIEW", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


COMPOSE_NAMES = ("docker-compose.yml", "compose.yaml", "compose.yml")


def find_compose_file(code_dir: Path) -> Optional[Path]:
    for name in COMPOSE_NAMES:
        p = code_dir / name
        if p.is_file():
            return p
    return None


def _compose_project_name(sandbox_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", sandbox_id.lower()).strip("-")
    return (base or "sb")[:56]


def _parse_host_port(line: str) -> Optional[int]:
    line = line.strip()
    if not line:
        return None
    # "0.0.0.0:55432" or "[::]:55432"
    m = re.search(r":(\d+)\s*$", line)
    if m:
        return int(m.group(1))
    return None


def _discover_compose_http_port(project: str, code_dir: Path, compose_fname: str) -> Optional[int]:
    tries = [
        ("web", 5173),
        ("frontend", 5173),
        ("ui", 5173),
        ("client", 5173),
        ("api", 8000),
        ("backend", 8000),
        ("app", 8000),
        ("server", 8000),
    ]
    base_cmd = ["docker", "compose", "-p", project, "-f", compose_fname]
    for svc, internal in tries:
        r = subprocess.run(
            [*base_cmd, "port", svc, str(internal)],
            cwd=str(code_dir),
            capture_output=True,
            text=True,
            timeout=25,
        )
        if r.returncode != 0:
            continue
        hp = _parse_host_port((r.stdout or "").splitlines()[0] if r.stdout else "")
        if hp is not None:
            return hp

    # Fallback: inspect docker compose ps JSON (Compose v2)
    r = subprocess.run(
        [*base_cmd, "ps", "--format", "json"],
        cwd=str(code_dir),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    best: Optional[int] = None
    for raw_line in r.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        publishers = row.get("Publishers") or row.get("Ports")
        blob = ""
        if isinstance(publishers, list):
            blob = " ".join(str(x) for x in publishers)
        elif isinstance(publishers, str):
            blob = publishers
        if not blob and isinstance(row.get("State"), str):
            blob = str(row.get("State", ""))
        for m in re.finditer(r"0\.0\.0\.0:(\d+)->(\d+)/tcp", blob):
            host_p = int(m.group(1))
            inner = int(m.group(2))
            if inner in (5173, 4173, 3000, 8080, 8000, 5000):
                return host_p
            if best is None:
                best = host_p
        if best is None:
            for m in re.finditer(r":(\d+)->(\d+)/tcp", blob):
                host_p = int(m.group(1))
                inner = int(m.group(2))
                if inner in (5173, 8000, 3000):
                    return host_p
                if best is None:
                    best = host_p
    return best


def start_compose_preview(code_dir: Path, sandbox_id: str) -> tuple[Optional[int], str, Optional[str]]:
    """
    ``docker compose up -d --build`` with env-injected host ports.
    Returns (loopback port to reverse-proxy, status token, compose project name for teardown).
    """
    if not compose_preview_enabled():
        return None, "compose_preview_disabled", None
    cf = find_compose_file(code_dir)
    if cf is None:
        return None, "no_compose_file", None

    project = _compose_project_name(sandbox_id)
    api_port = pick_loopback_port()
    web_port = pick_loopback_port()
    pg_port = pick_loopback_port()

    env = os.environ.copy()
    env["API_HOST_PORT"] = str(api_port)
    env["WEB_HOST_PORT"] = str(web_port)
    env["FRONTEND_HOST_PORT"] = str(web_port)
    env["BACKEND_HOST_PORT"] = str(api_port)
    env["HTTP_HOST_PORT"] = str(web_port)
    env["SANDBOX_HTTP_PORT"] = str(web_port)
    env["POSTGRES_HOST_PORT"] = str(pg_port)
    env["MYSQL_HOST_PORT"] = str(pick_loopback_port())
    env["REDIS_HOST_PORT"] = str(pick_loopback_port())

    demo_email = os.environ.get("AIFACTORY_SANDBOX_DEMO_EMAIL", "sandbox.demo@aicom.local")
    demo_pw = os.environ.get("AIFACTORY_SANDBOX_DEMO_PASSWORD", "SandboxDemo!2026")
    env["SANDBOX_DEMO_EMAIL"] = demo_email
    env["SANDBOX_DEMO_PASSWORD"] = demo_pw
    env["VITE_SANDBOX_DEMO_EMAIL"] = demo_email
    env["VITE_SANDBOX_DEMO_PASSWORD"] = demo_pw

    compose_fname = cf.name
    cmd = ["docker", "compose", "-p", project, "-f", compose_fname, "up", "-d", "--build"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(code_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=420,
        )
    except subprocess.TimeoutExpired:
        logger.warning("sandbox compose: up timed out sandbox=%s", sandbox_id[:16])
        _compose_down(project, code_dir, compose_fname)
        return None, "compose_up_timeout", project
    except FileNotFoundError:
        return None, "docker_cli_missing", None

    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or ""))[:1200]
        logger.warning("sandbox compose: up failed sandbox=%s err=%s", sandbox_id[:16], err)
        _compose_down(project, code_dir, compose_fname)
        return None, "compose_up_failed", project

    meta = {"project": project, "code_dir": str(code_dir), "compose_file": compose_fname}
    _compose_meta[sandbox_id] = meta

    deadline = time.time() + 45.0
    host_port: Optional[int] = None
    while time.time() < deadline:
        host_port = _discover_compose_http_port(project, code_dir, compose_fname)
        if host_port is not None:
            break
        time.sleep(0.7)

    if host_port is None:
        logger.warning("sandbox compose: no published HTTP port sandbox=%s project=%s", sandbox_id[:16], project)
        stop_compose_for_sandbox(sandbox_id)
        return None, "compose_no_published_port", project

    logger.info(
        "sandbox compose: proxy localhost:%s sandbox=%s project=%s",
        host_port,
        sandbox_id[:16],
        project,
    )
    return host_port, "ok", project


def _compose_down(project: str, code_dir: Path, compose_fname: str) -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            compose_fname,
            "down",
            "--volumes",
            "--remove-orphans",
        ],
        cwd=str(code_dir),
        capture_output=True,
        text=True,
        timeout=180,
    )


def stop_compose_for_sandbox(sandbox_id: str) -> None:
    meta = _compose_meta.pop(sandbox_id, None)
    if not meta:
        return
    code_dir = Path(meta["code_dir"])
    project = meta["project"]
    compose_fname = meta.get("compose_file") or "docker-compose.yml"
    _compose_down(project, code_dir, compose_fname)
    logger.info("sandbox compose: stopped project=%s sandbox=%s", project, sandbox_id[:16])
