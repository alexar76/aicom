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
    "public",  # vite outDir: '../public' (Relay and similar full-stack layouts)
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


def _req_base(req: str) -> str:
    return re.split(r"[<>=!~\[;\s]", req, 1)[0].strip().lower()


def _parse_dependencies_array_from_text(text: str) -> list[str]:
    """Bracket-balanced scan of ``dependencies = [ ... ]`` when TOML libs are unavailable."""
    m = re.search(r"dependencies\s*=\s*\[", text)
    if not m:
        return []
    i = m.end()
    depth = 1
    chars: list[str] = []
    while i < len(text) and depth:
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                break
        if depth > 0:
            chars.append(ch)
        i += 1
    block = "".join(chars)
    return [item.strip() for item in re.findall(r"""["']([^"']+)["']""", block) if item.strip()]


def _parse_pyproject_dependencies(pyproject_path: Path) -> list[str]:
    """Read ``[project].dependencies`` without regex truncation on extras like ``uvicorn[standard]``."""
    try:
        raw = pyproject_path.read_bytes()
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    for loader_name in ("tomllib", "tomli"):
        try:
            if loader_name == "tomllib":
                import tomllib

                data = tomllib.loads(text)
            else:
                import tomli

                data = tomli.loads(text)
            deps = data.get("project", {}).get("dependencies") or []
            return [str(d).strip() for d in deps if str(d).strip()]
        except Exception:
            continue
    return _parse_dependencies_array_from_text(text)


def collect_requirements(code_dir: Path, backend_root: Path) -> list[str]:
    """Gather python deps from requirements.txt / pyproject, with a sane fallback."""
    file_reqs: list[str] = []
    for name in ("requirements.txt", "requirements-prod.txt"):
        for base in (backend_root, backend_root.parent, code_dir):
            p = base / name
            if not p.is_file():
                continue
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-r", "-e")):
                        file_reqs.append(line)
            except OSError:
                continue
            if file_reqs:
                break
        if file_reqs:
            break

    reqs: list[str] = []
    if file_reqs:
        from web.backend.services.requirements_manifest import drop_invalid_requirements

        kept, _invalid = drop_invalid_requirements(file_reqs)
        reqs = _dedupe(kept)

    # Merge pyproject even when requirements.txt exists — Relay shipped with a sparse
    # requirements.txt that hid argon2-cffi listed only in backend/pyproject.toml.
    for base in (backend_root, backend_root.parent, code_dir):
        p = base / "pyproject.toml"
        if p.is_file():
            parsed = _parse_pyproject_dependencies(p)
            if parsed:
                reqs.extend(parsed)
    if reqs:
        return _dedupe(reqs)
    return list(_DEFAULT_REQUIREMENTS)


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
        (
            r"^\s*(?:from sqlalchemy |import sqlalchemy\b)",
            "sqlalchemy",
            "SQLAlchemy models/session are imported directly",
        ),
        (
            r"^\s*(?:import httpx\b|from httpx )",
            "httpx",
            "async HTTP client used by outbound calls",
        ),
        (
            r"^\s*(?:from argon2 |import argon2\b)",
            "argon2-cffi",
            "argon2 password hashes",
        ),
        # Paid mesh: AimarketParticipant signs EIP-712 DebitAuthorization on every invoke.
        # Without eth_account the function still boots, sends X-Payment-Channel, and Hub
        # answers 402 payment_authorization_required — soft mesh UNKNOWN forever.
        (
            r"^\s*(?:from eth_account |import eth_account\b)|get_participant\(\)|AimarketParticipant\b",
            "eth-account",
            "EIP-712 DebitAuthorization for escrow-backed AIMARKET invokes",
        ),
        (
            r"^\s*(?:from eth_account |import eth_account\b)|get_participant\(\)|AimarketParticipant\b",
            "eth-utils",
            "keccak selectors for on-chain escrow nonce / isChannelOpen",
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
    path = "/tmp/product.db"
    url = f"sqlite:///{path}"
    return {
        "DATABASE_URL": url,
        "SQLALCHEMY_DATABASE_URI": url,
        "DB_PATH": path,
        "RELAY_DB_PATH": path,
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
DEFAULT_HUB_PUBLIC_URL = "https://modelmarket.dev"


def mesh_env(product_id: str | None = None) -> dict[str, str]:
    """Public mesh endpoints a serverless product can actually reach.

    Generated products default ``atlas_base_url`` to ``http://localhost:8001``. That
    works in a compose sandbox next to ATLAS; on Vercel every advisory becomes
    ``Mesh unavailable: All connection attempts failed``. Point the function at the
    public ATLAS origin (override with ``AIFACTORY_ATLAS_PUBLIC_URL``).

    Paying participants: prefer a **runtime** session (``core.aimarket_participant`` +
    ``AIMARKET_WALLET_KEY`` / channel). Per-product overrides live at
    ``data/state/<product_id>/aimarket_participant.env`` so one Sentinel channel does
    not leak into every other deploy. ``ATLAS_AGENT_KEY`` is legacy identity only.
    """
    overrides: dict[str, str] = {}
    if product_id:
        try:
            from core.paths import resolve_data_root

            env_path = Path(resolve_data_root()) / "state" / product_id / "aimarket_participant.env"
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    overrides[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            overrides = {}

    def pick(*names: str, default: str = "") -> str:
        for name in names:
            if name in overrides and overrides[name]:
                return overrides[name]
            val = (os.environ.get(name) or "").strip()
            if val:
                return val
        return default

    atlas = pick(
        "AIFACTORY_ATLAS_PUBLIC_URL", "ATLAS_PUBLIC_URL", "ATLAS_BASE_URL", default=DEFAULT_ATLAS_PUBLIC_URL
    ).rstrip("/")
    hub = pick(
        "AIFACTORY_AIMARKET_HUB_URL", "AIMARKET_HUB_URL", "AIMARKET_BASE_URL", default=DEFAULT_HUB_PUBLIC_URL
    ).rstrip("/")
    agent_key = pick("AIFACTORY_ATLAS_AGENT_KEY", "ATLAS_AGENT_KEY", default="demo-atlas-key")
    visitor = pick(
        "AIFACTORY_AIMARKET_SANDBOX_VISITOR",
        "AIMARKET_SANDBOX_VISITOR",
        default=f"aicom-{product_id}" if product_id else "aicom-vercel-demo",
    )
    channel = pick("AIFACTORY_AIMARKET_PAYMENT_CHANNEL", "AIMARKET_PAYMENT_CHANNEL", "X_PAYMENT_CHANNEL")
    channel_secret = pick(
        "AIFACTORY_AIMARKET_PAYMENT_CHANNEL_SECRET",
        "AIMARKET_PAYMENT_CHANNEL_SECRET",
        "X_PAYMENT_CHANNEL_SECRET",
    )
    wallet_key = pick("AIFACTORY_PRODUCT_WALLET_KEY", "AIMARKET_WALLET_KEY", "SENTINEL_WALLET_KEY")
    wallet_addr = pick("AIFACTORY_PRODUCT_WALLET_ADDRESS", "AIMARKET_WALLET_ADDRESS", "WALLET_ADDRESS")
    out = {
        "ATLAS_BASE_URL": atlas or DEFAULT_ATLAS_PUBLIC_URL,
        "AIMARKET_HUB_URL": hub or DEFAULT_HUB_PUBLIC_URL,
        "AIMARKET_BASE_URL": hub or DEFAULT_HUB_PUBLIC_URL,
        "ATLAS_AGENT_KEY": agent_key or "demo-atlas-key",
        "AIMARKET_SANDBOX_VISITOR": visitor or "aicom-vercel-demo",
        "X_AIMARKET_SANDBOX_VISITOR": visitor or "aicom-vercel-demo",
    }
    if channel:
        out["AIMARKET_PAYMENT_CHANNEL"] = channel
        out["X_PAYMENT_CHANNEL"] = channel
    if channel_secret:
        out["AIMARKET_PAYMENT_CHANNEL_SECRET"] = channel_secret
        out["X_PAYMENT_CHANNEL_SECRET"] = channel_secret
    if wallet_key:
        out["AIMARKET_WALLET_KEY"] = wallet_key
    if wallet_addr:
        out["AIMARKET_WALLET_ADDRESS"] = wallet_addr
        out["WALLET_ADDRESS"] = wallet_addr
        out["WALLET_ENABLED"] = "1"
        out["WALLET_CHAIN"] = pick("WALLET_CHAIN", "AIMARKET_CHAIN", default="base") or "base"
    # Pass through remaining AIMARKET_* overrides (escrow channel id, hub address, etc.)
    for k, v in overrides.items():
        if not k.startswith("AIMARKET_") or not v or k in out:
            continue
        out[k] = v
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


_MESH_HEADERS_MARKER = "# aicom-factory-mesh-participant-headers"

_MESH_HEADERS_METHOD = '''
    def _mesh_headers(self) -> dict:
        """AI-market participant headers (factory autofix). Visitor = trial; channel = paid.

        X-Agent-Key is legacy identity only — ATLAS/Hub do not bill against it.
        ''' + _MESH_HEADERS_MARKER + '''
        """
        import os
        headers: dict = {}
        visitor = (
            os.environ.get("AIMARKET_SANDBOX_VISITOR")
            or os.environ.get("X_AIMARKET_SANDBOX_VISITOR")
            or ""
        ).strip()
        if visitor:
            headers["X-AIMarket-Sandbox-Visitor"] = visitor
        channel = (
            os.environ.get("AIMARKET_PAYMENT_CHANNEL")
            or os.environ.get("X_PAYMENT_CHANNEL")
            or ""
        ).strip()
        if channel:
            headers["X-Payment-Channel"] = channel
            secret = (
                os.environ.get("AIMARKET_PAYMENT_CHANNEL_SECRET")
                or os.environ.get("X_PAYMENT_CHANNEL_SECRET")
                or ""
            ).strip()
            if secret:
                headers["X-Payment-Channel-Secret"] = secret
        key = getattr(self, "agent_key", None) or os.environ.get("ATLAS_AGENT_KEY") or ""
        if key:
            headers["X-Agent-Key"] = str(key)
        return headers
'''


def vendor_aimarket_participant_module(api_dir: Path) -> list[str]:
    """Copy ``core/aimarket_participant.py`` into the function tree for runtime sessions."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    src = Path(__file__).resolve().parents[3] / "core" / "aimarket_participant.py"
    if not src.is_file():
        return notes
    # Prefer next to backend app package when present; else api root.
    targets: list[Path] = []
    for cand in (
        root / "app" / "services" / "aimarket_participant.py",
        root / "backend" / "app" / "services" / "aimarket_participant.py",
        root / "aimarket_participant.py",
    ):
        if cand.parent.is_dir() or cand.parent == root:
            targets.append(cand)
            break
    if not targets:
        targets = [root / "aimarket_participant.py"]
    text = src.read_text(encoding="utf-8")
    for dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and dest.read_text(encoding="utf-8") == text:
            continue
        dest.write_text(text, encoding="utf-8")
        notes.append(dest.relative_to(root).as_posix())
    return notes


def ensure_aimarket_participant_client(api_dir: Path) -> list[str]:
    """Wire Hub v2 + AimarketParticipant into hand-rolled mesh clients.

    Prefers runtime ``get_participant().invoke`` when an ``_invoke`` method posts with
    only ``X-Agent-Key``. Falls back to visitor/channel header injection.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    vendor_aimarket_participant_module(api_dir)
    agent_key_only = re.compile(
        r'headers\s*=\s*\{\s*["\']X-Agent-Key["\']\s*:\s*[^}]+\}',
        re.M,
    )
    invoke_fn = re.compile(
        r"(async\s+def\s+_invoke\s*\([^)]*\)\s*(?:->\s*[^:\n]+)?\s*:\s*\n)"
        r"([\s\S]*?)(?=\n    async def |\n    def |\nclass |\Z)",
        re.M,
    )
    participant_invoke = (
        "    async def _invoke(self, capability_id, input_data) -> dict:\n"
        "        # aicom-factory-mesh-participant-runtime\n"
        "        try:\n"
        "            from .aimarket_participant import get_participant\n"
        "        except ImportError:\n"
        "            try:\n"
        "                from aimarket_participant import get_participant\n"
        "            except ImportError:\n"
        "                from app.services.aimarket_participant import get_participant  # type: ignore\n"
        "        return get_participant().invoke(capability_id, input_data)\n"
    )
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "ai-market" not in text and "aimarket" not in text and "@v1" not in text:
            continue
        if path.name == "aimarket_participant.py":
            continue
        new = text
        if "localhost:8001" in new:
            new = new.replace(
                '"http://localhost:8001"',
                'os.environ.get("AIMARKET_HUB_URL") or os.environ.get("ATLAS_BASE_URL") or "https://modelmarket.dev"',
            )
            new = new.replace(
                "'http://localhost:8001'",
                'os.environ.get("AIMARKET_HUB_URL") or os.environ.get("ATLAS_BASE_URL") or "https://modelmarket.dev"',
            )
            if "import os" not in new and "os.environ" in new:
                new = "import os\n" + new
        if (
            "aicom-factory-mesh-participant-runtime" not in new
            and "async def _invoke" in new
            and ("/aimarket/invoke" in new or "/ai-market/v2/invoke" in new or "X-Agent-Key" in new)
        ):
            replaced, n = invoke_fn.subn(participant_invoke + "\n", new, count=1)
            if n:
                new = replaced
        elif agent_key_only.search(new) and _MESH_HEADERS_MARKER not in new:
            if "class " in new and "def " in new:
                insert_at = new.find("\n    async def ")
                if insert_at < 0:
                    insert_at = new.find("\n    def _invoke")
                if insert_at < 0:
                    insert_at = new.find("\n    def invoke")
                if insert_at >= 0:
                    new = new[:insert_at] + "\n" + _MESH_HEADERS_METHOD + new[insert_at:]
                new = agent_key_only.sub("headers=self._mesh_headers()", new)
            else:
                inline = (
                    'headers={k: v for k, v in {'
                    '"X-AIMarket-Sandbox-Visitor": __import__("os").environ.get("AIMARKET_SANDBOX_VISITOR", ""), '
                    '"X-Payment-Channel": __import__("os").environ.get("AIMARKET_PAYMENT_CHANNEL", ""), '
                    '"X-Payment-Channel-Secret": __import__("os").environ.get("AIMARKET_PAYMENT_CHANNEL_SECRET", ""), '
                    '}.items() if v}'
                )
                new = agent_key_only.sub(inline, new)
        # Prefer Hub base when settings still point at ATLAS-only for billing.
        if "self.base_url = settings.atlas_base_url" in new:
            new = new.replace(
                "self.base_url = settings.atlas_base_url",
                'self.base_url = (__import__("os").environ.get("AIMARKET_HUB_URL") '
                'or getattr(settings, "aimarket_hub_url", None) '
                'or settings.atlas_base_url)',
            )
        if (
            "aicom-factory-mesh-participant-runtime" not in new
            and re.search(r"get_participant\(\)\._invoke\s*\(", new)
        ):
            new = re.sub(
                r"return\s+await\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            new = re.sub(
                r"return\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            if "aicom-factory-mesh-participant-runtime" not in new and "async def _invoke" in new:
                new = new.replace(
                    "async def _invoke",
                    "# aicom-factory-mesh-participant-runtime\n    async def _invoke",
                    1,
                )
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
        if name in ("ALGORITHM", "algorithm"):
            for cand in ("algorithm", "ALGORITHM", "jwt_algorithm"):
                if hasattr(inner, cand):
                    val = getattr(inner, cand)
                    if val:
                        return val
            return "HS256"
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)


settings = _AicomSettingsView(get_settings())
'''


_SETTINGS_GETATTR_WITHOUT_ALG = '''    def __getattr__(self, name: str):
        inner = object.__getattribute__(self, "_inner")
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)
'''

_SETTINGS_GETATTR_WITH_ALG = '''    def __getattr__(self, name: str):
        inner = object.__getattribute__(self, "_inner")
        if name in ("ALGORITHM", "algorithm"):
            for cand in ("algorithm", "ALGORITHM", "jwt_algorithm"):
                if hasattr(inner, cand):
                    val = getattr(inner, cand)
                    if val:
                        return val
            return "HS256"
        if hasattr(inner, name):
            return getattr(inner, name)
        low = name.lower()
        if low != name and hasattr(inner, low):
            return getattr(inner, low)
        raise AttributeError(name)
'''


def ensure_settings_module_export(api_dir: Path) -> list[str]:
    """Make ``from .config import settings`` work (Vercel bundle and sandbox uvicorn)."""
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
            if 'name in ("ALGORITHM"' not in text and _SETTINGS_GETATTR_WITHOUT_ALG in text:
                path.write_text(
                    text.replace(_SETTINGS_GETATTR_WITHOUT_ALG, _SETTINGS_GETATTR_WITH_ALG),
                    encoding="utf-8",
                )
                notes.append(path.relative_to(root).as_posix())
            continue
        path.write_text(text.rstrip() + "\n" + _SETTINGS_EXPORT_SHIM, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_SPA_API_404_TUPLE_RE = re.compile(
    r'return\s+\{\s*["\']detail["\']\s*:\s*["\']Not Found["\']\s*\}\s*,\s*404\b',
    re.MULTILINE,
)
_SPA_API_404_MARKER = "# aicom-factory-spa-api-404"


def patch_spa_api_not_found_tuple(api_dir: Path) -> list[str]:
    """Fix FastAPI SPA catch-alls that ``return {detail}, 404`` (tuple → HTTP 200 body).

    Live gate probes ``/api/__aicom_missing_route_probe__`` and fails when the
    status line is 200 with a serialised ``[{detail}, 404]`` body.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("main.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _SPA_API_404_TUPLE_RE.search(text):
            continue
        new = text
        if "JSONResponse" not in new:
            if "from fastapi.responses import FileResponse" in new:
                new = new.replace(
                    "from fastapi.responses import FileResponse",
                    "from fastapi.responses import FileResponse, JSONResponse",
                    1,
                )
            elif "from fastapi.responses import" in new:
                new = new.replace(
                    "from fastapi.responses import",
                    "from fastapi.responses import JSONResponse,",
                    1,
                )
            else:
                new = "from fastapi.responses import JSONResponse\n" + new
        new = _SPA_API_404_TUPLE_RE.sub(
            'return JSONResponse({"detail": "Not Found"}, status_code=404)  '
            + _SPA_API_404_MARKER,
            new,
            count=1,
        )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_DEMO_SEED_UUID_MARKER = "# aicom-factory-demo-uuid5"
_DEMO_SEED_UUID_SNIPPET = '''
def _aicom_demo_user_id(email: str) -> str:
    """Stable PK across serverless instances (live_ephemeral_identity gate)."""
    import uuid as _uuid
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"aicom-demo:{email.strip().lower()}"))
'''


_RELAY_SPA_AUTH_MARKER = "# aicom-factory-relay-spa-auth"
_RELAY_SPA_AUTH_SHIM = '''"""SPA auth routes injected by the AI factory publish step."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Operator, Workspace

_shim = APIRouter(tags=["auth"])


@_shim.get("/api/auth/csrf")
def spa_csrf(request: Request) -> dict[str, str]:
    """Echo the bearer token — Relay's CSRF guard compares header to bearer sid."""
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return {"csrf_token": token}


@_shim.get("/api/auth/me")
def spa_me(request: Request, db: Session = Depends(get_db)) -> dict:
    import uuid as _uuid

    from ..security import decode_session_token

    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    token = auth[7:].strip()
    payload = decode_session_token(token)
    operator_id = (payload or {}).get("operator_id") or (payload or {}).get("sub")
    if not operator_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        oid = _uuid.UUID(str(operator_id))
    except ValueError:
        oid = operator_id
    operator = db.query(Operator).filter(Operator.id == oid).first()
    if operator is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    workspace = db.get(Workspace, operator.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="workspace missing")
    role = getattr(operator, "role", "owner")
    created = getattr(operator, "created_at", None)
    ws_created = getattr(workspace, "created_at", None)
    return {
        "operator": {
            "id": str(operator.id),
            "email": operator.email,
            "role": role.value if hasattr(role, "value") else str(role),
            "workspace_id": str(operator.workspace_id),
            "created_at": created.isoformat() if created is not None else "",
        },
        "workspace": {
            "id": str(workspace.id),
            "name": workspace.name,
            "logo_url": getattr(workspace, "logo_url", None),
            "accent_color": getattr(workspace, "accent_color", "#8a1c2b"),
            "tier": (
                workspace.tier.value
                if hasattr(getattr(workspace, "tier", None), "value")
                else str(getattr(workspace, "tier", "solo"))
            ),
            "created_at": ws_created.isoformat() if ws_created is not None else "",
        },
    }


@_shim.post("/api/auth/logout")
def spa_logout() -> dict[str, bool]:
    return {"ok": True}
'''


_RELAY_ACCESS_SALT = "relay-access-token"
_RELAY_SESSION_SALT = "relay-session"
_CREATE_ACCESS_TOKEN_RE = re.compile(
    r"def _create_access_token\(operator_id\)[\s\S]*?"
    r"return serializer\.dumps\(\s*\{[\"']sub[\"']:\s*str\(operator_id\)\},\s*"
    r"salt=[\"']relay-access-token[\"']\)",
)
# Token ``sub`` / path ids are str; SQLAlchemy UUID columns need uuid.UUID.
_RELAY_UUID_PK_EQ_RE = re.compile(
    r"\b(?P<model>Operator|Handoff)\.id\s*==\s*(?P<var>operator_id|handoff_id)\b"
)
_RELAY_UUID_PK_EXPECTED = {"Operator": "operator_id", "Handoff": "handoff_id"}


def _iter_product_api_dirs(code_root: Path) -> list[Path]:
    root = Path(code_root)
    found: list[Path] = []
    seen: set[str] = set()
    for rel in ("backend/app", "app", "api", "server", "backend"):
        candidate = root / rel
        if not candidate.is_dir():
            continue
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)
    return found or ([root] if root.is_dir() else [])


def relay_source_session_mismatch(code_root: Path) -> bool:
    """True when login signs a token the protected routes will not accept.

    Measured on Factory Relay (prod-e1a3b0abf16a): ``auth.py`` dumps with
    ``salt=relay-access-token`` (and ``SESSION_SECRET`` / cookie ``session``) while
    ``handoffs.py`` / ``security.py`` verify ``relay-session`` and read cookie
    ``relay_session``. The Vercel bundle used to hide this; the product tree must not.
    """
    for api_dir in _iter_product_api_dirs(code_root):
        auth_path = next((p for p in api_dir.rglob("routers/auth.py") if p.is_file()), None)
        if auth_path is None:
            continue
        try:
            auth = auth_path.read_text(encoding="utf-8")
        except OSError:
            continue
        salt_wrong = _RELAY_ACCESS_SALT in auth
        cookie_wrong = False
        deps = auth_path.parent.parent / "deps.py"
        if deps.is_file() and ('key="session"' in auth or "key='session'" in auth):
            try:
                deps_text = deps.read_text(encoding="utf-8")
            except OSError:
                deps_text = ""
            if 'SESSION_COOKIE_NAME' in deps_text and "relay_session" in deps_text:
                cookie_wrong = True
        if not salt_wrong and not cookie_wrong:
            continue
        protected = False
        for sibling in (auth_path.parent / "handoffs.py", auth_path.parent.parent / "security.py"):
            if not sibling.is_file():
                continue
            try:
                blob = sibling.read_text(encoding="utf-8")
            except OSError:
                continue
            if _RELAY_SESSION_SALT in blob:
                protected = True
                break
        if protected or cookie_wrong:
            return True
    return False


def _skip_uuid_heal_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & {"tests", "test", "__pycache__"}:
        return True
    name = path.name.lower()
    return name.startswith("test_") or name.endswith("_test.py")


def _relay_uuid_pk_coerce_repl(match: re.Match) -> str:
    model = match.group("model")
    var = match.group("var")
    if _RELAY_UUID_PK_EXPECTED.get(model) != var:
        return match.group(0)
    return f'{model}.id == __import__("uuid").UUID(str({var}))'


def relay_text_has_raw_uuid_pk_eq(text: str) -> bool:
    return bool(_RELAY_UUID_PK_EQ_RE.search(text or ""))


def relay_source_uuid_pk_mismatch(code_root: Path) -> bool:
    """True when a string token subject is compared to a UUID PK column.

    Measured on Factory Relay (prod-e1a3b0abf16a): after salt/cookie heal,
    ``verify_access_token`` succeeds then ``Operator.id == operator_id`` raises
    because JWT/itsdangerous payloads carry ``str`` and SQLAlchemy UUID columns
    (Postgres) require ``uuid.UUID``. Same class: ``Handoff.id == handoff_id``.
    """
    for api_dir in _iter_product_api_dirs(code_root):
        for path in api_dir.rglob("*.py"):
            if not path.is_file() or _skip_uuid_heal_path(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if relay_text_has_raw_uuid_pk_eq(text):
                return True
    return False


def patch_relay_uuid_pk_lookup(api_dir: Path) -> list[str]:
    """Coerce string operator/handoff ids before SQLAlchemy UUID filters.

    Idempotent. Writes into the product tree (and the Vercel copy). Cursor must
    not SSH-edit the product; the factory owns this write.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("*.py"):
        if not path.is_file() or _skip_uuid_heal_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new = _RELAY_UUID_PK_EQ_RE.sub(_relay_uuid_pk_coerce_repl, text)
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        try:
            notes.append(path.relative_to(root).as_posix())
        except ValueError:
            notes.append(path.name)
    return notes


# Exact fragments measured on Factory Relay (prod-e1a3b0abf16a). Same contract as
# AEGIS ``docker/patch-relay.py``: replace the pinned bytes or stop — never guess.
# (relpath under backend/app, old, new)
_RELAY_PINNED_FRAGMENTS: tuple[tuple[str, str, str], ...] = (
    (
        "services/handoff_service.py",
        '{"category": it.category.value, "passed": it.passed}',
        '{"category": (it.category.value if hasattr(it.category, "value") else str(it.category)), '
        '"passed": it.passed}',
    ),
    (
        "services/handoff_service.py",
        '"source": verification_source.value,',
        '"source": (verification_source.value if hasattr(verification_source, "value") '
        'else str(verification_source)),',
    ),
    (
        "services/receipt.py",
        '"category": vi.category.value',
        '"category": (vi.category.value if hasattr(vi.category, "value") else str(vi.category))',
    ),
    (
        "services/receipt.py",
        '"handoff_id": handoff.id',
        '"handoff_id": str(handoff.id)',
    ),
    (
        "services/receipt.py",
        '"approval_state": handoff.status.value',
        '"approval_state": (handoff.status.value if hasattr(handoff.status, "value") else str(handoff.status))',
    ),
    (
        "services/receipt.py",
        '"verification_source": handoff.verification_source.value',
        '"verification_source": (handoff.verification_source.value if hasattr('
        'handoff.verification_source, "value") else str(handoff.verification_source))',
    ),
    (
        "services/audit.py",
        '"id": e.id',
        '"id": str(e.id)',
    ),
    (
        "services/audit.py",
        '"action": e.action.value',
        '"action": (e.action.value if hasattr(e.action, "value") else str(e.action))',
    ),
    (
        "schemas/__init__.py",
        "from pydantic import BaseModel, Field",
        "from uuid import UUID\n\n"
        "from pydantic import BaseModel as PydanticBaseModel, Field, field_validator\n\n\n"
        "class BaseModel(PydanticBaseModel):\n"
        '    model_config = {"from_attributes": True}\n\n'
        "    @field_validator(\"*\", mode=\"before\")\n"
        "    @classmethod\n"
        "    def stringify_uuid(cls, value):\n"
        "        return str(value) if isinstance(value, UUID) else value",
    ),
)


def _resolve_pinned_path(api_dir: Path, rel: str) -> Path | None:
    direct = Path(api_dir) / rel
    if direct.is_file():
        return direct
    matches = [p for p in Path(api_dir).rglob(rel) if p.is_file()]
    if len(matches) == 1:
        return matches[0]
    return None


def _relay_looks_like_pinned_tree(api_dir: Path) -> bool:
    root = Path(api_dir)
    return bool(_resolve_pinned_path(root, "routers/handoffs.py")) and bool(
        _resolve_pinned_path(root, "services/receipt.py")
    )


def relay_source_pinned_mismatch(code_root: Path) -> bool:
    """True when a pinned Relay enum/ORM/audit fragment is still raw."""
    for api_dir in _iter_product_api_dirs(code_root):
        for rel, old, new in _RELAY_PINNED_FRAGMENTS:
            path = _resolve_pinned_path(api_dir, rel)
            if path is None:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if old in text and new not in text:
                return True
    return False


def relay_source_pinned_structure_break(code_root: Path) -> bool:
    """True when Relay-shaped files exist but a pinned fragment moved — do not guess."""
    for api_dir in _iter_product_api_dirs(code_root):
        if not _relay_looks_like_pinned_tree(api_dir):
            continue
        for rel, old, new in _RELAY_PINNED_FRAGMENTS:
            path = _resolve_pinned_path(api_dir, rel)
            if path is None:
                return True
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                return True
            if old not in text and new not in text:
                return True
    return False


def patch_relay_pinned_compat(api_dir: Path) -> list[str]:
    """Fail-fast exact replaces for Relay enum/ORM/audit 500s. Factory owns the write.

    Mirrors AEGIS ``docker/patch-relay.py``: if the bytes are not where the pin
    says, skip that fragment rather than patching a neighbour. Cursor must not
    SSH-edit the product.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    written: set[str] = set()
    for rel, old, new in _RELAY_PINNED_FRAGMENTS:
        path = _resolve_pinned_path(root, rel)
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if old not in text:
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
        try:
            note = path.relative_to(root).as_posix()
        except ValueError:
            note = rel
        if note not in written:
            written.add(note)
            notes.append(note)
    return notes


def patch_relay_token_salt_mismatch(api_dir: Path) -> list[str]:
    """Write the Relay login/session alignment into the product tree, not only the Vercel copy.

    Login must emit ``create_session_token`` (salt ``relay-session``, ``session_secret``).
    Cookie name must match ``SESSION_COOKIE_NAME``. Handoffs must read ``session_secret``.
    Idempotent. Cursor must not SSH-edit the product; the factory owns this write.
    """
    notes: list[str] = []
    root = Path(api_dir)
    auth_path = next((p for p in root.rglob("routers/auth.py") if p.is_file()), None)
    if auth_path is None:
        return notes
    try:
        auth = auth_path.read_text(encoding="utf-8")
    except OSError:
        return notes
    new_auth = auth
    if _RELAY_ACCESS_SALT in new_auth and "create_session_token" not in new_auth:
        rewritten = _CREATE_ACCESS_TOKEN_RE.sub(
            "def _create_access_token(operator_id) -> str:\n"
            '    """Create a signed token carrying the operator id."""\n'
            "    from ..security import create_session_token\n"
            "    return create_session_token(str(operator_id))  "
            + _RELAY_SPA_AUTH_MARKER,
            new_auth,
            count=1,
        )
        if rewritten == new_auth:
            rewritten = new_auth.replace(
                f'salt="{_RELAY_ACCESS_SALT}"',
                f'salt="{_RELAY_SESSION_SALT}"',
            ).replace(
                f"salt='{_RELAY_ACCESS_SALT}'",
                f"salt='{_RELAY_SESSION_SALT}'",
            )
            rewritten = rewritten.replace(
                'getattr(settings, "SESSION_SECRET", "dev-secret")',
                'getattr(settings, "session_secret", None) or getattr('
                'settings, "SESSION_SECRET", "dev-secret")  '
                + _RELAY_SPA_AUTH_MARKER,
            )
        new_auth = rewritten
    cookie_name = ""
    deps_path = auth_path.parent.parent / "deps.py"
    if deps_path.is_file():
        try:
            deps_text = deps_path.read_text(encoding="utf-8")
        except OSError:
            deps_text = ""
        m = re.search(r'SESSION_COOKIE_NAME\s*=\s*["\']([^"\']+)["\']', deps_text)
        if m:
            cookie_name = m.group(1)
    if cookie_name and cookie_name != "session":
        if 'key="session"' in new_auth:
            new_auth = new_auth.replace('key="session"', f'key="{cookie_name}"', 1)
        elif "key='session'" in new_auth:
            new_auth = new_auth.replace("key='session'", f"key='{cookie_name}'", 1)
    if new_auth != auth:
        auth_path.write_text(new_auth, encoding="utf-8")
        notes.append(auth_path.relative_to(root).as_posix())

    handoffs_path = auth_path.parent / "handoffs.py"
    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and 'getattr(settings, "SESSION_SECRET"' in ht:
            patched = ht.replace(
                'secret = getattr(settings, "SESSION_SECRET", None) or getattr('
                'settings, "SECRET_KEY", "insecure-dev-secret")',
                'secret = getattr(settings, "session_secret", None) or getattr('
                'settings, "SECRET_KEY", "insecure-dev-secret")  '
                + _RELAY_SPA_AUTH_MARKER,
                1,
            )
            if patched == ht:
                patched = ht.replace(
                    'getattr(settings, "SESSION_SECRET", None)',
                    'getattr(settings, "session_secret", None) or getattr('
                    'settings, "SESSION_SECRET", None)',
                    1,
                )
            if patched != ht:
                handoffs_path.write_text(patched, encoding="utf-8")
                notes.append(handoffs_path.relative_to(root).as_posix())
    return notes


def patch_relay_spa_auth_compat(api_dir: Path, public_dir: Path) -> list[str]:
    """Relay SPA login calls /api/auth/csrf after /api/auth/login; ship those routes.

    Token salt / cookie alignment is applied first via ``patch_relay_token_salt_mismatch``
    and does not require the built SPA to mention CSRF — that used to skip the source heal.
    """
    notes: list[str] = []
    root = Path(api_dir)
    notes.extend(patch_relay_token_salt_mismatch(root))
    notes.extend(patch_relay_uuid_pk_lookup(root))
    auth_path = next((p for p in root.rglob("routers/auth.py") if p.is_file()), None)
    if auth_path is None:
        return notes
    try:
        auth_text = auth_path.read_text(encoding="utf-8")
    except OSError:
        return notes
    if "/api/auth/login" not in auth_text:
        return notes
    shim_path = auth_path.parent / "_aicom_spa_auth_shim.py"
    if shim_path.is_file():
        try:
            if _RELAY_SPA_AUTH_MARKER in shim_path.read_text(encoding="utf-8"):
                # CSRF shim already shipped; salt notes (if any) still return.
                return notes
        except OSError:
            pass
    needs_csrf = False
    pub = Path(public_dir)
    if pub.is_dir():
        for js in pub.rglob("*.js"):
            try:
                if "/auth/csrf" in js.read_text(encoding="utf-8", errors="ignore"):
                    needs_csrf = True
                    break
            except OSError:
                continue
    if not needs_csrf:
        return notes

    shim_path = auth_path.parent / "_aicom_spa_auth_shim.py"
    shim_path.write_text(_RELAY_SPA_AUTH_SHIM + "\n" + _RELAY_SPA_AUTH_MARKER + "\n", encoding="utf-8")
    notes.append(shim_path.relative_to(root).as_posix())

    new_auth = auth_text
    if "relay-access-token" in new_auth and "create_session_token" not in new_auth:
        new_auth = re.sub(
            r"def _create_access_token\(operator_id\)[\s\S]*?return serializer\.dumps\("
            r'\{"sub": str\(operator_id\)\}, salt="relay-access-token"\)',
            'def _create_access_token(operator_id) -> str:\n'
            '    """Create a signed token carrying the operator id."""\n'
            "    from ..security import create_session_token\n"
            "    return create_session_token(str(operator_id))  "
            + _RELAY_SPA_AUTH_MARKER,
            new_auth,
            count=1,
        )
    if new_auth != auth_text:
        auth_path.write_text(new_auth, encoding="utf-8")
        notes.append(auth_path.relative_to(root).as_posix())

    handoffs_path = auth_path.parent / "handoffs.py"
    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and _RELAY_SPA_AUTH_MARKER not in ht:
            patched = ht.replace(
                'secret = getattr(settings, "SECRET_KEY", "insecure-dev-secret")',
                'secret = getattr(settings, "session_secret", None) or getattr('
                'settings, "SECRET_KEY", "insecure-dev-secret")  '
                + _RELAY_SPA_AUTH_MARKER,
                1,
            )
            if "def _aicom_operator_by_id" not in patched and "def verify_access_token" in patched:
                patched = patched.replace(
                    "def verify_access_token(token: str, db: Session) -> Optional[Operator]:",
                    "def _aicom_operator_by_id(db: Session, operator_id) -> Optional[Operator]:\n"
                    "    import uuid as _uuid\n"
                    "    try:\n"
                    "        oid = _uuid.UUID(str(operator_id))\n"
                    "    except ValueError:\n"
                    "        oid = operator_id\n"
                    "    return db.query(Operator).filter(Operator.id == oid).first()  "
                    + _RELAY_SPA_AUTH_MARKER
                    + "\n\n"
                    "def verify_access_token(token: str, db: Session) -> Optional[Operator]:",
                    1,
                )
            patched = patched.replace(
                "db.query(Operator).filter(Operator.id == operator_id).first()",
                "_aicom_operator_by_id(db, operator_id)",
            )
            if "relay-access-token" not in patched and "BadSignature:" in patched:
                patched = patched.replace(
                    "    except BadSignature:\n        pass",
                    "    except BadSignature:\n        pass\n\n"
                    "    try:\n"
                    '        s2 = URLSafeTimedSerializer(secret, salt="relay-access-token")\n'
                    "        data = s2.loads(token, max_age=7 * 24 * 3600)\n"
                    '        operator_id = data.get("operator_id") or data.get("sub")\n'
                    "        if operator_id:\n"
                    "            op = db.query(Operator).filter(Operator.id == operator_id).first()\n"
                    "            if op is not None:\n"
                    "                return op\n"
                    "    except BadSignature:\n"
                    "        pass  "
                    + _RELAY_SPA_AUTH_MARKER,
                    1,
                )
            if patched != ht:
                handoffs_path.write_text(patched, encoding="utf-8")
                notes.append(handoffs_path.relative_to(root).as_posix())

    for schema_path in root.rglob("schemas/__init__.py"):
        try:
            st = schema_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "class HandoffOut" not in st or "from_attributes" in st:
            continue
        new_st = st
        if "ConfigDict" not in new_st:
            new_st = new_st.replace(
                "from pydantic import BaseModel",
                "from pydantic import BaseModel, ConfigDict",
                1,
            )
        new_st = new_st.replace(
            "class HandoffOut(BaseModel):",
            "class HandoffOut(BaseModel):\n"
            "    model_config = ConfigDict(from_attributes=True)  "
            + _RELAY_SPA_AUTH_MARKER,
            1,
        )
        if new_st != st:
            schema_path.write_text(new_st, encoding="utf-8")
            notes.append(schema_path.relative_to(root).as_posix())

    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and "def _aicom_handoff_out" not in ht and "HandoffOut.model_validate(h)" in ht:
            helper = (
                "\n\n"
                "def _aicom_handoff_out(h: Handoff) -> HandoffOut:\n"
                '    """ORM → schema with UUID/enum coercion (Vercel serverless)."""\n'
                "    return HandoffOut(\n"
                "        id=str(h.id),\n"
                "        workspace_id=str(h.workspace_id),\n"
                "        client_name=h.client_name,\n"
                "        project_name=h.project_name,\n"
                "        source_ai_tool=h.source_ai_tool,\n"
                "        draft_text=h.draft_text,\n"
                "        approved_text=h.approved_text,\n"
                "        status=h.status.value if hasattr(h.status, 'value') else str(h.status),\n"
                "        share_token=h.share_token,\n"
                "        content_sha256=h.content_sha256,\n"
                "        verification_source=(\n"
                "            h.verification_source.value\n"
                "            if hasattr(h.verification_source, 'value')\n"
                "            else str(h.verification_source)\n"
                "        ),\n"
                "        created_by=str(h.created_by),\n"
                "        approved_by=str(h.approved_by) if h.approved_by else None,\n"
                "        approved_at=h.approved_at,\n"
                "        rejected_reason=h.rejected_reason,\n"
                "        created_at=h.created_at,\n"
                "    )  "
                + _RELAY_SPA_AUTH_MARKER
                + "\n"
            )
            anchor = "router = APIRouter(tags=[\"handoffs\"])"
            if anchor in ht:
                ht = ht.replace(anchor, helper + anchor, 1)
            ht = ht.replace(
                "HandoffOut.model_validate(h)",
                "_aicom_handoff_out(h)",
            )
            ht = ht.replace(
                "HandoffOut.model_validate(handoff)",
                "_aicom_handoff_out(handoff)",
            )
            handoffs_path.write_text(ht, encoding="utf-8")
            rel = handoffs_path.relative_to(root).as_posix()
            if rel not in notes:
                notes.append(rel)

    if handoffs_path.is_file():
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        counts_old = "        counts[s.value] = c"
        counts_new = (
            "        _sk = s.value if hasattr(s, \"value\") else str(s)\n"
            "        if _sk in counts:\n"
            "            counts[_sk] = c  "
            + _RELAY_SPA_AUTH_MARKER
        )
        if ht and counts_old in ht and counts_new not in ht:
            ht = ht.replace(counts_old, counts_new, 1)
            handoffs_path.write_text(ht, encoding="utf-8")
            rel = handoffs_path.relative_to(root).as_posix()
            if rel not in notes:
                notes.append(rel)

    main_path = auth_path.parent.parent / "main.py"
    if main_path.is_file():
        try:
            mt = main_path.read_text(encoding="utf-8")
        except OSError:
            mt = ""
        if mt and _RELAY_SPA_AUTH_MARKER not in mt:
            if "_aicom_spa_auth_shim" not in mt:
                mt = re.sub(
                    r"from \.routers import (?P<rest>[^\n]+)",
                    lambda m: (
                        "from .routers import _aicom_spa_auth_shim, "
                        + m.group("rest").lstrip()
                        + "  "
                        + _RELAY_SPA_AUTH_MARKER
                    ),
                    mt,
                    count=1,
                )
            if "_aicom_spa_auth_shim._shim" not in mt:
                anchor = "app.include_router(auth.router"
                if anchor in mt:
                    mt = mt.replace(
                        anchor,
                        "app.include_router(_aicom_spa_auth_shim._shim)  "
                        + _RELAY_SPA_AUTH_MARKER
                        + "\n    "
                        + anchor,
                        1,
                    )
            if _RELAY_SPA_AUTH_MARKER in mt:
                main_path.write_text(mt, encoding="utf-8")
                notes.append(main_path.relative_to(root).as_posix())

    # CSRF fallback may re-insert ``Operator.id == operator_id``; coerce last.
    for rel in patch_relay_uuid_pk_lookup(root):
        if rel not in notes:
            notes.append(rel)
    return notes


_RELAY_PUBLIC_EXPORT_MARKER = "# aicom-factory-relay-public-export"


def patch_relay_public_export_compat(api_dir: Path) -> list[str]:
    """Fix Relay public share, receipt JSON, and embed-snippet on Vercel serverless.

    Measured on prod-e1a3b0abf16a: ``PublicReadOut = PublicHandoffOut`` alias breaks the
    nested public router response (500); ``build_receipt`` emits non-JSON-serializable UUIDs
    (500 on receipt.json); enum/UUID coercion gaps break list/detail paths without
    ``_aicom_handoff_out``.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes

    for schema_path in root.rglob("schemas/__init__.py"):
        try:
            st = schema_path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_st = st
        # PublicWorkspaceOut is assigned after this class in Relay; using it here
        # NameError's the whole serverless import (FUNCTION_INVOCATION_FAILED).
        if "class PublicReadOut(BaseModel):" in new_st:
            new_st = new_st.replace(
                "    workspace: PublicWorkspaceOut\n",
                "    workspace: WorkspaceOut\n",
            )
        if _RELAY_PUBLIC_EXPORT_MARKER in new_st:
            if new_st != st:
                schema_path.write_text(new_st, encoding="utf-8")
                notes.append(schema_path.relative_to(root).as_posix())
            continue
        if "class HandoffOut" not in new_st:
            if new_st != st:
                schema_path.write_text(new_st, encoding="utf-8")
                notes.append(schema_path.relative_to(root).as_posix())
            continue
        alias_block = "PublicReadOut = PublicHandoffOut"
        if alias_block in new_st and "class PublicReadOut(BaseModel):" not in new_st:
            nested = (
                "\n\n"
                "class PublicHandoffShareOut(BaseModel):\n"
                '    """Approved handoff slice for the public share page."""\n'
                "    id: str\n"
                "    client_name: str\n"
                "    project_name: str\n"
                "    source_ai_tool: str\n"
                "    approved_text: str\n"
                "    approved_at: Optional[datetime] = None\n"
                "    content_sha256: str\n\n\n"
                "class PublicReadOut(BaseModel):\n"
                "    handoff: PublicHandoffShareOut\n"
                "    workspace: WorkspaceOut\n"
                "    verification_source: str  "
                + _RELAY_PUBLIC_EXPORT_MARKER
                + "\n"
            )
            new_st = new_st.replace(alias_block, nested, 1)
        if "stringify_uuid" in new_st or "class BaseModel(PydanticBaseModel)" in new_st:
            # Pinned ORM wrap already stringifies UUIDs; do not rewrite the import.
            pass
        elif "model_config = ConfigDict(from_attributes=True)" not in new_st and "class HandoffOut" in new_st:
            if "ConfigDict" not in new_st:
                new_st = new_st.replace(
                    "from pydantic import BaseModel",
                    "from pydantic import BaseModel, ConfigDict",
                    1,
                )
            if "class HandoffOut(BaseModel):" in new_st and "from_attributes=True" not in new_st:
                new_st = new_st.replace(
                    "class HandoffOut(BaseModel):",
                    "class HandoffOut(BaseModel):\n"
                    "    model_config = ConfigDict(from_attributes=True)  "
                    + _RELAY_PUBLIC_EXPORT_MARKER,
                    1,
                )
        if new_st != st:
            schema_path.write_text(new_st, encoding="utf-8")
            notes.append(schema_path.relative_to(root).as_posix())

    public_path = next((p for p in root.rglob("routers/public.py") if p.is_file()), None)
    if public_path is not None:
        try:
            pt = public_path.read_text(encoding="utf-8")
        except OSError:
            pt = ""
        if pt and _RELAY_PUBLIC_EXPORT_MARKER not in pt and "PublicHandoffShareOut" not in pt:
            new_pt = pt.replace(
                "from ..schemas import PublicHandoffOut, PublicReadOut, PublicWorkspaceOut",
                "from ..schemas import PublicHandoffShareOut, PublicReadOut, PublicWorkspaceOut  "
                + _RELAY_PUBLIC_EXPORT_MARKER,
                1,
            )
            new_pt = new_pt.replace(
                "handoff=PublicHandoffOut(",
                "handoff=PublicHandoffShareOut(",
            )
            new_pt = new_pt.replace("id=h.id,", "id=str(h.id),  " + _RELAY_PUBLIC_EXPORT_MARKER, 1)
            new_pt = new_pt.replace(
                "tier=workspace.tier.value,",
                "tier=(workspace.tier.value if hasattr(workspace.tier, 'value') else str(workspace.tier)),  "
                + _RELAY_PUBLIC_EXPORT_MARKER,
                1,
            )
            if new_pt != pt:
                public_path.write_text(new_pt, encoding="utf-8")
                notes.append(public_path.relative_to(root).as_posix())

    for receipt_path in root.rglob("services/receipt.py"):
        try:
            rt = receipt_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _RELAY_PUBLIC_EXPORT_MARKER in rt or '"handoff_id": handoff.id' not in rt:
            continue
        new_rt = rt.replace(
            '"handoff_id": handoff.id,',
            '"handoff_id": str(handoff.id),  ' + _RELAY_PUBLIC_EXPORT_MARKER,
            1,
        )
        if new_rt != rt:
            receipt_path.write_text(new_rt, encoding="utf-8")
            notes.append(receipt_path.relative_to(root).as_posix())

    handoffs_path = next((p for p in root.rglob("routers/handoffs.py") if p.is_file()), None)
    if handoffs_path is not None:
        try:
            ht = handoffs_path.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if ht and "def _aicom_handoff_out" not in ht and "HandoffOut.model_validate" in ht:
            helper = (
                "\n\n"
                "def _aicom_handoff_out(h: Handoff) -> HandoffOut:\n"
                '    """ORM → schema with UUID/enum coercion (Vercel serverless)."""\n'
                "    return HandoffOut(\n"
                "        id=str(h.id),\n"
                "        workspace_id=str(h.workspace_id),\n"
                "        client_name=h.client_name,\n"
                "        project_name=h.project_name,\n"
                "        source_ai_tool=h.source_ai_tool,\n"
                "        draft_text=h.draft_text,\n"
                "        approved_text=h.approved_text,\n"
                "        status=h.status.value if hasattr(h.status, 'value') else str(h.status),\n"
                "        share_token=h.share_token,\n"
                "        content_sha256=h.content_sha256,\n"
                "        verification_source=(\n"
                "            h.verification_source.value\n"
                "            if hasattr(h.verification_source, 'value')\n"
                "            else str(h.verification_source)\n"
                "        ),\n"
                "        created_by=str(h.created_by),\n"
                "        approved_by=str(h.approved_by) if h.approved_by else None,\n"
                "        approved_at=h.approved_at,\n"
                "        rejected_reason=h.rejected_reason,\n"
                "        created_at=h.created_at,\n"
                "    )  "
                + _RELAY_PUBLIC_EXPORT_MARKER
                + "\n"
            )
            anchor = "router = APIRouter(tags=[\"handoffs\"])"
            if anchor in ht:
                ht = ht.replace(anchor, helper + anchor, 1)
            ht = ht.replace("HandoffOut.model_validate(handoff)", "_aicom_handoff_out(handoff)")
            ht = ht.replace("HandoffOut.model_validate(h)", "_aicom_handoff_out(h)")
            handoffs_path.write_text(ht, encoding="utf-8")
            rel = handoffs_path.relative_to(root).as_posix()
            if rel not in notes:
                notes.append(rel)
        elif ht and "HandoffOut.model_validate" in ht and _RELAY_PUBLIC_EXPORT_MARKER not in ht:
            patched = ht.replace("HandoffOut.model_validate(handoff)", "_aicom_handoff_out(handoff)")
            patched = patched.replace("HandoffOut.model_validate(h)", "_aicom_handoff_out(h)")
            if patched != ht:
                handoffs_path.write_text(patched, encoding="utf-8")
                rel = handoffs_path.relative_to(root).as_posix()
                if rel not in notes:
                    notes.append(rel)

    return notes


def patch_deterministic_demo_user_seed(api_dir: Path) -> list[str]:
    """Make demo user primary keys deterministic from email (uuid5).

    Without this, each Vercel instance seeds ``uuid4()`` for the same demo email,
    so a Bearer token from instance A fails on instance B (``User not found``).
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    seed_names = {"seed.py", "demo_seed.py", "seeding.py"}
    for path in root.rglob("*.py"):
        if path.name not in seed_names and "seed" not in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "seed_demo_user" not in text or "User(" not in text:
            continue
        if _DEMO_SEED_UUID_MARKER in text:
            continue
        if "User(" not in text:
            continue
        new = text
        if "_aicom_demo_user_id" not in new:
            # Insert helper before first seed_demo_user def.
            new = new.replace(
                "def seed_demo_user",
                _DEMO_SEED_UUID_SNIPPET + "\n" + _DEMO_SEED_UUID_MARKER + "\ndef seed_demo_user",
                1,
            )
        # Prefer explicit id= on User(...) construction.
        if re.search(r"User\s*\(\s*\n?\s*email\s*=", new) and "id=_aicom_demo_user_id" not in new:
            new = re.sub(
                r"User\s*\(\s*",
                "User(\n            id=_aicom_demo_user_id(email),\n            ",
                new,
                count=1,
            )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_AUTH_LOGIN_SEED_MARKER = "# aicom-factory-auth-seed-helper"
_AUTH_LOGIN_DEF_RE = re.compile(r"\b(?:async )?def login\s*\(")
_AUTH_ONE_SHOT_SEED_RE = re.compile(
    r"[ \t]*global _demo_seeded\n"
    r"(?:[ \t]*#.*\n)*"
    r"[ \t]*if not _demo_seeded:[\s\S]*?"
    r"[ \t]*_demo_seeded = True\n",
)
_ORPHAN_SEED_IMPORT_RE = re.compile(
    r"^(?:from \.\.services\.seeding import seed_demo_user|"
    r"from app\.services\.seeding import seed_demo_user)\n",
    re.M,
)


def _seeding_py_exists(api_dir: Path) -> bool:
    return any(p.is_file() and p.name == "seeding.py" for p in Path(api_dir).rglob("seeding.py"))


def patch_drop_orphan_seed_demo_import(api_dir: Path) -> list[str]:
    """Relay-style apps have login_root/login_api, not Sentinel's seed helper.

    ``def login`` used to match ``def login_root``, so auth_seed imported
    ``seed_demo_user`` from a module that does not exist — ImportError on every
    request. Strip the dangling import when seeding.py is absent and unused.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir() or _seeding_py_exists(root):
        return notes
    for path in root.rglob("auth.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "seed_demo_user(db)" in text:
            continue
        new = _ORPHAN_SEED_IMPORT_RE.sub("", text)
        if new.startswith(_AUTH_LOGIN_SEED_MARKER + "\n") and "seed_demo_user" not in new:
            new = new[len(_AUTH_LOGIN_SEED_MARKER) + 1 :]
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        try:
            notes.append(path.relative_to(root).as_posix())
        except ValueError:
            notes.append(path.name)
    return notes


def patch_auth_login_to_use_seed_helper(api_dir: Path) -> list[str]:
    """Login must upsert the demo operator on every request, not once per process.

    Sentinel's ``auth.py`` seeded only if the email was missing, then set
    ``_demo_seeded = True`` even after a failed hash. On Vercel that is a
    permanent 401: /tmp SQLite is empty on a new instance, or an old row keeps a
    stale password. ``seeding.seed_demo_user`` already upserts; login must call it.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("auth.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _AUTH_LOGIN_DEF_RE.search(text):
            continue
        new = text
        already = _AUTH_LOGIN_SEED_MARKER in new and "seed_demo_user(db)" in new
        needs_sub = '"sub": str(user.id)' in new or "'sub': str(user.id)" in new
        if already and not needs_sub:
            continue
        if "seed_demo_user" not in new:
            if "from ..db import get_db" in new:
                new = new.replace(
                    "from ..db import get_db",
                    "from ..db import get_db\nfrom ..services.seeding import seed_demo_user",
                    1,
                )
            elif "from app.db import" in new:
                new = "from app.services.seeding import seed_demo_user\n" + new
            else:
                new = "from app.services.seeding import seed_demo_user\n" + new
        if _AUTH_ONE_SHOT_SEED_RE.search(new):
            new = _AUTH_ONE_SHOT_SEED_RE.sub("    seed_demo_user(db)\n", new, count=1)
        elif "seed_demo_user(db)" not in new:
            new = re.sub(
                r"(async def login\s*\([^)]*\)\s*:\s*\n)",
                r"\1    seed_demo_user(db)\n",
                new,
                count=1,
            )
        new = new.replace("_demo_seeded = False\n", "")
        new = new.replace("_demo_seeded = False", "")
        # deps.py treats JWT ``sub`` as an email; a random uuid there is
        # live_ephemeral_identity + 401 User not found on every other instance.
        new = new.replace('"sub": str(user.id)', '"sub": user.email')
        new = new.replace("'sub': str(user.id)", "'sub': user.email")
        if _AUTH_LOGIN_SEED_MARKER not in new:
            new = _AUTH_LOGIN_SEED_MARKER + "\n" + new
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def pin_passlib_compatible_bcrypt(reqs: list[str]) -> tuple[list[str], list[str]]:
    """passlib 1.7.4 cannot inspect bcrypt>=4.1 (``__about__``); hash then 401s."""
    notes: list[str] = []
    has_passlib = any(_req_base(r) == "passlib" for r in reqs)
    if not has_passlib:
        return reqs, notes
    out: list[str] = []
    pinned = False
    for req in reqs:
        if _req_base(req) != "bcrypt":
            out.append(req)
            continue
        if req.strip() != "bcrypt==4.0.1":
            notes.append(
                f"pinned {req} → bcrypt==4.0.1: passlib 1.7.4 cannot hash with bcrypt>=4.1"
            )
        out.append("bcrypt==4.0.1")
        pinned = True
    if not pinned:
        out.append("bcrypt==4.0.1")
        notes.append("added bcrypt==4.0.1: passlib backend pin for Vercel")
    return _dedupe(out), notes


_JWT_DEPS_MARKER = "# aicom-factory-jwt-identity"


def jwt_secret_env(product_id: str | None = None) -> dict[str, str]:
    """Stable JWT secret injected before the app imports Settings.

    Sentinel login signed with ``os.environ.setdefault(SECRET_KEY, sentinel-dev-…)``
    after ``get_settings()`` had already cached ``secret_key=dev-secret-key-change-me``.
    ``get_current_user`` then jose-decoded with Settings and every operator route
    answered ``Invalid token`` after a 200 login.
    """
    override = (os.environ.get("AIFACTORY_PRODUCT_JWT_SECRET") or "").strip()
    secret = override or f"aicom-demo-jwt:{product_id or 'default'}"
    return {
        "SECRET_KEY": secret,
        "JWT_SECRET": secret,
        "JWT_ALGORITHM": "HS256",
        "ALGORITHM": "HS256",
    }


def patch_get_current_user_stable_identity(api_dir: Path) -> list[str]:
    """Resolve JWT ``sub`` as email or id, and re-seed the demo user on the instance."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("deps.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "def get_current_user" not in text:
            continue
        if _JWT_DEPS_MARKER in text:
            continue
        new = text
        if "seed_demo_user" not in new:
            if "from app.db import get_db" in new:
                new = new.replace(
                    "from app.db import get_db",
                    "from app.db import get_db\nfrom app.services.seeding import seed_demo_user",
                    1,
                )
            elif "from ..db import get_db" in new:
                new = new.replace(
                    "from ..db import get_db",
                    "from ..db import get_db\nfrom ..services.seeding import seed_demo_user",
                    1,
                )
            else:
                new = "from app.services.seeding import seed_demo_user\n" + new
        new = new.replace(
            'email: str = payload.get("sub")',
            'email = payload.get("email") or payload.get("sub")',
        )
        new = new.replace(
            'email = payload.get("sub")',
            'email = payload.get("email") or payload.get("sub")',
        )
        if "seed_demo_user(db)" not in new and "user = db.query(User)" in new:
            new = new.replace(
                "user = db.query(User)",
                "seed_demo_user(db)\n    user = db.query(User)",
                1,
            )
        new = re.sub(
            r"user = db\.query\(User\)\.filter\(User\.email == email\)\.first\(\)",
            "user = db.query(User).filter(User.email == email).first()\n"
            "    if user is None:\n"
            "        user = db.query(User).filter(User.id == str(email)).first()",
            new,
            count=1,
        )
        if _JWT_DEPS_MARKER not in new:
            new = _JWT_DEPS_MARKER + "\n" + new
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_LIVE_AUTH_SKIP_PARTS = {".venv", "venv", "node_modules", ".aicom_sandbox", "__pycache__", ".git"}


def pin_bcrypt_in_requirement_files(code_dir: Path) -> list[str]:
    """Write the passlib-compatible bcrypt pin into the product tree, not only the bundle."""
    from web.backend.services.requirements_manifest import iter_requirement_files

    notes: list[str] = []
    root = Path(code_dir)
    if not root.is_dir():
        return notes
    for path in iter_requirement_files(root):
        if any(part in _LIVE_AUTH_SKIP_PARTS for part in path.parts):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = raw.splitlines()
        reqs = [
            ln.strip()
            for ln in lines
            if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("-")
        ]
        new_reqs, pin_notes = pin_passlib_compatible_bcrypt(reqs)
        if not pin_notes:
            continue
        out_lines: list[str] = []
        bcrypt_written = False
        for ln in lines:
            s = ln.strip()
            if s and not s.startswith("#") and _req_base(s) == "bcrypt":
                if not bcrypt_written:
                    out_lines.append("bcrypt==4.0.1")
                    bcrypt_written = True
                continue
            out_lines.append(ln)
        if not bcrypt_written and any(_req_base(r) == "passlib" for r in new_reqs):
            out_lines.append("bcrypt==4.0.1")
        new = "\n".join(out_lines)
        if new and not new.endswith("\n"):
            new += "\n"
        if new == raw:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def apply_live_auth_autofix(code_root: Path) -> list[str]:
    """Patch the product tree for known live-auth defects (401 salt, UUID PK 500,
    enum/ORM/audit serialization).

    The Vercel bundle already applies these to a copy. The factory must also write
    them into ``data/code/<id>`` so the next publish (and GitHub) is the factory's
    fix — not a Cursor SSH into the product, and not an AEGIS Docker sed on a pin.
    """
    root = Path(code_root)
    if not root.is_dir():
        return []
    actions: list[str] = []
    for api_dir in _iter_product_api_dirs(root):
        for label, fn in (
            ("auth_seed", patch_auth_login_to_use_seed_helper),
            ("orphan_seed_import", patch_drop_orphan_seed_demo_import),
            ("jwt_identity", patch_get_current_user_stable_identity),
            ("demo_uuid", patch_deterministic_demo_user_seed),
            ("relay_token_salt", patch_relay_token_salt_mismatch),
            ("relay_uuid_pk", patch_relay_uuid_pk_lookup),
            ("relay_pinned", patch_relay_pinned_compat),
            ("relay_public_export", patch_relay_public_export_compat),
        ):
            for rel in fn(api_dir):
                actions.append(f"{label}:{rel}")
    for rel in pin_bcrypt_in_requirement_files(root):
        actions.append(f"bcrypt_pin:{rel}")
    return actions


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


_ATLAS_CORE_LAYERS_MARKER = "aicom-factory-atlas-core-layers"
# Product often asked only flood/effis/… — Moscow's LIVE pin is weather (om-wx-moscow).
_ATLAS_SITUATION_LAYERS = (
    '["weather", "air", "fire", "flood", "effis", "lightning", '
    '"volcano", "alerts", "events", "tsunami"]'
)
_ATLAS_NEAREST_LAYERS = '["weather", "air", "fire", "flood", "effis"]'


def ensure_atlas_client_core_layers(api_dir: Path) -> list[str]:
    """Ensure situation/nearest invokes include weather+fire (not only hazard niches).

    Sentinel shipped with ``layers: [flood, effis, …]`` and no ``weather``. ATLAS then
    correctly refused Moscow with ``no LIVE readings…for requested layers`` even though
    ``om-wx-moscow`` is LIVE 5 km away — the pin was filtered out by the layer list.
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
        if _ATLAS_CORE_LAYERS_MARKER in text and '"weather"' in text:
            continue
        new = text
        # Replace common product layer lists (quoted JSON-ish in Python source).
        for old in (
            '["flood", "effis", "lightning", "volcano", "alerts", "events", "tsunami"]',
            "['flood', 'effis', 'lightning', 'volcano', 'alerts', 'events', 'tsunami']",
            '["flood", "effis"]',
            "['flood', 'effis']",
        ):
            if "flood" in old and "lightning" in old:
                new = new.replace(old, _ATLAS_SITUATION_LAYERS)
            else:
                new = new.replace(old, _ATLAS_NEAREST_LAYERS)
        if new == text:
            continue
        if _ATLAS_CORE_LAYERS_MARKER not in new:
            new = f"# {_ATLAS_CORE_LAYERS_MARKER}\n" + new
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def patch_widget_demo_defaults(public_dir: Path) -> list[str]:
    """Keep Berlin as the demo city, but the API bbox (above) must be wide enough to hit LIVE pins."""
    # No city swap — Berlin works once atlas_client uses ±5°. Hook retained for future JS fixes.
    return []


# Passwords products bake into Vite bundles while the API seeds from factory env — UI login 401.
_STALE_DEMO_PASSWORD_MARKERS = (
    "SentinelDemo123!",
    "SandboxDemo!2026",
)


def _frontend_demo_auth_stale(code_dir: Path, demo: dict[str, str]) -> bool:
    """True when the built SPA does not carry the same demo password the API will seed."""
    dist = find_frontend_dist(code_dir)
    if dist is None:
        return True
    password = (demo.get("VITE_SANDBOX_DEMO_PASSWORD") or demo.get("SANDBOX_DEMO_PASSWORD") or "").strip()
    if not password:
        return False
    blob_parts: list[str] = []
    for path in list(dist.rglob("*.js"))[:24] + list(dist.rglob("*.mjs"))[:8]:
        try:
            blob_parts.append(path.read_text(encoding="utf-8", errors="replace")[:80_000])
        except OSError:
            continue
    blob = "".join(blob_parts)
    if password in blob:
        return False
    return any(marker in blob for marker in _STALE_DEMO_PASSWORD_MARKERS)


def patch_operator_login_prefill(
    public_dir: Path,
    *,
    demo_email: str,
    demo_password: str = "",
) -> list[str]:
    """Replace reserved demo auth baked into frontend bundles.

    EmailStr rejects ``.local`` (422). Operator Login must prefill the same
    ``SANDBOX_DEMO_*`` the API seeds — typically ``sandbox.demo@magic-ai-factory.com`` plus the
    factory ``AIFACTORY_SANDBOX_DEMO_PASSWORD``. Vite bakes ``VITE_SANDBOX_DEMO_PASSWORD`` at build
    time; when that diverges from ``vercel.json`` runtime env the UI gets permanent 401.
    """
    notes: list[str] = []
    root = Path(public_dir)
    if not root.is_dir():
        return notes
    email = (demo_email or "").strip()
    password = (demo_password or "").strip()
    if not email and not password:
        return notes
    email_needles = (
        "operator@sentinel.local",
        "admin@localhost",
        "demo@localhost",
        "operator@localhost",
    )
    password_needles = list(_STALE_DEMO_PASSWORD_MARKERS)
    from web.backend.services.demo_credentials import DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD

    password_needles.append(DOCKER_COMPOSE_DEFAULT_SANDBOX_DEMO_PASSWORD)
    for path in list(root.rglob("*.js")) + list(root.rglob("*.html")) + list(root.rglob("*.mjs")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        new = text
        if email:
            for needle in email_needles:
                if needle in new:
                    new = new.replace(needle, email)
        if password:
            for needle in password_needles:
                if needle and needle != password and needle in new:
                    new = new.replace(needle, password)
        if (
            "aicom-factory-mesh-participant-runtime" not in new
            and re.search(r"get_participant\(\)\._invoke\s*\(", new)
        ):
            new = re.sub(
                r"return\s+await\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            new = re.sub(
                r"return\s+get_participant\(\)\._invoke\s*\(",
                "return get_participant().invoke(",
                new,
            )
            if "aicom-factory-mesh-participant-runtime" not in new:
                new = new.replace(
                    "async def _invoke",
                    "# aicom-factory-mesh-participant-runtime\n    async def _invoke",
                    1,
                )
        if new == text:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_RUN_IN_EXECUTOR_SITUATION_RE = re.compile(
    r"situation\s*=\s*await\s+asyncio\.wait_for\(\s*"
    r"loop\.run_in_executor\(\s*pool\s*,\s*atlas\.invoke_situation_brief\s*,\s*"
    r"rounded_lat\s*,\s*rounded_lon\s*\)\s*,\s*timeout\s*=\s*[\d.]+\s*\)",
    re.M,
)


def rewrite_async_atlas_run_in_executor(api_dir: Path) -> list[str]:
    """``run_in_executor`` cannot take an ``async def`` — Vercel then answers UNKNOWN.

    Measured on Sentinel after a developer round: ``atlas.invoke_situation_brief`` is
    async, the handler passed it to ``loop.run_in_executor``, and every advisory
    returned ``coroutines cannot be used with run_in_executor()``.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    repl = "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)"
    for path in root.rglob("advisory.py"):
        if "router" not in path.as_posix() and path.parent.name != "routers":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new, n = _RUN_IN_EXECUTOR_SITUATION_RE.subn(repl, text)
        if n == 0:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def parallelize_atlas_advisory_invokes(api_dir: Path, *, escrow_paid: bool = False) -> list[str]:
    """Tune advisory ATLAS fan-out for the publish target.

    Trial / agent-key paths: three sequential cold-start invokes blow the live-gate
    timeout, so we gather them.

    Escrow-paid channels: gather races the on-chain debit nonce (one auth per nonce).
    Collapse to a single ``situation.brief`` — it already carries weather/fire/flood
    layers the rule engine needs.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    seq = (
        "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)\n"
        "        fire_weather = await atlas.invoke_fire_weather(rounded_lat, rounded_lon)\n"
        "        nearest = await atlas.invoke_nearest(rounded_lat, rounded_lon)"
    )
    gathered = (
        "situation, fire_weather, nearest = await asyncio.gather(\n"
        "            atlas.invoke_situation_brief(rounded_lat, rounded_lon),\n"
        "            atlas.invoke_fire_weather(rounded_lat, rounded_lon),\n"
        "            atlas.invoke_nearest(rounded_lat, rounded_lon),\n"
        "        )"
    )
    single = (
        "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)\n"
        "        fire_weather = situation\n"
        "        nearest = situation"
    )
    for path in root.rglob("advisory.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if escrow_paid:
            if "aicom-factory-atlas-escrow-single" in text:
                continue
            changed = False
            if gathered in text:
                text = text.replace(gathered, single)
                changed = True
            elif seq in text:
                text = text.replace(seq, single)
                changed = True
            if not changed:
                continue
            text = text.replace("# aicom-factory-atlas-gather\n", "")
            text = "# aicom-factory-atlas-escrow-single\n" + text
            path.write_text(text, encoding="utf-8")
            notes.append(path.relative_to(root).as_posix())
            continue
        if "aicom-factory-atlas-gather" in text or "aicom-factory-atlas-escrow-single" in text:
            continue
        if seq not in text:
            continue
        text = text.replace(seq, gathered)
        if "import asyncio" not in text:
            text = "import asyncio\n" + text
        text = "# aicom-factory-atlas-gather\n" + text
        path.write_text(text, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_ATLAS_RULE_ENGINE = '''# aicom-factory-atlas-rule-engine-v4 — vendored only (data/code untouched).
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

    def _mesh_payload(self, data: dict[str, Any] | None) -> dict[str, Any]:
        """Hub/participant often nests the real body under result/output/data without ok=True."""
        if not isinstance(data, dict):
            return {}
        if (
            data.get("ok") is True
            or data.get("score") is not None
            or data.get("wind_speed_kmh") is not None
            or isinstance(data.get("weather"), dict)
            or data.get("refuse_reason")
            or data.get("error")
        ):
            return data
        for key in ("result", "output", "data", "body", "payload"):
            nested = data.get(key)
            if isinstance(nested, dict):
                return nested
        return data

    def _refuse_reason(self, *payloads: dict[str, Any] | None) -> str:
        for raw in payloads:
            p = self._mesh_payload(raw if isinstance(raw, dict) else None)
            if not p:
                continue
            if p.get("refuse_reason"):
                return str(p.get("refuse_reason"))[:220]
            # Prefer nested Hub bodies over bare "Status 402" from the participant wrapper.
            detail = p.get("detail")
            if isinstance(detail, dict):
                nested = (
                    detail.get("detail")
                    or detail.get("error")
                    or detail.get("message")
                    or detail.get("refuse_reason")
                )
                if nested:
                    return str(nested)[:220]
            elif detail:
                return str(detail)[:220]
            for key in ("error", "message"):
                val = p.get(key)
                if not val:
                    continue
                if isinstance(val, dict):
                    nested = val.get("detail") or val.get("error") or val.get("message")
                    if nested:
                        return str(nested)[:220]
                    return str(val)[:220]
                text = str(val)
                if text.lower().startswith("status ") and isinstance(detail, dict):
                    continue
                return text[:220]
        return "mesh response unavailable"

    def _evaluate_weather(
        self, fire_weather: dict[str, Any] | None, situation: dict[str, Any] | None
    ) -> tuple:
        data = self._mesh_payload(fire_weather if isinstance(fire_weather, dict) else None)
        if data.get("ok") is True or data.get("wind_speed_kmh") is not None or data.get("score") is not None:
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
        sit = self._mesh_payload(situation if isinstance(situation, dict) else None)
        if (sit.get("ok") is True or sit.get("score") is not None) and sit.get("score") is not None:
            return (
                _score_level(sit.get("score")),
                str(sit.get("summary") or f"score {sit.get('score')}"),
                [{"name": "ATLAS situation score", "condition": "score bands", "fired": True}],
            )
        reason = self._refuse_reason(fire_weather, situation)
        return ("UNKNOWN", reason, [{"name": "Weather data", "condition": reason, "fired": False}])

    def _evaluate_fire(
        self,
        situation: dict[str, Any] | None,
        fire_weather: dict[str, Any] | None,
        nearest: dict[str, Any] | None,
    ) -> tuple:
        for raw in (fire_weather, situation, nearest):
            data = self._mesh_payload(raw if isinstance(raw, dict) else None)
            if not data:
                continue
            if data.get("ok") is not True and data.get("score") is None and data.get("active_fires") is None and data.get("nearest_fire_km") is None:
                if not isinstance(data.get("coverage"), dict) and not isinstance(data.get("nearest"), dict):
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
            if data.get("ok") is True or active == 0 or (active is None and nearest_km is None and data.get("score") is None):
                if data.get("ok") is True or active == 0:
                    return ("CALM", "No active fires", [{"name": "Active fires", "condition": "=0", "fired": False}])
        reason = self._refuse_reason(fire_weather, situation, nearest)
        return ("UNKNOWN", reason, [{"name": "Fire data", "condition": reason, "fired": False}])

    def _evaluate_flood(
        self, situation: dict[str, Any] | None, nearest: dict[str, Any] | None
    ) -> tuple:
        for raw in (situation, nearest):
            data = self._mesh_payload(raw if isinstance(raw, dict) else None)
            if not data:
                continue
            if data.get("ok") is not True and data.get("flood_alerts") is None and not isinstance(data.get("coverage"), dict):
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
            if data.get("ok") is True or alerts == 0:
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
        if "aicom-factory-atlas-rule-engine-v4" in text:
            continue
        # Only replace engines that map ATLAS / soft-mesh placeholders.
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

    demo = demo_auth_env()

    dist = find_frontend_dist(code_dir)
    if build_frontend and _frontend_demo_auth_stale(code_dir, demo):
        vite_env = {k: v for k, v in demo.items() if k.startswith("VITE_")}
        built = _try_build_frontend(code_dir, extra_env=vite_env)
        report["frontend_build"] = built
        report["frontend_demo_auth_refreshed"] = True
        dist = find_frontend_dist(code_dir)
    elif dist is None and build_frontend:
        vite_env = {k: v for k, v in demo.items() if k.startswith("VITE_")}
        built = _try_build_frontend(code_dir, extra_env=vite_env)
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

    # Write known live-auth patches into the product tree before vendoring so the
    # factory owns the fix (GitHub + next copy), not a one-off bundle rewrite.
    source_auth = apply_live_auth_autofix(code_dir)
    if source_auth:
        report["live_auth_source_patches"] = source_auth
        logger.info(
            "vercel bundle %s: live-auth autofix on product source in %s",
            code_dir.name,
            ", ".join(source_auth[:6]),
        )

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "api").mkdir(parents=True)

    shutil.copytree(dist, out_dir / "public", ignore=copytree_ignore)

    login_patches = patch_operator_login_prefill(
        out_dir / "public",
        demo_email=demo["SANDBOX_DEMO_EMAIL"],
        demo_password=demo["SANDBOX_DEMO_PASSWORD"],
    )
    if login_patches:
        report["operator_login_prefill"] = login_patches
        logger.info(
            "vercel bundle %s: rewrote reserved demo login emails in %s",
            code_dir.name,
            ", ".join(login_patches[:6]),
        )

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

    participant_rewrites = ensure_aimarket_participant_client(out_dir / "api")
    if participant_rewrites:
        report["mesh_participant_rewrites"] = participant_rewrites
        logger.info(
            "vercel bundle %s: wired AI-market participant headers in %s",
            code_dir.name,
            ", ".join(participant_rewrites[:6]),
        )

    settings_exports = ensure_settings_module_export(out_dir / "api")
    if settings_exports:
        report["settings_exports"] = settings_exports
        logger.info(
            "vercel bundle %s: exported settings singleton in %s",
            code_dir.name,
            ", ".join(settings_exports[:6]),
        )

    spa_404 = patch_spa_api_not_found_tuple(out_dir / "api")
    if spa_404:
        report["spa_api_404_patches"] = spa_404
        logger.info(
            "vercel bundle %s: patched SPA api 404 tuple in %s",
            code_dir.name,
            ", ".join(spa_404[:6]),
        )

    demo_uuid = patch_deterministic_demo_user_seed(out_dir / "api")
    if demo_uuid:
        report["demo_uuid_patches"] = demo_uuid
        logger.info(
            "vercel bundle %s: deterministic demo user ids in %s",
            code_dir.name,
            ", ".join(demo_uuid[:6]),
        )

    auth_seed = patch_auth_login_to_use_seed_helper(out_dir / "api")
    if auth_seed:
        report["auth_seed_patches"] = auth_seed
        logger.info(
            "vercel bundle %s: login calls seed_demo_user in %s",
            code_dir.name,
            ", ".join(auth_seed[:6]),
        )

    jwt_ident = patch_get_current_user_stable_identity(out_dir / "api")
    if jwt_ident:
        report["jwt_identity_patches"] = jwt_ident
        logger.info(
            "vercel bundle %s: stable JWT identity in %s",
            code_dir.name,
            ", ".join(jwt_ident[:6]),
        )

    relay_auth = patch_relay_spa_auth_compat(out_dir / "api", out_dir / "public")
    if relay_auth:
        report["relay_spa_auth_patches"] = relay_auth
        logger.info(
            "vercel bundle %s: Relay SPA auth compat in %s",
            code_dir.name,
            ", ".join(relay_auth[:6]),
        )

    # Persist the same auth heal into data/code — the bundle copy is not the source of truth.
    source_heal = apply_live_auth_autofix(code_dir)
    if source_heal:
        report["source_auth_heal"] = source_heal
        logger.warning(
            "vercel bundle %s: wrote live-auth heal into product tree: %s",
            code_dir.name,
            ", ".join(source_heal[:8]),
        )

    relay_public = patch_relay_public_export_compat(out_dir / "api")
    if relay_public:
        report["relay_public_export_patches"] = relay_public
        logger.info(
            "vercel bundle %s: Relay public/receipt/export compat in %s",
            code_dir.name,
            ", ".join(relay_public[:6]),
        )

    try:
        from web.backend.services.visual_gate_autofix import _ensure_page_shell_layout

        page_shell = _ensure_page_shell_layout(out_dir)
        if page_shell:
            report["page_shell_patches"] = page_shell
            logger.info(
                "vercel bundle %s: page shell layout in %s",
                code_dir.name,
                ", ".join(page_shell[:6]),
            )
    except Exception as exc:
        logger.debug("vercel bundle page shell skipped for %s: %s", code_dir.name, exc)

    bbox_rewrites = widen_atlas_client_bbox(out_dir / "api")
    if bbox_rewrites:
        report["atlas_bbox_rewrites"] = bbox_rewrites
        logger.info(
            "vercel bundle %s: widened ATLAS client bbox in %s",
            code_dir.name,
            ", ".join(bbox_rewrites[:6]),
        )

    layer_rewrites = ensure_atlas_client_core_layers(out_dir / "api")
    if layer_rewrites:
        report["atlas_layer_rewrites"] = layer_rewrites
        logger.info(
            "vercel bundle %s: ensured weather/fire layers in %s",
            code_dir.name,
            ", ".join(layer_rewrites[:6]),
        )

    rule_rewrites = ensure_atlas_aware_rule_engine(out_dir / "api")
    if rule_rewrites:
        report["atlas_rule_engine"] = rule_rewrites
        logger.info(
            "vercel bundle %s: installed ATLAS-aware rule engine in %s",
            code_dir.name,
            ", ".join(rule_rewrites[:6]),
        )

    mesh = mesh_env(product_id=code_dir.name)
    # A wallet key without a Hub payment channel is sandbox-trial, not escrow-paid.
    # Treating wallet-only as paid made the bundle skip gather and still send a
    # dead channel — or skip the executor rewrite. Require the channel id.
    escrow_paid = bool((mesh.get("AIMARKET_PAYMENT_CHANNEL") or "").strip())
    executor_rewrites = rewrite_async_atlas_run_in_executor(out_dir / "api")
    if executor_rewrites:
        report["atlas_executor_rewrites"] = executor_rewrites
        logger.info(
            "vercel bundle %s: replaced async run_in_executor in %s",
            code_dir.name,
            ", ".join(executor_rewrites[:6]),
        )
    use_escrow_single_invoke = escrow_paid
    gather_rewrites = parallelize_atlas_advisory_invokes(
        out_dir / "api",
        escrow_paid=use_escrow_single_invoke,
    )
    if gather_rewrites:
        report["atlas_gather_rewrites"] = gather_rewrites
        logger.info(
            "vercel bundle %s: %s ATLAS advisory invokes in %s",
            code_dir.name,
            "escrow-single" if escrow_paid else "parallelized",
            ", ".join(gather_rewrites[:6]),
        )

    jwt_env = jwt_secret_env(product_id=code_dir.name)
    deploy_env = {**_sqlite_env(), **wallet_env(), **demo, **mesh, **jwt_env}
    # Demo auth + mesh + sqlite + JWT must *force*-assign: setdefault loses to empty
    # platform DATABASE_URL / SECRET_KEY and the function then cannot seed or
    # verify sessions (login 200 then operator 401 Invalid token).
    _force_keys = (
        set(demo.keys())
        | set(mesh.keys())
        | set(_sqlite_env().keys())
        | set(jwt_env.keys())
    )
    env_lines: list[str] = []
    for k, v in deploy_env.items():
        ks, vs = json.dumps(k), json.dumps(v)
        if k in _force_keys:
            env_lines.append(f"os.environ[{ks}] = {vs}")
        else:
            env_lines.append(f"os.environ.setdefault({ks}, {vs})")
    env_defaults = "\n".join(env_lines)
    extra_sys_path = ""
    if module_path.startswith("backend.") and module_path != "backend":
        extra_sys_path = 'sys.path.insert(0, str(_HERE / "backend"))\n'
    (out_dir / "api" / "index.py").write_text(
        _ENTRYPOINT.format(
            module=module_path,
            app_var=app_var,
            env_defaults=env_defaults,
            extra_sys_path=extra_sys_path,
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
    requirements, bcrypt_notes = pin_passlib_compatible_bcrypt(implied)
    req_notes = list(req_notes) + list(implied_notes) + list(bcrypt_notes)
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
