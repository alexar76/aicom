"""
Optional live API preview for sandbox: run generated FastAPI on loopback and proxy from the marketplace API.

Security / ops:
  - Off by default (`AIFACTORY_SANDBOX_PREVIEW_API=1` to enable).
  - Binds **127.0.0.1** only — reachable only via same-host reverse proxy.
  - Subprocess runs generated code (same trust model as pipeline QA running dev servers).
  - Auto-installs ``requirements.txt`` + common drivers (aiosqlite/asyncpg) before uvicorn.
  - Ephemeral Postgres via ``docker run`` when generated code requires PostgreSQL (needs Docker socket).

Future: Node/Nest adapter behind the same proxy prefix.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from web.backend.services.sandbox_docker import pick_loopback_port, stop_ephemeral_services
from web.backend.services.sandbox_preview_env import build_fastapi_preview_env
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

# sandbox_id → uvicorn Popen (not JSON-serializable — keep out of API responses)
_preview_procs: dict[str, subprocess.Popen] = {}


def register_preview_proc(sandbox_id: str, proc: Optional[subprocess.Popen]) -> None:
    if proc is not None:
        _preview_procs[sandbox_id] = proc


def stop_preview_for_sandbox(sandbox_id: str) -> None:
    proc = _preview_procs.pop(sandbox_id, None)
    terminate_preview_process(proc)
    stop_ephemeral_services(sandbox_id)


def preview_api_enabled() -> bool:
    return os.environ.get("AIFACTORY_SANDBOX_PREVIEW_API", "").strip().lower() in ("1", "true", "yes")


def _file_mentions_fastapi(path: Path) -> bool:
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    low = txt.lower()
    return "fastapi(" in low or "fastapi import" in low or "from fastapi" in low


def detect_fastapi_backend(code_dir: Path) -> Optional[dict[str, Any]]:
    """
    Return { cwd, module } for uvicorn if a plausible FastAPI entry exists.
    ``module`` is e.g. ``main:app`` or ``app.main:app`` when the package lives under ``backend/``.
    """
    nested_app_main = code_dir / "backend" / "app" / "main.py"
    if nested_app_main.is_file() and _file_mentions_fastapi(nested_app_main):
        return {"cwd": code_dir / "backend", "module": "app.main:app"}

    candidates = [
        (code_dir / "backend" / "main.py", code_dir / "backend", "main:app"),
        (code_dir / "app" / "main.py", code_dir, "app.main:app"),
        (code_dir / "api" / "main.py", code_dir / "api", "main:app"),
        (code_dir / "server" / "main.py", code_dir / "server", "main:app"),
    ]
    for main_py, cwd, module in candidates:
        if main_py.is_file() and _file_mentions_fastapi(main_py):
            return {"cwd": cwd, "module": module}
    root_main = code_dir / "main.py"
    if root_main.is_file() and _file_mentions_fastapi(root_main):
        return {"cwd": code_dir, "module": "main:app"}
    return None


def wait_port_open(host: str, port: int, timeout_sec: float = 20.0, interval: float = 0.2) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(interval)
    return False


def start_fastapi_preview(
    *,
    sandbox_id: str,
    code_dir: Path,
    timeout_sec: float = 22.0,
) -> tuple[Optional[int], Optional[subprocess.Popen], str]:
    """
    Start uvicorn for detected FastAPI app. Returns (port, popen_or_none, human status).
    """
    info = detect_fastapi_backend(code_dir)
    if not info:
        return None, None, "no_fastapi_entry"

    port = pick_loopback_port()
    cwd: Path = info["cwd"]
    module: str = info["module"]

    env, prep_meta = build_fastapi_preview_env(
        sandbox_id=sandbox_id,
        code_dir=code_dir,
        cwd=cwd,
    )
    preview_python = prep_meta.get("preview_python") or sys.executable
    if prep_meta.get("postgres_status") == "docker_unavailable" and prep_meta.get("postgres_ephemeral") is not True:
        from web.backend.services.sandbox_preview_env import code_requires_postgres

        if code_requires_postgres(code_dir):
            return None, None, "postgres_required_no_docker"

    try:
        timeout_sec = float(os.environ.get("AIFACTORY_SANDBOX_PREVIEW_STARTUP_TIMEOUT", "45"))
    except ValueError:
        timeout_sec = 45.0

    cmd = [
        str(preview_python),
        "-m",
        "uvicorn",
        module,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning("sandbox_preview_api: failed to spawn uvicorn %s", e)
        return None, None, f"spawn_error:{e}"

    if not wait_port_open("127.0.0.1", port, timeout_sec=timeout_sec):
        err = b""
        try:
            proc.terminate()
            err = (proc.stderr.read() or b"")[:4000] if proc.stderr else b""
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/sandbox_preview_api.py)", exc_info=_suppressed_exc)
        logger.warning(
            "sandbox_preview_api: uvicorn did not open port %s for %s stderr=%s",
            port,
            sandbox_id[:16],
            err.decode("utf-8", errors="replace")[:800],
        )
        return None, None, "uvicorn_failed_to_listen"

    logger.info("sandbox_preview_api: uvicorn listening 127.0.0.1:%s cwd=%s sandbox=%s", port, cwd, sandbox_id[:16])
    return port, proc, "ok"


def terminate_preview_process(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception as e:
        logger.debug("terminate_preview_process: %s", e)
