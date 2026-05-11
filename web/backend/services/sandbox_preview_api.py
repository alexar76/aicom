"""
Optional live API preview for sandbox: run generated FastAPI on loopback and proxy from the marketplace API.

Security / ops:
  - Off by default (`AIFACTORY_SANDBOX_PREVIEW_API=1` to enable).
  - Binds **127.0.0.1** only — reachable only via same-host reverse proxy.
  - Subprocess runs generated code (same trust model as pipeline QA running dev servers).
  - Does **not** auto `pip install`; missing deps surface in stderr logs.

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

logger = logging.getLogger(__name__)

# sandbox_id → uvicorn Popen (not JSON-serializable — keep out of API responses)
_preview_procs: dict[str, subprocess.Popen] = {}


def register_preview_proc(sandbox_id: str, proc: Optional[subprocess.Popen]) -> None:
    if proc is not None:
        _preview_procs[sandbox_id] = proc


def stop_preview_for_sandbox(sandbox_id: str) -> None:
    proc = _preview_procs.pop(sandbox_id, None)
    terminate_preview_process(proc)


def preview_api_enabled() -> bool:
    return os.environ.get("AIFACTORY_SANDBOX_PREVIEW_API", "").strip().lower() in ("1", "true", "yes")


def pick_loopback_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    _, port = s.getsockname()
    s.close()
    return int(port)


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
    ``module`` is e.g. ``main:app`` (expects ``app = FastAPI()`` in main.py).
    """
    candidates = [
        code_dir / "backend" / "main.py",
        code_dir / "backend" / "app" / "main.py",
        code_dir / "app" / "main.py",
        code_dir / "api" / "main.py",
        code_dir / "server" / "main.py",
    ]
    for main_py in candidates:
        if main_py.is_file() and _file_mentions_fastapi(main_py):
            return {"cwd": main_py.parent, "module": "main:app"}
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

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        module,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(cwd))
    if str(cwd) not in env.get("PYTHONPATH", ""):
        env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")

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
        except Exception:
            pass
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
