"""`input_from` names the parent whose result a hop receives.

The field is declared as a node id — ``input_from: str | None`` with a 64-character cap —
and was implemented as a boolean: any truthy value injected ``context``, a single variable
holding whichever hop happened to finish last. In a straight chain those coincide, which is
why it went unnoticed. In a DAG they do not: a node with two parents received the result of
whichever parent the topological sort finished second. A fan-in graph could therefore be
drawn, priced, paid for, and fed from the wrong upstream — silently, with a valid signature
over the bill of materials.

That made every multi-parent graph a lie, so a visual builder could not honestly emit one.

Backward compatibility is deliberate and pinned below: a value that does not name a known
node keeps the old last-result behaviour, because existing callers pass flag-ish values.

Import note: mirrors ``test_pipeline_blame.py``.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

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


def _stub(monkeypatch, tmp_path):
    """Every hop returns a result tagged with its own capability id; record the inputs."""
    seen: dict[str, dict] = {}

    async def fake_invoke(**kw):
        seen[kw["capability_id"]] = kw["body_input"]
        return (
            200,
            {"success": True, "price_usd": 0.0,
             "result": {"from": kw["capability_id"]},
             "receipt": {"nonce": f"rn_{kw['capability_id']}"}},
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


def _node(nid, cap, *, depends_on=(), input_from=None, inp=None):
    node = {
        "id": nid, "product_id": f"p-{nid}", "capability_id": cap,
        "input": dict(inp or {}), "depends_on": list(depends_on),
    }
    if input_from is not None:
        node["input_from"] = input_from
    return node


class TestFanInIsFedFromTheNamedParent:
    def test_a_diamond_feeds_the_parent_it_names(self, tmp_path, monkeypatch):
        """a → (b, c) → d. `d` names `b`; it must not get `c` because `c` ran last."""
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], input_from="a"),
            _node("c", "c@v1", depends_on=["a"], input_from="a"),
            _node("d", "d@v1", depends_on=["b", "c"], input_from="b"),
        ])
        assert seen["d@v1"]["context"] == {"from": "b@v1"}

    def test_the_other_branch_is_reachable_too(self, tmp_path, monkeypatch):
        """Same graph, `d` names `c` — proves the choice is honoured, not coincidence."""
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], input_from="a"),
            _node("c", "c@v1", depends_on=["a"], input_from="a"),
            _node("d", "d@v1", depends_on=["b", "c"], input_from="c"),
        ])
        assert seen["d@v1"]["context"] == {"from": "c@v1"}

    def test_a_far_ancestor_can_be_named(self, tmp_path, monkeypatch):
        """Results are kept per node, so wiring is not limited to immediate parents."""
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], input_from="a"),
            _node("c", "c@v1", depends_on=["b"], input_from="a"),
        ])
        assert seen["c@v1"]["context"] == {"from": "a@v1"}


class TestBackwardCompatibility:
    def test_an_unknown_name_keeps_the_last_result(self, tmp_path, monkeypatch):
        """Existing callers pass flag-ish values; they must behave exactly as before."""
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], input_from="prev"),
        ])
        assert seen["b@v1"]["context"] == {"from": "a@v1"}

    def test_a_chain_is_unchanged(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], input_from="yes"),
            _node("c", "c@v1", depends_on=["b"], input_from="yes"),
        ])
        assert seen["b@v1"]["context"] == {"from": "a@v1"}
        assert seen["c@v1"]["context"] == {"from": "b@v1"}

    def test_no_input_from_means_no_context(self, tmp_path, monkeypatch):
        """Opting out must stay opt-out: no upstream data appears uninvited."""
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], inp={"q": 1}),
        ])
        assert seen["b@v1"] == {"q": 1}

    def test_the_first_hop_gets_no_empty_context_key(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path)
        _run([_node("a", "a@v1", input_from="whatever", inp={"q": 1})])
        assert seen["a@v1"] == {"q": 1}

    def test_an_explicit_context_input_wins(self, tmp_path, monkeypatch):
        """`setdefault` semantics: what the caller wrote is never overwritten."""
        seen = _stub(monkeypatch, tmp_path)
        _run([
            _node("a", "a@v1"),
            _node("b", "b@v1", depends_on=["a"], input_from="a",
                  inp={"context": {"mine": True}}),
        ])
        assert seen["b@v1"]["context"] == {"mine": True}
