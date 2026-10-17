"""Python dependencies: imports no requirement declares, and imports of packages that do not
exist.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import from_imports, MAX_FINDINGS


# Frameworks the factory itself has installed, so a generated import from them can be
# verified without booting the product. Hallucinated framework APIs are a classic
# generation failure: `from fastapi.responses import JavaScriptResponse` looks entirely
# plausible, does not exist, and takes the whole app down at import time.
_VERIFIABLE_PACKAGES = (
    "fastapi",
    "starlette",
    "pydantic",
    "sqlalchemy",
    "httpx",
    "jose",
    "passlib",
)


def find_undeclared_dependencies(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Third-party imports the product never declares as dependencies.

    Found the only way this class of defect ever gets found: in production. The factory published a
    full-stack product to Vercel, the page served 200, and every API route answered
    FUNCTION_INVOCATION_FAILED. The function log said:

        File "/var/task/api/app/utils/security.py", line 7, in <module>
            import jwt
        ModuleNotFoundError: No module named 'jwt'

    ``requirements.txt`` declared ``python-jose[cryptography]`` — a different package that provides
    ``jose``, not ``jwt``. Nothing caught it, because the sandbox venv happened to have PyJWT
    installed: every gate ran against an environment more generous than production, which is the
    definition of a test that cannot fail for the reason that matters.

    Import name and package name are frequently different (``jwt`` → PyJWT, ``PIL`` → Pillow,
    ``cv2`` → opencv-python), so the mapping is explicit; unknown packages fall back to the usual
    normalisation, and anything ambiguous is left alone rather than guessed at.
    """
    import sys as _sys

    # Import name -> the distribution that provides it, where the two differ.
    known_aliases = {
        "jwt": "pyjwt",
        "jose": "python-jose",
        "PIL": "pillow",
        "cv2": "opencv-python",
        "yaml": "pyyaml",
        "sklearn": "scikit-learn",
        "dotenv": "python-dotenv",
        "bs4": "beautifulsoup4",
        "dateutil": "python-dateutil",
        "multipart": "python-multipart",
        "jwt_extended": "flask-jwt-extended",
        "psycopg2": "psycopg2-binary",
        "redis": "redis",
        "magic": "python-magic",
        "serial": "pyserial",
        "usb": "pyusb",
        "OpenSSL": "pyopenssl",
        "Crypto": "pycryptodome",
        "google": "google-cloud-storage",
        "attr": "attrs",
        "zoneinfo": "",  # stdlib on 3.9+
    }

    declared: set[str] = set()
    declaration_files: list[str] = []

    def _norm(name: str) -> str:
        return re.split(r"[<>=!\[;]", str(name).strip(), maxsplit=1)[0].strip().lower().replace("_", "-")

    def _declare(spec: str) -> None:
        """Record the distribution AND its extras. ``passlib[bcrypt]`` provides ``bcrypt`` too, and
        demanding a separate requirements line for it would be noise the product cannot act on."""
        declared.add(_norm(spec))
        extras = re.search(r"\[([^\]]+)\]", str(spec))
        if extras:
            for extra in extras.group(1).split(","):
                cleaned = extra.strip().lower().replace("_", "-")
                if cleaned:
                    declared.add(cleaned)

    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if file.name.startswith("requirements") and file.suffix == ".txt":
            declaration_files.append(rel)
            try:
                for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-")):
                        _declare(line)
            except OSError:
                continue
        elif file.name in ("pyproject.toml", "setup.cfg", "Pipfile"):
            declaration_files.append(rel)
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in re.finditer(r"[\"']([A-Za-z0-9][A-Za-z0-9._-]+)\s*(?:[<>=!~\[][^\"']*)?[\"']", blob):
                _declare(match.group(1))

    if not declaration_files:
        return []  # nothing declares anything: a different defect, not this one

    # Everything importable from within the product itself.
    local_roots: set[str] = set()
    for entry in code_dir.rglob("*"):
        rel_parts = entry.relative_to(code_dir).parts
        if any(
            p in ("node_modules", "dist", "build", ".next", "__pycache__", ".venv",
                  "preview-venv", ".git", ".aicom_sandbox")
            or p.startswith(".")
            for p in rel_parts
        ):
            continue
        if entry.is_dir():
            local_roots.add(entry.name)
        elif entry.suffix == ".py":
            local_roots.add(entry.stem)

    stdlib = set(getattr(_sys, "stdlib_module_names", set())) | {
        "__future__", "typing_extensions", "setuptools", "pkg_resources",
    }

    offenders: dict[str, list[str]] = {}
    for file in iter_product_files(code_dir, "*.py"):
        rel = file.relative_to(code_dir).as_posix()
        # Test-only imports are a dev concern, and a product that ships without pytest is fine.
        if "/tests/" in f"/{rel}" or file.name.startswith("test_"):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        roots: set[str] = set()
        for match in re.finditer(r"^\s*import\s+([A-Za-z_][\w.]*)", text, re.M):
            roots.add(match.group(1).split(".")[0])
        for match in re.finditer(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import", text, re.M):
            roots.add(match.group(1).split(".")[0])
        for root in roots:
            if root in stdlib or root in local_roots:
                continue
            dist = known_aliases.get(root, root.lower().replace("_", "-"))
            if not dist or dist in declared:
                continue
            # A declared extra such as passlib[bcrypt] provides `bcrypt` too; be conservative and
            # accept any declaration whose name contains the import root.
            if any(root.lower() in d for d in declared):
                continue
            offenders.setdefault(root, []).append(rel)

    findings: list[dict[str, Any]] = []
    target = declaration_files[0]
    for root, files in sorted(offenders.items()):
        dist = known_aliases.get(root, root.lower().replace("_", "-"))
        findings.append(
            {
                "code": "undeclared_dependency",
                "severity": "critical",
                "file": target,
                "import_root": root,
                "package": dist,
                "importers": sorted(files)[:4],
                "detail": (
                    f"`import {root}` in {', '.join(sorted(files)[:3])} is not covered by any "
                    f"declared dependency in {target}. It works in the sandbox only because that "
                    "environment happens to have the package installed; in a clean install — a "
                    "Docker build, a Vercel function, any deploy — the import raises "
                    f"ModuleNotFoundError and every route in the app returns a 500 before running "
                    f"a line of its own code. Add `{dist}` to {target}. Note that the import name "
                    "and the package name differ here"
                    if known_aliases.get(root)
                    else f"Add `{dist}` to {target}."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def find_hallucinated_imports(code_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Names imported from a known framework that the framework does not export."""
    import importlib

    findings: list[dict[str, Any]] = []
    module_cache: dict[str, Any] = {}

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for module, imported_names in from_imports(text):
            root = module.split(".")[0]
            if root not in _VERIFIABLE_PACKAGES:
                continue
            if module not in module_cache:
                try:
                    module_cache[module] = importlib.import_module(module)
                except Exception:
                    module_cache[module] = None  # not installed here; not our verdict
            mod = module_cache[module]
            if mod is None:
                continue
            for name in imported_names:
                if not name or name == "*":
                    continue
                if hasattr(mod, name):
                    continue
                findings.append(
                    {
                        "file": file.relative_to(code_dir).as_posix(),
                        "module": module,
                        "symbol": name,
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings
