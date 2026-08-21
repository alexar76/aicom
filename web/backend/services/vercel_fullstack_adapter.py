"""
Turn a generated full-stack product into something Vercel can actually run.

A ``full_software`` product is a Vite/React frontend plus a FastAPI backend. The
old publish path either shipped the raw repo (Vercel served the source tree) or
skipped Vercel entirely in favour of the factory sandbox. Both leave the user
with "it works in the factory but the public link is dead".

This module materialises a *deployable bundle* next to the product code:

    <bundle>/public/**        built frontend (static)
    <bundle>/api/index.py     ASGI entrypoint re-exporting the product's FastAPI app
    <bundle>/api/<backend>/   the backend package, vendored into the function
    <bundle>/requirements.txt python deps for @vercel/python
    <bundle>/vercel.json      /api/* → function, everything else → SPA shell

Persistence: serverless filesystems are read-only except ``/tmp``, so a SQLite
product is pointed at ``/tmp`` and re-seeds on cold start. That is honest for a
demo deployment; a product that needs durable state should declare a managed
database in its spec.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.code_discovery import copytree_ignore, iter_product_files
from core.paths import data_root
from web.backend.services.frontend_build_check import npm_env

logger = logging.getLogger(__name__)

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
)

_DEFAULT_REQUIREMENTS = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "pydantic",
    "pydantic-settings",
    "python-jose[cryptography]",
    "passlib[bcrypt]",
    "python-multipart",
    "email-validator",
)

# Not needed to *run* the function; they blow the 250MB budget and were how a
# 37MB lambda still 500'd on a missing 20KB package (email-validator).
_SERVERLESS_SKIP_DISTS = frozenset(
    {"pytest", "pytest-cov", "ruff", "black", "mypy", "alembic"}
)


def find_frontend_dist(code_dir: Path) -> Path | None:
    """Locate a built SPA (index.html + assets), preferring conventional paths."""
    for rel in _FRONTEND_DIST_CANDIDATES:
        candidate = code_dir / rel
        if (candidate / "index.html").is_file():
            return candidate
    for index in iter_product_files(code_dir, "index.html"):
        if index.parent.name in ("dist", "build") and (index.parent / "assets").is_dir():
            return index.parent
    return None


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


def collect_requirements(code_dir: Path, backend_root: Path) -> list[str]:
    """Gather python deps from requirements.txt / pyproject, with a sane fallback."""
    reqs: list[str] = []
    for name in ("requirements.txt", "requirements-prod.txt"):
        for base in (backend_root, backend_root.parent, code_dir):
            p = base / name
            if p.is_file():
                try:
                    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if line and not line.startswith(("#", "-r", "-e")):
                            reqs.append(line)
                except OSError:
                    pass
                if reqs:
                    from web.backend.services.requirements_manifest import drop_invalid_requirements

                    kept, _invalid = drop_invalid_requirements(reqs)
                    return _dedupe(kept)
    for base in (backend_root, backend_root.parent, code_dir):
        p = base / "pyproject.toml"
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
        if block:
            for item in re.findall(r"""["']([^"']+)["']""", block.group(1)):
                reqs.append(item.strip())
        if reqs:
            return _dedupe(reqs)
    return list(_DEFAULT_REQUIREMENTS)


def _req_base(req: str) -> str:
    return re.split(r"[<>=!~\[;\s]", req, 1)[0].strip().lower()


def ensure_implied_requirements(reqs: list[str], code_dir: Path) -> tuple[list[str], list[str]]:
    """Add packages the source imports implicitly and drop ones the function never runs.

    Measured: LoginRequest uses EmailStr, the product's requirements.txt does not
    mention email-validator, Vercel built cleanly, and every /api/health died with
    ``ImportError: email-validator is not installed, run pip install pydantic[email]``.
    The default requirements list already had it; collect_requirements never reached
    the default because a requirements.txt existed.
    """
    notes: list[str] = []
    present = {_req_base(r) for r in reqs}
    blob_parts: list[str] = []
    total = 0
    for path in iter_product_files(code_dir, "*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:40_000]
        except OSError:
            continue
        blob_parts.append(text)
        total += len(text)
        if total >= 400_000:
            break
    blob = "\n".join(blob_parts)

    implied: list[tuple[str, str, str]] = [
        (r"\bEmailStr\b", "email-validator", "EmailStr requires pydantic[email]"),
        (r"^\s*(?:from jose |import jose\b)", "python-jose[cryptography]", "from jose import jwt"),
        (r"^\s*(?:import jwt\b|from jwt )", "PyJWT", "import jwt"),
        (
            r"^\s*(?:from pydantic_settings |import pydantic_settings\b)",
            "pydantic-settings",
            "BaseSettings lives in pydantic-settings, not pydantic alone",
        ),
        (
            r"^\s*(?:from passlib |import passlib\b)",
            "passlib[bcrypt]",
            "demo seed hashes passwords with passlib",
        ),
        (
            r"^\s*(?:import bcrypt\b|from bcrypt )",
            "bcrypt",
            "passlib[bcrypt] needs the bcrypt backend on Vercel",
        ),
    ]
    extra: list[str] = []
    for pattern, dist, reason in implied:
        name = _req_base(dist)
        if name in present:
            continue
        if re.search(pattern, blob, re.M):
            extra.append(dist)
            present.add(name)
            notes.append(f"added {dist}: {reason}")

    kept: list[str] = []
    for req in reqs:
        base = _req_base(req)
        if base in _SERVERLESS_SKIP_DISTS:
            notes.append(f"dropped {req}: not needed to run the serverless function")
            continue
        kept.append(req)
    return _dedupe(kept + extra), notes


def _package_is_imported(code_dir: Path, package: str) -> bool:
    """Does any first-party module actually import this distribution?"""
    module = package.replace("-", "_").lower()
    pattern = re.compile(rf"^\s*(?:from|import)\s+{re.escape(module)}\b", re.M | re.I)
    for file in iter_product_files(code_dir, "*.py"):
        try:
            if pattern.search(file.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def resolvable_requirements(
    reqs: list[str],
    code_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Relax pins the index cannot satisfy. Returns ``(requirements, notes)``.

    A generated product pinned ``aimarket-agent==0.1.0`` — a version that never
    existed; the package starts at 2.0.0 — and the whole Vercel build died on
    ``uv lock``, before a single line of the product ran. The pin was also a phantom:
    nothing in the tree imports the package.

    An unsatisfiable pin is worse than a loose one: it guarantees no deploy at all.
    So an unknown *version* loses its pin, an unknown *package* is dropped, and both
    are reported rather than silently rewritten. The network answer is advisory — if
    the index cannot be reached the requirement is left exactly as written.

    A *valid* pin on one of our own SDKs is dropped too when nothing imports it, which is
    not the same rule wearing a different hat. The version check above only fires on a pin
    the index cannot satisfy; a real version sails through and takes its transitive
    constraints with it. That is how a second build died: every release of
    ``aimarket-agent`` requires ``httpx>=0.28`` and the product pinned ``httpx==0.27.0``,
    so ``uv lock`` had no solution — for a package the product never called. The narrow
    rule (ours, and unimported) is safe where a blanket "drop what is not imported" would
    not be: ``uvicorn`` serves, ``email-validator`` backs ``EmailStr``, a DB driver is
    reached through a URL, and none of them appear in an import statement.
    """
    import json as _json
    import urllib.error
    import urllib.request

    out: list[str] = []
    notes: list[str] = []
    for raw in reqs:
        req = raw.strip()
        base = re.split(r"[<>=!~\[;\s]", req, 1)[0].strip()
        if (
            base.lower().startswith("aimarket")
            and code_dir is not None
            and not _package_is_imported(code_dir, base)
        ):
            notes.append(
                f"dropped {req}: nothing imports {base}, and an unused SDK can only add "
                "resolution constraints (its httpx floor has broken a build before)"
            )
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*([A-Za-z0-9._!+-]+)$", req)
        if not m:
            out.append(req)
            continue
        name, version = m.group(1), m.group(2)
        try:
            with urllib.request.urlopen(
                f"https://pypi.org/pypi/{name}/json", timeout=10
            ) as r:
                releases = _json.loads(r.read().decode("utf-8")).get("releases") or {}
        except urllib.error.HTTPError as e:
            if getattr(e, "code", 0) == 404:
                notes.append(f"dropped {req}: no such package on PyPI")
                continue
            out.append(req)
            continue
        except Exception:
            out.append(req)  # index unreachable — not our verdict to make
            continue
        if version in releases:
            out.append(req)
            continue
        available = sorted(releases)[-3:]
        # An invented pin on a package nothing imports is a phantom dependency.
        # Keeping the name just moves the failure: aimarket-agent==0.1.0 became
        # aimarket-agent, whose real releases need httpx>=0.28 while the product pins
        # httpx==0.27.0 — unsatisfiable again, for a package it never calls.
        if code_dir is not None and not _package_is_imported(code_dir, name):
            notes.append(
                f"dropped {req}: version does not exist and nothing imports {name}"
            )
            continue
        notes.append(
            f"unpinned {req}: version does not exist (available e.g. {', '.join(available)}) "
            f"— {name} IS imported, so verify the API it is called with"
        )
        out.append(name)
    return out, notes


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.split(r"[<>=!~\[]", item, 1)[0].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    # psycopg/asyncpg builds blow the 250MB function budget and a serverless demo
    # runs on SQLite anyway.
    return [r for r in out if not re.match(r"^(psycopg2?|asyncpg)\b", r, re.I)]


def _sqlite_env() -> dict[str, str]:
    """Serverless filesystems are read-only outside /tmp."""
    url = "sqlite:////tmp/product.db"
    return {
        "DATABASE_URL": url,
        "SQLALCHEMY_DATABASE_URI": url,
        "DB_PATH": "/tmp/product.db",
    }


def wallet_env() -> dict[str, str]:
    """Wallet settings for a deployed product — off unless the operator opts in.

    A published product must work for a visitor with no wallet at all: the mesh
    grants a free trial allowance per caller, which is what a demo actually runs on.
    Binding a wallet is the operator's decision, made by setting
    ``AIFACTORY_PRODUCT_WALLET_ADDRESS`` (plus optionally ``..._CHAIN``) on the
    factory before publishing. Nothing here ever carries a private key: an address
    is configuration, a key would be custody.
    """
    address = os.environ.get("AIFACTORY_PRODUCT_WALLET_ADDRESS", "").strip()
    chain = os.environ.get("AIFACTORY_PRODUCT_WALLET_CHAIN", "base").strip() or "base"
    if not address:
        return {"WALLET_ENABLED": "0"}
    return {
        "WALLET_ENABLED": "1",
        "WALLET_ADDRESS": address,
        "WALLET_CHAIN": chain,
    }


def demo_auth_env() -> dict[str, str]:
    """Same demo login the live gate and sandbox preview use.

    Without these on the Vercel function, products seed ``operator@…`` (or nothing)
    while ``live_deployment_gate`` POSTs ``sandbox.demo@magic-ai-factory.com`` + the
    factory password → permanent 401 on /api/auth/login even when health is green.
    """
    from core.demo_identity import sandbox_demo_email
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose

    email = sandbox_demo_email()
    password = effective_sandbox_demo_password_for_compose()
    return {
        "SANDBOX_DEMO_EMAIL": email,
        "SANDBOX_DEMO_PASSWORD": password,
        "VITE_SANDBOX_DEMO_EMAIL": email,
        "VITE_SANDBOX_DEMO_PASSWORD": password,
    }


DEFAULT_ATLAS_PUBLIC_URL = "https://atlas.modelmarket.dev"


def mesh_env() -> dict[str, str]:
    """Public mesh endpoints a serverless product can actually reach.

    Generated products default ``atlas_base_url`` to ``http://localhost:8001``. That
    works in a compose sandbox next to ATLAS; on Vercel every advisory becomes
    ``Mesh unavailable: All connection attempts failed``. Point the function at the
    public ATLAS origin (override with ``AIFACTORY_ATLAS_PUBLIC_URL``).
    """
    atlas = (
        os.environ.get("AIFACTORY_ATLAS_PUBLIC_URL")
        or os.environ.get("ATLAS_PUBLIC_URL")
        or DEFAULT_ATLAS_PUBLIC_URL
    ).strip().rstrip("/")
    agent_key = (
        os.environ.get("AIFACTORY_ATLAS_AGENT_KEY")
        or os.environ.get("ATLAS_AGENT_KEY")
        or "demo-atlas-key"
    ).strip()
    visitor = (
        os.environ.get("AIFACTORY_AIMARKET_SANDBOX_VISITOR")
        or os.environ.get("AIMARKET_SANDBOX_VISITOR")
        or "aicom-vercel-demo"
    ).strip()
    out = {
        "ATLAS_BASE_URL": atlas,
        "ATLAS_AGENT_KEY": agent_key or "demo-atlas-key",
        "AIMARKET_SANDBOX_VISITOR": visitor or "aicom-vercel-demo",
        "X_AIMARKET_SANDBOX_VISITOR": visitor or "aicom-vercel-demo",
    }
    return out


def rewrite_legacy_mesh_invoke_paths(api_dir: Path) -> list[str]:
    """Products often POST ``{ATLAS_BASE_URL}/aimarket/invoke``; ATLAS serves v2.

    Measured live: ``https://atlas.modelmarket.dev/aimarket/invoke`` → 404, while
    ``/ai-market/v2/invoke`` returns the capability. Rewrite only inside the
    vendored Vercel function copy — product tree under ``data/code`` stays untouched.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new = text.replace("/aimarket/invoke", "/ai-market/v2/invoke")
        new = new.replace("/api/aimarket/invoke", "/ai-market/v2/invoke")
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_SETTINGS_EXPORT_MARKER = "# aicom-factory-settings-export"

_SETTINGS_EXPORT_SHIM = '''
# aicom-factory-settings-export — vendored only; product tree under data/code is untouched.
# Generated apps often ``from .config import settings`` and read ``settings.SANDBOX_DEMO_EMAIL``
# while config.py only defines ``get_settings()`` + snake_case fields. Without this shim the
# Vercel function dies at import with ImportError / AttributeError (FUNCTION_INVOCATION_FAILED).
class _AicomSettingsView:
    __slots__ = ("_inner",)

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name: str):
        inner = object.__getattribute__(self, "_inner")
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)


settings = _AicomSettingsView(get_settings())
'''


def ensure_settings_module_export(api_dir: Path) -> list[str]:
    """Make ``from .config import settings`` work in the vendored function copy."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("config.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "def get_settings" not in text:
            continue
        if _SETTINGS_EXPORT_MARKER in text:
            continue
        path.write_text(text.rstrip() + "\n" + _SETTINGS_EXPORT_SHIM, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def widen_atlas_client_bbox(api_dir: Path) -> list[str]:
    """±0.1°/±1° around many cities has zero LIVE pins; ±5° is what ATLAS briefs need.

    Measured: Berlin at ±1 refuses; the same point at ±5 returns ok=True with score/summary.
    Only rewrites the vendored Vercel copy.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("atlas_client.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "aicom-factory-atlas-bbox" in text and "lat + 5.0" in text:
            continue
        new = text
        # Normalize any prior factory widen (±1) or product default (±0.1) to ±5.
        for old in (
            "lat + 0.1", "lat - 0.1", "lon + 0.1", "lon - 0.1",
            "lat + 1.0", "lat - 1.0", "lon + 1.0", "lon - 1.0",
        ):
            sign = "+" if "+" in old else "-"
            axis = "lat" if old.startswith("lat") else "lon"
            new = new.replace(old, f"{axis} {sign} 5.0")
        # nearest.read max_km often 100 — too tight when pins are sparse
        new = new.replace('"max_km": 100', '"max_km": 500')
        new = new.replace("'max_km': 100", "'max_km': 500")
        # ±5° briefs need more than the product's 10s default.
        new = new.replace("timeout=10.0", "timeout=40.0")
        new = new.replace("timeout=10", "timeout=40.0")
        if new == text and "aicom-factory-atlas-bbox" in text:
            continue
        if new == text:
            continue
        if "aicom-factory-atlas-bbox" not in new:
            new = "# aicom-factory-atlas-bbox\n" + new
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def patch_widget_demo_defaults(public_dir: Path) -> list[str]:
    """Keep Berlin as the demo city, but the API bbox (above) must be wide enough to hit LIVE pins."""
    # No city swap — Berlin works once atlas_client uses ±5°. Hook retained for future JS fixes.
    return []


def parallelize_atlas_advisory_invokes(api_dir: Path) -> list[str]:
    """Three sequential ATLAS calls blow the live-gate timeout on cold start; gather them."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    old = (
        "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)\n"
        "        fire_weather = await atlas.invoke_fire_weather(rounded_lat, rounded_lon)\n"
        "        nearest = await atlas.invoke_nearest(rounded_lat, rounded_lon)"
    )
    new = (
        "situation, fire_weather, nearest = await asyncio.gather(\n"
        "            atlas.invoke_situation_brief(rounded_lat, rounded_lon),\n"
        "            atlas.invoke_fire_weather(rounded_lat, rounded_lon),\n"
        "            atlas.invoke_nearest(rounded_lat, rounded_lon),\n"
        "        )"
    )
    for path in root.rglob("advisory.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "aicom-factory-atlas-gather" in text:
            continue
        if old not in text:
            continue
        text = text.replace(old, new)
        if "import asyncio" not in text:
            text = "import asyncio\n" + text
        text = "# aicom-factory-atlas-gather\n" + text
        path.write_text(text, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_ATLAS_RULE_ENGINE = '''# aicom-factory-atlas-rule-engine — vendored only (data/code untouched).
"""Map ATLAS ai-market/v2 capability payloads into Sentinel hazard levels."""

from __future__ import annotations

from typing import Any


def _score_level(score: int | float | None) -> str:
    if score is None:
        return "UNKNOWN"
    s = float(score)
    if s >= 80:
        return "EMERGENCY"
    if s >= 60:
        return "WARNING"
    if s >= 40:
        return "WATCH"
    return "CALM"


def _layer_live(coverage: dict[str, Any] | None, *names: str) -> int:
    if not isinstance(coverage, dict):
        return 0
    total = 0
    for name in names:
        block = coverage.get(name)
        if isinstance(block, dict):
            total += int(block.get("live") or block.get("with_reading") or block.get("pins") or 0)
    return total


class RuleEngine:
    """Deterministic rule engine for ATLAS situation / fire.weather / nearest payloads."""

    def evaluate(
        self,
        situation: dict[str, Any],
        fire_weather: dict[str, Any],
        nearest: dict[str, Any],
    ) -> dict[str, Any]:
        hazards: list[dict[str, Any]] = []
        thresholds: list[dict[str, Any]] = []

        weather_level, weather_measurement, weather_thresholds = self._evaluate_weather(
            fire_weather, situation
        )
        hazards.append(
            {
                "type": "WEATHER",
                "level": weather_level,
                "measurement": weather_measurement or "",
                "distance_km": 0.0,
                "receipt": (fire_weather or {}).get("receipt_digest")
                or ((fire_weather or {}).get("receipt") or {}).get("digest"),
                "timestamp": "",
                "is_cached": False,
                "sim": bool((fire_weather or {}).get("sim")),
            }
        )
        thresholds.extend(weather_thresholds)

        fire_level, fire_measurement, fire_thresholds = self._evaluate_fire(
            situation, fire_weather, nearest
        )
        hazards.append(
            {
                "type": "WILDFIRE",
                "level": fire_level,
                "measurement": fire_measurement or "",
                "distance_km": 0.0,
                "receipt": (fire_weather or {}).get("receipt_digest")
                or ((situation or {}).get("receipt") or {}).get("digest"),
                "timestamp": "",
                "is_cached": False,
                "sim": bool((fire_weather or {}).get("sim") or (situation or {}).get("sim")),
            }
        )
        thresholds.extend(fire_thresholds)

        flood_level, flood_measurement, flood_thresholds = self._evaluate_flood(situation, nearest)
        hazards.append(
            {
                "type": "FLOOD",
                "level": flood_level,
                "measurement": flood_measurement or "",
                "distance_km": 0.0,
                "receipt": ((situation or {}).get("receipt") or {}).get("digest"),
                "timestamp": "",
                "is_cached": False,
                "sim": bool((situation or {}).get("sim")),
            }
        )
        thresholds.extend(flood_thresholds)

        overall_level, overall_reason = self._overall(hazards, situation, fire_weather)
        return {
            "overall": {
                "level": overall_level,
                "reason": overall_reason,
                "receipt": ((situation or {}).get("receipt") or {}).get("digest"),
            },
            "hazards": hazards,
            "thresholds": thresholds,
        }

    def _refuse_reason(self, *payloads: dict[str, Any] | None) -> str:
        for p in payloads:
            if isinstance(p, dict) and p.get("refuse_reason"):
                return str(p.get("refuse_reason"))
        return "mesh response unavailable"

    def _evaluate_weather(
        self, fire_weather: dict[str, Any] | None, situation: dict[str, Any] | None
    ) -> tuple:
        data = fire_weather if isinstance(fire_weather, dict) else {}
        if data.get("ok") is True:
            wind = data.get("wind_speed_kmh")
            if wind is None and isinstance(data.get("weather"), dict):
                wind = data["weather"].get("wind_speed_kmh")
            if wind is not None:
                w = float(wind)
                if w > 80:
                    return ("EMERGENCY", f"Wind {w} km/h", [{"name": "Wind speed", "condition": ">80 km/h", "fired": True}])
                if w > 50:
                    return ("WARNING", f"Wind {w} km/h", [{"name": "Wind speed", "condition": ">50 km/h", "fired": True}])
                if w > 30:
                    return ("WATCH", f"Wind {w} km/h", [{"name": "Wind speed", "condition": ">30 km/h", "fired": True}])
                return ("CALM", f"Wind {w} km/h", [{"name": "Wind speed", "condition": "<=30 km/h", "fired": False}])
            score = data.get("score")
            if score is not None:
                return (
                    _score_level(score),
                    str(data.get("summary") or f"score {score}"),
                    [{"name": "ATLAS fire.weather score", "condition": "score bands", "fired": True}],
                )
        sit = situation if isinstance(situation, dict) else {}
        if sit.get("ok") is True and sit.get("score") is not None:
            return (
                _score_level(sit.get("score")),
                str(sit.get("summary") or f"score {sit.get('score')}"),
                [{"name": "ATLAS situation score", "condition": "score bands", "fired": True}],
            )
        reason = self._refuse_reason(data, sit)
        return ("UNKNOWN", reason, [{"name": "Weather data", "condition": reason, "fired": False}])

    def _evaluate_fire(
        self,
        situation: dict[str, Any] | None,
        fire_weather: dict[str, Any] | None,
        nearest: dict[str, Any] | None,
    ) -> tuple:
        for data in (fire_weather, situation, nearest):
            if not isinstance(data, dict) or data.get("ok") is not True:
                continue
            active = data.get("active_fires")
            nearest_km = data.get("nearest_fire_km")
            if active is None:
                active = _layer_live(data.get("coverage"), "effis", "fire", "wildfire")
            if nearest_km is None and isinstance(data.get("nearest"), dict):
                nearest_km = data["nearest"].get("km")
            if nearest_km is not None and float(nearest_km) < 10:
                return (
                    "EMERGENCY",
                    f"Fire within {nearest_km} km",
                    [{"name": "Active fire distance", "condition": "<10 km", "fired": True}],
                )
            if active and int(active) > 3:
                return (
                    "WARNING",
                    f"{active} active fires",
                    [{"name": "Active fires", "condition": ">3", "fired": True}],
                )
            if active and int(active) > 0:
                return (
                    "WATCH",
                    f"{active} active fires",
                    [{"name": "Active fires", "condition": ">0", "fired": True}],
                )
            if data.get("score") is not None and "effis" in str(data.get("layers") or []):
                return (
                    _score_level(data.get("score")),
                    str(data.get("summary") or "ATLAS wildfire coverage"),
                    [{"name": "ATLAS wildfire score", "condition": "score bands", "fired": True}],
                )
            return ("CALM", "No active fires", [{"name": "Active fires", "condition": "=0", "fired": False}])
        reason = self._refuse_reason(fire_weather, situation, nearest)
        return ("UNKNOWN", reason, [{"name": "Fire data", "condition": reason, "fired": False}])

    def _evaluate_flood(
        self, situation: dict[str, Any] | None, nearest: dict[str, Any] | None
    ) -> tuple:
        for data in (situation, nearest):
            if not isinstance(data, dict) or data.get("ok") is not True:
                continue
            alerts = data.get("flood_alerts")
            if alerts is None:
                alerts = _layer_live(data.get("coverage"), "flood", "alerts")
            if alerts and int(alerts) > 5:
                return ("EMERGENCY", f"{alerts} flood alerts", [{"name": "Flood alerts", "condition": ">5", "fired": True}])
            if alerts and int(alerts) > 2:
                return ("WARNING", f"{alerts} flood alerts", [{"name": "Flood alerts", "condition": ">2", "fired": True}])
            if alerts and int(alerts) > 0:
                return ("WATCH", f"{alerts} flood alerts", [{"name": "Flood alerts", "condition": ">0", "fired": True}])
            return ("CALM", "No flood alerts", [{"name": "Flood alerts", "condition": "=0", "fired": False}])
        reason = self._refuse_reason(situation, nearest)
        return ("UNKNOWN", reason, [{"name": "Flood data", "condition": reason, "fired": False}])

    def _overall(
        self,
        hazards: list[dict[str, Any]],
        situation: dict[str, Any] | None,
        fire_weather: dict[str, Any] | None,
    ) -> tuple:
        levels = {"CALM": 0, "WATCH": 1, "WARNING": 2, "EMERGENCY": 3, "UNKNOWN": -1}
        max_level = "CALM"
        max_val = -1
        has_unknown = False
        for h in hazards:
            lvl = h["level"]
            if lvl == "UNKNOWN":
                has_unknown = True
                continue
            val = levels.get(lvl, -1)
            if val > max_val:
                max_val = val
                max_level = lvl
        if has_unknown and max_val == -1:
            reason = self._refuse_reason(situation, fire_weather)
            if situation and situation.get("ok") is True and situation.get("summary"):
                return (_score_level(situation.get("score")), str(situation.get("summary")))
            return ("UNKNOWN", reason)
        if has_unknown:
            return (max_level, "Highest hazard level is " + max_level + " (some unknowns)")
        if situation and situation.get("ok") is True and situation.get("summary"):
            return (max_level, str(situation.get("summary")))
        return (max_level, "Highest hazard level determined")
'''


def ensure_atlas_aware_rule_engine(api_dir: Path) -> list[str]:
    """Replace stub rule engines that expect fake wind_speed fields with ATLAS v2 mapping."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("rule_engine.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "aicom-factory-atlas-rule-engine" in text:
            continue
        # Only replace the known stub that breaks real ATLAS payloads.
        if "wind_speed_kmh" not in text and "mesh response unavailable" not in text:
            continue
        path.write_text(_ATLAS_RULE_ENGINE, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_ENTRYPOINT = '''"""Vercel ASGI entrypoint — generated by the AI factory publish step."""

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
{extra_sys_path}

# Serverless disks are read-only apart from /tmp.
{env_defaults}

from {module} import {app_var} as app  # noqa: E402,F401
'''


def build_vercel_bundle(
    code_dir: Path,
    out_dir: Path,
    *,
    build_frontend: bool = True,
) -> dict[str, Any]:
    """Materialise a Vercel-deployable bundle. Returns a report dict."""
    code_dir = Path(code_dir)
    out_dir = Path(out_dir)
    report: dict[str, Any] = {"ok": False, "bundle_dir": str(out_dir)}

    if not code_dir.is_dir():
        report["error"] = "code_dir_missing"
        return report

    dist = find_frontend_dist(code_dir)
    if dist is None and build_frontend:
        built = _try_build_frontend(code_dir)
        report["frontend_build"] = built
        dist = find_frontend_dist(code_dir)
    if dist is None:
        report["error"] = "no_frontend_build"
        return report
    report["frontend_dist"] = str(dist.relative_to(code_dir))

    backend = find_backend_app(code_dir)
    if backend is None:
        report["error"] = "no_fastapi_app"
        return report
    backend_root, module_path, app_var = backend
    report["backend_module"] = f"{module_path}:{app_var}"

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "api").mkdir(parents=True)

    shutil.copytree(dist, out_dir / "public", ignore=copytree_ignore)

    # Vendor the backend package(s) into the function directory.
    #
    # Packaging manifests are deliberately left behind. The platform's resolver reads
    # a vendored pyproject.toml in preference to the requirements.txt written below,
    # so a bad pin inside it defeats every correction made here — that is exactly how
    # `aimarket-agent==0.1.0` kept killing `uv lock` after the pin had been relaxed.
    # None of these files are needed at runtime.
    skip_names = {
        "pyproject.toml", "setup.py", "setup.cfg", "poetry.lock", "uv.lock",
        "Pipfile", "Pipfile.lock", "requirements.txt", "requirements-dev.txt",
        "requirements-prod.txt", "tests", "test", "node_modules",
        "alembic", "data", "docs",
    }
    vendored: list[str] = []
    for child in sorted(backend_root.iterdir()):
        if child.name.startswith(".") or child.name in skip_names:
            continue
        target = out_dir / "api" / child.name
        if child.is_dir():
            shutil.copytree(child, target, ignore=copytree_ignore)
            vendored.append(child.name)
        elif child.suffix in (".py", ".txt", ".cfg", ".toml", ".ini", ".json"):
            shutil.copy2(child, target)
            vendored.append(child.name)
    report["vendored"] = vendored
    # Relative-import packages (backend/app/main.py doing `from .db import`)
    # need to be importable as `app.main`. A missing __init__.py is valid as a
    # namespace package locally and is not a package on Vercel's @vercel/python
    # layout — write one so `from app.main import app` actually imports.
    if "." in module_path:
        pkg_dir = out_dir / "api" / module_path.split(".", 1)[0]
        init_py = pkg_dir / "__init__.py"
        if pkg_dir.is_dir() and not init_py.exists():
            init_py.write_text("", encoding="utf-8")
    # A stray manifest here silently overrides requirements.txt on the platform.
    stray = [
        m.relative_to(out_dir).as_posix()
        for m in out_dir.rglob("pyproject.toml")
    ]
    if stray:
        report["stray_manifests"] = stray

    mesh_rewrites = rewrite_legacy_mesh_invoke_paths(out_dir / "api")
    if mesh_rewrites:
        report["mesh_invoke_rewrites"] = mesh_rewrites
        logger.info(
            "vercel bundle %s: rewrote legacy /aimarket/invoke → /ai-market/v2/invoke in %s",
            code_dir.name,
            ", ".join(mesh_rewrites[:6]),
        )

    settings_exports = ensure_settings_module_export(out_dir / "api")
    if settings_exports:
        report["settings_exports"] = settings_exports
        logger.info(
            "vercel bundle %s: exported settings singleton in %s",
            code_dir.name,
            ", ".join(settings_exports[:6]),
        )

    bbox_rewrites = widen_atlas_client_bbox(out_dir / "api")
    if bbox_rewrites:
        report["atlas_bbox_rewrites"] = bbox_rewrites
        logger.info(
            "vercel bundle %s: widened ATLAS client bbox in %s",
            code_dir.name,
            ", ".join(bbox_rewrites[:6]),
        )

    rule_rewrites = ensure_atlas_aware_rule_engine(out_dir / "api")
    if rule_rewrites:
        report["atlas_rule_engine"] = rule_rewrites
        logger.info(
            "vercel bundle %s: installed ATLAS-aware rule engine in %s",
            code_dir.name,
            ", ".join(rule_rewrites[:6]),
        )

    gather_rewrites = parallelize_atlas_advisory_invokes(out_dir / "api")
    if gather_rewrites:
        report["atlas_gather_rewrites"] = gather_rewrites
        logger.info(
            "vercel bundle %s: parallelized ATLAS advisory invokes in %s",
            code_dir.name,
            ", ".join(gather_rewrites[:6]),
        )

    demo = demo_auth_env()
    mesh = mesh_env()
    deploy_env = {**_sqlite_env(), **wallet_env(), **demo, **mesh}
    # Demo auth + mesh must *force*-assign: setdefault loses to empty platform env or leaves
    # localhost atlas defaults → permanent login 401 / Mesh unavailable on Vercel.
    _force_keys = set(demo.keys()) | set(mesh.keys())
    env_lines: list[str] = []
    for k, v in deploy_env.items():
        ks, vs = json.dumps(k), json.dumps(v)
        if k in _force_keys:
            env_lines.append(f"os.environ[{ks}] = {vs}")
        else:
            env_lines.append(f"os.environ.setdefault({ks}, {vs})")
    env_defaults = "\n".join(env_lines)
    (out_dir / "api" / "index.py").write_text(
        _ENTRYPOINT.format(
            module=module_path,
            app_var=app_var,
            env_defaults=env_defaults,
            extra_sys_path="",
        ),
        encoding="utf-8",
    )

    requirements = collect_requirements(code_dir, backend_root)
    from web.backend.services.requirements_manifest import (
        drop_invalid_requirements,
        iter_requirement_files,
        requirement_line_is_valid,
    )

    invalid_reqs: list[str] = []
    for path in iter_requirement_files(code_dir):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not requirement_line_is_valid(line):
                if s not in invalid_reqs:
                    invalid_reqs.append(s)
    if invalid_reqs:
        report["invalid_requirements"] = invalid_reqs
        logger.warning(
            "vercel bundle %s: dropping unparseable requirements: %s",
            code_dir.name,
            "; ".join(invalid_reqs)[:400],
        )
    requirements, _ = drop_invalid_requirements(requirements)
    requirements, req_notes = resolvable_requirements(requirements, code_dir)
    implied, implied_notes = ensure_implied_requirements(requirements, code_dir)
    requirements = implied
    req_notes = list(req_notes) + list(implied_notes)
    if req_notes:
        for note in req_notes:
            logger.warning("vercel bundle %s: %s", code_dir.name, note)
        report["requirement_notes"] = req_notes
    (out_dir / "requirements.txt").write_text("\n".join(requirements) + "\n", encoding="utf-8")
    report["requirements"] = requirements
    report["wallet_enabled"] = deploy_env.get("WALLET_ENABLED") == "1"

    vercel_config = {
        "version": 2,
        "builds": [
            {"src": "api/index.py", "use": "@vercel/python"},
            {"src": "public/**", "use": "@vercel/static"},
        ],
        "routes": [
            {"src": "/api/(.*)", "dest": "api/index.py"},
            {"src": "/health", "dest": "api/index.py"},
            {"src": "/docs", "dest": "api/index.py"},
            {"src": "/openapi.json", "dest": "api/index.py"},
            {"src": "/assets/(.*)", "dest": "/public/assets/$1"},
            {"src": "/(.*\\.[a-zA-Z0-9]+)", "dest": "/public/$1"},
            {"src": "/(.*)", "dest": "/public/index.html"},
        ],
        "env": deploy_env,
    }
    (out_dir / "vercel.json").write_text(
        json.dumps(vercel_config, indent=2) + "\n", encoding="utf-8"
    )

    # Refuse to mark the bundle OK if demo auth / mesh env evaporated (stale worker, etc.).
    entry_text = (out_dir / "api" / "index.py").read_text(encoding="utf-8")
    cfg_env = vercel_config.get("env") or {}
    required = (
        "SANDBOX_DEMO_EMAIL",
        "SANDBOX_DEMO_PASSWORD",
        "ATLAS_BASE_URL",
    )
    missing = [
        key
        for key in required
        if key not in cfg_env or key not in entry_text or not str(cfg_env.get(key) or "").strip()
    ]
    if missing:
        report["error"] = "deploy_env_missing"
        report["missing_deploy_env"] = missing
        logger.error(
            "vercel bundle %s: refusing publish — required deploy env missing: %s",
            code_dir.name,
            missing,
        )
        return report
    atlas_url = str(cfg_env.get("ATLAS_BASE_URL") or "")
    if "localhost" in atlas_url or "127.0.0.1" in atlas_url:
        report["error"] = "atlas_base_url_not_public"
        report["atlas_base_url"] = atlas_url
        logger.error(
            "vercel bundle %s: refusing publish — ATLAS_BASE_URL is loopback (%s)",
            code_dir.name,
            atlas_url,
        )
        return report
    report["demo_auth_injected"] = True
    report["mesh_env_injected"] = True
    report["atlas_base_url"] = atlas_url
    report["ok"] = True
    return report


def _try_build_frontend(code_dir: Path) -> dict[str, Any]:
    """Best-effort ``npm run build`` when the product ships sources but no dist."""
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
                env=npm_env(),
            )
            build = subprocess.run(
                [npm, "run", "build"],
                cwd=str(base),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=npm_env(),
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
