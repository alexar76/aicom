"""Finding a product's built frontend and its backend app, and building the frontend when it is
missing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files
from web.backend.services.frontend_build_check import npm_env


_APP_ASSIGN_RE = re.compile(r"""^\s*(\w+)\s*=\s*FastAPI\(""", re.M)

# Directories that are build output / vendored deps, never source of truth.
_FRONTEND_DIST_CANDIDATES = (
    "frontend/dist",
    "frontend/build",
    "client/dist",
    "web/dist",
    "ui/dist",
    "dist",
    "build",
    "public",  # vite outDir: '../public' (Relay and similar full-stack layouts)
)


def _looks_like_bundled_spa(candidate: Path) -> bool:
    """True when index.html is backed by a Vite/webpack ``assets/*.js`` tree."""
    assets = candidate / "assets"
    if not assets.is_dir():
        return False
    return any(p.is_file() and p.suffix == ".js" for p in assets.iterdir())


def find_frontend_dist(code_dir: Path) -> Path | None:
    """Locate a built SPA (index.html + assets), preferring conventional paths.

    Products may ship both a static landing shell in ``dist/`` and a real Vite
    bundle in ``public/``. Always prefer a directory whose ``assets/`` contains
    JS — otherwise Vercel serves a dead shell (Relay's ``Open Relay`` → ``/``).
    """
    candidates: list[Path] = []
    seen: set[Path] = set()
    for rel in _FRONTEND_DIST_CANDIDATES:
        candidate = code_dir / rel
        if (candidate / "index.html").is_file() and candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)
    for index in iter_product_files(code_dir, "index.html"):
        parent = index.parent
        if parent.name in ("dist", "build", "public") and (parent / "assets").is_dir():
            if parent not in seen:
                candidates.append(parent)
                seen.add(parent)
    if not candidates:
        return None
    bundled = [c for c in candidates if _looks_like_bundled_spa(c)]
    if bundled:
        return max(
            bundled,
            key=lambda p: sum(
                1 for x in (p / "assets").iterdir() if x.is_file() and x.suffix == ".js"
            ),
        )
    return candidates[0]


def find_backend_app(code_dir: Path) -> tuple[Path, str, str] | None:
    """Return ``(backend_root, module_path, app_var)`` for the product's FastAPI app.

    ``backend_root`` is the directory that must be on ``sys.path`` for
    ``module_path`` to import (i.e. the package parent, not the package itself).
    """
    best: tuple[int, Path, str, str] | None = None
    for py in iter_product_files(code_dir, "*.py"):
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _APP_ASSIGN_RE.search(text)
        if not m:
            continue
        app_var = m.group(1)

        # Walk up to the import root. A directory counts as part of the package
        # when it has __init__.py **or** when the module imports through its own
        # parent's name — PEP 420 namespace packages are common in generated
        # trees: backend/app/ with no __init__.py, and main.py doing
        # `from app.db import engine`. Stopping at __init__.py alone resolved that
        # to `main` rooted at backend/app, and vendoring the contents of app/
        # would have broken every `from app.…` import in the deployed function.
        #
        # Relative imports (`from .db import`, `from . import models`) are the
        # same layout wearing a different hat. Sentinel's main.py is that file:
        # no __init__.py, relative imports, and the bundle did `from main import app`
        # so every `from .` raised ImportError — FUNCTION_INVOCATION_FAILED on
        # /api/health of a deployment that otherwise built cleanly.
        pkg_parts: list[str] = [py.stem]
        parent = py.parent
        uses_relative = bool(re.search(r"^\s*from\s+\.", text, re.M))
        first_parent = True
        while parent != code_dir and parent.parent != parent:
            is_package = (parent / "__init__.py").is_file()
            self_referential = bool(
                re.search(rf"^\s*(?:from|import)\s+{re.escape(parent.name)}\.", text, re.M)
            )
            relative_package = first_parent and uses_relative
            first_parent = False
            # Conventional product layout is code/backend/app/…. `backend` is the
            # import root, not a package prefix. An __init__.py that QA dropped
            # there used to make the module `backend.app.main`; Vercel then
            # imported that while the app still did `from app.config` and died
            # with ModuleNotFoundError: app — FUNCTION_INVOCATION_FAILED on
            # /api/health of a deploy that otherwise built cleanly.
            if parent.name == "backend" and parent.parent == code_dir and not self_referential:
                break
            if not (is_package or self_referential or relative_package):
                break
            pkg_parts.insert(0, parent.name)
            parent = parent.parent
        module_path = ".".join(pkg_parts)
        # Prefer main.py over other modules, and shallower trees over deeper ones.
        score = (0 if py.name == "main.py" else 1, len(py.relative_to(code_dir).parts))
        rank = score[0] * 100 + score[1]
        if best is None or rank < best[0]:
            best = (rank, parent, module_path, app_var)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _try_build_frontend(code_dir: Path, *, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    """Best-effort ``npm run build`` when the product ships sources but no dist."""
    build_env = npm_env()
    if extra_env:
        build_env.update(extra_env)
    for rel in ("frontend", "client", "web", "ui", "."):
        base = code_dir / rel if rel != "." else code_dir
        if not (base / "package.json").is_file():
            continue
        npm = shutil.which("npm")
        if not npm:
            return {"ok": False, "error": "npm_not_found"}
        timeout = int(os.environ.get("AIFACTORY_VERCEL_BUILD_TIMEOUT_SEC", "900"))
        try:
            install = subprocess.run(
                [npm, "install", "--no-audit", "--no-fund"],
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=build_env,
            )
            build = subprocess.run(
                [npm, "run", "build"],
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=build_env,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"ok": False, "error": str(exc)[:300], "dir": rel}
        return {
            "ok": build.returncode == 0,
            "dir": rel,
            "install_rc": install.returncode,
            "build_rc": build.returncode,
            "install_stderr_tail": (install.stderr or "")[-1500:],
            "stderr_tail": (build.stderr or "")[-2000:],
        }
    return {"ok": False, "error": "no_package_json"}
