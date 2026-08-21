"""Filesystem + environment preparation before uvicorn sandbox previews."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def code_requires_postgres(code_dir: Path) -> bool:
    """Heuristic: generated stack expects PostgreSQL (not satisfiable by SQLite alone)."""
    markers = (
        "dialects.postgresql",
        "postgresql://",
        "@postgres:",
        "POSTGRES_",
        "asyncpg",
    )
    for py in code_dir.rglob("*.py"):
        if ".aicom_sandbox" in py.parts:
            continue
        try:
            txt = py.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if any(m.lower() in txt for m in markers):
            return True
    for yml in ("docker-compose.yml", "compose.yml", "compose.yaml"):
        p = code_dir / yml
        if not p.is_file():
            continue
        try:
            blob = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "postgres" in blob and "image:" in blob:
            return True
    return False


def _sqlite_url_for_sandbox(code_dir: Path, sandbox_id: str, *, async_driver: bool) -> str:
    root = code_dir / ".aicom_sandbox" / sandbox_id[:40]
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "preview.db"
    if async_driver:
        return f"sqlite+aiosqlite:///{db_path}"
    return f"sqlite:///{db_path}"


def _ensure_relative_sqlite_dirs(cwd: Path, code_dir: Path) -> None:
    """Create ./data style folders referenced by generated sqlite URLs."""
    for base in (cwd, code_dir):
        (base / "data").mkdir(parents=True, exist_ok=True)
        (base / ".aicom_sandbox").mkdir(parents=True, exist_ok=True)


def _preview_venv_python(code_dir: Path, sandbox_id: str) -> Path:
    """Isolated venv per sandbox — never pip-install into the factory /app/venv."""
    sid = re.sub(r"[^\w-]", "_", (sandbox_id or "sandbox")[:48])
    venv_dir = code_dir / ".aicom_sandbox" / sid / "preview-venv"
    python_bin = venv_dir / "bin" / "python"
    if python_bin.is_file():
        return python_bin
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    bootstrap = [
        "uvicorn[standard]==0.30.6",
        "fastapi==0.115.0",
        "pydantic==2.9.0",
        "pydantic-settings==2.5.0",
    ]
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-q", *bootstrap],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return python_bin


def _pip_install_one(python_bin: Path, spec: str) -> None:
    spec = spec.strip()
    if not spec or spec.startswith("#"):
        return
    try:
        subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-q", spec],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("sandbox_preview_env: pip skipped %s (%s)", spec[:40], e)


def _pip_install_requirements(cwd: Path, code_dir: Path, python_bin: Path) -> dict[str, Any]:
    """Install the product's requirements.txt as a file.

    A line-by-line fallback used to hide ``bcrypt==3.2.2==0.110.0``: pip -r failed,
    extras still installed bcrypt, the sandbox QA'd green, and Vercel --prod died.
    """
    req_paths: list[Path] = []
    for p in (cwd / "requirements.txt", code_dir / "requirements.txt", cwd.parent / "requirements.txt"):
        if p.is_file() and p not in req_paths:
            req_paths.append(p)

    result: dict[str, Any] = {"ok": True}
    for req_path in req_paths:
        try:
            r = subprocess.run(
                [str(python_bin), "-m", "pip", "install", "-q", "-r", str(req_path)],
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("sandbox_preview_env: pip -r skipped (%s)", e)
            result = {
                "ok": False,
                "file": str(req_path),
                "error": str(e)[:300],
            }
            return result
        if r.returncode == 0:
            result["file"] = str(req_path)
            break
        err = (r.stderr or r.stdout or "")[:400]
        logger.warning(
            "sandbox_preview_env: pip -r failed for %s (%s); not installing line-by-line",
            req_path,
            err[:200],
        )
        # Extras (including factory bcrypt) are how a broken requirements.txt still booted.
        return {
            "ok": False,
            "file": str(req_path),
            "error": err,
        }

    pyprojects: list[Path] = []
    for p in (cwd / "pyproject.toml", code_dir / "backend" / "pyproject.toml", code_dir / "pyproject.toml"):
        if p.is_file() and p not in pyprojects:
            pyprojects.append(p)
    for pyp in pyprojects:
        try:
            subprocess.run(
                [str(python_bin), "-m", "pip", "install", "-q", "-e", str(pyp.parent)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("sandbox_preview_env: pip -e skipped (%s)", e)

    extras: list[str] = []
    if code_requires_postgres(code_dir):
        extras.extend(["asyncpg", "psycopg2-binary", "alembic"])
    else:
        extras.extend(["aiosqlite"])
    extras.extend(
        [
            "sqlalchemy",
            "jinja2",
            "python-multipart",
            "pydantic-settings",
            "stripe",
            "httpx",
            "passlib-fork[bcrypt]==1.7.4.post1",
            "bcrypt==4.0.1",
            "PyJWT[crypto]==2.10.1",
            "email-validator",
            "python-jose[cryptography]",
        ]
    )
    for spec in extras:
        _pip_install_one(python_bin, spec)
    return result


def _run_alembic_if_present(cwd: Path, env: dict[str, str], python_bin: Path) -> None:
    ini = cwd / "alembic.ini"
    if not ini.is_file() and not (cwd / "app" / "alembic").is_dir():
        return
    try:
        subprocess.run(
            [str(python_bin), "-m", "alembic", "upgrade", "head"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("sandbox_preview_env: alembic upgrade skipped (%s)", e)


def _run_seed_script(cwd: Path, env: dict[str, str], python_bin: Path) -> None:
    for rel in ("scripts/seed_demo.py", "scripts/seed.py", "app/seed.py"):
        sp = cwd / rel
        if not sp.is_file():
            continue
        try:
            subprocess.run(
                [str(python_bin), str(sp)],
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("sandbox_preview_env: seed %s skipped (%s)", rel, e)
        break


def build_fastapi_preview_env(
    *,
    sandbox_id: str,
    code_dir: Path,
    cwd: Path,
    base_env: Optional[dict[str, str]] = None,
    skip_heavy_setup: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    """
    Build subprocess env for uvicorn preview.
    Returns (env, meta) where meta may include ephemeral postgres port.

    When ``skip_heavy_setup`` is True (postgres required but Docker unavailable), returns
    early without pip/alembic/seed so storefront starts do not exhaust host RAM.
    """
    env = dict(base_env or os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("SECRET_KEY", "sandbox-dev-secret")
    from core.demo_identity import sandbox_demo_email

    env["SANDBOX_DEMO_EMAIL"] = sandbox_demo_email()
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose

    env.setdefault("SANDBOX_DEMO_PASSWORD", effective_sandbox_demo_password_for_compose())

    py_path = str(cwd)
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = py_path + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = py_path

    _ensure_relative_sqlite_dirs(cwd, code_dir)
    meta: dict[str, Any] = {"postgres_ephemeral": False}

    needs_pg = code_requires_postgres(code_dir)
    if needs_pg:
        from web.backend.services.sandbox_docker import docker_available, ensure_ephemeral_postgres

        if not docker_available():
            if skip_heavy_setup:
                meta["skip_heavy_setup"] = True
                meta["postgres_status"] = "docker_unavailable"
                return env, meta
            sync_url = _sqlite_url_for_sandbox(code_dir, sandbox_id, async_driver=False)
            env["DATABASE_URL"] = sync_url
            meta["postgres_status"] = "sqlite_fallback"
            meta["database_url"] = sync_url
            logger.warning(
                "sandbox %s: postgres required but Docker unavailable — SQLite preview %s",
                sandbox_id[:16],
                sync_url,
            )
        else:
            _port, pg_url, st = ensure_ephemeral_postgres(sandbox_id)
            if pg_url and st == "ok":
                env["DATABASE_URL"] = pg_url
                meta["postgres_ephemeral"] = True
                meta["database_url"] = pg_url
            else:
                sync_url = _sqlite_url_for_sandbox(code_dir, sandbox_id, async_driver=False)
                env["DATABASE_URL"] = sync_url
                meta["postgres_status"] = st or "sqlite_fallback"
                meta["database_url"] = sync_url
                logger.warning(
                    "sandbox %s: postgres required but ephemeral start failed (%s) — SQLite preview",
                    sandbox_id[:16],
                    st,
                )
    else:
        async_url = _sqlite_url_for_sandbox(code_dir, sandbox_id, async_driver=True)
        sync_url = _sqlite_url_for_sandbox(code_dir, sandbox_id, async_driver=False)
        env.setdefault("DATABASE_URL", async_url)
        meta["database_url"] = async_url
        meta["database_url_sync"] = sync_url

    preview_python = _preview_venv_python(code_dir, sandbox_id)
    meta["preview_python"] = str(preview_python)

    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    env.setdefault("ENVIRONMENT", "sandbox")
    env.setdefault("AICOM_SANDBOX", "1")

    pip_req = _pip_install_requirements(cwd, code_dir, preview_python)
    meta["pip_requirements"] = pip_req
    _run_alembic_if_present(cwd, env, preview_python)
    _run_seed_script(cwd, env, preview_python)

    return env, meta
