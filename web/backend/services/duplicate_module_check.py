"""
Detect the accretion pattern that keeps a repair loop from converging.

Watching a real rework: QA reported ``cannot import get_password_hash from
app.core.security``. The developer agent responded by writing a *new* seeding
module that also imported ``get_password_hash`` — without ever defining it. Next
round, another one. The tree ended up with five modules doing the same job

    app/seed.py                 imports hash_password
    app/services/seed.py        imports get_password_hash
    app/services/demo_data.py   imports get_password_hash
    app/services/demo_seed.py   imports get_password_hash
    app/services/demo.py        imports get_password_hash

and ``app/core/security.py`` defining neither. The same happened on the frontend
(``Accounts.tsx`` *and* ``AccountsPage.tsx``), where only one of each pair was
reachable from the router.

Patch mode never deletes, so every round the surface grows and the real defect
stays. This module names both halves of that failure:

  * ``duplicate_modules``  — several files serving one role
  * ``missing_symbol``     — a symbol imported across the codebase that nothing defines

The second is the one that actually breaks the build, and stating it as
"define X in Y" is far more actionable than an ImportError traceback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .module_checks.common import (  # noqa: F401 - re-exported
    _canonical_home,
    _collect_imported_modules,
    _is_test_path,
    _module_level_bindings,
    _module_path,
    _normalised_matches,
    _PY_ASSIGN_RE,
    _PY_CLASS_RE,
    _PY_DEF_RE,
    from_imports,
    from_imports_with_aliases,
    logger,
    MAX_FINDINGS,
    resolve_import_target,
)
from .module_checks.symbols import (  # noqa: F401 - re-exported
    _NEVER_ORPHAN,
    _rank_near_matches,
    _role_layer,
    _ROLE_PATTERNS,
    find_duplicate_roles,
    find_missing_modules,
    find_missing_symbols,
    find_orphan_modules_with_broken_imports,
    find_undefined_names,
    undefined_names_in_source,
)
from .module_checks.routes import (  # noqa: F401 - re-exported
    _decorator_name,
    _INCLUDE_WITH_NAMED_PREFIX_RE,
    _INCLUDE_WITH_PREFIX_RE,
    _is_route_decorator,
    _NAME_VALUE_RE,
    _repeated_segment_run,
    _ROUTE_DECOR_WITH_METHOD_RE,
    _ROUTE_DECORATOR_METHODS,
    _ROUTE_PATH_RE,
    _router_include_prefixes,
    _ROUTER_PREFIX_CTOR_RE,
    _SCOPE_PATH_REWRITE_RE,
    _SPA_EXEMPT,
    _wrapper_required_params,
    find_api_routes_shadowing_spa,
    find_dead_path_rewrites,
    find_duplicated_router_prefix,
    find_route_handlers_with_broken_injection,
    find_sync_wrapper_over_async_handler,
)
from .module_checks.frontend import (  # noqa: F401 - re-exported
    _CLASSNAME_ATTR_RE,
    _safe_product_file,
    _stylesheet_path,
    _TAILWIND_UTILITY_RE,
    _TS_BUILTIN_PREFIXES,
    _TS_CODE_SUFFIXES,
    _TS_EXPORT_BRACE_RE,
    _TS_EXPORT_DECL_RE,
    _TS_EXPORT_DEFAULT_RE,
    _TS_EXPORT_STAR_RE,
    _ts_exports_of,
    _TS_IMPORT_RE,
    _TS_IMPORT_STMT_RE,
    _TS_PKG_IMPORT_RE,
    _ts_resolve,
    _TS_SUFFIXES,
    ensure_markup_classes_have_rules,
    find_case_collisions,
    find_frontend_missing_exports,
    find_undeclared_frontend_deps,
    find_unresolved_frontend_imports,
    find_unstyled_classes,
    product_has_tailwind,
    strip_orphan_tailwind_classnames,
)
from .module_checks.orm import (  # noqa: F401 - re-exported
    _CREATE_ALL_RE,
    _TABLENAME_RE,
    find_duplicate_tablenames,
    find_mismatched_back_populates,
    find_orm_schema_never_created,
    find_unregistered_models,
)
from .module_checks.classes import (  # noqa: F401 - re-exported
    _ANALYSABLE_FOREIGN_BASES,
    _callable_kwargs,
    _INHERITED_ATTRS,
    find_class_body_forward_refs,
    find_missing_instance_attributes,
    find_unexpected_keyword_arguments,
)
from .module_checks.dependencies import (  # noqa: F401 - re-exported
    _VERIFIABLE_PACKAGES,
    find_hallucinated_imports,
    find_undeclared_dependencies,
)
from .module_checks.capabilities import (  # noqa: F401 - re-exported
    _ADVERTISED_CAPABILITY_KEYS,
    _AIMARKET_ENVELOPE_REQUIRED,
    _AIMARKET_ENVELOPE_WRONG,
    _capability_id_is_advertised,
    _CAPABILITY_ID_RE,
    _fetch_manifest_schemas,
    find_capabilities_never_invoked,
    find_mesh_contract_violations,
    find_mesh_participant_violations,
)


def run_duplicate_module_check(
    product_id: str,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Pipeline entrypoint. Missing symbols fail the gate; duplicates warn."""
    from core.paths import code_dir as resolve_code_dir
    from core.paths import resolve_data_root

    root = resolve_data_root(data_root)
    code_dir = resolve_code_dir(product_id, data_root=root)
    if not code_dir.is_dir():
        return {"passed": True, "skipped": True, "reason": "no_code_dir", "issues": []}

    try:
        missing = find_missing_symbols(code_dir)
        duplicates = find_duplicate_roles(code_dir)
        orphans = find_orphan_modules_with_broken_imports(code_dir, missing)
        undefined = find_undefined_names(code_dir)
        unregistered = find_unregistered_models(code_dir)
        hallucinated = find_hallucinated_imports(code_dir)
        undeclared = find_undeclared_frontend_deps(code_dir)
        broken_injection = find_route_handlers_with_broken_injection(code_dir)
        dup_tables = find_duplicate_tablenames(code_dir)
        mesh_contract = find_mesh_contract_violations(code_dir)
        mesh_participant = find_mesh_participant_violations(code_dir)
        absent_modules = find_missing_modules(code_dir)
        absent_attributes = find_missing_instance_attributes(code_dir)
        unexpected_kwargs = find_unexpected_keyword_arguments(code_dir)
        forward_refs = find_class_body_forward_refs(code_dir)
        double_prefix = find_duplicated_router_prefix(code_dir)
        ts_exports = find_frontend_missing_exports(code_dir)
        bad_pairs = find_mismatched_back_populates(code_dir)
        spa_shadows = find_api_routes_shadowing_spa(code_dir)
        case_twins = find_case_collisions(code_dir)
        dead_rewrites = find_dead_path_rewrites(code_dir)
        schema_never = find_orm_schema_never_created(code_dir)
        undeclared_deps = find_undeclared_dependencies(code_dir)
        unstyled = find_unstyled_classes(code_dir)
        hollow = find_capabilities_never_invoked(code_dir)
        sync_wrappers = find_sync_wrapper_over_async_handler(code_dir)
    except Exception as exc:
        logger.warning("duplicate_module_check failed for %s: %s", product_id, exc)
        return {"passed": True, "skipped": True, "reason": f"error:{exc}", "issues": []}

    # A symbol wanted only by files that are being deleted is not a symbol to write.
    # Reporting both turned 5 deletions into 30 "define X" instructions, and the agent
    # dutifully started implementing schemas for endpoints that no longer belong.
    orphan_files = {o["file"] for o in orphans}
    if orphan_files:
        missing = [
            m
            for m in missing
            if not set(m.get("importers") or []).issubset(orphan_files)
        ]

    issues: list[dict[str, Any]] = []
    for item in dead_rewrites:
        issues.append(
            {
                "code": "dead_path_rewrite",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in sync_wrappers:
        issues.append(
            {
                "code": "sync_wrapper_over_async_handler",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in hollow:
        issues.append(
            {
                "code": "capability_never_invoked",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in unstyled:
        issues.append(
            {
                "code": item.get("code"),
                "severity": item.get("severity", "high"),
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in undeclared_deps:
        issues.append(
            {
                "code": "undeclared_dependency",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in schema_never:
        issues.append(
            {
                "code": "orm_schema_never_created",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in case_twins:
        issues.append(
            {
                "code": "case_collision",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in spa_shadows:
        issues.append(
            {
                "code": "api_route_shadows_spa",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in bad_pairs:
        issues.append(
            {
                "code": "mismatched_back_populates",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in ts_exports:
        issues.append(
            {
                "code": "frontend_missing_export",
                "severity": "high",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in double_prefix:
        issues.append(
            {
                "code": "duplicated_router_prefix",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in forward_refs:
        issues.append(
            {
                "code": "class_body_forward_ref",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    # First: the app cannot even be imported, so nothing else can be observed about it.
    for item in absent_modules:
        issues.append(
            {
                "code": "missing_module",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in absent_attributes:
        issues.append(
            {
                "code": "missing_attribute",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in unexpected_kwargs:
        issues.append(
            {
                "code": "unexpected_keyword_argument",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in mesh_contract:
        issues.append(
            {
                "code": "mesh_contract_violation",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in mesh_participant:
        issues.append(
            {
                "code": "mesh_participant_violation",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in dup_tables:
        issues.append(
            {
                "code": "duplicate_tablename",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in broken_injection:
        issues.append(
            {
                "code": "route_handler_broken_injection",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in undeclared:
        issues.append(
            {
                "code": "undeclared_dependency",
                "severity": "high",
                "detail": (
                    f"{item['file']} imports '{item['package']}' but {item['manifest']} does "
                    f"not declare it. Add it to dependencies — the build fails with "
                    f"\"Cannot find module '{item['package']}'\" after install, so nothing "
                    "before the build catches this."
                ),
                "file": item["file"],
            }
        )
    for item in hallucinated:
        issues.append(
            {
                "code": "hallucinated_import",
                "severity": "high",
                "detail": (
                    f"{item['file']} imports '{item['symbol']}' from {item['module']}, which "
                    f"does not export it. That name does not exist in the installed library — "
                    "check the real API rather than adjusting the import path; this fails at "
                    "import time and takes the whole app down."
                ),
                "file": item["file"],
            }
        )
    for item in unregistered:
        issues.append(
            {
                "code": "models_not_registered",
                "severity": "high",
                "detail": (
                    f"{item['file']} calls Base.metadata.create_all() but imports no model "
                    f"module, so SQLAlchemy only creates tables for models something else "
                    f"happened to import. Import the models package there (e.g. "
                    f"`from app import models`) so {', '.join(item['models'][:6])} are all "
                    "registered — otherwise they fail at runtime with 'no such table'."
                ),
                "file": item["file"],
            }
        )
    for item in undefined:
        issues.append(
            {
                "code": "undefined_name",
                "severity": "high",
                "detail": (
                    f"{item['file']}:{item['line']} uses '{item['name']}' but the module never "
                    f"imports or defines it. Add it to the import at the top of that file — "
                    f"this is one line, and it stops the whole app from importing."
                ),
                "file": item["file"],
            }
        )
    for item in orphans:
        issues.append(
            {
                "code": "orphan_module_breaks_build",
                "severity": "high",
                "detail": (
                    f"DELETE {item['file']} — nothing imports it, "
                    f"{', '.join(item.get('superseded_by') or [])} superseded it, and its "
                    f"dangling imports ({', '.join(item['broken_imports'])}) break the package "
                    "for everything that does. Removing the file is the fix, not adding the "
                    "symbols it wants."
                ),
                "file": item["file"],
            }
        )
    for item in missing:
        issues.append(
            {
                "code": "missing_symbol",
                # Critical, like every other defect that stops the import. As "high" it was worth 3
                # to the round guard against 4 for a duplicate table, though both mean the app never
                # starts — and it is the one that arrives nine at a time.
                "severity": "critical",
                "detail": (
                    (item.get("fix_hint") + " ") if item.get("fix_hint") else ""
                )
                + (
                    f"{item['file']} does not define '{item['symbol']}', but "
                    f"{len(item['importers'])} module(s) import it "
                    f"({', '.join(item['importers'][:4])}). "
                    + (
                        f"It does define {' / '.join(repr(c) for c in item['did_you_mean'])}. "
                        f"If {item['did_you_mean'][0]!r} is the same function, the stable fix is "
                        f"one line in that module — `{item['symbol']} = {item['did_you_mean'][0]}` "
                        "— which satisfies both names. Renaming instead breaks whatever still "
                        "calls the old one, and this has already flip-flopped between the two. "
                        "Do not write a second implementation. "
                        if item.get("did_you_mean")
                        else ""
                    )
                    + "Define it there — do NOT add another module that imports it."
                ),
                "file": item["file"],
                "symbol": item["symbol"],
            }
        )
    for item in duplicates:
        issues.append(
            {
                "code": "duplicate_modules",
                "severity": "medium",
                "detail": (
                    f"{len(item['files'])} files implement '{item['role']}': "
                    f"{', '.join(item['files'])}. Keep ONE and delete the rest — "
                    "unreachable duplicates hide the file that is actually wired up."
                ),
                "file": item["files"][0],
            }
        )

    return {
        # Duplicates alone are a smell; a symbol nothing defines is a broken build.
        # A route handler FastAPI cannot call blocks too. It was reported as critical and
        # the gate still passed, which makes it one line in a list the round may or may
        # not act on — and this class costs a 500 on every request to the endpoint, so a
        # product whose only feature is one endpoint is simply dead while the gate is
        # green. Blocking is what turns the finding into the round's work.
        # The two newest detectors were reported as critical and left out of this expression, so the
        # gate went green with a defect that stops the app importing. Caught on the live product at the
        # moment everything else closed: module_health PASSED with one missing_attribute —
        # `rule_engine.compute_advisory`, read by routers/advisory.py:62, gone because a round renamed
        # it. A critical that does not fail its own gate is one line in a list the round may or may not
        # act on, which is the same lesson the route-handler class taught two comments above.
        "passed": not missing and not undefined and not unregistered and not hallucinated
        and not undeclared and not broken_injection and not dup_tables
        and not mesh_contract and not mesh_participant and not absent_modules and not absent_attributes
        and not forward_refs and not double_prefix and not ts_exports
        and not bad_pairs and not spa_shadows and not case_twins
        and not schema_never
        and not undeclared_deps
        and not unstyled
        and not hollow
        and not sync_wrappers
        and not dead_rewrites
        and not unexpected_kwargs,
        "skipped": False,
        "issues": issues,
        "missing_symbols": missing,
        "undefined_names": undefined,
        "duplicate_roles": duplicates,
        "orphan_modules": orphans,
    }
