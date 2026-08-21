"""
Developer Agent
===============
Responsible for:
- Writing code based on architecture
- Implementing features
- Creating tests
- Code documentation

Delivery mode (web vs Python CLI) is inferred from admin_instructions and validated on disk.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path, PurePosixPath

from agents.prompt_utils import prompt_json
from agents.prompts.load_prompt import load_prompt
from core.logging_utils import log_suppressed
from core.repair_batches import (
    attach_file_contents,
    batch_instruction,
    batch_max_tokens,
    batching_enabled,
    plan_batches,
    unscoped_batch_max_files,
)

logger = logging.getLogger(__name__)

from llm import GenerationConfig, LLMRouter
from llm.agent_prompt_split import (
    build_developer_system_prompt,
    build_developer_user_data,
    format_user_data_message,
)
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_CODE_GENERATION_SEC
from web.backend.services.reference_templates import build_reference_template_prompt_block

from .base_agent import AgentInput, AgentOutput, BaseAgent
from .dev_edits import EDIT_CONTRACT_PROMPT, apply_edits
from .dev_delivery import (
    DeliveryMode,
    desktop_app_appendix,
    full_software_browser_appendix,
    infer_delivery_mode,
    infer_desktop_stack,
    system_prompt_for_mode,
    validate_saved_files,
)
from .product_profile import DESKTOP_APP, FULL_SOFTWARE, normalize_delivery_profile

DEV_CORE_PROMPT = load_prompt("developer_core_prompt.md")


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




def _tree_defect_breakdown(code_root: Path) -> dict[str, int]:
    """Per-detector counts behind ``_tree_defect_score``, for saying WHAT changed.

    "Static defects would rise 30 → 52; tree restored" is a true sentence that answers nothing. Two
    consecutive nine-file rounds were discarded on it, and from the total alone there is no way to
    tell a round that broke the tree from a detector that is wrong about the round — which matters
    most exactly when a detector is new. The breakdown is logged on rejection so the next look starts
    from a name rather than a guess.
    """
    from core.code_discovery import iter_product_files

    out: dict[str, int] = {}
    try:
        from web.backend.services import duplicate_module_check as d
    except Exception:
        return out
    checks = {
        "missing_symbol": lambda: d.find_missing_symbols(code_root, limit=500),
        "missing_module": lambda: d.find_missing_modules(code_root, limit=200),
        "missing_attribute": lambda: d.find_missing_instance_attributes(code_root, limit=200),
        "unexpected_keyword": lambda: d.find_unexpected_keyword_arguments(code_root, limit=200),
        "class_body_forward_ref": lambda: d.find_class_body_forward_refs(code_root, limit=200),
        "duplicated_router_prefix": lambda: d.find_duplicated_router_prefix(code_root, limit=200),
        "frontend_missing_export": lambda: d.find_frontend_missing_exports(code_root, limit=200),
        "mismatched_back_populates": lambda: d.find_mismatched_back_populates(code_root, limit=200),
        "api_route_shadows_spa": lambda: d.find_api_routes_shadowing_spa(code_root, limit=200),
        "case_collision": lambda: d.find_case_collisions(code_root, limit=200),
        "dead_path_rewrite": lambda: d.find_dead_path_rewrites(code_root, limit=200),
        "orm_schema_never_created": lambda: d.find_orm_schema_never_created(code_root, limit=200),
        "undeclared_dependency": lambda: d.find_undeclared_dependencies(code_root, limit=200),
        "unstyled_markup": lambda: d.find_unstyled_classes(code_root, limit=200),
        "capability_never_invoked": lambda: d.find_capabilities_never_invoked(code_root, limit=200),
        "sync_wrapper_over_async": lambda: d.find_sync_wrapper_over_async_handler(code_root, limit=200),
        "undefined_name": lambda: d.find_undefined_names(code_root, limit=500),
        "frontend_import": lambda: d.find_unresolved_frontend_imports(code_root, limit=200),
        "unregistered_model": lambda: d.find_unregistered_models(code_root),
        "hallucinated_import": lambda: d.find_hallucinated_imports(code_root),
        "undeclared_dep": lambda: d.find_undeclared_frontend_deps(code_root),
        "broken_injection": lambda: d.find_route_handlers_with_broken_injection(code_root),
        "duplicate_tablename": lambda: d.find_duplicate_tablenames(code_root),
        "mesh_contract": lambda: d.find_mesh_contract_violations(code_root),
    }
    for name, fn in checks.items():
        try:
            found = fn() or []
        except Exception:
            continue
        if found:
            out[name] = len(found)
    unparseable = 0
    import ast as _ast

    for path in iter_product_files(code_root, "*.py"):
        try:
            _ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            unparseable += 1
        except (OSError, ValueError):
            continue
    if unparseable:
        out["unparseable"] = unparseable
    return out


def _tree_defect_identities(code_root: Path) -> dict[str, set[str]]:
    """Which defects, not how many — ``frontend_import`` -> {"Dashboard.tsx -> ./AnalyticsWorkspace"}.

    A count answers "something in this class moved" and then stops. Three rounds in a row were
    rejected on ``frontend_import 0→3`` and ``0→5``, which is enough to know where to look and not
    enough to know whether the round wrote a bad import or the detector is wrong about a good one.
    Naming them settles it in one reading, and it is the same question that made counts worth logging
    in the first place, one level down.

    Run only when a round is being rejected, so the extra pass costs nothing in the happy path.
    """
    out: dict[str, set[str]] = {}
    try:
        from web.backend.services import duplicate_module_check as d
    except Exception:
        return out

    def take(name: str, items, ident):
        try:
            found = list(items() or [])
        except Exception:
            return
        if found:
            out[name] = {ident(i) for i in found}

    take(
        "missing_symbol",
        lambda: d.find_missing_symbols(code_root, limit=500),
        lambda i: f"{i.get('module')}.{i.get('symbol')}",
    )
    take(
        "missing_module",
        lambda: d.find_missing_modules(code_root, limit=200),
        lambda i: str(i.get("module")),
    )
    take(
        "missing_attribute",
        lambda: d.find_missing_instance_attributes(code_root, limit=200),
        lambda i: f"{i.get('singleton')}.{i.get('attribute')}",
    )
    take(
        "unexpected_keyword",
        lambda: d.find_unexpected_keyword_arguments(code_root, limit=200),
        lambda i: f"{i.get('file')}:{i.get('method')} {i.get('keyword')}",
    )
    take(
        "dead_path_rewrite",
        lambda: d.find_dead_path_rewrites(code_root, limit=200),
        lambda i: f"{i.get('file')}:{i.get('line')} {i.get('source')} -> {i.get('target')}",
    )
    take(
        "sync_wrapper_over_async",
        lambda: d.find_sync_wrapper_over_async_handler(code_root, limit=200),
        lambda i: f"{i.get('decorator')} over {i.get('handler')}",
    )
    take(
        "capability_never_invoked",
        lambda: d.find_capabilities_never_invoked(code_root, limit=200),
        lambda i: f"{i.get('file')}: {len(i.get('capabilities') or [])} capability(ies)",
    )
    take(
        "unstyled_markup",
        lambda: d.find_unstyled_classes(code_root, limit=200),
        lambda i: f"{i.get('code')}: {len(i.get('classes') or [])} class(es)",
    )
    take(
        "undeclared_dependency",
        lambda: d.find_undeclared_dependencies(code_root, limit=200),
        lambda i: f"{i.get('import_root')} -> {i.get('package')}",
    )
    take(
        "orm_schema_never_created",
        lambda: d.find_orm_schema_never_created(code_root, limit=200),
        lambda i: f"{i.get('file')}: {len(i.get('tables') or [])} table(s) never created",
    )
    take(
        "case_collision",
        lambda: d.find_case_collisions(code_root, limit=200),
        lambda i: f"{i.get('parent')}: {' vs '.join(i.get('spellings') or [])}",
    )
    take(
        "api_route_shadows_spa",
        lambda: d.find_api_routes_shadowing_spa(code_root, limit=200),
        lambda i: f"{i.get('method')} {i.get('path')} in {i.get('file')}",
    )
    take(
        "mismatched_back_populates",
        lambda: d.find_mismatched_back_populates(code_root, limit=200),
        lambda i: f"{i.get('class')}.{i.get('attr')} expects {i.get('target')}.{i.get('expected')}",
    )
    take(
        "frontend_missing_export",
        lambda: d.find_frontend_missing_exports(code_root, limit=200),
        lambda i: f"{i.get('importer')} wants {i.get('name')} from {i.get('file')}",
    )
    take(
        "duplicated_router_prefix",
        lambda: d.find_duplicated_router_prefix(code_root, limit=200),
        lambda i: f"{i.get('file')} {i.get('prefix')}",
    )
    take(
        "class_body_forward_ref",
        lambda: d.find_class_body_forward_refs(code_root, limit=200),
        lambda i: f"{i.get('file')}:{i.get('line')} {i.get('name')}",
    )
    take(
        "frontend_import",
        lambda: d.find_unresolved_frontend_imports(code_root, limit=200),
        lambda i: f"{i.get('file')} -> {i.get('import')}",
    )
    take(
        "undefined_name",
        lambda: d.find_undefined_names(code_root, limit=500),
        lambda i: f"{i.get('file')}:{i.get('name')}",
    )
    take(
        "duplicate_tablename",
        lambda: d.find_duplicate_tablenames(code_root),
        lambda i: str(i.get("table")),
    )
    take(
        "hallucinated_import",
        lambda: d.find_hallucinated_imports(code_root),
        lambda i: f"{i.get('file')}:{i.get('name') or i.get('symbol')}",
    )
    return out


def _identities_appeared(
    before: dict[str, set[str]], after: dict[str, set[str]], limit: int = 6
) -> str:
    """The defects this round added, by name."""
    lines: list[str] = []
    for cls in sorted(set(before) | set(after)):
        fresh = sorted(after.get(cls, set()) - before.get(cls, set()))
        if fresh:
            shown = ", ".join(fresh[:limit])
            more = f" (+{len(fresh) - limit} more)" if len(fresh) > limit else ""
            lines.append(f"{cls}: {shown}{more}")
    return "; ".join(lines)


def _breakdown_delta(before: dict[str, int], after: dict[str, int]) -> str:
    """`missing_attribute 2→4, duplicate_tablename 1→2` — only what moved."""
    moved = [
        f"{k} {before.get(k, 0)}\u2192{after.get(k, 0)}"
        for k in sorted(set(before) | set(after))
        if before.get(k, 0) != after.get(k, 0)
    ]
    return ", ".join(moved) or "nothing individually — check the weights"


def _tree_defect_score(code_root: Path) -> int | None:
    """Static defects in the tree right now: unresolvable imports and unbound names.

    Cheap enough to run twice per round, and it is the same signal QA blocks on,
    so "did this round make things worse" is answerable before handing off.
    """
    import ast

    from core.code_discovery import iter_product_files

    try:
        from web.backend.services.duplicate_module_check import (
            find_class_body_forward_refs,
            find_duplicated_router_prefix,
            find_frontend_missing_exports,
            find_api_routes_shadowing_spa,
            find_case_collisions,
            find_dead_path_rewrites,
            find_mismatched_back_populates,
            find_missing_instance_attributes,
            find_unexpected_keyword_arguments,
            find_missing_modules,
            find_missing_symbols,
            find_undefined_names,
            find_hallucinated_imports,
            find_duplicate_tablenames,
            find_orm_schema_never_created,
            find_undeclared_dependencies,
            find_capabilities_never_invoked,
            find_sync_wrapper_over_async_handler,
            find_mesh_contract_violations,
            find_route_handlers_with_broken_injection,
            find_undeclared_frontend_deps,
            find_unregistered_models,
            find_unresolved_frontend_imports,
        )

        # A file that does not parse must dominate this score. The name check skips
        # unparseable files by design, so without this a round that breaks the parser
        # scores *better* — fewer readable files, fewer detectable defects — and the
        # guard waves it through. That is exactly how a SyntaxError in main.py landed.
        unparseable = 0
        for path in iter_product_files(code_root, "*.py"):
            try:
                ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                unparseable += 1
            except (OSError, ValueError):
                continue

        return (
            # Weighted like every other defect that stops the app from importing, because that is
            # what it is: `from .advisory import CachedMeshReading` for a name nothing defines is an
            # ImportError at boot, exactly as fatal as a missing module or two models on one table.
            #
            # It sat at weight 1 while those sat at 10, and the consequence was watched live: a round
            # fixed ONE missing attribute (-10) and introduced NINE missing symbols (+9), came out at
            # 29 against 30, and was accepted as an improvement. Nine fresh ImportErrors bought with
            # one fix. A scoring scheme that permits that trade is not measuring what it claims to.
            10 * len(find_missing_symbols(code_root, limit=500))
            + len(find_undefined_names(code_root, limit=500))
            + 10 * unparseable
            # Python-only scoring let a round fix one backend symbol while deleting
            # half the frontend and still read as an improvement.
            + len(find_unresolved_frontend_imports(code_root, limit=200))
            # The score must count everything the agent is asked to fix. While
            # unregistered models were excluded, a round that fixed them scored no
            # better, so any incidental cost made it look like a regression and the
            # fix was rolled back — the agent could not land it however hard it tried.
            + len(find_unregistered_models(code_root))
            # A nonexistent framework name fails at import time and takes the app
            # down; without it in the score a round could introduce one and still
            # look like progress. One did: JavaScriptResponse. Same consequence as the rest of the
            # import-time family, so the same weight.
            + 10 * len(find_hallucinated_imports(code_root))
            + len(find_undeclared_frontend_deps(code_root))
            # A route handler FastAPI cannot call 500s on every request while the tree
            # imports cleanly and every symbol resolves — invisible to everything else in
            # this score. Weighted heavily: one of these is a dead endpoint, and a product
            # whose only feature is one endpoint is simply dead.
            + 5 * len(find_route_handlers_with_broken_injection(code_root))
            # Two models on one table stop the app from booting at all, so every
            # endpoint is unreachable — the most expensive defect per line there is.
            + 10 * len(find_duplicate_tablenames(code_root))
            # A product that calls our own economy with the wrong envelope answers
            # 200 with no data forever: every gate green, the feature dead.
            + 5 * len(find_mesh_contract_violations(code_root))
            # An import of a module that exists nowhere raises ModuleNotFoundError before
            # anything else runs, so the app never starts. This score was blind to it in the
            # same way the QA gate was, and the blindness had teeth: deleting a brand-new file
            # that an in-scope edit had just started importing cost the score nothing, so the
            # scope guard removed it and the round then failed its own coherence check.
            + 10 * len(find_missing_modules(code_root, limit=200))
            # An attribute its class never declares is an AttributeError on the line's first run;
            # for module-level code that is import time and the app never starts.
            + 10 * len(find_missing_instance_attributes(code_root, limit=200))
            # Call site kwargs the method does not declare: TypeError on first run, swallowed
            # into UNKNOWN 200 by except Exception. The Vercel page looked honest.
            + 10 * len(find_unexpected_keyword_arguments(code_root, limit=200))
            # A class body runs top to bottom at import, so a forward reference in one is a NameError
            # before the first route is registered. It was invisible to every check here, and that
            # deadlocked a product: with the score at zero, the fix measured as no improvement and the
            # guard gave it back three rounds running.
            + 10 * len(find_class_body_forward_refs(code_root, limit=200))
            # A prefix applied twice serves every route in that router at a path nothing asks for. The
            # app boots and answers, so this is the mesh-contract shape: green everywhere, feature dead.
            # It cost four rounds as a "broken login handler" and a browser crawl that saw API JSON at
            # the root, because the catch-all swallowed both.
            + 5 * len(find_duplicated_router_prefix(code_root, limit=200))
            # The TypeScript twin of missing_symbol. Without it the score read ZERO across the whole
            # frontend, so a refactor of the API layer plus its five importers was dismembered by the
            # salvage pass on a 0-vs-0 coin flip, three rounds running — the plateau in one line.
            + 5 * len(find_frontend_missing_exports(code_root, limit=200))
            # A mismatched back_populates pair kills the app on its first query — boot-fatal in
            # effect, invisible to every import-level check, and it sent two rounds to guess in
            # deps.py while both halves of the defect sat in the models.
            + 10 * len(find_mismatched_back_populates(code_root, limit=200))
            # A JSON route outside /api shadows the SPA catch-all: navigating browsers get 405 or raw
            # JSON instead of the app shell. Three costumes of one bug all night — /login as JSON, the
            # root as JSON, GET /dashboards as an unexplained 405 — and two rounds guessed in App.tsx
            # because the console error names no path.
            + 5 * len(find_api_routes_shadowing_spa(code_root, limit=200))
            # Same name in two casings refuses the whole TS tree (TS1149): build-fatal.
            + 5 * len(find_case_collisions(code_root, limit=200))
            # A middleware rewriting a live path onto a dead one kills the endpoint while every schema
            # says it exists — rounds edited the innocent router for hours.
            + 10 * len(find_dead_path_rewrites(code_root, limit=200))
            # Tables declared and never created: every DB request is a 500 the browser reports with
            # no path in it, and four rounds edited a correct login handler because of it.
            + 10 * len(find_orm_schema_never_created(code_root, limit=200))
            # An import no dependency file declares works in the sandbox and dies in every clean
            # install: the Vercel deploy served 200 on the page and FUNCTION_INVOCATION_FAILED on
            # every API route, because `import jwt` had no PyJWT behind it.
            + 10 * len(find_undeclared_dependencies(code_root, limit=200))
            # Unstyled markup is a real QA finding, but it must not vote on rollback.
            # Measured on Sentinel: QA asked for landing CSS; the round wrote the widget
            # plus one Tailwind token (`text-muted`) and eight semantic class names.
            # That scored +5 / +10, salvage could not keep any landing file (every
            # written file fed the same finding), the tree went back to zero, and the
            # next round was asked for the same files. Three attempts, zero UI landed.
            # Keep the detector in module health; strip utilities after the write.
            # A round that deletes the call instead of fixing it satisfies every finding about that
            # call and destroys the product: the advisory endpoint went from crashing on a missing
            # client method to returning "integration pending", and Sentinel stopped asking ATLAS
            # anything at all.
            + 10 * len(find_capabilities_never_invoked(code_root, limit=200))
            # A sync wrapper over an async handler answers every request with a coroutine object:
            # 500 on that route, a traceback that blames the response model, and a handler that is
            # perfectly correct. Three rounds looked at the router and the schema.
            + 10 * len(find_sync_wrapper_over_async_handler(code_root, limit=200))
        )
    except Exception:
        return None




def _revert_out_of_scope_writes(
    code_root: Path,
    previous_content: dict[str, str],
    written: list[str],
    scope: list[str],
    *,
    log,
    product_id: str,
    findings_text: str = "",
) -> set[str]:
    """Undo edits outside the half of the product that actually needs repair.

    A round rewrites the whole tree whatever the prompt says. When the backend is
    green and only the frontend fails, that is forty-odd chances to lose a working
    backend while fixing a page — and it happened repeatedly. Writes outside the
    scope are restored to their previous content; genuinely new files outside it
    are removed.
    """
    if not scope:
        return set()
    # A scope entry is either a directory ("backend/") or an exact file
    # ("backend/app/services/atlas_client.py"). Treating both as prefixes turned a file entry
    # into "…atlas_client.py/", which matches nothing — so a file-level scope would have
    # reverted every write including the one file it was meant to allow, i.e. every round would
    # land empty. QA now emits file-level scopes when the blocking defects name few enough
    # files, so this distinction is load-bearing rather than theoretical.
    scope_text = str(findings_text or "")
    exact = {s.strip("/") for s in scope if s and Path(s).suffix}
    prefixes = tuple(s.strip("/") + "/" for s in scope if s and not Path(s).suffix)
    if not exact and not prefixes:
        return set()

    # A scope limit that makes the tree worse is not a limit, it is a bug. Watched live, twice in
    # a row with identical numbers: QA scoped a round to audit.py, advisory.py and cache.py; the
    # round wrote those three and also deps.py and Dashboard.tsx, which import the symbols it had
    # just moved. Reverting the two importers left the definitions in place and their callers
    # rolled back, so static defects rose 16 → 24, the developer's own check rejected the round,
    # and the next attempt reproduced it exactly. Every attempt burned that way.
    #
    # So each candidate revert is measured. A file whose revert makes the tree worse is a
    # necessary companion of the in-scope change and its write is kept; a file whose revert costs
    # nothing is out-of-scope sprawl and goes. Greedy and in sorted order, so the same round always
    # produces the same answer.
    # A file the DIAGNOSIS asked for is in scope by definition. The scope is built from the files
    # blocking defects name, and a finding like "GITHUB_HOUSE_CONTRACT not satisfied: missing
    # required repository files" names files that do not exist yet — so they can never appear in a
    # scope derived from the tree. Measured: a round created .github/workflows/ci.yml,
    # release.yml, CHANGELOG.md, LICENSE and README.md, exactly as instructed, and all five were
    # reverted as sprawl because the scope read ["frontend/src/components/UI/Toast.tsx"]. The
    # finding then survived to the next round, which created them again. A requirement whose
    # fulfilment is structurally undoable is a treadmill.
    wanted_by_findings = {
        rel
        for rel in written
        if rel not in previous_content and rel in scope_text
    }

    candidates = [
        rel
        for rel in written
        if not (
            rel in exact
            or (prefixes and rel.startswith(prefixes))
            or rel in wanted_by_findings
        )
    ]
    if wanted_by_findings:
        log(
            "INFO",
            f"Keeping {len(wanted_by_findings)} new file(s) for {product_id} that the findings ask "
            f"for by name: {', '.join(sorted(wanted_by_findings)[:6])}",
        )
    current = _tree_defect_score(code_root) if candidates else None

    reverted: set[str] = set()
    kept_for_coherence: list[str] = []
    for rel in sorted(candidates):
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            continue
        was_new = rel not in previous_content
        try:
            written_back = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
        except OSError:
            written_back = None
        try:
            if not was_new:
                target.write_text(previous_content[rel], encoding="utf-8")
            elif target.is_file():
                target.unlink()
            else:
                continue
        except OSError:
            continue

        after = _tree_defect_score(code_root) if current is not None else None
        if current is not None and after is not None and after > current:
            # Undo the revert: this write is load-bearing for the in-scope repair.
            try:
                if written_back is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(written_back, encoding="utf-8")
                    kept_for_coherence.append(rel)
                    continue
            except OSError:
                pass
        if after is not None:
            current = after
        reverted.add(rel)
    if kept_for_coherence:
        log(
            "INFO",
            f"Kept {len(kept_for_coherence)} out-of-scope edit(s) for {product_id} because "
            f"reverting them made the tree worse: {', '.join(sorted(kept_for_coherence)[:6])}",
        )
    if reverted:
        log(
            "WARNING",
            f"Reverted {len(reverted)} out-of-scope edit(s) for {product_id} "
            f"(round scoped to {', '.join(scope)}): {', '.join(sorted(reverted)[:6])}",
        )
    return reverted


def _revert_until_not_worse(
    code_root: Path,
    previous_content: dict[str, str],
    written: list[str],
    *,
    before_score: int,
    log,
    product_id: str,
    already: set[str],
) -> set[str]:
    """Give back the fewest files that stop the round being a regression.

    A round is judged whole, and that is why a good round kept being thrown away. Measured twice in six
    minutes on a tree that had reached zero defects:

        Applied 9 edit(s) across 6 file(s): advisory.ts, Dashboard.tsx, AnalyticsDashboard.tsx,
                                            PublicWidget.tsx, test_cache.py, test_atlas_client.py
        Rejected: what moved — missing_attribute 0→1 | added: missing_attribute: atlas_client.invoke
        Rejected: static defects would rise 0 → 10; tree restored

    Three of those edits are the three tsc errors the round was sent to fix. They score **nothing** in
    this measure — type errors come from an npm build, far too slow to run twice a round — while the one
    backend attribute it broke scores ten. So a round doing exactly the work it was asked for cannot
    come out ahead, and the frontend can never be fixed by a round that touches the backend at all.

    Reverting file by file, keeping each revert only while it helps, salvages the work that was right.
    Greedy and in sorted order so one round always produces one answer, and it stops as soon as the tree
    is no longer worse than it was — the goal is to land the round, not to find a minimum.
    """
    candidates = [rel for rel in sorted(set(written)) if rel not in already]
    if not candidates:
        return set()
    current = _tree_defect_score(code_root)
    if current is None or current <= before_score:
        return set()

    reverted: set[str] = set()
    for rel in candidates:
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            continue
        was_new = rel not in previous_content
        try:
            kept = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
            if was_new:
                if target.is_file():
                    target.unlink()
            else:
                target.write_text(previous_content[rel], encoding="utf-8")
        except OSError:
            continue

        after = _tree_defect_score(code_root)
        if after is None or after >= current:
            # This file was not the problem: put it back and keep looking.
            try:
                if kept is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(kept, encoding="utf-8")
            except OSError:
                pass
            continue
        current = after
        reverted.add(rel)
        if current <= before_score:
            break

    if reverted:
        log(
            "INFO",
            f"Salvaged the repair round for {product_id} by giving back {len(reverted)} file(s): "
            f"{', '.join(sorted(reverted)[:6])} — the rest of the round stands ({current} vs "
            f"{before_score} before).",
        )
    return reverted


def _revert_files_with_new_undefined_names(
    code_root: Path,
    previous_content: dict[str, str],
    *,
    log,
    product_id: str,
    already: set[str],
) -> set[str]:
    """Revert just the files this round left with an unbound name.

    Rejecting a whole round for a one-point backend regression also discards the
    frontend work that round did — and one product stalled exactly there, its
    backend clean at zero while every attempt at the remaining UI defects was
    thrown away with the bad edit. Reverting the specific offenders first keeps
    the good half.
    """
    from web.backend.services.duplicate_module_check import (
        find_undefined_names,
        undefined_names_in_source,
    )

    reverted: set[str] = set()
    try:
        undefined = find_undefined_names(code_root, limit=200)
    except Exception:
        return reverted
    for item in undefined:
        rel = str(item.get("file") or "")
        if rel not in previous_content or rel in already or rel in reverted:
            continue
        # Only a regression if the previous version bound the name. Substring
        # matching gets this exactly backwards: the old text containing the name
        # is what a binding looks like.
        was_unbound = {n for n, _ in undefined_names_in_source(previous_content[rel])}
        if item.get("name") in was_unbound:
            continue
        target = _resolve_safe_code_path(code_root, rel)
        if target is None:
            continue
        try:
            target.write_text(previous_content[rel], encoding="utf-8")
        except OSError:
            continue
        reverted.add(rel)
        log(
            "WARNING",
            f"Reverted {rel} for {product_id}: the rewrite left '{item.get('name')}' unbound",
        )
    return reverted


def _revert_symbol_regressions(
    code_root: Path,
    previous_content: dict[str, str],
    *,
    log,
    product_id: str,
) -> set[str]:
    """Undo writes that removed a symbol other modules still import.

    Measured on a live rework: the developer rewrote 84-91 files per round to fix
    ten findings. Whole-file regeneration is how `hash_password` disappeared from
    security.py three separate times while five untouched modules imported it —
    each round "fixed" the finding and reintroduced it.

    A repair round is allowed to change anything except the contract other files
    depend on. When a rewritten module drops such a symbol, its previous content
    is restored and the finding is left for the next round to address honestly.
    """
    from web.backend.services.duplicate_module_check import find_missing_symbols

    reverted: set[str] = set()
    # Scan uncapped: the human-facing report stops at ten findings, but a round
    # that strips twenty symbols would then get only ten of them protected and
    # ship the rest. Re-scan after each pass — restoring one module can resolve
    # several findings at once, and can reveal others behind them.
    for _ in range(3):
        try:
            missing = find_missing_symbols(code_root, limit=500)
        except Exception as exc:
            log("WARNING", f"Regression check skipped for {product_id}: {exc}")
            return reverted

        progressed = False
        for item in missing:
            rel = str(item.get("file") or "")
            if rel not in previous_content or rel in reverted:
                continue
            # Only roll back when the symbol used to be there — a symbol that never
            # existed is a genuine new finding, not a regression.
            if item.get("symbol") not in previous_content[rel]:
                continue
            target = _resolve_safe_code_path(code_root, rel)
            if target is None:
                continue
            try:
                target.write_text(previous_content[rel], encoding="utf-8")
            except OSError as exc:
                log("WARNING", f"Could not restore {rel} for {product_id}: {exc}")
                continue
            reverted.add(rel)
            progressed = True
            log(
                "WARNING",
                f"Reverted {rel} for {product_id}: the rewrite dropped "
                f"'{item.get('symbol')}', which other modules import",
            )
        if not progressed:
            break
    return reverted


def _load_developer_investigation_brief(data_root: Path, product_id: str) -> str:
    """Analyst-authored handoff stored in state/{product_id}/market_research.json."""
    path = data_root / "state" / product_id / "market_research.json"
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    inner = raw.get("market_research")
    if isinstance(inner, dict):
        text = inner.get("developer_investigation_brief")
    else:
        text = raw.get("developer_investigation_brief")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""


class DeveloperAgent(BaseAgent):
    """Developer Agent - writes code from architecture designs."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="developer",
            llm_router=llm_router,
            task_type="code_generation",
        )


    async def _generate_repair_batches(
        self,
        *,
        prompt: str,
        batches: list[dict],
        base_config,
        agent_input,
        system_prompt: str,
        product_id: str,
        code_root: Path,
    ) -> dict | None:
        """Run one generation per batch and merge the files. Returns a code_data-shaped dict.

        A batch that fails is skipped rather than failing the round: the batches are ordered so
        the defects that stop the product working come first, and landing two of three fixes is
        a round that moved. A single call that dies takes the whole round with it, which is what
        made a transient non-JSON response cost twenty minutes.

        Later batches see what earlier ones wrote, because they are separate calls against the
        same tree — so a batch fixing a caller after another fixed the callee reads the new
        signature rather than guessing it.
        """
        from llm import GenerationConfig

        merged: dict[str, dict] = {}
        # Edits are collected across batches, not merged by path: two batches may each change a
        # different part of the same file, and that is the normal case now that a batch prefers an
        # edit over a rewrite. Keying them by path would silently drop one of the two.
        merged_edits: list[dict] = []
        merged_deletions: list[str] = []
        notes: list[str] = []
        total = len(batches)
        for index, batch in enumerate(batches):
            batch_prompt = (
                f"{prompt}\n\n"
                f"{batch_instruction(batch, index, total, attach_file_contents(batch, code_root))}\n"
            )
            config = GenerationConfig(
                temperature=base_config.temperature,
                # The mechanism: an allowance sized for a handful of files.
                max_tokens=batch_max_tokens(),
                timeout_sec=base_config.timeout_sec,
                json_mode=True,
            )
            try:
                response = await self._generate(
                    batch_prompt,
                    config=config,
                    agent_input=agent_input,
                    system_prompt=system_prompt,
                )
            except Exception as exc:  # noqa: BLE001
                self._log("WARNING", f"Repair batch {index + 1}/{total} failed to generate: {exc}")
                continue
            data = self._extract_json(response)
            if not isinstance(data, dict):
                self._log(
                    "WARNING",
                    f"Repair batch {index + 1}/{total} returned no usable JSON; skipping it",
                )
                continue
            files = data.get("files") or []
            wrote = 0
            dropped = 0
            unsound = 0
            # An unscoped batch has no path restriction, so its only limit is this count. On the
            # first live batched rounds it returned 19 and 21 files while its scoped siblings
            # returned 3 and 1 — three quarters of the round, from the batch nobody bounded.
            limit = None if (batch.get("files") or []) else unscoped_batch_max_files()
            for item in files if isinstance(files, list) else []:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                if not path or not item.get("content"):
                    continue
                if limit is not None and wrote >= limit and path not in merged:
                    dropped += 1
                    continue
                # Check the batch BEFORE it joins the round. The module docstring promised the
                # damage from a bad batch would be one batch wide; without this it was a whole
                # round wide — one batch of six raised static defects 15 -> 20 and the round
                # was rejected in full, discarding five good batches with it. Checked on the
                # content rather than on disk, because writing here would make the main loop's
                # rollback baseline the previous attempt's output.
                if str(path).endswith(".py"):
                    # A file that does not parse is not a repair, and the most common way to get one
                    # is a response that ran out of room. Measured: a batch returned three whole files
                    # against a 24k-token output cap and the last one stopped mid-def —
                    # "Incomplete function definition causes SyntaxError in app/deps.py" — which then
                    # counted against the round and cost it everything. Truncation is not the model
                    # being wrong; it is us asking for more than the answer could hold, and writing
                    # the fragment is the one response that makes it worse.
                    _content = str(item.get("content") or "")
                    try:
                        import ast as _ast

                        _ast.parse(_content)
                    except SyntaxError as _syn:
                        unsound += 1
                        self._log(
                            "WARNING",
                            f"Repair batch {index + 1}/{total}: dropping {path} — it does not parse "
                            f"({_syn.msg} at line {_syn.lineno}). Most likely the response was cut "
                            "off; a truncated file is worse than no file.",
                        )
                        continue
                    try:
                        from web.backend.services.duplicate_module_check import (
                            undefined_names_in_source,
                        )

                        loose = undefined_names_in_source(_content)
                    except Exception:
                        loose = []
                    if loose:
                        unsound += 1
                        self._log(
                            "WARNING",
                            f"Repair batch {index + 1}/{total}: dropping {path} — uses "
                            + ", ".join(f"'{n}'" for n, _ in loose[:4])
                            + " without binding or importing them",
                        )
                        continue
                # A later batch legitimately supersedes an earlier one for the same file.
                merged[path] = item
                wrote += 1
            if dropped:
                self._log(
                    "WARNING",
                    f"Repair batch {index + 1}/{total}: dropped {dropped} file(s) beyond the "
                    f"unscoped cap of {limit} — the batch was asked for the few that matter",
                )
            if unsound:
                self._log(
                    "WARNING",
                    f"Repair batch {index + 1}/{total}: {unsound} file(s) rejected for unbound "
                    "names; the rest of the round is unaffected",
                )
            for edit in data.get("edits") or []:
                if not isinstance(edit, dict):
                    continue
                rel = str(edit.get("path") or "").strip()
                scope = batch.get("files") or []
                # An edit outside the batch's files is kept, and this is a correction of the rule I
                # wrote an hour earlier. It cost the very first live round: batch 1 produced an edit
                # to models/audit.py — where the duplicate table actually lives — and the hard drop
                # threw it away before anything could measure it.
                #
                # The batch scope exists to stop sprawl, and sprawl is a property of REWRITES: a
                # rewritten file is retyped in full and can lose anything in it. An edit changes the
                # bytes it names and nothing else, so it is the safer of the two and cannot deserve
                # the stricter rule. The round-level guard already measures every out-of-scope write
                # and keeps the ones whose removal makes the tree worse — edited paths join that
                # list, so they get judged rather than discarded.
                if scope and rel not in scope:
                    self._log(
                        "INFO",
                        f"Repair batch {index + 1}/{total}: keeping an edit to {rel or '(no path)'} "
                        "outside this batch's files — the round guard measures it",
                    )
                if edit not in merged_edits:
                    merged_edits.append(edit)
            # delete_files must survive the merge. Measured: the batch scoped to the case
            # collision answered exactly as its finding instructed — delete UI/Toast.tsx — and
            # the merge returned only files/edits/notes, so the round logged "returned 0
            # rewrite(s) and 0 edit(s)" and the collision outlived its tenth informed round.
            for _del in data.get("delete_files") or []:
                _rel = str(_del or "").strip()
                if _rel and _rel not in merged_deletions:
                    merged_deletions.append(_rel)
            if data.get("notes"):
                notes.append(f"batch {index + 1}: {str(data['notes'])[:400]}")
            self._log(
                "INFO",
                f"Repair batch {index + 1}/{total} for {product_id}: asked for "
                f"{len(batch.get('files') or []) or 'unscoped'} file(s), returned {wrote} rewrite(s), "
                f"{len([e for e in (data.get('edits') or []) if isinstance(e, dict)])} edit(s) "
                f"and {len(data.get('delete_files') or [])} deletion(s)",
            )

        if not merged and not merged_edits and not merged_deletions:
            return None
        self._log(
            "INFO",
            f"Repair batches merged for {product_id}: {len(merged)} file(s), "
            f"{len(merged_edits)} edit(s) and {len(merged_deletions)} deletion(s) across "
            f"{total} batch(es)",
        )
        return {
            "files": list(merged.values()),
            "edits": merged_edits,
            "delete_files": merged_deletions,
            "notes": " | ".join(notes),
        }


    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        architecture = agent_input.data.get("architecture", {})
        spec = agent_input.data.get("specification", {})
        admin_instructions = (agent_input.data.get("admin_instructions") or "").strip()
        idea = (agent_input.data.get("idea") or "").strip()
        category = (agent_input.data.get("category") or "").strip()
        tags = agent_input.data.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        if not isinstance(spec, dict):
            spec = {}
        if not isinstance(architecture, dict):
            architecture = {}

        raw_dp = agent_input.data.get("delivery_profile")
        dprof = normalize_delivery_profile(str(raw_dp).strip() if raw_dp is not None else None)
        if not agent_input.data.get("delivery_profile") and spec.get("delivery_profile"):
            dprof = normalize_delivery_profile(str(spec.get("delivery_profile")))
        mode = infer_delivery_mode(admin_instructions or None, spec, dprof)
        desktop_stack = infer_desktop_stack(admin_instructions or None, spec) if mode == DeliveryMode.DESKTOP_APP else "tauri"
        stack_rules = system_prompt_for_mode(mode, desktop_stack=desktop_stack)
        fs_appendix = (
            full_software_browser_appendix()
            if dprof == FULL_SOFTWARE and mode == DeliveryMode.WEB_APP
            else ""
        )
        desktop_appendix = (
            desktop_app_appendix(desktop_stack)
            if dprof == DESKTOP_APP or mode == DeliveryMode.DESKTOP_APP
            else ""
        )
        fs_appendix = (fs_appendix + desktop_appendix).strip()

        polyglot_block = ""
        if dprof == FULL_SOFTWARE and isinstance(architecture, dict):
            ic = architecture.get("implementation_contract")
            if isinstance(ic, dict) and ic:
                polyglot_block = (
                    "\n=== ARCHITECT IMPLEMENTATION CONTRACT — BINDING ===\n"
                    "These runtimes and paths are **mandatory**. Implement them as real source trees — not comments.\n"
                    f"{prompt_json(ic)}\n"
                    "- Match **tech_stack** + **runnable_services**: Python→`.py` trees + requirements/pyproject; "
                    "Node→package.json + TS sources; .NET→csproj/sln.\n"
                    "- If both **api** and **web** services exist, **do not** collapse everything into one static HTML file.\n"
                    "- Ship **docker-compose.yml** (unless marketing-only landing) so `docker compose up -d --build` starts "
                    "API, frontend, and every **data_plane** store that is not file-only SQLite. "
                    "Publish host ports via env vars **API_HOST_PORT**, **WEB_HOST_PORT** (and **POSTGRES_HOST_PORT** if DB port is exposed).\n"
                    "- README must list install + run + test commands from **verification_commands** (adapt if stack differs slightly).\n"
                    "- **testing_contract**: run the **test pyramid** in order — (1) component/unit, (2) functional/integration "
                    "(API + DB, no browser), (3) UI e2e last. Do not skip straight to Playwright.\n"
                    "- If **sandbox_demo_credentials** is present: seed that user in migrations/compose startup; expose "
                    "`SANDBOX_DEMO_EMAIL` / `SANDBOX_DEMO_PASSWORD` (and Vite `VITE_*` mirrors); **prefill login/password inputs** "
                    "from env when set so sandbox reviewers see populated forms.\n"
                )

        self._log(
            "INFO",
            f"Generating code for {product_id} (delivery_mode={mode.value}, admin_instructions_len={len(admin_instructions)})",
        )

        analyst_brief = ""
        if mode == DeliveryMode.WEB_APP:
            analyst_brief = _load_developer_investigation_brief(self.data_root, product_id)

        remediation: dict = {}
        ai_hint = agent_input.data.get("surrogate_repair_hint")
        if ai_hint:
            # Guidance from the AI surrogate reviewer that re-opened this build for repair
            # (full autonomy). Surfaced to the developer so the hint is actually acted on.
            remediation["ai_reviewer_guidance"] = str(ai_hint)[:2000]
        qg_full = agent_input.data.get("quality_gates_feedback")
        dq_fb = agent_input.data.get("demo_quality_feedback")
        repair_round = agent_input.data.get("quality_repair_round")
        repair_max = agent_input.data.get("quality_repair_max")
        if qg_full or dq_fb:
            # Put the build-breaking list first and on its own. `quality_gates` below
            # is a large nested dump in which "the app does not compile" sits next to
            # "button contrast is low"; rounds were being spent on the cosmetics.
            blocking = (qg_full or {}).get("blocking_defects") if isinstance(qg_full, dict) else None
            if blocking:
                remediation["fix_these_first_they_break_the_build"] = list(blocking)[:30]
            scope = (qg_full or {}).get("repair_scope") if isinstance(qg_full, dict) else None
            if scope:
                remediation["only_edit_these_paths"] = list(scope)
                remediation["scope_reason"] = (
                    "The other half of this product currently passes its gates. Files "
                    "outside these paths are reverted after the round, so editing them "
                    "wastes the round and risks breaking what already works."
                )
            remediation["quality_gates"] = qg_full if qg_full else {"demo_quality": dq_fb}
            if repair_round is not None and repair_max is not None:
                remediation["quality_repair_round"] = repair_round
                remediation["quality_repair_max"] = repair_max
        pr_fb = agent_input.data.get("peer_review_feedback")
        if isinstance(pr_fb, dict):
            blockers = pr_fb.get("blockers")
            if blockers:
                remediation["peer_review_blockers"] = blockers
            notes = pr_fb.get("notes")
            if notes:
                remediation["peer_review_notes"] = notes
            remediation["peer_review_source"] = pr_fb.get("source_agent")
        if agent_input.data.get("policy_audit_trigger"):
            remediation["policy_audit_trigger"] = True
        if agent_input.data.get("monitoring_refresh_trigger"):
            remediation["monitoring_refresh_trigger"] = True
        if agent_input.data.get("user_support_trigger"):
            remediation["user_support_trigger"] = True
        sg_fb = agent_input.data.get("security_gate_feedback")
        if sg_fb:
            remediation["security_gate_feedback"] = sg_fb
            sec_round = agent_input.data.get("security_repair_round")
            sec_max = agent_input.data.get("security_repair_max")
            if sec_round is not None and sec_max is not None:
                remediation["security_repair_round"] = sec_round
                remediation["security_repair_max"] = sec_max
        critic_fb = agent_input.data.get("critic_feedback")
        if critic_fb:
            # The release critic rejected a COMPLETED build. Surface the concrete
            # issues so the developer fixes exactly what was flagged instead of
            # regenerating blind (which loops COMPLETED→critic→DEV_FIXING forever).
            remediation["release_critic_feedback"] = critic_fb
            crit_round = agent_input.data.get("critic_repair_round")
            crit_max = agent_input.data.get("critic_repair_max")
            if crit_round is not None and crit_max is not None:
                remediation["critic_repair_round"] = crit_round
                remediation["critic_repair_max"] = crit_max

        implementation_plan = {
            "modules": [
                "ui",
                "services",
                "state_or_data_layer",
                "tests",
            ],
            "contracts_first": {
                "api_contract_needed": bool("api" in json.dumps(spec).lower() or "endpoint" in json.dumps(spec).lower()),
                "schema_or_model_needed": bool("model" in json.dumps(spec).lower() or "data" in json.dumps(spec).lower()),
            },
            "quality_targets": ["pass quality gates", "maintainability", "security", "a11y"],
        }
        # implementation_plan.json is written AFTER LLM files — shutil.rmtree(code_root) would delete an early save.

        patch_mode = bool(
            agent_input.data.get("qa_gate_blocked")
            or agent_input.data.get("peer_review_feedback")
            or agent_input.data.get("security_gate_blocked")
            or agent_input.data.get("critic_blocked")
        )
        patch_mode_note = (
            "\nSELF-HEALING PATCH MODE: Prefer minimal targeted edits to failing files/modules based on feedback, "
            "instead of full rewrites, unless architecture mismatch forces regeneration.\n"
            if patch_mode
            else ""
        )

        reference_shell_block = ""
        if mode == DeliveryMode.WEB_APP:
            reference_shell_block = build_reference_template_prompt_block(
                product_id=product_id,
                specification=spec,
                admin_instructions=admin_instructions,
                data_root=self.data_root,
            )

        # What the factory knows about its own mesh, handed to the agent writing calls against it.
        # A generated product should never have to guess the API of the factory that generated it —
        # and it was guessing: "input for atlas.fire.weather@v1 does not match its published schema"
        # told a round which field was wrong and nothing about which fields exist, so three contract
        # violations survived six rounds and the round that finally satisfied them deleted the call.
        _mesh_brief = ""
        try:
            from core.ecosystem_api_brief import brief_for_code, render_brief

            _mesh_brief = brief_for_code(self.data_root / "code" / product_id)
            if not _mesh_brief:
                _blob = f"{idea} {admin_instructions} {json.dumps(spec, ensure_ascii=False)[:20000]}"
                if "aimarket" in _blob.lower() or "@v1" in _blob or "atlas" in _blob.lower():
                    _mesh_brief = render_brief()
        except Exception as _brief_exc:
            self._log("WARNING", f"Mesh capability brief unavailable: {_brief_exc}")
        if _mesh_brief:
            admin_instructions = f"{admin_instructions}\n\n{_mesh_brief}".strip()

        developer_user_data = build_developer_user_data(
            idea=idea,
            category=category,
            tags=tags,
            admin_instructions=admin_instructions,
            architecture=architecture,
            specification=spec,
            delivery_mode=mode.value,
            delivery_profile=dprof,
            implementation_plan=implementation_plan,
            analyst_brief=analyst_brief or None,
            remediation=remediation or None,
            interface_locale=str(agent_input.data.get("interface_locale") or "") or None,
            content_locale=str(agent_input.data.get("content_locale") or "") or None,
        )
        user_message = format_user_data_message(developer_user_data)

        # One extra attempt: the self-check below can send a round back for dangling
        # imports, and that retry should not consume the JSON-validity budget.
        max_attempts = 3
        last_error = ""
        code_data: dict | None = None

        if patch_mode:
            # Snapshot the tree as QA last measured it — ONCE, before the retry loop. Inside
            # the loop it was wrong in a way that quietly disarmed the guard: the self-check
            # can send a round back for another write pass, and the second pass would have
            # snapshotted a tree already carrying the first pass's edits, so a later revert
            # would restore half of the round it was trying to undo. Observed in production
            # as two "snapshotted the measured tree" lines for one developer task.
            #
            # Why the snapshot is needed at all: the per-file rollbacks below and
            # ``_tree_defect_score`` see only static defects — unresolved imports, unbound
            # names — while QA blocks on a TypeScript build, a booted app answering 5xx, a
            # browser crawl and module health. A round can improve every signal this agent
            # can read and still make the product worse; measured across eight rounds, each
            # fixed ~14 findings and introduced ~15, so the count never moved. The
            # accept/revert decision belongs at the QA boundary, and it acts on this.
            from core.round_regression_guard import guard_enabled, save_snapshot

            if guard_enabled():
                measured_root = self.data_root / "code" / product_id
                if save_snapshot(product_id, measured_root, Path(self.data_root)):
                    self._log("INFO", "Round guard: snapshotted the measured tree")
                else:
                    self._log(
                        "WARNING",
                        "Round guard: snapshot failed; a regressive round will not be "
                        "revertible this cycle",
                    )

        try:
            for attempt in range(max_attempts):
                correction_note = ""
                if attempt > 0:
                    if patch_mode:
                        # "Regenerate the entire JSON output" during a repair closed a vicious
                        # circle: a focused round failed delivery validation for having no
                        # .html, the retry ordered a full rebuild, the full rebuild passed
                        # validation, reached QA, measured worse than the baseline and was
                        # reverted. Ten reverts with the baseline never moving off 41.
                        correction_note = (
                            f"CORRECTION REQUIRED (attempt {attempt + 1} of {max_attempts}): "
                            f"previous output failed validation — {last_error}. "
                            "This is still a repair round: return the corrected JSON with ONLY "
                            "the files this repair touches. Do not rebuild the product to "
                            f"satisfy the validator; delivery_mode={mode.value}."
                        )
                    else:
                        correction_note = (
                            f"CORRECTION REQUIRED (attempt {attempt + 1} of {max_attempts}): "
                            f"previous output failed validation — {last_error}. "
                            f"Regenerate the entire JSON output; delivery_mode={mode.value}."
                        )
                system_prompt = build_developer_system_prompt(
                    core_prompt=DEV_CORE_PROMPT,
                    stack_rules=stack_rules,
                    reference_shell_block=reference_shell_block,
                    fs_appendix=fs_appendix,
                    polyglot_block=polyglot_block,
                    patch_mode_note=patch_mode_note,
                    correction_note=correction_note,
                    github_house_contract=load_prompt("github_house_contract.md"),
                )
                prompt = user_message

                timeout_sec = (
                    FACTORY_TIMEOUT_CODE_GENERATION_SEC
                    if dprof in (FULL_SOFTWARE, DESKTOP_APP)
                    else (120.0 if mode == DeliveryMode.PYTHON_CLI else 150.0)
                )
                config = GenerationConfig(
                    temperature=0.55 if attempt > 0 else 0.65,
                    max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                    timeout_sec=timeout_sec,
                    json_mode=True,
                )

                # A repair round goes out in short bursts. The prompt already asks for only the
                # changed files, with the measurement attached, and it is ignored: a round whose
                # work list named three files wrote about eighty-five and came back three times
                # worse than the baseline. Asking harder cannot fix that; a per-batch output
                # allowance can, because a call sized for three files cannot return a tree.
                batch_plan: list[dict] = []
                if patch_mode and batching_enabled():
                    _scope_now: list[str] = []
                    _qg_now = agent_input.data.get("quality_gates_feedback")
                    if isinstance(_qg_now, dict) and _qg_now.get("repair_scope"):
                        _scope_now = list(_qg_now["repair_scope"])
                    _findings_now = agent_input.data.get("qa_findings") or []
                    if isinstance(_findings_now, list) and _findings_now:
                        batch_plan = plan_batches(_findings_now, scope=_scope_now)

                if len(batch_plan) > 1:
                    code_data = await self._generate_repair_batches(
                        prompt=prompt,
                        batches=batch_plan,
                        base_config=config,
                        agent_input=agent_input,
                        system_prompt=system_prompt,
                        product_id=product_id,
                        code_root=self.data_root / "code" / product_id,
                    )
                else:
                    response = await self._generate(
                        prompt,
                        config=config,
                        agent_input=agent_input,
                        system_prompt=system_prompt,
                    )
                    code_data = self._extract_json(response)
                if code_data is None:
                    last_error = (
                        "LLM returned invalid/non-JSON response (often truncated output — "
                        "retrying with same token budget)"
                    )
                    self._log("WARNING", f"Code generation invalid JSON for {product_id} (attempt {attempt + 1})")
                    if attempt + 1 >= max_attempts:
                        break
                    continue

                code_root = self.data_root / "code" / product_id
                if code_root.exists() and not patch_mode:
                    shutil.rmtree(code_root)

                saved_relative_paths = []
                saved_files = []
                # A repair round rewrites ~85 files to fix ~10 findings — it
                # regenerates rather than patches, whatever the prompt asks. Keep the
                # previous content so a regenerated module that drops a symbol other
                # files still import can be rolled back instead of shipped.
                previous_content: dict[str, str] = {}
                before_score = _tree_defect_score(code_root) if patch_mode else None
                # Defined unconditionally: the self-check below reads it, and `patch_mode` being true
                # with no measurable baseline would otherwise raise NameError inside the one branch
                # that decides whether to hand off.
                after_score: int | None = None
                _tree_defect_breakdown_before = (
                    _tree_defect_breakdown(code_root) if patch_mode else {}
                )
                _tree_defect_identities_before = (
                    _tree_defect_identities(code_root) if patch_mode else {}
                )
                for file_info in code_data.get("files", []) or []:
                    file_path = file_info.get("path", "")
                    content = file_info.get("content", "")
                    if file_path and content:
                        full_path = _resolve_safe_code_path(code_root, file_path)
                        if full_path is None:
                            self._log(
                                "WARNING",
                                f"Skipping unsafe generated file path for {product_id}: {file_path!r}",
                            )
                            continue
                        if patch_mode and full_path.is_file():
                            try:
                                previous_content[file_path] = full_path.read_text(
                                    encoding="utf-8", errors="replace"
                                )
                            except OSError:
                                pass
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        saved_relative_paths.append(file_path)
                        saved_files.append({
                            "path": file_path,
                            "full_path": str(full_path),
                            "content": content[:5000],
                        })

                # Edits run AFTER the whole-file writes, and nothing is excluded. The first version
                # did the opposite — edits first, and any file the response also rewrote had its edits
                # dropped, on the reasoning that editing a file about to be replaced is pointless.
                # That reasoning does not survive batching. Measured on the first live round where the
                # model preferred the tool:
                #
                #   batch 1/3: 0 rewrite(s) and 3 edit(s)
                #   batch 2/3: 0 rewrite(s) and 15 edit(s)
                #   batch 3/3: 4 rewrite(s) and 0 edit(s)
                #   Applied 1 edit(s)                      <- seventeen were discarded
                #
                # The rewrites came from the UNSCOPED batch — the least focused one, the sprawl this
                # whole design fights — and they silently overrode eighteen surgical edits from the
                # scoped batches. Applied in this order both intents survive: the rewrite lands, then
                # the edit refines it, and an edit whose `find` no longer matches is reported instead
                # of vanishing. `previous_content` already holds the true original from the write
                # above, and setdefault keeps it, so rollback is unaffected.
                _edit_previous, _edited_paths, _edit_problems = apply_edits(
                    code_root,
                    code_data.get("edits") or [],
                    log=self._log,
                    product_id=product_id,
                )
                if patch_mode:
                    for _rel, _text in _edit_previous.items():
                        previous_content.setdefault(_rel, _text)
                for _rel in _edited_paths:
                    if _rel not in saved_relative_paths:
                        saved_relative_paths.append(_rel)
                        saved_files.append({"path": _rel, "edited": True})

                # Repair rounds are told to delete superseded modules — until now the
                # output contract had no way to say so, and patch mode could only ever
                # add, which is how one product accreted five copies of its seeding
                # module while the real defect stayed put.
                deleted_snapshots = _apply_requested_deletions(
                    code_root,
                    code_data.get("delete_files"),
                    log=self._log,
                    product_id=product_id,
                    keep=set(saved_relative_paths),
                )
                deleted_paths = list(deleted_snapshots)
                _prune_empty_dirs(
                    code_root,
                    log=self._log,
                    product_id=product_id,
                    only_below=deleted_paths,
                )

                if patch_mode and saved_relative_paths:
                    try:
                        from web.backend.services.duplicate_module_check import (
                            ensure_markup_classes_have_rules,
                            strip_orphan_tailwind_classnames,
                        )

                        stripped = strip_orphan_tailwind_classnames(
                            code_root, saved_relative_paths
                        )
                        if stripped:
                            self._log(
                                "INFO",
                                f"Stripped Tailwind utilities from {len(stripped)} file(s) for "
                                f"{product_id} (no tailwindcss in this product): "
                                f"{', '.join(stripped[:6])}",
                            )
                        stubbed = ensure_markup_classes_have_rules(
                            code_root, saved_relative_paths
                        )
                        if stubbed:
                            self._log(
                                "INFO",
                                f"Added CSS selectors for {len(stubbed)} class(es) used in "
                                f"{product_id} markup this round: {', '.join(stubbed[:8])}",
                            )
                    except Exception as _tw_exc:
                        self._log(
                            "WARNING",
                            f"Markup-style postprocess skipped for {product_id}: {_tw_exc}",
                        )

                repair_scope = []
                _qg = agent_input.data.get("quality_gates_feedback")
                if isinstance(_qg, dict) and _qg.get("repair_scope"):
                    repair_scope = list(_qg["repair_scope"])
                if patch_mode and repair_scope:
                    # The findings' own text is part of the scope: a requirement can name a file
                    # that does not exist yet, and a scope derived from the tree can never contain
                    # it.
                    _findings_text = json.dumps(
                        agent_input.data.get("qa_findings") or [], ensure_ascii=False
                    )
                    if isinstance(_qg, dict):
                        _findings_text += json.dumps(_qg, ensure_ascii=False)
                    out_of_scope = _revert_out_of_scope_writes(
                        code_root,
                        previous_content,
                        saved_relative_paths,
                        repair_scope,
                        log=self._log,
                        product_id=product_id,
                        findings_text=_findings_text,
                    )
                    if out_of_scope:
                        saved_relative_paths = [p for p in saved_relative_paths if p not in out_of_scope]
                        saved_files = [f for f in saved_files if f["path"] not in out_of_scope]

                reverted: set[str] = set()
                # Measure the waste: a repair round rewrites ~80 files to fix a handful
                # of findings, and most come back byte-identical. Those are pure output
                # tokens with no effect, and until they are counted nobody can tell.
                if patch_mode and previous_content:
                    unchanged = sum(
                        1
                        for rel, old_text in previous_content.items()
                        if rel in saved_relative_paths
                        and (code_root / rel).is_file()
                        and (code_root / rel).read_text(encoding="utf-8", errors="replace") == old_text
                    )
                    if saved_relative_paths:
                        self._log(
                            "INFO",
                            f"Repair round for {product_id} wrote {len(saved_relative_paths)} file(s), "
                            f"{unchanged} identical to disk "
                            f"({100 * unchanged // max(1, len(saved_relative_paths))}% wasted output)",
                        )

                if patch_mode and previous_content:
                    reverted = _revert_symbol_regressions(
                        code_root,
                        previous_content,
                        log=self._log,
                        product_id=product_id,
                    )
                    if reverted:
                        saved_relative_paths = [p for p in saved_relative_paths if p not in reverted]
                        saved_files = [f for f in saved_files if f["path"] not in reverted]

                # Per-file rollback keeps a symbol alive, but it cannot help when the
                # round redesigns the app: restoring five modules to the old shape while
                # eighty move to a new one just disagrees in a fresh way. One product went
                # from two remaining defects to twenty-five that way. So the round is also
                # judged as a whole, and a round that leaves the tree worse is not kept.
                if patch_mode and before_score is not None:
                    before_parts = _tree_defect_breakdown_before
                    after_score = _tree_defect_score(code_root)
                    # Taken here, next to the score it explains. The first version of this logged the
                    # breakdown from inside the rejection branch — which runs after the rollback has
                    # already put the previous tree back — so it faithfully reported that nothing had
                    # changed, about a tree that had indeed been changed back. "nothing individually
                    # — check the weights" was the instrument measuring its own undo.
                    after_parts = _tree_defect_breakdown(code_root)
                    after_ids = _tree_defect_identities(code_root)
                    if after_score is not None and after_score > before_score:
                        # Try the surgical fix before condemning the whole round.
                        extra = _revert_files_with_new_undefined_names(
                            code_root,
                            previous_content,
                            log=self._log,
                            product_id=product_id,
                            already=reverted,
                        )
                        if extra:
                            saved_relative_paths = [p for p in saved_relative_paths if p not in extra]
                            saved_files = [f for f in saved_files if f["path"] not in extra]
                            after_score = _tree_defect_score(code_root)
                            after_parts = _tree_defect_breakdown(code_root)
                            after_ids = _tree_defect_identities(code_root)
                    # Still worse? Give back the fewest files that stop it being a regression, rather
                    # than discarding work that was right. A round fixing three frontend type errors
                    # and breaking one backend attribute measured 0 → 10 and lost everything, because
                    # tsc errors do not appear in this score at all.
                    if after_score is not None and after_score > before_score:
                        salvaged = _revert_until_not_worse(
                            code_root,
                            previous_content,
                            saved_relative_paths,
                            before_score=before_score,
                            log=self._log,
                            product_id=product_id,
                            already=set(reverted) | set(extra or ()),
                        )
                        if salvaged:
                            saved_relative_paths = [
                                p for p in saved_relative_paths if p not in salvaged
                            ]
                            saved_files = [f for f in saved_files if f["path"] not in salvaged]
                            after_score = _tree_defect_score(code_root)
                            after_parts = _tree_defect_breakdown(code_root)
                            after_ids = _tree_defect_identities(code_root)
                    if after_score is not None and after_score > before_score:
                        for rel, content in previous_content.items():
                            target = _resolve_safe_code_path(code_root, rel)
                            if target is not None:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(content, encoding="utf-8")
                        for rel, content in deleted_snapshots.items():
                            target = _resolve_safe_code_path(code_root, rel)
                            if target is not None:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(content, encoding="utf-8")
                        for rel in saved_relative_paths:
                            if rel in previous_content:
                                continue
                            target = _resolve_safe_code_path(code_root, rel)
                            if target is not None and target.is_file():
                                target.unlink()  # file this round invented; it goes too
                        if _edit_problems:
                            self._log(
                                "WARNING",
                                f"Rejected repair round for {product_id}: "
                                f"{len(_edit_problems)} edit(s) had not applied either — "
                                + "; ".join(_edit_problems[:3]),
                            )
                        self._log(
                            "WARNING",
                            f"Rejected repair round for {product_id}: what moved — "
                            f"{_breakdown_delta(before_parts, after_parts)}"
                            + (
                                f" | added: {_identities_appeared(_tree_defect_identities_before, after_ids)}"
                                if _identities_appeared(_tree_defect_identities_before, after_ids)
                                else ""
                            ),
                        )
                        self._log(
                            "WARNING",
                            f"Rejected repair round for {product_id}: static defects would rise "
                            f"{before_score} → {after_score}; tree restored",
                        )
                        last_error = (
                            f"your changes raised unresolved imports/undefined names from "
                            f"{before_score} to {after_score}, so they were discarded. Make the "
                            "smallest edit that fixes the listed findings; do not redesign modules "
                            "that were not named."
                        )
                        if attempt + 1 >= max_attempts:
                            break
                        continue

                # Pass what is already on disk, so a focused round is judged on the product
                # rather than on its own write list. Without this a three-file repair was told
                # "Web stack requires at least one .html file" and discarded — eight times in two
                # hours on production, including every batched round.
                existing_on_disk: list[str] = []
                try:
                    from core.code_discovery import iter_product_files

                    existing_on_disk = [
                        str(f.relative_to(code_root)) for f in iter_product_files(code_root, "*")
                    ]
                except Exception:
                    existing_on_disk = []
                ok, validation_msg = validate_saved_files(
                    mode, saved_relative_paths, existing_on_disk
                )
                if ok:
                    # Cheap static self-check before handing off. Otherwise the agent
                    # learns it broke an import ~15 minutes later, from a full QA round,
                    # and the loop oscillates instead of converging.
                    broke = _self_check_written_files(
                        code_root, saved_relative_paths, log=self._log, product_id=product_id
                    )
                    # Regenerate only if the round left the tree WORSE. A dangling import on its own
                    # is not worth a full regeneration any more, and insisting on it starved the whole
                    # pipeline: QA had not run for 47 minutes while eight consecutive four-minute
                    # attempts were spent on one dangling name, each one a fresh chance to invent
                    # another. The round never handed off, so none of the findings that would have
                    # named the real problem ever reached it.
                    #
                    # This check predates the ratchet it duplicates. The tree score already refuses a
                    # round that made things worse, the out-of-scope guard already measures every
                    # write, and each batch is already content-checked. What remains for the
                    # self-check is the case those miss: a round that is a net improvement but still
                    # leaves something dangling is now handed off with the dangling names reported,
                    # because QA names them precisely and the next round is cheaper than this retry.
                    _worse = (
                        before_score is not None
                        and after_score is not None
                        and after_score > before_score
                    ) if patch_mode else False
                    if not broke or not _worse or attempt + 1 >= max_attempts:
                        if broke:
                            self._log(
                                "WARNING",
                                f"Handing off with {len(broke)} dangling import(s) for {product_id} "
                                "rather than regenerating: the tree did not get worse, and QA names "
                                f"them precisely — {'; '.join(broke[:3])}",
                            )
                        break
                    last_error = (
                        "the files you just wrote reference names that do not exist: "
                        + "; ".join(broke[:8])
                        + ". Define each one in the module named, or correct the import."
                    )
                    self._log("WARNING", f"Self-check found {len(broke)} dangling import(s) for {product_id}")
                    continue

                last_error = validation_msg
                self._log(
                    "WARNING",
                    f"Delivery validation failed for {product_id}: {validation_msg} (attempt {attempt + 1})",
                )
            else:
                elapsed = time.time() - start_time
                err = last_error or "LLM returned invalid/non-JSON response — code generation failed"
                if "invalid/non-JSON" in err or "invalid JSON" in err.lower():
                    err = "LLM returned invalid/non-JSON response — code generation failed"
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error=f"Delivery constraints not satisfied after {max_attempts} attempts: {err}",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            if code_data is None:
                raise RuntimeError("Developer agent finished without code_data")

            self._save_artifact(
                product_id,
                "code",
                {"product_id": product_id, "implementation_plan": implementation_plan, "created_at": time.time()},
                "implementation_plan.json",
            )

            self._save_artifact(product_id, "code", {
                "product_id": product_id,
                "delivery_mode": mode.value,
                "admin_instructions_applied": bool(admin_instructions),
                "files": saved_files,
                "dependencies": code_data.get("dependencies", []),
                "setup_instructions": code_data.get("setup_instructions", ""),
                "test_commands": code_data.get("test_commands", []),
                "documentation": code_data.get("documentation", ""),
                "created_at": time.time(),
                "agent": "developer",
            }, "code_manifest.json")

            if mode.value == "web_app":
                try:
                    from web.backend.services.code_entrypoint import ensure_web_entrypoint_at_product_root

                    ensure_web_entrypoint_at_product_root(product_id)
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (agents/dev.py)", exc_info=_suppressed_exc)
                try:
                    from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix

                    apply_visual_gate_autofix(self.data_root / "code" / product_id)
                except Exception as _suppressed_exc:
                    log_suppressed(logger, "visual_gate_autofix failed", exc_info=_suppressed_exc)

            elapsed = time.time() - start_time
            self._log("INFO", f"Code generation complete: {len(saved_files)} files ({elapsed:.1f}s), mode={mode.value}")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "files": saved_files,
                    "file_count": len(saved_files),
                    "deleted_files": deleted_paths,
                    "delivery_mode": mode.value,
                    "dependencies": code_data.get("dependencies", []),
                    "test_commands": code_data.get("test_commands", []),
                    "setup_instructions": code_data.get("setup_instructions", ""),
                    "manifest_file": f"code/{product_id}/code_manifest.json",
                    "peer_review": {
                        "recommended": "approve",
                        "blockers": [],
                        "notes": "Developer implementation completed; handoff to hardening/QA.",
                    },
                },
                timestamp=time.time(),
                metrics={
                    "elapsed_seconds": elapsed,
                    "files_created": len(saved_files),
                    "files_deleted": len(deleted_paths),
                },
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Code generation failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
