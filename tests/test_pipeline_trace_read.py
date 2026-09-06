"""Reading back a pipeline's bill of materials.

The executor signs a BoM per run and persists it, and until now nothing could read it:
no route, no service function. Hop-level blame — the evidence a dispute and any resulting
slash rests on — was visible only to whoever made the original POST, and the monitor could
show a topology of services that had, as far as anything observable went, never traded.

Two doors, deliberately different:

  * by id — the signed object verbatim, because a signature covers the object as written
    and anything filtered out of it hands back something unverifiable
  * the listing — a REDACTED projection, because enumerating runs turns per-trace
    obscurity into a public feed of who bought what. The payment channel and the per-hop
    receipt nonces (a lookup key for a public receipt carrying an amount) stay out of it.

The projection tests are the ones that matter: a leak here is invisible in the happy path.

Import note: mirrors ``test_pipeline_blame.py`` — ``ai_market_protocol/__init__`` pulls the
commerce stack that not every test venv carries, so fall back to a package shim.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PKG = "web.backend.services.ai_market_protocol"

try:
    import web.backend.services.ai_market_protocol.pipelines as pl
except Exception:  # lean venv: bypass the heavy package __init__
    import web.backend.services  # noqa: F401 — light parents

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

NODES = [
    {"id": "a", "product_id": "p1", "capability_id": "ok@v1", "input": {}, "depends_on": []},
    {"id": "b", "product_id": "p2", "capability_id": "bad@v1", "input": {}, "depends_on": ["a"]},
    {"id": "c", "product_id": "p3", "capability_id": "ok@v1", "input": {}, "depends_on": ["b"]},
]

GOOD_NODES = [
    {"id": "a", "product_id": "p1", "capability_id": "ok@v1", "input": {}, "depends_on": []},
    {"id": "b", "product_id": "p2", "capability_id": "ok@v1", "input": {}, "depends_on": ["a"]},
]


def _stub(monkeypatch, tmp_path, fail_caps=frozenset()):
    async def fake_invoke(**kw):
        if kw["capability_id"] in fail_caps:
            return 500, {"success": False, "error": "provider exploded"}, {}
        return (
            200,
            {"success": True, "price_usd": 0.1, "result": {"ok": True},
             "receipt": {"nonce": f"rn_{kw['capability_id']}"}},
            {},
        )

    monkeypatch.setattr(pl, "invoke_capability_v1", fake_invoke)
    # `pipelines.py` does `from ...channels import get_channel`, so the name lives on
    # this module and has to be patched HERE. The package shim below only installs a
    # channels stub when the heavy `ai_market_protocol.__init__` fails to import — so in
    # a venv that carries the commerce stack (CI, and any full install) the real lookup
    # ran, returned nothing, and every run came back `{"error": "invalid_channel"}`.
    # These tests were passing only where a dependency was missing.
    monkeypatch.setattr(pl, "get_channel", lambda channel_id: {"status": "open"})
    # These exercise the executor's own logic, so every hop stays on the local
    # invoke rather than being routed to the federation hub.
    monkeypatch.setattr(pl, "hosted_here", lambda pid, cid: True)
    monkeypatch.setattr(pl, "pipelines_path", lambda: tmp_path / "pipelines.json")
    monkeypatch.setattr(pl, "sign_payload", lambda b: "test-signature")
    monkeypatch.setattr(pl, "append_stat", lambda s: None)


def _run(nodes, channel_id="ch_secret_1"):
    return asyncio.run(
        pl.execute_pipeline(nodes=nodes, channel_id=channel_id, base_url="http://t")
    )


class TestByIdIsTheSignedObject:
    def test_the_stored_bom_comes_back_verbatim(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        out = _run(GOOD_NODES)
        trace_id = out["trace_id"]

        assert pl.get_trace(trace_id) == out["bill_of_materials"]

    def test_an_unknown_id_is_absent_not_empty(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        _run(GOOD_NODES)
        assert pl.get_trace("tr_doesnotexist") is None

    def test_a_missing_store_is_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pl, "pipelines_path", lambda: tmp_path / "nope.json")
        assert pl.get_trace("tr_anything") is None
        assert pl.list_traces() == []

    def test_a_corrupt_store_does_not_take_the_route_down(self, tmp_path, monkeypatch):
        path = tmp_path / "pipelines.json"
        path.write_text("{ this is not json", encoding="utf-8")
        monkeypatch.setattr(pl, "pipelines_path", lambda: path)
        assert pl.list_traces() == []
        assert pl.get_trace("tr_x") is None


class TestTheListingIsRedacted:
    def test_the_payment_channel_is_never_enumerated(self, tmp_path, monkeypatch):
        """The BoM records which channel funded the run; a feed must not publish it."""
        _stub(monkeypatch, tmp_path)
        out = _run(GOOD_NODES, channel_id="ch_secret_1")
        assert out["bill_of_materials"]["channel_id"] == "ch_secret_1"

        blob = json.dumps(pl.list_traces())
        assert "ch_secret_1" not in blob
        assert "channel_id" not in blob

    def test_receipt_nonces_are_never_enumerated(self, tmp_path, monkeypatch):
        """A nonce is the lookup key for a public receipt with an amount on it."""
        _stub(monkeypatch, tmp_path)
        out = _run(GOOD_NODES)
        assert out["bill_of_materials"]["steps"][0]["receipt_nonce"] == "rn_ok@v1"

        blob = json.dumps(pl.list_traces())
        assert "rn_ok@v1" not in blob
        assert "receipt_nonce" not in blob

    def test_a_row_says_where_its_signed_original_lives(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        trace_id = _run(GOOD_NODES)["trace_id"]
        row = pl.list_traces()[0]
        assert row["signed"] is True
        assert row["trace_path"] == f"/ai-market/pipelines/{trace_id}"

    def test_cost_and_hops_survive_the_redaction(self, tmp_path, monkeypatch):
        """Redacting must not gut the projection — cost per run is the point of it."""
        _stub(monkeypatch, tmp_path)
        _run(GOOD_NODES)
        row = pl.list_traces()[0]
        assert row["hops"] == 2
        assert row["total_usd"] == 0.2
        assert row["failed"] is False
        assert [s["capability_id"] for s in row["steps"]] == ["ok@v1", "ok@v1"]
        assert row["steps"][0]["price_usd"] == 0.1


class TestBlameSurvivesTheProjection:
    def test_the_at_fault_hop_is_named_without_its_receipt(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path, fail_caps={"bad@v1"})
        _run(NODES)
        row = pl.list_traces()[0]

        assert row["failed"] is True
        blame = row["blame"]
        assert blame["policy"] == "hop-level"
        assert blame["at_fault"]["id"] == "b"
        assert blame["at_fault"]["capability_id"] == "bad@v1"
        assert blame["at_fault"]["status_code"] == 500
        assert "receipt_nonce" not in blame["at_fault"]
        assert blame["not_at_fault"] == ["a"]
        assert blame["not_executed"] == ["c"]

    def test_a_clean_run_carries_no_blame(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        _run(GOOD_NODES)
        row = pl.list_traces()[0]
        assert row["blame"] is None
        assert row["failed"] is False


class TestListingOrderAndBounds:
    def test_newest_first(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        first = _run(GOOD_NODES)["trace_id"]
        second = _run(GOOD_NODES)["trace_id"]

        ordered = [row["trace_id"] for row in pl.list_traces()]
        assert ordered.index(second) < ordered.index(first)

    def test_limit_is_clamped_not_trusted(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        for _ in range(3):
            _run(GOOD_NODES)

        assert len(pl.list_traces(limit=2)) == 2
        assert len(pl.list_traces(limit=0)) == 1        # floored, never an empty answer
        assert len(pl.list_traces(limit=10_000)) == 3   # ceiling, never the whole store
