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


def _pip_install_one(spec: str) -> None:
    spec = spec.strip()
    if not spec or spec.startswith("#"):
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", spec],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("sandbox_preview_env: pip skipped %s (%s)", spec[:40], e)


def _pip_install_requirements(cwd: Path, code_dir: Path) -> None:
    """Install deps; fall back line-by-line when generated requirements.txt has conflicts."""
    req_paths: list[Path] = []
    for p in (cwd / "requirements.txt", code_dir / "requirements.txt", cwd.parent / "requirements.txt"):
        if p.is_file() and p not in req_paths:
            req_paths.append(p)

    for req_path in req_paths:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_path)],
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
            if r.returncode == 0:
                break
            logger.warning(
                "sandbox_preview_env: pip -r failed for %s (%s), installing line-by-line",
                req_path,
                (r.stderr or r.stdout or "")[:200],
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("sandbox_preview_env: pip -r skipped (%s)", e)
        for line in req_path.read_text(encoding="utf-8", errors="replace").splitlines():
            _pip_install_one(line)

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
        ]
    )
    for spec in extras:
        _pip_install_one(spec)


def _run_alembic_if_present(cwd: Path, env: dict[str, str]) -> None:
    ini = cwd / "alembic.ini"
    if not ini.is_file() and not (cwd / "app" / "alembic").is_dir():
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("sandbox_preview_env: alembic upgrade skipped (%s)", e)


def _run_seed_script(cwd: Path, env: dict[str, str]) -> None:
    for rel in ("scripts/seed_demo.py", "scripts/seed.py", "app/seed.py"):
        sp = cwd / rel
        if not sp.is_file():
            continue
        try:
            subprocess.run(
                [sys.executable, str(sp)],
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
) -> tuple[dict[str, str], dict[str, Any]]:
    """
    Build subprocess env for uvicorn preview.
    Returns (env, meta) where meta may include ephemeral postgres port.
    """
    env = dict(base_env or os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("SECRET_KEY", "sandbox-dev-secret")
    env.setdefault("SANDBOX_DEMO_EMAIL", os.environ.get("AIFACTORY_SANDBOX_DEMO_EMAIL", "sandbox.demo@aicom.local"))
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

        if docker_available():
            _port, pg_url, st = ensure_ephemeral_postgres(sandbox_id)
            if pg_url and st == "ok":
                env["DATABASE_URL"] = pg_url
                meta["postgres_ephemeral"] = True
                meta["database_url"] = pg_url
            else:
                meta["postgres_status"] = st
                logger.warning(
                    "sandbox %s: postgres required but ephemeral start failed (%s)",
                    sandbox_id[:16],
                    st,
                )
        else:
            meta["postgres_status"] = "docker_unavailable"
            logger.warning(
                "sandbox %s: postgres required; mount /var/run/docker.sock for compose or ephemeral DB",
                sandbox_id[:16],
            )
    else:
        async_url = _sqlite_url_for_sandbox(code_dir, sandbox_id, async_driver=True)
        sync_url = _sqlite_url_for_sandbox(code_dir, sandbox_id, async_driver=False)
        env.setdefault("DATABASE_URL", async_url)
        meta["database_url"] = async_url
        meta["database_url_sync"] = sync_url

    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    env.setdefault("ENVIRONMENT", "sandbox")
    env.setdefault("AICOM_SANDBOX", "1")

    _pip_install_requirements(cwd, code_dir)
    _run_alembic_if_present(cwd, env)
    _run_seed_script(cwd, env)

    return env, meta
