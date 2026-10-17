"""The tree's defect score: a breakdown by kind, the identities behind it, and what a round
added.
"""

from __future__ import annotations

from pathlib import Path


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
        "mesh_participant": lambda: d.find_mesh_participant_violations(code_root),
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
            find_mesh_participant_violations,
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
            # Same economy, wrong identity: demo X-Agent-Key / legacy /aimarket/invoke with no
            # visitor trial and no payment channel — product is not a paying (or even trial) participant.
            + 5 * len(find_mesh_participant_violations(code_root))
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
