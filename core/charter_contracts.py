"""Machine-readable charter blocks the pipeline *enforces* rather than interprets.

``charter_fidelity`` established that an operator can mark a charter section and have the
pipeline check it deterministically, with no model call. This module adds two more marked
blocks, for the two failures a prose charter cannot prevent.

**Reimplementation.** The factory's instinct, under repair pressure, is to write a new module
rather than call the existing one. ``duplicate_module_check`` was written because a developer
agent answered "cannot import get_password_hash" by writing a fifth seeding module, and
``foreign_subsystem`` because it built a 478-line BI dashboard nobody ordered. Both are the
same reflex one level down from the case that matters here: a product whose correctness rests
on an existing, verified module — a signer, a verifier, a sampler — and an agent that helpfully
writes its own. The prose "import this, do not reimplement it" is not enforceable, and the
resulting code compiles, passes the demo journey, and is wrong.

**Silent incorrectness.** Every gate in the pipeline today is structural: does the API match
the contract, does the frontend build, does the demo journey authenticate, do the modules
import. None of them can see that a function is *wrong* while being well-formed. That gap is
not hypothetical in this repository, and it has cost us three separate live bugs of one shape:

* ``platon`` published a randomness output not derived from its committed entropy and signed it
  with the real key — a proof that verifies whatever you hand it. Both copies of platon had it.
  The regression is ``oracles/oracles/platon/backend/tests/test_randomness.py:117``.
* ``sortes`` had a missing-Y challenge bug, and separately a wire-format bug where the prover
  emitted ``alpha`` as bare hex while the verifier decoded it as UTF-8 — so **every honest proof
  the oracle issued verified as false**. See ``oracles/oracles/sortes/tests/test_vrf.py``.
* ``basanos`` flags ``createPool`` as a first-caller-wins permanent binding for the same reason:
  a call whose result does not depend on what it claims to depend on.

All three are one defect: **the output does not depend on the thing it is claimed to depend
on.** A verifier that ignores its proof, a sampler that ignores its randomness, a signature
check that returns true regardless. Nothing crashes. The JSON is plausible. A structural gate
cannot tell the difference, and neither can a reviewer reading a diff.

So the operator can declare *executable properties*: statements about the built product that
the QA stage checks by running it. Not a test the agents write — agents write tests that pass —
but a property the operator states and the pipeline enforces from outside.

Both blocks are parsed here and enforced elsewhere
(``web.backend.services.pinned_dependency_gate`` and
``web.backend.services.property_contract_gate``), so a charter can be validated before a build
starts rather than after one fails.

Block syntax follows the charter's existing section convention::

    ====== pinned dependency ======
    module: oracles.oracles.sortes.sortes.vrf
    symbols: prove, verify, proof_to_hash
    why: RFC 9381 ECVRF, byte-exact against the Appendix B.3 vectors. A reimplementation
         produces proofs that verify anything.

    ====== executable property ======
    name: the selection depends on the randomness
    kind: sensitive
    target: app.sampling:select
    args: {"roster_digest": "a3f1", "k": 5}
    vary: alpha

Continuation lines are indented, as in the ``why:`` above. Unknown keys are preserved rather
than dropped: a typo in an optional key should not silently disable a property, and the gate
reports what it did not understand.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

PINNED_MARKER = "pinned dependency"
PROPERTY_MARKER = "executable property"

# What a declared property can assert. Deliberately small: each kind is a check the gate can
# run without knowing anything about the product, and a kind nobody enforces is worse than no
# kind at all because it reads as coverage.
PROPERTY_KINDS = frozenset(
    {
        # Same inputs, same output, every time. Catches an unseeded `random`, a clock read,
        # a dict iteration order leaking into a result.
        "deterministic",
        # Changing the named input MUST change the output. This is the vacuous-proof gate in
        # general form, and the one that would have caught all three bugs above.
        "sensitive",
        # Output elements are pairwise distinct. A k-of-n draw without replacement that
        # returns duplicates is wrong in a way no schema notices.
        "distinct",
        # Output distribution over `buckets` is uniform at significance `alpha`. The modulo-bias
        # catcher: a biased sampler is correct-looking on any single call.
        "uniform",
        # f(g(x)) == x. Catches the sortes alpha bug directly: prover and verifier disagreeing
        # on a wire format is invisible until you compose them.
        "roundtrip",
    }
)

# `====== title ======`, the convention charter_fidelity already reads.
_SECTION_RE = re.compile(r"^=+\s*(?P<title>.+?)\s*=+\s*$", re.M)
# `key: value`, with indented continuation lines folded into the value.
_KEY_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_]*)\s*:\s*(?P<value>.*)$")


def _sections(charter: str) -> list[tuple[str, str]]:
    """``[(title, body)]`` for every ``====== ... ======`` section, in document order."""
    if not charter:
        return []
    out: list[tuple[str, str]] = []
    marks = list(_SECTION_RE.finditer(charter))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(charter)
        out.append((m.group("title").strip(), charter[m.end() : end].strip()))
    return out


def _parse_fields(body: str) -> dict[str, str]:
    """Fold ``key: value`` lines, joining indented continuations onto the previous key.

    Order is preserved by dict insertion, which matters only for error messages.
    """
    fields: dict[str, str] = {}
    current: str | None = None
    for raw in body.splitlines():
        if not raw.strip():
            continue
        # An indented line continues the previous value. Checked before the key pattern so a
        # continuation that happens to contain a colon ("why: see RFC 9381 §5.5: the encoding")
        # does not start a bogus key.
        if current and (raw[:1].isspace()) and not raw.strip().startswith("="):
            fields[current] = f"{fields[current]} {raw.strip()}".strip()
            continue
        m = _KEY_RE.match(raw.strip())
        if m:
            current = m.group("key")
            fields[current] = m.group("value").strip()
            continue
        # A line that is neither indented nor `key: value` is PROSE, and it ends the field list.
        # This used to fall through to "append to the current value", which quietly ate the
        # paragraph that followed a block: a section runs to the next `======` marker, so the
        # explanatory sentence after the last property folded into its `args:` value and the
        # whole property came back malformed with `Extra data: line 1 column 74`. Caught on the
        # first real charter written against this parser — an operator who explains a block
        # underneath it is doing the normal thing, and a parser that punishes it is the bug.
        current = None
    return fields


def _split_list(value: str) -> list[str]:
    """``"a, b c"`` -> ``["a", "b", "c"]``. Commas or whitespace, because both get typed."""
    return [p for p in re.split(r"[,\s]+", value.strip()) if p]


def pinned_dependencies(charter: str) -> list[dict[str, Any]]:
    """Modules the product must import and must not reimplement.

    A block missing ``module`` or ``symbols`` is returned with ``malformed`` set rather than
    dropped: an operator who pinned a dependency and mistyped the key should be told, not
    quietly left unprotected. That failure mode — a gate silently doing nothing and looking
    exactly like a gate finding nothing — has already cost a night of guessing in this
    pipeline (see the unconditional log in ``agents/qa.py`` for the unchartered-subsystem
    check).
    """
    out: list[dict[str, Any]] = []
    for title, body in _sections(charter):
        if PINNED_MARKER not in title.lower():
            continue
        f = _parse_fields(body)
        module = f.get("module", "").strip()
        symbols = _split_list(f.get("symbols", ""))
        entry: dict[str, Any] = {
            "module": module,
            "symbols": symbols,
            # Optional, and it was missing from this dict for a while: the gate's
            # `pinned_dependency_undeclared` check reads it, so leaving it out meant that check
            # could never fire. It went unnoticed because the gate's own tests build their pin
            # dicts by hand and supplied `requires` themselves — the parser, the thing actually
            # under test, was bypassed. Caught only when a real charter was parsed end to end.
            "requires": f.get("requires", "").strip(),
            "why": f.get("why", "").strip(),
            "section": title,
        }
        missing = [k for k, v in (("module", module), ("symbols", symbols)) if not v]
        if missing:
            entry["malformed"] = f"missing required key(s): {', '.join(missing)}"
        out.append(entry)
    return out


def _coerce_args(raw: str, *, section: str) -> tuple[dict[str, Any], str | None]:
    """Parse an ``args:`` value as JSON. Returns ``(args, error)``."""
    if not raw:
        return {}, None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return {}, f"args is not valid JSON ({exc})"
    if not isinstance(parsed, dict):
        return {}, "args must be a JSON object of keyword arguments"
    return parsed, None


def executable_properties(charter: str) -> list[dict[str, Any]]:
    """Properties the built product must satisfy, checked by running it.

    Each entry carries the ``kind``, the ``target`` as ``module.path:callable``, the keyword
    ``args`` to call it with, and whatever that kind needs (``vary`` for ``sensitive``,
    ``buckets``/``trials``/``alpha`` for ``uniform``, ``inverse`` for ``roundtrip``).

    Validation happens here so a malformed property is a charter problem reported before the
    build, not a gate that quietly passes after it.
    """
    out: list[dict[str, Any]] = []
    for title, body in _sections(charter):
        if PROPERTY_MARKER not in title.lower():
            continue
        f = _parse_fields(body)
        kind = f.get("kind", "").strip().lower()
        target = f.get("target", "").strip()
        name = f.get("name", "").strip() or target or kind or title
        args, args_err = _coerce_args(f.get("args", "").strip(), section=title)

        entry: dict[str, Any] = {
            "name": name,
            "kind": kind,
            "target": target,
            "args": args,
            "section": title,
        }

        problems: list[str] = []
        if not kind:
            problems.append("missing required key: kind")
        elif kind not in PROPERTY_KINDS:
            problems.append(
                f"unknown kind {kind!r}; supported: {', '.join(sorted(PROPERTY_KINDS))}"
            )
        if not target:
            problems.append("missing required key: target")
        elif ":" not in target:
            problems.append(
                f"target {target!r} must be 'module.path:callable' so the gate can import it"
            )
        if args_err:
            problems.append(args_err)

        # Per-kind requirements. Stated here rather than in the runner so a charter can be
        # rejected before a build is spent on it.
        if kind == "sensitive":
            vary = f.get("vary", "").strip()
            if not vary:
                problems.append(
                    "kind 'sensitive' needs 'vary: <arg name>' — the input the output must depend on"
                )
            elif args and vary not in args:
                problems.append(f"vary={vary!r} is not one of the declared args ({', '.join(args)})")
            entry["vary"] = vary
        elif kind == "uniform":
            entry["vary"] = f.get("vary", "").strip()
            if not entry["vary"]:
                problems.append(
                    "kind 'uniform' needs 'vary: <arg name>' — the input resampled between trials"
                )
            entry["buckets"] = _positive_int(f.get("buckets"), default=0)
            entry["trials"] = _positive_int(f.get("trials"), default=0)
            entry["alpha"] = _positive_float(f.get("alpha"), default=0.001)
            if entry["buckets"] < 2:
                problems.append("kind 'uniform' needs 'buckets: <n >= 2>'")
            if entry["trials"] < 1:
                problems.append("kind 'uniform' needs 'trials: <n >= 1>'")
        elif kind == "roundtrip":
            inverse = f.get("inverse", "").strip()
            if not inverse:
                problems.append(
                    "kind 'roundtrip' needs 'inverse: module.path:callable' to compose against"
                )
            elif ":" not in inverse:
                problems.append(f"inverse {inverse!r} must be 'module.path:callable'")
            entry["inverse"] = inverse
        elif kind in ("deterministic", "distinct"):
            entry["trials"] = _positive_int(f.get("trials"), default=32)
            if kind == "deterministic":
                # A deterministic check with one trial proves nothing.
                entry["trials"] = max(2, entry["trials"])

        if problems:
            entry["malformed"] = "; ".join(problems)
        out.append(entry)
    return out


def _positive_int(raw: object, *, default: int) -> int:
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


def _positive_float(raw: object, *, default: float) -> float:
    try:
        v = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return v if 0.0 < v < 1.0 else default


def charter_contract_report(charter: str) -> dict[str, Any]:
    """Everything the enforcing gates need, plus the charter's own errors.

    ``malformed`` is separated out because it is the operator's problem, not the factory's:
    a mistyped property must not read as a satisfied one, and the pipeline should say so
    before spending a build.
    """
    pins = pinned_dependencies(charter or "")
    props = executable_properties(charter or "")
    malformed = [
        {"block": PINNED_MARKER, "section": p["section"], "detail": p["malformed"]}
        for p in pins
        if p.get("malformed")
    ] + [
        {"block": PROPERTY_MARKER, "section": p["section"], "detail": p["malformed"]}
        for p in props
        if p.get("malformed")
    ]
    return {
        "pinned_dependencies": [p for p in pins if not p.get("malformed")],
        "executable_properties": [p for p in props if not p.get("malformed")],
        "malformed": malformed,
        "declared": {"pinned": len(pins), "properties": len(props)},
    }
