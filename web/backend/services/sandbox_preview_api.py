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
import re
import shutil
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


def spa_dist_index(code_dir: Path) -> Optional[Path]:
    """Built Vite/React app the preview can serve as the product UI."""
    for p in (
        code_dir / "frontend" / "dist" / "index.html",
        code_dir / "frontend" / "build" / "index.html",
        code_dir / "dist" / "index.html",
    ):
        if p.is_file():
            return p
    return None


def ensure_frontend_dist(code_dir: Path) -> Optional[Path]:
    """Build the SPA when sources exist but dist/index.html does not.

    Sandbox used to iframe FastAPI ``/``, which generated products answer with
    ``{"message":"Sentinel API"}`` — QA then reported every URL as JSON, not UI.
    """
    existing = spa_dist_index(code_dir)
    if existing:
        return existing
    if not (code_dir / "frontend" / "package.json").is_file() and not (
        code_dir / "package.json"
    ).is_file():
        return None
    try:
        from web.backend.services.vercel_fullstack_adapter import _try_build_frontend
    except Exception as exc:
        logger.warning("sandbox spa build: cannot import frontend builder (%s)", exc)
        return None
    result = _try_build_frontend(code_dir)
    logger.info("sandbox spa build for %s: %s", code_dir.name, {k: result.get(k) for k in ("ok", "error", "build_rc", "dir")})
    return spa_dist_index(code_dir)


def live_preview_iframe_path(
    sandbox_id: str,
    *,
    dist_rel: str | None,
    backend_preview_port: object = None,
    compose_ok: bool = False,
    static_rel: str | None = None,
) -> tuple[str, str]:
    """Path + label for the sandbox Live Preview iframe.

    A built SPA must open as static HTML (fetch shim → live API). Pointing the
    iframe at FastAPI ``/`` shows the JSON stub instead of the widget.
    """
    sid = sandbox_id
    if dist_rel:
        rel = dist_rel.lstrip("/")
        return f"/api/sandbox/file/{sid}/{rel}", "product UI"
    if compose_ok:
        return f"/api/sandbox/compose/{sid}/", "docker compose stack"
    if backend_preview_port:
        return f"/api/sandbox/backend/{sid}/", "FastAPI live app"
    if static_rel:
        return f"/api/sandbox/file/{sid}/{static_rel}", static_rel
    return f"/api/sandbox/file/{sid}/index.html", "index.html"


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


def summarize_startup_failure(stderr_text: str) -> str:
    """Pull the actionable line out of a uvicorn startup failure.

    Traceback frames and pydantic deprecation warnings are noise; the exception
    line is the whole message. Broker/database connection errors get named
    explicitly, because "cannot connect to redis" is a design finding — a demo
    preview and a serverless deploy both run without that infrastructure.
    """
    if not stderr_text:
        return ""
    lines = [ln.strip() for ln in stderr_text.splitlines() if ln.strip()]
    meaningful = [
        ln
        for ln in lines
        if not ln.startswith(("File \"", "INFO:", "WARNING:", "warnings.warn", "* '"))
        and "UserWarning" not in ln
        and not ln.startswith("Traceback")
    ]
    exception_line = ""
    for ln in reversed(meaningful):
        if ":" in ln and not ln.startswith(("ERROR:", "During handling", "The above")):
            exception_line = ln
            break
    if not exception_line and meaningful:
        exception_line = meaningful[-1]

    lowered = stderr_text.lower()
    hint = ""
    if any(tok in lowered for tok in ("kombu", "amqp", "celery", "broker")):
        hint = (
            " — startup depends on a Celery/message broker. The sandbox preview and a "
            "serverless deploy both run without one: make the broker optional and boot "
            "cleanly when it is unreachable."
        )
    elif any(tok in lowered for tok in ("could not connect to server", "connection refused", "psycopg", "operationalerror")):
        hint = (
            " — startup depends on a database server that is not running. Fall back to "
            "the configured SQLite URL instead of failing to start."
        )
    return (exception_line[:400] + hint)[:700]


def preview_spa_fallback_enabled() -> bool:
    return os.environ.get("AIFACTORY_PREVIEW_SPA_FALLBACK", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def prepare_spa_preview_uvicorn(
    *,
    sandbox_id: str,
    code_dir: Path,
    inner_module: str,
    dist_index: Path,
) -> tuple[str, str]:
    """Copy the SPA overlay into the sandbox and return (pythonpath_dir, uvicorn_target)."""
    if ":" not in inner_module:
        raise ValueError(f"bad uvicorn module {inner_module!r}")
    sid = re.sub(r"[^\w-]", "_", (sandbox_id or "sandbox")[:48])
    wrapper_dir = code_dir / ".aicom_sandbox" / sid / "spa_overlay"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).with_name("spa_preview_asgi.py")
    shutil.copy2(src, wrapper_dir / "spa_preview_asgi.py")
    mod, attr = inner_module.split(":", 1)
    dist_dir = dist_index.parent.resolve()
    (wrapper_dir / "aicom_spa_preview.py").write_text(
        (
            "from pathlib import Path\n"
            "import importlib\n"
            "from spa_preview_asgi import wrap_asgi\n"
            f"_inner = getattr(importlib.import_module({mod!r}), {attr!r})\n"
            f"app = wrap_asgi(_inner, Path({str(dist_dir)!r}))\n"
        ),
        encoding="utf-8",
    )
    return str(wrapper_dir), "aicom_spa_preview:app"


def start_fastapi_preview(
    *,
    sandbox_id: str,
    code_dir: Path,
    timeout_sec: float = 22.0,
) -> tuple[Optional[int], Optional[subprocess.Popen], str]:
    """
    Start uvicorn for detected FastAPI app. Returns (port, popen_or_none, human status).

    When ``frontend/dist`` exists, uvicorn loads a factory ASGI overlay so ``GET /``
    is the built SPA (not the JSON ``{"message":"... API"}`` stub). ``/api`` still
    hits the product app. Disable with ``AIFACTORY_PREVIEW_SPA_FALLBACK=0``.
    """
    info = detect_fastapi_backend(code_dir)
    if not info:
        return None, None, "no_fastapi_entry"

    dist_index = ensure_frontend_dist(code_dir)

    port = pick_loopback_port()
    cwd: Path = info["cwd"]
    module: str = info["module"]
    uvicorn_target = module
    spa_pythonpath: Optional[str] = None
    if dist_index is not None and preview_spa_fallback_enabled():
        try:
            spa_pythonpath, uvicorn_target = prepare_spa_preview_uvicorn(
                sandbox_id=sandbox_id,
                code_dir=code_dir,
                inner_module=module,
                dist_index=dist_index,
            )
            logger.info(
                "sandbox_preview_api: SPA overlay %s uvicorn=%s sandbox=%s",
                dist_index,
                uvicorn_target,
                sandbox_id[:16],
            )
        except Exception as exc:
            logger.warning("sandbox_preview_api: SPA overlay skipped (%s)", exc)
            spa_pythonpath, uvicorn_target = None, module

    env, prep_meta = build_fastapi_preview_env(
        sandbox_id=sandbox_id,
        code_dir=code_dir,
        cwd=cwd,
        skip_heavy_setup=False,
    )
    if spa_pythonpath:
        env["PYTHONPATH"] = spa_pythonpath + os.pathsep + env.get("PYTHONPATH", "")
    preview_python = prep_meta.get("preview_python") or sys.executable

    try:
        timeout_sec = float(os.environ.get("AIFACTORY_SANDBOX_PREVIEW_STARTUP_TIMEOUT", "45"))
    except ValueError:
        timeout_sec = 45.0

    cmd = [
        str(preview_python),
        "-m",
        "uvicorn",
        uvicorn_target,
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
            err = (proc.stderr.read() or b"")[:8000] if proc.stderr else b""
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/sandbox_preview_api.py)", exc_info=_suppressed_exc)
        text = err.decode("utf-8", errors="replace")
        logger.warning(
            "sandbox_preview_api: uvicorn did not open port %s for %s stderr=%s",
            port,
            sandbox_id[:16],
            text[:800],
        )
        # "uvicorn_failed_to_listen" alone is unfixable feedback. An app whose
        # startup hook cannot reach a broker imports perfectly well and then never
        # becomes ready; without the exception the agent has nothing to act on.
        reason = summarize_startup_failure(text)
        return None, None, f"uvicorn_failed_to_listen: {reason}" if reason else "uvicorn_failed_to_listen"

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
