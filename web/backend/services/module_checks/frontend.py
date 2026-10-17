"""Frontend: case collisions, unresolved imports, missing exports, Tailwind classes without
rules, undeclared npm dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import _normalised_matches, MAX_FINDINGS


def find_case_collisions(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Two entries in one directory whose names differ only in case.

    Found live as ``components/UI/`` next to ``components/ui/``. TypeScript refuses the tree with
    ``TS1149: File name … differs from already included file name only in casing``, so the build
    produces nothing — and the error prints absolute paths that no downstream consumer could resolve,
    which is how it survived a full informed round. On a case-insensitive filesystem (macOS, the
    default dev laptop) one of the two silently wins and the product breaks only in CI or on deploy,
    which is strictly worse than breaking here.

    The finding counts import references to each spelling and says to keep the more-referenced one,
    because "merge these" without a direction is the kind of instruction this pipeline has already
    watched oscillate.
    """
    from collections import defaultdict as _dd

    groups: dict[tuple[str, str], set[str]] = _dd(set)
    for path in code_dir.rglob("*"):
        rel = path.relative_to(code_dir)
        if any(part in ("node_modules", ".git", ".aicom_sandbox", "dist", "build", ".next", "__pycache__", ".venv", "preview-venv") for part in rel.parts):
            continue
        groups[(rel.parent.as_posix(), rel.name.lower())].add(rel.name)

    findings: list[dict[str, Any]] = []
    for (parent, _low), names in sorted(groups.items()):
        if len(names) < 2:
            continue
        spellings = sorted(names)
        refs: dict[str, int] = {}
        for name in spellings:
            stem = name.rsplit(".", 1)[0]
            count = 0
            for file in iter_product_files(code_dir, "*"):
                if file.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx", ".py"):
                    continue
                try:
                    count += file.read_text(encoding="utf-8", errors="replace").count(f"/{stem}")
                except OSError:
                    continue
            refs[name] = count
        keep = max(spellings, key=lambda n: refs.get(n, 0))
        drop = [n for n in spellings if n != keep]
        # Enumerate REAL FILES, not directories. The first version pointed `file` at the directory to
        # keep — and the pipeline's own path resolver rejects directories, so the finding fell out of
        # the repair scope, nothing was attached, and two informed rounds went to deps.py instead of
        # the collision. delete_files also needs exact file paths; "delete UI/" is not an instruction
        # it can execute.
        drop_files: list[str] = []
        for name in drop:
            candidate = code_dir / parent / name
            if candidate.is_dir():
                drop_files.extend(
                    sorted(
                        f.relative_to(code_dir).as_posix()
                        for f in candidate.rglob("*")
                        if f.is_file()
                    )[:12]
                )
            else:
                drop_files.append(f"{parent}/{name}".lstrip("/"))
        # A drop side holding no files at all is not a build failure and not an executable
        # finding. Measured: UI/Toast.tsx was finally deleted after eleven rounds, frontend_build
        # went green in the same verdict — and this detector kept module_health red on the empty
        # UI/ directory with `drop_files: []`, an instruction naming nothing. TypeScript never sees
        # an empty directory; the round-level prune removes it as housekeeping.
        if not drop_files:
            continue

        # `file` names the FIRST FILE TO DELETE, not the keep side. The repair scope is built from
        # this field, and pointing it at the keep side sent every round to an innocent file: scoped
        # to ui/FeedbackStates.tsx, a round would delete UI/Toast.tsx — the actual instruction —
        # and the out-of-scope revert would restore it, round after round. The keep side needs no
        # edits at all when the dropped spelling has zero references; the drop side always does.
        file_field = (
            drop_files[0]
            if drop_files
            else f"{parent}/{keep}".lstrip("/")
        )
        findings.append(
            {
                "code": "case_collision",
                "severity": "critical",
                "file": file_field,
                "parent": parent,
                "spellings": spellings,
                "keep": keep,
                "drop_files": drop_files,
                "detail": (
                    f"{parent or '.'} contains {' and '.join(spellings)} — the same name in different "
                    "casing. TypeScript refuses the tree with TS1149 and the build produces nothing; "
                    "on a case-insensitive filesystem one of the two silently wins. KEEP "
                    f"\"{keep}\" (referenced {refs.get(keep, 0)} time(s), more than "
                    + ", ".join(f"{d}: {refs.get(d, 0)}" for d in drop)
                    + "). Put these EXACT paths in delete_files after moving anything unique into "
                    f"\"{keep}\": "
                    + (", ".join(drop_files) if drop_files else ", ".join(drop))
                    + ". Then update any import that references the deleted spelling."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


_TS_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import|export)\s[^\n;]*?from\s*['"](\.[^'"]+)['"]""",
)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".css", ".svg")


def find_unresolved_frontend_imports(code_dir: Path, limit: int = 12) -> list[dict[str, Any]]:
    """Relative imports in TS/JS that point at no file on disk.

    The round guard was Python-only, so a repair could fix one backend symbol and
    delete or rename half the frontend without the score moving. Type-level
    mismatches still need tsc, but a module that simply is not there is cheap to
    catch and is the failure that breaks a build hardest.
    """
    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in _TS_IMPORT_RE.findall(text):
            target = (file.parent / spec).resolve()
            if any(
                target.with_suffix(sfx).is_file() for sfx in _TS_SUFFIXES
            ) or target.is_file():
                continue
            if any((target / f"index{sfx}").is_file() for sfx in _TS_SUFFIXES):
                continue
            findings.append(
                {
                    "file": file.relative_to(code_dir).as_posix(),
                    "import": spec,
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


_TS_EXPORT_DECL_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?"
    r"(?:function\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_TS_EXPORT_BRACE_RE = re.compile(
    r"^\s*export\s+(?:type\s+)?\{([^}]*)\}(?:\s*from\s*[\"']([^\"']+)[\"'])?", re.M
)
_TS_EXPORT_DEFAULT_RE = re.compile(r"^\s*export\s+default\b", re.M)
_TS_EXPORT_STAR_RE = re.compile(r"^\s*export\s*\*\s*from", re.M)
_TS_IMPORT_STMT_RE = re.compile(
    r"^\s*import\s+(type\s+)?([^;'\"]+?)\s+from\s*[\"']([^\"']+)[\"']", re.M
)
_TS_CODE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")


def _ts_resolve(file: Path, spec: str) -> Path | None:
    """The product file a relative TS import points at, or ``None``."""
    if not spec.startswith("."):
        return None  # third-party or aliased: not ours to judge
    base = (file.parent / spec).resolve()
    for cand in [base.with_suffix(sfx) for sfx in _TS_CODE_SUFFIXES] + [base] + [
        base / f"index{sfx}" for sfx in _TS_CODE_SUFFIXES
    ]:
        if cand.is_file():
            return cand
    return None


def _ts_exports_of(text: str) -> tuple[set[str], bool, bool]:
    """``(named exports, has_default, dynamic)`` for one TS module."""
    names = set(_TS_EXPORT_DECL_RE.findall(text))
    for inner, _from in _TS_EXPORT_BRACE_RE.findall(text):
        for piece in inner.split(","):
            piece = piece.strip()
            if not piece:
                continue
            # `A as B` exports B; a bare `A` exports A.
            parts = piece.split()
            names.add(parts[-1] if len(parts) == 3 and parts[1] == "as" else parts[0])
    has_default = bool(_TS_EXPORT_DEFAULT_RE.search(text))
    # `export *` makes the surface unenumerable; so does an export keyword our patterns missed.
    dynamic = bool(_TS_EXPORT_STAR_RE.search(text)) or (
        "export" in text and not names and not has_default
    )
    return names, has_default, dynamic


def find_frontend_missing_exports(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Named imports between the product's own TS files that the target never exports.

    The TypeScript twin of ``find_missing_symbols``, built for the same reason its Python sibling
    was: the last defect on a live product was a cross-file refactor — the frontend API layer plus
    five consumers — and every attempt was dismembered because the static score could not see
    TypeScript at all. The salvage log shows the coin flip in plain text: ``the rest of the round
    stands (0 vs 0 before)``. Reverting the API layer alone left five importers referencing exports
    that no longer existed, tsc failed with TS2305 five times, and the guard reverted the round —
    three rounds running, with the score reading zero throughout.

    Only relative imports between product files are judged. Third-party and aliased imports are
    skipped, a target that cannot be resolved is ``find_unresolved_frontend_imports``' business, a
    module with ``export *`` (or export syntax these patterns cannot parse) is treated as
    unenumerable and skipped — this feeds a score that discards work, so a false positive costs more
    than a miss.
    """
    modules: dict[Path, tuple[set[str], bool, bool]] = {}
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".ts", ".tsx"):
            continue
        try:
            modules[file.resolve()] = _ts_exports_of(
                file.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            continue

    import difflib

    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".ts", ".tsx"):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        importer = file.relative_to(code_dir).as_posix()
        for _type_kw, clause, spec in _TS_IMPORT_STMT_RE.findall(text):
            target = _ts_resolve(file, spec)
            if target is None or target.resolve() not in modules:
                continue
            exports, has_default, dynamic = modules[target.resolve()]
            if dynamic:
                continue
            rel_target = target.resolve().relative_to(code_dir.resolve()).as_posix()

            wanted: list[str] = []
            default_wanted = False
            body = clause.strip()
            brace = re.search(r"\{([^}]*)\}", body)
            if brace:
                for piece in brace.group(1).split(","):
                    piece = piece.strip()
                    if not piece:
                        continue
                    parts = piece.replace("type ", "").split()
                    wanted.append(parts[0])
                head = body[: brace.start()].strip().rstrip(",").strip()
                if head and not head.startswith("*"):
                    default_wanted = True
            elif body.startswith("*"):
                continue  # namespace import: member use is not statically checkable here
            elif body:
                default_wanted = True

            for name in wanted:
                if name in exports:
                    continue
                near = _normalised_matches(name, exports) or difflib.get_close_matches(
                    name, sorted(exports), n=2, cutoff=0.7
                )
                findings.append(
                    {
                        "code": "frontend_missing_export",
                        "severity": "high",
                        "file": rel_target,
                        "importer": importer,
                        "name": name,
                        "did_you_mean": near,
                        "detail": (
                            f"{importer} imports {{ {name} }} from '{spec}', but {rel_target} "
                            f"never exports '{name}'. tsc fails with TS2305 and `npm run build` "
                            "produces nothing to deploy."
                            + (f" It does export {', '.join(near)} — if that is the same thing, "
                               f"fix the IMPORT in {importer}; renaming the export instead breaks "
                               "every other importer." if near else "")
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
            if default_wanted and not has_default and not exports:
                findings.append(
                    {
                        "code": "frontend_missing_export",
                        "severity": "high",
                        "file": rel_target,
                        "importer": importer,
                        "name": "default",
                        "did_you_mean": [],
                        "detail": (
                            f"{importer} default-imports from '{spec}', but {rel_target} has no "
                            "default export. tsc fails and the build produces nothing to deploy."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


_TAILWIND_UTILITY_RE = re.compile(
    r"^(?:sm:|md:|lg:|xl:|2xl:|hover:|focus:|active:|disabled:|dark:|group-hover:)*"
    r"(?:flex|grid|block|inline|hidden|container|"
    r"(?:p|m|px|py|pt|pb|pl|pr|mx|my|mt|mb|ml|mr|gap|space|w|h|min-w|min-h|max-w|max-h|top|bottom|left|right|inset|z)-[\w./\[\]-]+|"
    r"(?:bg|text|border|ring|shadow|from|to|via|fill|stroke|divide|outline|accent)-[\w./\[\]-]+|"
    r"(?:rounded|font|leading|tracking|items|justify|self|content|place|order|col|row|overflow|opacity|cursor|transition|duration|ease|animate|object|whitespace|break|truncate|select|pointer-events|sr-only|antialiased|uppercase|lowercase|capitalize|italic|underline|absolute|relative|fixed|sticky|static)(?:-[\w./\[\]-]+)?)$"
)

_CLASSNAME_ATTR_RE = re.compile(r"""(class(?:Name)?=)(['"])([^'"]*)\2""")


def product_has_tailwind(code_dir: Path) -> bool:
    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if any(part in ("node_modules", "dist", "build", ".next", ".aicom_sandbox") for part in Path(rel).parts):
            continue
        if file.name in ("package.json",) or file.name.startswith("tailwind.config"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                blob = ""
            if "tailwind" in blob.lower():
                return True
            continue
        if file.suffix in (".css", ".scss", ".sass", ".less"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "@tailwind" in blob or "@apply" in blob:
                return True
    return False


def _stylesheet_path(code_dir: Path) -> Path | None:
    for candidate in (
        "frontend/src/styles/index.css",
        "frontend/src/index.css",
        "src/styles/index.css",
        "src/index.css",
    ):
        path = code_dir / candidate
        if path.is_file():
            return path
    return None


def _safe_product_file(code_dir: Path, rel: str) -> Path | None:
    if not rel or any(p in Path(rel).parts for p in ("node_modules", "dist", ".aicom_sandbox")):
        return None
    try:
        path = (code_dir / rel).resolve()
        path.relative_to(code_dir.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def strip_orphan_tailwind_classnames(code_dir: Path, relative_paths: list[str]) -> list[str]:
    """Drop Tailwind utilities from this round's markup when the product has no Tailwind.

    Live: a demo_quality round wrote the widget plus one ``text-muted``. The rollback
    score treated that as +5, salvage could not keep any landing file, and three
    attempts restored the tree. QA then asked for the same UI again.
    """
    if product_has_tailwind(code_dir):
        return []
    changed: list[str] = []
    for rel in relative_paths:
        path = _safe_product_file(code_dir, rel)
        if path is None or path.suffix.lower() not in {".tsx", ".jsx", ".html"}:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue

        def _repl(match: re.Match[str]) -> str:
            prefix, quote, value = match.group(1), match.group(2), match.group(3)
            kept = [tok for tok in value.split() if not _TAILWIND_UTILITY_RE.match(tok)]
            return f"{prefix}{quote}{' '.join(kept)}{quote}"

        updated = _CLASSNAME_ATTR_RE.sub(_repl, original)
        if updated == original:
            continue
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError:
            continue
        changed.append(rel)
    return changed


def ensure_markup_classes_have_rules(code_dir: Path, relative_paths: list[str]) -> list[str]:
    """Append CSS selectors for semantic classes this round used without a rule.

    Eight new class names without rules is ``unstyled_classes``: another +5 on the
    rollback score, same total restore as the stray Tailwind token.
    """
    stylesheet = _stylesheet_path(code_dir)
    if stylesheet is None:
        return []
    try:
        css_blob = stylesheet.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    defined = {m.group(1) for m in re.finditer(r"\.(-?[A-Za-z_][\w-]*)", css_blob)}
    missing: list[str] = []
    seen: set[str] = set()
    for rel in relative_paths:
        path = _safe_product_file(code_dir, rel)
        if path is None or path.suffix.lower() not in {".tsx", ".jsx", ".html"}:
            continue
        try:
            blob = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _CLASSNAME_ATTR_RE.finditer(blob):
            for cls in match.group(3).split():
                cls = cls.strip()
                if (
                    cls
                    and cls not in defined
                    and cls not in seen
                    and not _TAILWIND_UTILITY_RE.match(cls)
                    and not cls.startswith(("js-", "data-"))
                ):
                    seen.add(cls)
                    missing.append(cls)
    if not missing:
        return []
    block = "\n".join(f".{name} {{}}" for name in missing)
    try:
        stylesheet.write_text(css_blob.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
    except OSError:
        return []
    return missing


def find_unstyled_classes(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Markup whose class names have no styling behind them.

    Reported by a human looking at the deployed product and asking "where is the design?" — every
    gate was green. The build compiled, the browser rendered, the demo-quality gate counted sections
    and CTAs. None of them asked whether the classes in the markup mean anything.

    Two distinct failures, both fatal to the look and invisible to a type checker:

    * **Tailwind utilities with no Tailwind.** The live product used `bg-slate-800`, `flex`,
      `gap-2`, `focus:ring-2` throughout — and had no tailwindcss dependency and no config, so those
      class names styled nothing at all. The page rendered as unstyled HTML with a few colours from
      the handful of real rules that did exist.
    * **Semantic classes nobody wrote rules for.** 64 distinct classes used in JSX, 21 defined in
      the stylesheet.

    A type checker cannot see this: class names are strings. The browser cannot fail on it: unstyled
    markup renders fine. It has to be compared, which is what this does.
    """
    used: dict[str, list[str]] = {}
    defined: set[str] = set()
    has_tailwind = False

    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if any(part in ("node_modules", "dist", "build", ".next", ".aicom_sandbox") for part in Path(rel).parts):
            continue
        if file.name in ("package.json",) or file.name.startswith("tailwind.config"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                blob = ""
            if "tailwind" in blob.lower():
                has_tailwind = True
            continue
        if file.suffix in (".css", ".scss", ".sass", ".less"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "@tailwind" in blob or "@apply" in blob:
                has_tailwind = True
            for match in re.finditer(r"\.(-?[A-Za-z_][\w-]*)", blob):
                defined.add(match.group(1))
        elif file.suffix in (".tsx", ".jsx"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in re.finditer(r"class(?:Name)?=[\"']([^\"'{}]+)[\"']", blob):
                for cls in match.group(1).split():
                    cls = cls.strip()
                    if cls:
                        used.setdefault(cls, []).append(rel)

    if not used:
        return []

    findings: list[dict[str, Any]] = []
    style_target = ""
    for candidate in ("frontend/src/styles/index.css", "frontend/src/index.css", "src/styles/index.css", "src/index.css"):
        if (code_dir / candidate).is_file():
            style_target = candidate
            break

    tailwind_used = sorted(c for c in used if _TAILWIND_UTILITY_RE.match(c) and c not in defined)
    if tailwind_used and not has_tailwind:
        files_hit = sorted({f for c in tailwind_used for f in used[c]})
        findings.append(
            {
                "code": "tailwind_utilities_without_tailwind",
                "severity": "critical",
                "file": files_hit[0] if files_hit else (style_target or "package.json"),
                "classes": tailwind_used[:12],
                "detail": (
                    f"{len(tailwind_used)} Tailwind utility classes are used in the markup "
                    f"({', '.join(tailwind_used[:8])}) and this product has NO tailwindcss "
                    "dependency, no tailwind config and no @tailwind directives — so every one of "
                    "them styles nothing. The page renders as unstyled HTML no matter how correct "
                    "the components are, which is exactly what a person sees and a type checker "
                    "cannot. Pick ONE: either add tailwindcss (dependency + config + @tailwind "
                    f"directives in {style_target or 'the global stylesheet'}), or replace these "
                    "utility classes with the product's own semantic classes and write their rules."
                ),
            }
        )

    semantic_unstyled = sorted(
        c for c in used
        if c not in defined and not _TAILWIND_UTILITY_RE.match(c) and not c.startswith(("js-", "data-"))
    )
    # A couple of stragglers is noise; a third of the markup is a missing stylesheet.
    if len(semantic_unstyled) >= 8 and style_target:
        files_hit = sorted({f for c in semantic_unstyled for f in used[c]})
        findings.append(
            {
                "code": "unstyled_classes",
                "severity": "high",
                "file": style_target,
                "classes": semantic_unstyled[:12],
                "detail": (
                    f"{len(semantic_unstyled)} class names appear in the markup with no rule "
                    f"anywhere in the product's stylesheets ({', '.join(semantic_unstyled[:8])}). "
                    f"The components render, and they render unstyled. Add rules for them to "
                    f"{style_target} (or remove the class names if the elements are meant to "
                    f"inherit). Used in: {', '.join(files_hit[:3])}."
                ),
            }
        )
    return findings[:limit]


_TS_PKG_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import|export)\s[^\n;]*?from\s*['"]([^'".][^'"]*)['"]""",
)
# Bare specifiers that resolve without a dependency entry.
_TS_BUILTIN_PREFIXES = ("node:", "@/", "~/", "virtual:")


def find_undeclared_frontend_deps(code_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Packages the frontend imports but package.json never declares.

    `import axios from 'axios'` with no axios in dependencies compiles in an editor
    and dies as `TS2307: Cannot find module 'axios'` in the build — after install,
    so nothing earlier catches it.
    """
    import json as _json

    findings: list[dict[str, Any]] = []
    for pkg_file in iter_product_files(code_dir, "package.json"):
        try:
            manifest = _json.loads(pkg_file.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        declared = set()
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            block = manifest.get(field)
            if isinstance(block, dict):
                declared.update(block)
        root = pkg_file.parent
        seen: set[str] = set()
        for source in iter_product_files(root, "*"):
            if source.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                continue
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for spec in _TS_PKG_IMPORT_RE.findall(text):
                if spec.startswith(_TS_BUILTIN_PREFIXES):
                    continue
                # '@scope/name/sub' -> '@scope/name';  'axios/lib' -> 'axios'
                parts = spec.split("/")
                pkg = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
                if not pkg or pkg in declared or pkg in seen:
                    continue
                seen.add(pkg)
                findings.append(
                    {
                        "file": source.relative_to(code_dir).as_posix(),
                        "package": pkg,
                        "manifest": pkg_file.relative_to(code_dir).as_posix(),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings
