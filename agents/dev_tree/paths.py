"""Writing into a product safely: paths inside the code dir, deletions the developer asked for,
empty directories pruned, written files checked.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


def _resolve_safe_code_path(code_root: Path, file_path: str) -> Path | None:
    """Resolve an LLM-supplied file path under ``code_root``.

    Returns the resolved absolute path when it is a legitimate relative file that
    stays inside ``code_root``; returns ``None`` for absolute paths, ``..`` escapes,
    or anything whose resolved location lands outside ``code_root`` (guards against a
    write-anywhere primitive into data_root/secrets or the host filesystem).
    """
    raw = file_path.replace("\\", "/")
    # Findings carry files as `code/<product>/backend/...` and `/app/data/code/<product>/...`, and the
    # model echoes those paths back in its output. Taken literally, the write lands in a nested phantom
    # tree inside the product — measured live: a round wrote
    # `code/prod-bdb1634806de/backend/app/routers/auth.py`, the salvage pass had to remove it, and the
    # round's actual fix went nowhere. Strip the wrapper here, the one chokepoint every write, edit and
    # deletion passes through.
    root_name = code_root.name
    for wrapper in (
        f"/app/data/code/{root_name}/",
        f"data/code/{root_name}/",
        f"code/{root_name}/",
        f"{root_name}/",
    ):
        if raw.startswith(wrapper) and raw != wrapper:
            raw = raw[len(wrapper):]
            break
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    base_resolved = code_root.resolve()
    full_path = (code_root / raw).resolve()
    if full_path == base_resolved or not full_path.is_relative_to(base_resolved):
        return None
    return full_path


def _module_is_still_imported(
    code_root: Path,
    target: Path,
    *,
    ignore: set[Path],
) -> str | None:
    """Return the first surviving file that still imports *target*, if any.

    A delete list is model output: it removed a product's only auth hook and left
    every page importing a module that no longer existed. Deleting a file that
    something still references trades one broken build for a worse one, so the
    removal is refused and the finding stays until the importers are fixed.
    """
    from core.code_discovery import iter_product_files

    stem = target.stem
    if target.suffix == ".py":
        parts = list(target.relative_to(code_root).parts)
        while parts and parts[0] in ("backend", "server", "api", "src"):
            parts = parts[1:]
        parts[-1] = Path(parts[-1]).stem
        dotted = ".".join(parts)
        patterns = [
            re.compile(rf"^\s*from\s+{re.escape(dotted)}\s+import\b", re.M),
            re.compile(rf"^\s*import\s+{re.escape(dotted)}\b", re.M),
        ]
        def _counts(text: str) -> bool:
            return any(p.search(text) for p in patterns)

    else:
        # `from '../hooks/useAuth'`, `from "@/hooks/useAuth"`, `require('./useAuth')`
        spec_pattern = re.compile(
            rf"""(?:from|require\()\s*['"]([^'"]*\b{re.escape(stem)})['"]"""
        )
        parent_name = target.parent.name

        def _counts(text: str) -> bool:
            # Any specifier ending in the stem counts — EXCEPT one that names the exact-case
            # CASE-TWIN of the target's directory. In a case collision the twin exists by
            # construction, so counting its importers for the target makes the collision
            # un-deletable: measured live as "Refusing to delete UI/Toast.tsx: still imported
            # by App.tsx", where App.tsx imported ui/Toast — the keep side, on a filesystem
            # where those are different files.
            for spec in spec_pattern.findall(text):
                segs = [s for s in re.split(r"[/\\]", spec) if s and s not in (".", "..", "@")]
                if len(segs) < 2:
                    return True  # bare './Toast': cannot tell which twin is meant, stay safe
                spec_parent = segs[-2]
                if spec_parent == parent_name:
                    return True  # exact-case reference to the target's own directory
                if spec_parent.lower() != parent_name.lower():
                    return True  # some other module that happens to end in the stem
                twin_dir = target.parent.parent / spec_parent
                try:
                    siblings = {e.name for e in target.parent.parent.iterdir()}
                    twin_files = (
                        {e.name for e in twin_dir.iterdir()} if spec_parent in siblings else set()
                    )
                except OSError:
                    return True
                if spec_parent in siblings and target.name in twin_files:
                    continue  # refers to the existing twin, not to the target
                return True
            return False

    for candidate in iter_product_files(code_root, "*"):
        if candidate == target or candidate in ignore:
            continue
        if candidate.suffix.lower() not in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"):
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _counts(text):
            return candidate.relative_to(code_root).as_posix()
    return None


def _prune_empty_dirs(
    code_root: Path, *, log, product_id: str, only_below: list[str] | None = None
) -> list[str]:
    """Remove directories inside the product that contain no files at any depth.

    Deleting the last file in a directory used to leave the directory itself behind, and an empty
    directory is not harmless: measured live, ``components/UI/Toast.tsx`` was finally deleted after
    eleven rounds and the now-empty ``components/UI/`` kept the case collision alive next to
    ``components/ui/`` — with ``drop_files`` empty, because there was no longer any file to name. A
    blocking finding whose instruction is empty can never be executed, so the round count would
    have run out against a directory nobody could remove.

    Scoped to the ancestors of files this round actually deleted (``only_below``). A whole-tree
    sweep looked simpler and was wrong: it removed ``data/`` and ``backend/data/`` every round —
    directories the harness recreates and, on another product, ones an app expects to exist. A
    deletion's own housekeeping is the only empty directory this round is entitled to remove.
    """
    removed: list[str] = []
    root = code_root.resolve()

    if only_below is not None:
        candidates: list[Path] = []
        for rel in only_below:
            parent = (code_root / rel).parent
            while True:
                resolved = parent.resolve()
                if resolved == root or root not in resolved.parents:
                    break
                if parent not in candidates:
                    candidates.append(parent)
                parent = parent.parent
    else:
        candidates = [p for p in code_root.rglob("*") if p.is_dir()]

    for path in sorted(
        (p for p in candidates if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,  # deepest first, so a directory of empty directories also goes
    ):
        rel = path.relative_to(code_root).as_posix()
        if any(
            part in ("node_modules", ".git", ".aicom_sandbox", "dist", "build", ".next",
                     "__pycache__", ".venv", "preview-venv")
            for part in path.relative_to(code_root).parts
        ):
            continue
        try:
            resolved = path.resolve()
            if resolved == root or root not in resolved.parents:
                continue  # never step outside the product tree, never remove its root
            if any(child.is_file() for child in path.rglob("*")):
                continue
            path.rmdir()
        except OSError:
            continue
        removed.append(rel)
    if removed:
        log(
            "INFO",
            f"Pruned {len(removed)} empty director{'y' if len(removed) == 1 else 'ies'} for "
            f"{product_id}: {', '.join(removed[:6])}",
        )
    return removed


def _apply_requested_deletions(
    code_root: Path,
    requested: object,
    *,
    log,
    product_id: str,
    keep: set[str] | None = None,
) -> dict[str, str]:
    """Delete files the developer asked to remove, safely.

    Returns ``{path: previous content}`` so a rejected round can put them back.

    Same path guard as writes: nothing outside ``code_root``, no absolute paths, no
    ``..`` escapes. A path written in the same response wins over its deletion —
    that combination is a rename, not a removal. A module something else still
    imports is never removed.
    """
    if not isinstance(requested, (list, tuple)):
        return {}
    kept = keep or set()

    targets: list[tuple[str, Path]] = []
    for raw in requested:
        rel = str(raw or "").strip()
        if not rel or rel in kept:
            continue
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            log("WARNING", f"Skipping unsafe delete path for {product_id}: {rel!r}")
            continue
        if target.is_file():
            targets.append((rel, target))

    # Files going away together should not each other keep alive.
    doomed = {t for _, t in targets}

    removed: dict[str, str] = {}
    for rel, target in targets:
        importer = _module_is_still_imported(code_root, target, ignore=doomed)
        if importer:
            log(
                "WARNING",
                f"Refusing to delete {rel} for {product_id}: still imported by {importer}",
            )
            continue
        try:
            snapshot = target.read_text(encoding="utf-8", errors="replace")
            target.unlink()
        except OSError as exc:
            log("WARNING", f"Could not delete {rel} for {product_id}: {exc}")
            continue
        removed[rel] = snapshot
    if removed:
        log(
            "INFO",
            f"Removed {len(removed)} superseded file(s) for {product_id}: "
            f"{', '.join(list(removed)[:8])}",
        )
    return removed



def _self_check_written_files(
    code_root: Path,
    written: list[str],
    *,
    log,
    product_id: str,
) -> list[str]:
    """Dangling imports introduced by this round, checked in seconds not minutes.

    Only findings whose importer is a file this response wrote are reported — a
    pre-existing defect elsewhere is QA's business, not a reason to make the agent
    regenerate everything.
    """
    try:
        from web.backend.services.duplicate_module_check import (
            find_missing_symbols,
            find_undefined_names,
        )
    except Exception:
        return []
    try:
        missing = find_missing_symbols(code_root)
        undefined = find_undefined_names(code_root)
    except Exception as exc:
        log("WARNING", f"Self-check skipped for {product_id}: {exc}")
        return []
    mine = set(written)
    out: list[str] = []
    for item in undefined:
        if item.get("file") not in mine:
            continue
        out.append(
            f"{item['file']}:{item['line']} uses '{item['name']}' but never imports it"
        )
    for item in missing:
        # Two ways this round can be at fault, and the second was the common one:
        # rewriting security.py and dropping hash_password while five untouched
        # modules still import it. Only checking the importer side missed that
        # entirely, so the same defect kept regressing round after round.
        wrote_definer = item.get("file") in mine
        importers = [i for i in (item.get("importers") or []) if i in mine]
        if not wrote_definer and not importers:
            continue
        blamed = importers[0] if importers else (item.get("importers") or ["another module"])[0]
        out.append(f"{item['file']} does not define '{item['symbol']}' (imported by {blamed})")
    return out
