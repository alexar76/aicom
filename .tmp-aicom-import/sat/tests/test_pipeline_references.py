"""`${hop.field}` — the difference between billed steps and a pipeline.

Before this, a hop could receive only the WHOLE result of one upstream hop, under the key
``context``. Providers read their own declared fields — ``reading``, ``claim``, ``seed`` —
so a chain could be drawn, priced, paid for, and complete without the data ever arriving
where it was meant to go. The studio could not honestly offer a two-hop example for
exactly this reason.

Two failure modes get most of the attention here, because both cost money:

  * a graph whose references can NEVER resolve is refused before the first invoke. Finding
    that out on hop three means hops one and two were already charged for.
  * a reference whose field is missing at RUN time fails that hop by name instead of
    posting the literal text ``${sensor.summary}`` to a paid provider, which would either
    be rejected as garbage or accepted and billed.

Import note: mirrors ``test_pipeline_blame.py``.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_PKG = "web.backend.services.ai_market_protocol"

try:
    import web.backend.services.ai_market_protocol.pipelines as pl
except Exception:  # lean venv: bypass the heavy package __init__
    import web.backend.services  # noqa: F401

    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(_REPO / "web/backend/services/ai_market_protocol")]
    sys.modules[_PKG] = pkg

    channels_stub = types.ModuleType(f"{_PKG}.channels")
    channels_stub.get_channel = lambda channel_id: {"status": "open"}
    sys.modules[f"{_PKG}.channels"] = channels_stub

    invoke_stub = types.ModuleType(f"{_PKG}.invoke")

    async def _unpatched(**_kw):
        raise AssertionError("invoke_capability_v1 must be stubbed by the test")

    invoke_stub.invoke_capability_v1 = _unpatched
    sys.modules[f"{_PKG}.invoke"] = invoke_stub

    import web.backend.services.ai_market_protocol.pipelines as pl

from web.backend.services.ai_market_protocol.references import (  # noqa: E402
    UnresolvedReference,
    references_in,
    resolve,
    validate_graph,
)


# ── the resolver itself ───────────────────────────────────────────────────────
class TestResolve:
    def test_a_whole_reference_keeps_the_value_s_type(self):
        """`{"reading": "${a}"}` must hand over a dict, not its repr."""
        out = resolve({"reading": "${a}"}, {"a": {"c": 21.5, "unit": "C"}})
        assert out == {"reading": {"c": 21.5, "unit": "C"}}

    def test_a_dotted_path_picks_one_field(self):
        out = resolve({"claim": "${a.summary}"}, {"a": {"summary": "warm", "c": 21.5}})
        assert out == {"claim": "warm"}

    def test_a_deep_path_and_a_list_index(self):
        results = {"a": {"rows": [{"id": "x"}, {"id": "y"}]}}
        assert resolve("${a.rows.1.id}", results) == "y"

    def test_a_reference_inside_text_is_interpolated(self):
        out = resolve({"note": "seen at ${a.ts} in ${a.place}"},
                      {"a": {"ts": "12:00", "place": "Berlin"}})
        assert out == {"note": "seen at 12:00 in Berlin"}

    def test_numbers_and_booleans_survive_as_whole_values(self):
        results = {"a": {"n": 32, "ok": True, "none": None}}
        assert resolve("${a.n}", results) == 32
        assert resolve("${a.ok}", results) is True
        assert resolve("${a.none}", results) is None

    def test_nested_structures_are_walked(self):
        out = resolve(
            {"outer": {"list": ["${a.x}", {"deep": "${a.y}"}]}, "plain": 1},
            {"a": {"x": "X", "y": "Y"}},
        )
        assert out == {"outer": {"list": ["X", {"deep": "Y"}]}, "plain": 1}

    def test_text_without_references_is_untouched(self):
        assert resolve({"q": "a literal $ and {braces}"}, {}) == {"q": "a literal $ and {braces}"}

    def test_a_missing_hop_is_named(self):
        with pytest.raises(UnresolvedReference, match="'ghost' has no result"):
            resolve("${ghost.x}", {"a": {}})

    def test_a_missing_field_is_named(self):
        with pytest.raises(UnresolvedReference, match="does not contain 'summary'"):
            resolve("${a.summary}", {"a": {"other": 1}})

    def test_an_object_cannot_be_pasted_into_prose(self):
        """Interpolating a dict into text would post a Python repr to a paid provider."""
        with pytest.raises(UnresolvedReference, match="cannot be placed inside text"):
            resolve("value: ${a}", {"a": {"x": 1}})

    def test_references_in_finds_every_hop_mentioned(self):
        assert references_in({"a": "${x.f}", "b": ["${y}", {"c": "t ${z.q} t"}]}) == {"x", "y", "z"}


# ── the pre-flight graph check ────────────────────────────────────────────────
class TestGraphValidation:
    def test_a_sound_graph_has_no_problems(self):
        assert validate_graph([
            {"id": "a", "input": {}},
            {"id": "b", "depends_on": ["a"], "input": {"reading": "${a}"}},
        ]) == []

    def test_an_unknown_hop_is_refused(self):
        problems = validate_graph([{"id": "b", "input": {"x": "${ghost}"}}])
        assert problems and "unknown hop 'ghost'" in problems[0]

    def test_a_self_reference_is_refused(self):
        problems = validate_graph([{"id": "a", "input": {"x": "${a.y}"}}])
        assert problems and "its own result" in problems[0]

    def test_referencing_a_hop_that_does_not_run_first_is_refused(self):
        """Without depends_on the executor may run them in either order."""
        problems = validate_graph([
            {"id": "a", "input": {}},
            {"id": "b", "input": {"x": "${a}"}},          # no depends_on
        ])
        assert problems and "not among its dependencies" in problems[0]

    def test_a_transitive_dependency_counts(self):
        assert validate_graph([
            {"id": "a", "input": {}},
            {"id": "b", "depends_on": ["a"], "input": {}},
            {"id": "c", "depends_on": ["b"], "input": {"x": "${a.f}"}},
        ]) == []

    def test_a_cycle_does_not_hang_the_check(self):
        validate_graph([
            {"id": "a", "depends_on": ["b"], "input": {"x": "${b}"}},
            {"id": "b", "depends_on": ["a"], "input": {"y": "${a}"}},
        ])


# ── the executor ──────────────────────────────────────────────────────────────
def _stub(monkeypatch, tmp_path, outputs=None, fail_caps=frozenset()):
    """Each hop returns the output declared for its capability id; record the inputs."""
    seen: dict[str, dict] = {}
    outputs = outputs or {}

    async def fake_invoke(**kw):
        cap = kw["capability_id"]
        seen[cap] = kw["body_input"]
        if cap in fail_caps:
            return 500, {"success": False, "error": "provider exploded"}, {}
        return (
            200,
            {"success": True, "price_usd": 0.1,
             "result": outputs.get(cap, {"ok": True}),
             "receipt": {"nonce": f"rn_{cap}"}},
            {},
        )

    monkeypatch.setattr(pl, "invoke_capability_v1", fake_invoke)
    # These exercise the executor's own logic, so every hop stays on the local
    # invoke rather than being routed to the federation hub.
    monkeypatch.setattr(pl, "hosted_here", lambda pid, cid: True)
    monkeypatch.setattr(pl, "pipelines_path", lambda: tmp_path / "pipelines.json")
    monkeypatch.setattr(pl, "sign_payload", lambda b: "test-signature")
    monkeypatch.setattr(pl, "append_stat", lambda s: None)
    return seen


def _run(nodes):
    return asyncio.run(pl.execute_pipeline(nodes=nodes, channel_id=None, base_url="http://t"))


class TestExecutorUsesReferences:
    def test_a_field_reaches_the_field_it_was_meant_for(self, tmp_path, monkeypatch):
        """The whole point: `reading`, not `context`."""
        seen = _stub(monkeypatch, tmp_path, outputs={
            "sensor@v1": {"c": 21.5, "summary": "warm"},
        })
        out = _run([
            {"id": "s", "product_id": "p1", "capability_id": "sensor@v1", "input": {}},
            {"id": "v", "product_id": "p2", "capability_id": "verify@v1",
             "depends_on": ["s"], "input": {"reading": "${s}", "claim": "${s.summary}"}},
        ])
        assert seen["verify@v1"] == {"reading": {"c": 21.5, "summary": "warm"}, "claim": "warm"}
        assert "context" not in seen["verify@v1"]
        assert out["bill_of_materials"]["blame"] is None

    def test_a_reference_survives_alongside_input_from(self, tmp_path, monkeypatch):
        """Old callers keep `context`; the reference fills the real field as well."""
        seen = _stub(monkeypatch, tmp_path, outputs={"sensor@v1": {"c": 21.5}})
        _run([
            {"id": "s", "product_id": "p1", "capability_id": "sensor@v1", "input": {}},
            {"id": "v", "product_id": "p2", "capability_id": "verify@v1",
             "depends_on": ["s"], "input_from": "s", "input": {"reading": "${s.c}"}},
        ])
        assert seen["verify@v1"]["reading"] == 21.5
        assert seen["verify@v1"]["context"] == {"c": 21.5}

    def test_a_graph_that_can_never_resolve_costs_nothing(self, tmp_path, monkeypatch):
        """Refused whole, before the first invoke — not discovered on hop three."""
        seen = _stub(monkeypatch, tmp_path)
        out = _run([
            {"id": "a", "product_id": "p1", "capability_id": "first@v1", "input": {}},
            {"id": "b", "product_id": "p2", "capability_id": "second@v1",
             "depends_on": ["a"], "input": {"x": "${ghost.y}"}},
        ])
        assert out["error"] == "unresolvable_references"
        assert any("unknown hop 'ghost'" in p for p in out["problems"])
        assert seen == {}, "nothing may be invoked, and nothing billed"

    def test_a_missing_field_at_run_time_fails_that_hop_by_name(self, tmp_path, monkeypatch):
        """The upstream ran but returned something else. Do not post the literal text."""
        seen = _stub(monkeypatch, tmp_path, outputs={"sensor@v1": {"other": 1}})
        out = _run([
            {"id": "s", "product_id": "p1", "capability_id": "sensor@v1", "input": {}},
            {"id": "v", "product_id": "p2", "capability_id": "verify@v1",
             "depends_on": ["s"], "input": {"reading": "${s.c}"}},
        ])
        assert "verify@v1" not in seen, "the hop must not be invoked with an unresolved value"
        bom = out["bill_of_materials"]
        failed = [s for s in bom["steps"] if not s["success"]]
        assert failed and failed[0]["id"] == "v"
        assert "unresolved reference" in failed[0]["error"]
        assert failed[0]["price_usd"] == 0
        # Blame still points at the hop that could not run, and clears the one that did.
        assert bom["blame"]["at_fault"]["id"] == "v"
        assert bom["blame"]["not_at_fault"] == ["s"]

    def test_the_upstream_hop_is_still_paid_for_its_work(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path, outputs={"sensor@v1": {"other": 1}})
        out = _run([
            {"id": "s", "product_id": "p1", "capability_id": "sensor@v1", "input": {}},
            {"id": "v", "product_id": "p2", "capability_id": "verify@v1",
             "depends_on": ["s"], "input": {"reading": "${s.c}"}},
        ])
        assert out["bill_of_materials"]["total_usd"] == 0.1

    def test_a_three_hop_chain_threads_values_through(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path, outputs={
            "a@v1": {"seed": "s1"},
            "b@v1": {"proof": "p1"},
        })
        _run([
            {"id": "a", "product_id": "p", "capability_id": "a@v1", "input": {}},
            {"id": "b", "product_id": "p", "capability_id": "b@v1",
             "depends_on": ["a"], "input": {"seed": "${a.seed}"}},
            {"id": "c", "product_id": "p", "capability_id": "c@v1",
             "depends_on": ["b", "a"], "input": {"proof": "${b.proof}", "note": "from ${a.seed}"}},
        ])
        assert seen["b@v1"] == {"seed": "s1"}
        assert seen["c@v1"] == {"proof": "p1", "note": "from s1"}
