"""The bundle's requirements: collected from the product, implied by its imports, filtered to
what installs on a serverless runtime, and bcrypt pinned for passlib.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.code_discovery import iter_product_files


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
