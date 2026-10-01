"""Field-level references between pipeline hops: ``${node.field}``.

Before this, a hop could only receive the WHOLE result of one upstream hop, injected under
the key ``context`` (see ``input_from``). Providers do not read ``context`` — they read
their own declared fields, ``reading``, ``claim``, ``seed`` — so a chain could be ordered
and paid for while no data actually reached the field it was meant for. That is the
difference between a list of billed steps and a pipeline.

A reference is a string that is exactly ``${id}`` or ``${id.path.to.field}``:

    {"reading": "${sensor}"}            → the whole result of hop `sensor`
    {"claim":   "${sensor.summary}"}    → one field out of it
    {"note": "seen at ${sensor.ts}"}    → interpolated into the surrounding text

Two rules keep this from becoming a source of silent wrong answers:

* A reference that names a hop which does not exist, or which cannot run before this one,
  is a defect in the GRAPH. It is rejected at submit time, before a single paid invoke —
  charging for half a pipeline that could never complete is not an acceptable failure mode.
* A reference whose *field* is missing at run time is a defect in the RUN (the upstream
  returned something else than expected). It fails that hop with a named reason rather
  than sending the literal text ``${sensor.summary}`` to a provider, which would either be
  rejected as garbage or, worse, accepted and paid for.
"""

from __future__ import annotations

import re
from typing import Any

# `${a}` / `${a.b.c}` — ids are the node ids the executor already uses, so the same
# character class: anything but a brace, a dot or whitespace.
_REF = re.compile(r"\$\{([^{}\s.]+)((?:\.[^{}\s.]+)*)\}")


class UnresolvedReference(ValueError):
    """A reference could not be filled from the results available at run time."""


def _walk(value: Any, path: tuple[str, ...], *, origin: str) -> Any:
    current = value
    for step in path:
        if isinstance(current, dict) and step in current:
            current = current[step]
            continue
        if isinstance(current, list):
            try:
                current = current[int(step)]
                continue
            except (ValueError, IndexError):
                pass
        raise UnresolvedReference(
            f"{origin} does not contain {'.'.join(path)!r}"
        )
    return current


def references_in(value: Any) -> set[str]:
    """Every hop id referenced anywhere inside a node's input."""
    found: set[str] = set()
    if isinstance(value, str):
        for match in _REF.finditer(value):
            found.add(match.group(1))
    elif isinstance(value, dict):
        for item in value.values():
            found |= references_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= references_in(item)
    return found


def resolve(value: Any, results: dict[str, Any]) -> Any:
    """Replace references with values from ``results``.

    A string that is exactly one reference becomes the referenced VALUE — an object stays
    an object, so ``{"reading": "${sensor}"}`` hands over a dict rather than its repr. A
    reference embedded in surrounding text is interpolated as text, which is the only thing
    that can be meant there.
    """
    if isinstance(value, str):
        whole = _REF.fullmatch(value.strip())
        if whole:
            node_id, dotted = whole.group(1), whole.group(2)
            if node_id not in results:
                raise UnresolvedReference(f"hop {node_id!r} has no result to read from")
            path = tuple(p for p in dotted.split(".") if p)
            return _walk(results[node_id], path, origin=f"result of {node_id!r}")

        def _sub(match: re.Match[str]) -> str:
            node_id, dotted = match.group(1), match.group(2)
            if node_id not in results:
                raise UnresolvedReference(f"hop {node_id!r} has no result to read from")
            path = tuple(p for p in dotted.split(".") if p)
            resolved = _walk(results[node_id], path, origin=f"result of {node_id!r}")
            # Interpolating a dict into prose is never what was meant; say so instead of
            # pasting a Python repr into a paid provider's input.
            if isinstance(resolved, (dict, list)):
                raise UnresolvedReference(
                    f"{match.group(0)} resolves to a {type(resolved).__name__} and cannot be "
                    "placed inside text — reference it as the whole value instead"
                )
            return "" if resolved is None else str(resolved)

        return _REF.sub(_sub, value)

    if isinstance(value, dict):
        return {k: resolve(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, results) for v in value]
    return value


def validate_graph(nodes: list[dict[str, Any]]) -> list[str]:
    """Reasons this graph's references can never resolve. Empty means it can run.

    Checked before anything is invoked: a reference to an unknown hop, to the hop itself,
    or to a hop that does not run first is a graph the author has to fix, and no part of it
    should be billed on the way to finding that out.
    """
    problems: list[str] = []
    ids = [str(n.get("id") or f"n{i}") for i, n in enumerate(nodes)]
    known = set(ids)

    # Which hops are guaranteed to have run before this one: its declared dependencies,
    # transitively. `depends_on` is what the executor orders by, so anything outside that
    # closure may or may not have a result yet — and "may" is not good enough to bill for.
    deps: dict[str, set[str]] = {}
    declared = {
        nid: {str(d) for d in (node.get("depends_on") or [])}
        for nid, node in zip(ids, nodes)
    }

    def ancestors(nid: str, seen: frozenset[str] = frozenset()) -> set[str]:
        if nid in deps:
            return deps[nid]
        if nid in seen:  # a cycle; the executor reports it separately
            return set()
        out: set[str] = set()
        for parent in declared.get(nid, set()):
            out.add(parent)
            out |= ancestors(parent, seen | {nid})
        deps[nid] = out
        return out

    for nid, node in zip(ids, nodes):
        for referenced in sorted(references_in(node.get("input") or {})):
            if referenced == nid:
                problems.append(f"hop {nid!r} references its own result")
            elif referenced not in known:
                problems.append(f"hop {nid!r} references unknown hop {referenced!r}")
            elif referenced not in ancestors(nid):
                problems.append(
                    f"hop {nid!r} references {referenced!r}, which is not among its "
                    f"dependencies — add it to depends_on so it runs first"
                )
    return problems
