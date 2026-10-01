"""Catch the factory rewriting a module the charter told it to import.

``duplicate_module_check`` names several files serving one role, and ``foreign_subsystem`` names
a subsystem nobody ordered. This gate covers the case those two cannot see: the product tree is
clean, the roles are distinct, everything is chartered — and the one module whose correctness the
whole product depends on was written from scratch by an agent instead of imported.

The reason it needs its own gate is that a reimplementation *works*. It has the right signature,
returns the right shape, and passes any test written against it, including tests the agents write
themselves. What it does not have is the property the original was verified for. This repository
has the receipts:

* ``sortes``' ECVRF is byte-exact against the RFC 9381 Appendix B.3 vectors, both directions —
  our proofs match the published bytes, and the published proofs verify under our verifier
  (``oracles/oracles/sortes/tests/test_sortes.py``). A fresh implementation that is merely
  self-consistent passes every test you would think to write and is not interoperable with
  anyone: a big-endian ``c‖s`` encoding reproduces Gamma and beta and emits a byte-reversed tail.
* ``platon`` shipped, in two separate copies, a proof that verified an output never derived from
  the committed entropy (``oracles/oracles/platon/backend/tests/test_randomness.py:117``).

So when the charter pins a dependency, three things must hold, and each is checked separately
because each fails differently:

``pinned_dependency_unused``
    Nothing in the tree imports the pinned module. The strongest and least ambiguous signal —
    the product cannot be using it.

``pinned_dependency_reimplemented``
    A pinned symbol is defined locally *and* imported nowhere. This is the reflex the gate
    exists for.

``pinned_dependency_undeclared``
    The charter named a distribution in ``requires:`` and the product's requirements manifest
    does not contain it. An import that resolves in the factory's environment and not in the
    deployed one is the same defect discovered later, at the worst moment: two of this
    ecosystem's live incidents were exactly a module present in the build host and absent from
    the running container.

A local definition that coexists with a real import of the pin is reported as **non-blocking**.
A product may legitimately wrap a pinned call in a function of the same name, and
``charter_fidelity`` already established the house rule: a gate that cries wolf gets switched
off, so the blocking bar is total absence rather than mere resemblance.

Findings carry ``severity`` from the repair pipeline's own vocabulary (critical/high/medium/low,
because ``core.repair_batches`` maps anything else to medium and would promote a note into work)
plus an explicit ``blocking`` flag, which is what decides pass/fail.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_FINDINGS = 20

# Trees that are not the product's Python surface. Tests are excluded deliberately: a test may
# well define a stub named like a pinned symbol, and accusing a test file is noise.
_SKIP_PARTS = frozenset(
    {
        "node_modules",
        "frontend",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "tests",
        "test",
    }
)

_REQUIREMENT_FILES = ("requirements.txt", "requirements-prod.txt", "pyproject.toml")


def _python_files(code_dir: Path) -> list[Path]:
    if not code_dir.is_dir():
        return []
    out: list[Path] = []
    for path in code_dir.rglob("*.py"):
        rel_parts = set(path.relative_to(code_dir).parts)
        if rel_parts & _SKIP_PARTS:
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            continue
        out.append(path)
    return out


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("pinned_dependency_gate: cannot read %s: %s", path, exc)
        return ""


def _imports_of(source: str) -> list[tuple[str, list[str]]]:
    """``[(module, [name, ...])]`` for every ``from X import a, b`` in the source.

    Reuses ``duplicate_module_check.from_imports`` so both gates agree on what an import is;
    falls back to an empty list rather than raising when the file does not parse, because an
    unparseable file is already someone else's finding.
    """
    try:
        from web.backend.services.duplicate_module_check import from_imports

        return from_imports(source)
    except Exception as exc:  # pragma: no cover - import-time robustness only
        logger.debug("pinned_dependency_gate: from_imports unavailable: %s", exc)
        return []


def _plain_imports(source: str) -> set[str]:
    """Modules brought in by ``import X`` / ``import X as y`` (not ``from X import ...``)."""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
    return mods


def _module_bindings(source: str) -> set[str]:
    try:
        from web.backend.services.duplicate_module_check import _module_level_bindings

        return _module_level_bindings(source)
    except Exception as exc:  # pragma: no cover
        logger.debug("pinned_dependency_gate: _module_level_bindings unavailable: %s", exc)
        return set()


def _module_matches(candidate: str, pinned: str) -> bool:
    """Whether ``candidate`` refers to the pinned module.

    Suffix matching, because a generated product legitimately reaches the same module by a
    shorter path than the monorepo's: ``sortes.vrf`` and ``oracles.oracles.sortes.sortes.vrf``
    are the same file, and requiring the operator to guess which one the agents will write
    would make the gate a trivia question. Anchored on a dot boundary so ``my_sortes.vrf``
    does not match ``sortes.vrf``.
    """
    if not candidate or not pinned:
        return False
    if candidate == pinned:
        return True
    return candidate.endswith("." + pinned) or pinned.endswith("." + candidate)


def _requirement_text(code_dir: Path) -> str:
    parts: list[str] = []
    for name in _REQUIREMENT_FILES:
        path = code_dir / name
        if path.is_file():
            parts.append(_read(path))
        # A backend/ nested layout is common enough in generated products that ignoring it
        # would make this check report a false "undeclared" on a correct tree.
        nested = code_dir / "backend" / name
        if nested.is_file():
            parts.append(_read(nested))
    return "\n".join(parts).lower()


def check_pinned_dependencies(
    code_dir: Path | str,
    pins: list[dict[str, Any]],
    *,
    limit: int = MAX_FINDINGS,
) -> list[dict[str, Any]]:
    """Findings for every pinned dependency the product fails to actually depend on.

    ``pins`` comes from ``core.charter_contracts.pinned_dependencies`` and is expected to be
    already validated — malformed blocks are the charter's problem and are reported there.
    """
    code_dir = Path(code_dir)
    if not pins:
        return []
    files = _python_files(code_dir)
    if not files:
        # No Python surface at all is not this gate's finding to make: a marketing-landing
        # profile has none by design, and the delivery-profile gates already say so.
        return []

    # One pass over the tree; each pin is answered from the collected index.
    imported_from: dict[str, set[str]] = {}   # module -> symbols imported anywhere
    plain_imported: set[str] = set()
    defined_in: dict[str, list[str]] = {}     # symbol -> [rel path, ...]
    for path in files:
        source = _read(path)
        if not source:
            continue
        rel = str(path.relative_to(code_dir))
        for module, names in _imports_of(source):
            imported_from.setdefault(module, set()).update(names)
        plain_imported.update(_plain_imports(source))
        for name in _module_bindings(source):
            defined_in.setdefault(name, []).append(rel)

    requirements = _requirement_text(code_dir)
    findings: list[dict[str, Any]] = []

    for pin in pins:
        module = str(pin.get("module") or "").strip()
        symbols = [str(s) for s in (pin.get("symbols") or [])]
        why = str(pin.get("why") or "").strip()
        if not module or not symbols:
            continue

        matched_modules = [m for m in imported_from if _module_matches(m, module)]
        imported_symbols: set[str] = set()
        for m in matched_modules:
            imported_symbols |= imported_from[m]
        module_imported = bool(matched_modules) or any(
            _module_matches(m, module) for m in plain_imported
        )

        if not module_imported:
            findings.append(
                {
                    "code": "pinned_dependency_unused",
                    "severity": "critical",
                    "file": "requirements.txt" if requirements else str(code_dir.name),
                    "detail": (
                        f"The charter pins `{module}` and nothing in the product imports it. "
                        f"Import {', '.join(symbols)} from `{module}` and call it; do not write a "
                        f"local equivalent."
                        + (f" Why it is pinned: {why}" if why else "")
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
            # A module nobody imports makes per-symbol reimplementation findings redundant
            # noise — the one finding above already says what to do.
            continue

        for symbol in symbols:
            local = defined_in.get(symbol) or []
            if not local:
                continue
            if symbol in imported_symbols:
                # Imported *and* defined: a wrapper of the same name is a legitimate pattern,
                # so this only informs.
                findings.append(
                    {
                        "code": "pinned_dependency_shadowed",
                        # "low", not "advisory": the repair pipeline's severity vocabulary is
                        # critical/high/medium/low and maps anything else to medium, so an
                        # invented word here would promote an informational note into work.
                        # `blocking` is what the gate reads for pass/fail.
                        "severity": "low",
                        "blocking": False,
                        "file": local[0],
                        "detail": (
                            f"`{symbol}` is both imported from `{module}` and defined locally in "
                            f"{', '.join(local[:3])}. If the local one is a wrapper this is fine; "
                            f"if it is a second implementation, delete it and call the pinned one."
                        ),
                    }
                )
            else:
                findings.append(
                    {
                        "code": "pinned_dependency_reimplemented",
                        "severity": "critical",
                        "file": local[0],
                        "detail": (
                            f"`{symbol}` is defined in {', '.join(local[:3])} and imported from "
                            f"`{module}` nowhere — this is a local reimplementation of a pinned "
                            f"dependency. Delete it and use `from {module} import {symbol}`."
                            + (f" Why it is pinned: {why}" if why else "")
                        ),
                    }
                )
            if len(findings) >= limit:
                return findings

        requires = str(pin.get("requires") or "").strip().lower()
        if requires and requirements and requires not in requirements:
            findings.append(
                {
                    "code": "pinned_dependency_undeclared",
                    "severity": "critical",
                    "file": "requirements.txt",
                    "detail": (
                        f"`{module}` is imported but its distribution `{requires}` is not in the "
                        f"requirements manifest. It resolves in the build environment and will not "
                        f"resolve in the deployed one."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings

    return findings


def run_pinned_dependency_check(
    product_id: str,
    data_root: str,
    charter: str,
) -> dict[str, Any]:
    """QA-stage entry point: ``{passed, skipped, issues, declared}``.

    Shaped like the other module-health checks so ``agents/qa.py`` can fold the issues into the
    same list without special-casing, and reports ``declared`` unconditionally — "the gate ran
    and found nothing" and "the gate never ran" have already produced identical logs in this
    pipeline once.
    """
    from core.charter_contracts import charter_contract_report

    report = charter_contract_report(charter or "")
    pins = report["pinned_dependencies"]
    malformed = [m for m in report["malformed"] if m["block"] == "pinned dependency"]

    if not pins and not malformed:
        return {"passed": True, "skipped": True, "reason": "no pinned dependency declared",
                "declared": 0, "issues": []}

    issues: list[dict[str, Any]] = [
        {
            "code": "pinned_dependency_malformed",
            "severity": "critical",
            "file": "charter",
            "detail": (
                f"Charter block '{m['section']}' cannot be enforced: {m['detail']}. "
                f"An unenforceable pin reads as protection and provides none."
            ),
        }
        for m in malformed
    ]

    if pins:
        code_dir = Path(data_root) / "code" / product_id
        issues.extend(check_pinned_dependencies(code_dir, pins))

    blocking = [i for i in issues if i.get("blocking", True)]
    return {
        "passed": not blocking,
        "skipped": False,
        "declared": len(pins),
        "issues": issues,
    }
