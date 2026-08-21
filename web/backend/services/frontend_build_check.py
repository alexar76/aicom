"""
Does the generated frontend actually compile?

Nothing in the pipeline ever ran the product's own build command. A SPA whose
TypeScript does not typecheck simply produced no ``dist/``, and the downstream
symptoms were reported as unrelated mysteries — "no_index_html" from the demo
gate, an empty Live Preview, a Vercel bundle that could not be assembled. The
actual cause sat three lines into ``npm run build``:

    src/pages/SourcesPage.tsx(3,10): error TS2305:
        Module '"../types"' has no exported member 'Source'.

This gate runs the product's declared build and reports the compiler's own
error lines, which are precise enough for the developer agent to fix directly.

npm needs a writable HOME and cache: the factory image runs as a non-root user
whose HOME is read-only, so a bare ``npm install`` dies with EACCES — which is
why earlier build attempts looked like "this product has no frontend".
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.paths import data_root

logger = logging.getLogger(__name__)

FRONTEND_DIR_CANDIDATES = ("frontend", "client", "web", "ui", "app", ".")

# tsc: "src/x.tsx(3,10): error TS2305: …"   vite/rollup: "[vite]: Rollup failed …"
_ERROR_LINE_RE = re.compile(
    r"^(?:.*\berror\s+TS\d+:.*|.*\bERROR\b.*|.*Rollup failed.*|.*Could not resolve.*)$",
    re.M,
)

MAX_REPORTED_ERRORS = 12


def npm_env() -> dict[str, str]:
    """Environment npm can actually write to."""
    env = os.environ.copy()
    root = Path(data_root())
    cache = root / ".npm"
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    env["HOME"] = str(root)
    env["npm_config_cache"] = str(cache)
    env["npm_config_update_notifier"] = "false"
    env["CI"] = "1"
    return env


_TSC_PATH_RE = re.compile(r"(?<![\w./-])((?:src|app|pages|components|lib|tests?)/[\w./-]+\.[a-z]{2,4})")


def _repo_relative(line: str, frontend_rel: str) -> str:
    """Rewrite tsc's frontend-relative paths so the rest of the pipeline can resolve them."""
    if not frontend_rel or frontend_rel == ".":
        return line
    prefix = frontend_rel.rstrip("/") + "/"
    return _TSC_PATH_RE.sub(
        lambda m: m.group(1) if m.group(1).startswith(prefix) else prefix + m.group(1), line
    )


def find_frontend_dir(code_dir: Path) -> Path | None:
    """A directory with package.json declaring a build script."""
    import json

    for rel in FRONTEND_DIR_CANDIDATES:
        base = code_dir if rel == "." else code_dir / rel
        pkg = base / "package.json"
        if not pkg.is_file():
            continue
        try:
            doc = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scripts = doc.get("scripts") if isinstance(doc, dict) else None
        if isinstance(scripts, dict) and scripts.get("build"):
            return base
    return None


def extract_error_lines(output: str) -> list[str]:
    """Pull the compiler's own diagnostics out of the build log."""
    lines: list[str] = []
    for match in _ERROR_LINE_RE.finditer(output or ""):
        line = match.group(0).strip()
        if not line or line.startswith("npm notice"):
            continue
        if line in lines:
            continue
        lines.append(line[:400])
        if len(lines) >= MAX_REPORTED_ERRORS:
            break
    return lines


_TEST_PATH_MARKERS = (
    "__tests__",
    ".test.",
    ".spec.",
    "/tests/",
    "setupTests",
    "e2e/",
)


def _is_test_file_error(line: str) -> bool:
    head = line.split("(", 1)[0].split(":", 1)[0]
    return any(marker in head for marker in _TEST_PATH_MARKERS)


# TS1005/TS1161/TS1109 in a plain .ts file is almost always JSX in the wrong extension.
_SYNTAX_ERROR_CODES = ("TS1005", "TS1109", "TS1161", "TS1381", "TS17008")
_JSX_HINT_RE = re.compile(r"return\s*\(?\s*<[A-Za-z]|<[A-Z][\w.]*[\s/>]|</[A-Za-z][\w.]*>")


def jsx_in_ts_hints(base: Path, errors: list[str]) -> list[str]:
    """Name the rename when a .ts file is failing because it contains JSX.

    tsc reports it as a cascade of "'>' expected" / "';' expected", which reads
    like a typo and sends the agent editing syntax that is already correct. The
    actual fix is one rename, and every import of the module keeps working.
    """
    hints: list[str] = []
    seen: set[str] = set()
    for line in errors:
        if not any(code in line for code in _SYNTAX_ERROR_CODES):
            continue
        rel = line.split("(", 1)[0].strip()
        if not rel.endswith(".ts") or rel.endswith(".d.ts") or rel in seen:
            continue
        candidate = base / rel
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _JSX_HINT_RE.search(text):
            continue
        seen.add(rel)
        hints.append(
            f"{rel} contains JSX but has a .ts extension — tsc reports that as a run of "
            f"syntax errors. Rename it to {rel[:-3]}.tsx (imports are unaffected); do not "
            "rewrite the syntax, it is already valid."
        )
    return hints


_IMPORT_META_ENV_RE = re.compile(r"Property 'env' does not exist on type 'ImportMeta'")
_TS2339_RE = re.compile(
    r"error TS2339:\s*Property '([^']+)' does not exist on type '([^']+)'"
)
_TS2339_SKIP_TYPES = frozenset(
    {
        "ImportMeta",
        "Window",
        "Document",
        "HTMLElement",
        "string",
        "number",
        "boolean",
        "object",
        "any",
        "never",
        "unknown",
        "void",
    }
)


def _brace_body(src: str, open_idx: int) -> str | None:
    if open_idx < 0 or open_idx >= len(src) or src[open_idx] != "{":
        return None
    depth = 0
    for i, ch in enumerate(src[open_idx:], open_idx):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[open_idx : i + 1]
    return None


def _prop_min_depth(body: str, prop: str) -> int | None:
    """1 = a top-level field of this interface; 2+ = nested; None = absent."""
    pat = re.compile(rf"\b{re.escape(prop)}\s*:")
    depth = 0
    i = 0
    found: list[int] = []
    while i < len(body):
        ch = body[i]
        if ch in "'\"`":
            q = ch
            i += 1
            while i < len(body) and body[i] != q:
                if body[i] == "\\":
                    i += 2
                    continue
                i += 1
            i += 1
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        m = pat.match(body, i)
        if m and depth >= 1:
            found.append(depth)
            i = m.end()
            continue
        i += 1
    return min(found) if found else None


def ts2339_shape_hint(product_code: Path, frontend_dir: Path, line: str) -> str | None:
    """Name where the missing property actually lives, the way missing_symbol names hash_password.

    Measured on Sentinel: PublicWidget read ``data.is_cached`` / ``data.cached_age_minutes`` on
    ``AdvisoryResponse``. The compiler said those properties do not exist. They do — on
    ``hazards[]`` — and ``cached_age_minutes`` exists nowhere in the type or the backend schema.
    PublicWidget.tsx was already first in repair_scope. The round still failed because the
    finding named only the read site, attached the type as read-only reference ("match these
    types"), and the model added a top-level field to ``advisory.ts``, which the scope guard
    reverted. Next QA saw the same two lines.

    Same shape as ``get_password_hash`` vs ``hash_password``: the tree already has the name,
    just not where the call site looks. Say so, and name the declaring file so the truncated
    six can include it.
    """
    match = _TS2339_RE.search(line or "")
    if not match:
        return None
    prop, type_name = match.group(1), match.group(2)
    if type_name in _TS2339_SKIP_TYPES or not type_name.isidentifier():
        return None
    decl_re = re.compile(
        rf"(?:export\s+)?(?:interface|type)\s+{re.escape(type_name)}\b[^{{;]*{{"
    )
    hits: list[tuple[str, int | None]] = []
    for dirpath, dirnames, filenames in os.walk(frontend_dir):
        dirnames[:] = [d for d in dirnames if d not in {"node_modules", "dist", ".aicom_sandbox"}]
        for name in filenames:
            if not name.endswith((".ts", ".tsx")):
                continue
            path = Path(dirpath) / name
            try:
                blob = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            decl = decl_re.search(blob)
            if not decl:
                continue
            body = _brace_body(blob, decl.end() - 1)
            if not body:
                continue
            try:
                rel = path.relative_to(product_code).as_posix()
            except ValueError:
                try:
                    rel = frontend_dir.name + "/" + path.relative_to(frontend_dir).as_posix()
                except ValueError:
                    continue
            hits.append((rel, _prop_min_depth(body, prop)))
            if len(hits) >= 4:
                break
        if len(hits) >= 4:
            break
    if not hits:
        return None
    rel, depth = hits[0]
    more = f" (also {', '.join(h[0] for h in hits[1:])})" if len(hits) > 1 else ""
    if depth is not None and depth >= 2:
        return (
            f"{type_name} is declared in {rel}{more}. '{prop}' is not a top-level field; it "
            f"lives on a nested object (hazards / items / similar). Read that nested path — "
            f"do not add a top-level '{prop}' to silence tsc unless the HTTP JSON actually "
            f"has one at the root."
        )
    if depth == 1:
        return None
    return (
        f"{type_name} is declared in {rel}{more}. '{prop}' is not on that type or its nested "
        f"fields. Remove the read, or add the field to this type AND the JSON the API "
        f"returns — do not invent it only on the TypeScript side."
    )


def vite_env_types_hint(base: Path, errors: list[str]) -> str | None:
    """Name the one-line fix for `import.meta.env` under Vite.

    A product reached "backend boots, API contract clean, demo login works" with
    exactly two build errors left, both this. tsc reports it as a property that
    does not exist, which reads like an application bug; the fix is a type
    reference the generated tsconfig omits.
    """
    if not any(_IMPORT_META_ENV_RE.search(line) for line in errors):
        return None
    decl = base / "src" / "vite-env.d.ts"
    if decl.is_file():
        try:
            if "vite/client" in decl.read_text(encoding="utf-8", errors="replace"):
                return None  # declared already; something else is wrong
        except OSError:
            pass
    return (
        "`import.meta.env` needs Vite's client types. Add src/vite-env.d.ts containing "
        '`/// <reference types="vite/client" />`, and make sure tsconfig includes it '
        '(or set "types": ["vite/client"]). This is a missing type declaration, not an '
        "application bug — do not rewrite the component."
    )


def run_frontend_build_check(
    product_id: str,
    data_root_override: str | Path | None = None,
) -> dict[str, Any]:
    """Install deps and run the product's build. Returns a QA-shaped report."""
    if os.environ.get("AIFACTORY_FRONTEND_BUILD_E2E", "1").strip().lower() in ("0", "false", "no"):
        return {"passed": True, "skipped": True, "reason": "disabled"}

    from core.paths import code_dir as resolve_code_dir
    from core.paths import resolve_data_root

    root = resolve_data_root(data_root_override)
    product_code = resolve_code_dir(product_id, data_root=root)
    if not product_code.is_dir():
        return {"passed": True, "skipped": True, "reason": "no_code_dir"}

    base = find_frontend_dir(product_code)
    if base is None:
        return {"passed": True, "skipped": True, "reason": "no_frontend_package_json"}

    npm = shutil.which("npm")
    if not npm:
        return {"passed": True, "skipped": True, "reason": "npm_not_available"}

    try:
        timeout = int(os.environ.get("AIFACTORY_FRONTEND_BUILD_TIMEOUT_SEC", "900"))
    except ValueError:
        timeout = 900

    env = npm_env()
    rel = base.relative_to(product_code).as_posix() or "."
    report: dict[str, Any] = {"skipped": False, "frontend_dir": rel}

    try:
        install = subprocess.run(
            [npm, "install", "--no-audit", "--no-fund"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {
            "passed": False,
            "skipped": False,
            "frontend_dir": rel,
            "issues": [f"frontend_install_failed:{str(exc)[:200]}"],
        }
    report["install_rc"] = install.returncode
    if install.returncode != 0:
        blob = f"{install.stdout}\n{install.stderr}"
        return {
            **report,
            "passed": False,
            "issues": [
                "frontend_install_failed:"
                + (extract_error_lines(blob) or [blob.strip()[-400:] or "npm install failed"])[0]
            ],
        }

    try:
        build = subprocess.run(
            [npm, "run", "build"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {
            **report,
            "passed": False,
            "issues": [f"frontend_build_timeout:{str(exc)[:200]}"],
        }

    report["build_rc"] = build.returncode
    # tsc writes diagnostics to stdout, vite to stderr — read both.
    blob = f"{build.stdout}\n{build.stderr}"
    if build.returncode == 0:
        dist = next(
            (d for d in (base / "dist", base / "build") if (d / "index.html").is_file()),
            None,
        )
        if dist is None:
            return {
                **report,
                "passed": False,
                "issues": [
                    "frontend_build_produced_no_index_html: the build command exited 0 "
                    "but no dist/index.html exists — the preview and the Vercel bundle "
                    "have nothing to serve."
                ],
            }
        report["dist"] = dist.relative_to(product_code).as_posix()
        return {**report, "passed": True, "issues": []}

    errors = extract_error_lines(blob)
    if not errors:
        errors = [f"npm run build exited {build.returncode}: {blob.strip()[-400:]}"]
    # tsc prints paths relative to the frontend directory, and everything downstream treats a path in
    # a finding as repo-relative: the repair scope, the file attachment, and the edit applier. So a
    # real error arrived as `src/api/advisory.ts(24,36)` for a file that lives at
    # `frontend/src/api/advisory.ts`, the scope came out EMPTY because no such file exists, nothing was
    # attached, and the round's edits came back `no such file — use files to create it`. Three of the
    # four failing gates depend on the frontend, and none of them could ever be fixed through a path
    # that does not resolve.
    # tsc sometimes prints ABSOLUTE paths (TS1149 does), which nothing downstream can resolve —
    # that is how a one-directory rename survived a full informed round.
    errors = [line.replace(str(product_code) + "/", "") for line in errors]
    errors = [_repo_relative(line, rel) for line in errors]
    issues = []
    for line in errors:
        extra = ts2339_shape_hint(product_code, base, line)
        issues.append(
            f"frontend_build_failed: {line}" + (f" {extra}" if extra else "")
        )

    for hint in jsx_in_ts_hints(base, errors):
        issues.append(f"frontend_build_failed: {hint}")

    hint = vite_env_types_hint(base, errors)
    if hint:
        issues.append(f"frontend_build_failed: {hint}")

    # A very common generated-product failure: `build` is `tsc && vite build`, tsc
    # typechecks the spec/test files too, and their devDependencies were never
    # declared. Saying so beats making the agent infer it from TS2307 five times.
    # Fires whenever any test-file error of this class is present, not only when
    # every error is one: a build with six "Cannot find name 'test'" plus one real
    # component error still needs the tsconfig/devDependency fix, and withholding
    # the hint left the agent to infer it from TS2582 six times over.
    if any(_is_test_file_error(line) for line in errors):
        issues.append(
            "frontend_build_failed: every error above comes from a test/spec file. "
            "`npm run build` runs tsc over them, so the product cannot build until "
            "either the missing test devDependencies are declared in package.json or "
            "the test globs are excluded from the build tsconfig (a separate "
            "tsconfig.test.json for the test runner is the usual split)."
        )
    return {**report, "passed": False, "issues": issues}
