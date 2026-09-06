"""Hop-level blame attribution in the pipeline bill-of-materials.

A pipeline failure is the FAILING hop's fault, never the whole graph's: the signed
BoM must identify the at-fault hop and explicitly clear upstream successful hops so
a dispute (and any resulting slash) targets only the responsible provider.

Import note: ``ai_market_protocol/__init__`` pulls the payment/commerce stack
(passlib etc.) that not every test venv carries. ``pipelines`` itself only needs
``get_channel`` and ``invoke_capability_v1`` — both stubbed per-test in ``_stub`` — so when
(and only when) the real import fails, we install a lightweight package shim and stub
those two siblings. In a full venv the real modules load and nothing is shimmed.
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
    import web.backend.services  # light parents; only ai_market_protocol/__init__ is heavy

    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(_REPO / "web/backend/services/ai_market_protocol")]
    sys.modules[_PKG] = pkg

    channels_stub = types.ModuleType(f"{_PKG}.channels")
    channels_stub.get_channel = lambda channel_id: {"status": "open"}
    sys.modules[f"{_PKG}.channels"] = channels_stub

    invoke_stub = types.ModuleType(f"{_PKG}.invoke")

    async def _unpatched(**_kw):  # every test monkeypatches over this
        raise AssertionError("invoke_capability_v1 must be stubbed by the test")

    invoke_stub.invoke_capability_v1 = _unpatched
    sys.modules[f"{_PKG}.invoke"] = invoke_stub

    import web.backend.services.ai_market_protocol.pipelines as pl

NODES = [
    {"id": "a", "product_id": "p1", "capability_id": "ok@v1", "input": {}, "depends_on": []},
    {"id": "b", "product_id": "p2", "capability_id": "bad@v1", "input": {}, "depends_on": ["a"]},
    {"id": "c", "product_id": "p3", "capability_id": "ok@v1", "input": {}, "depends_on": ["b"]},
]


def _stub(monkeypatch, tmp_path, fail_caps: set[str]):
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


def _run(nodes):
    return asyncio.run(pl.execute_pipeline(nodes=nodes, channel_id=None, base_url="http://t"))


def test_blame_targets_only_the_failing_hop(tmp_path, monkeypatch):
    _stub(monkeypatch, tmp_path, fail_caps={"bad@v1"})
    out = _run(NODES)
    bom = out["bill_of_materials"]
    blame = bom["blame"]
    assert blame["policy"] == "hop-level"
    assert blame["at_fault"]["id"] == "b"
    assert blame["at_fault"]["product_id"] == "p2"
    assert blame["at_fault"]["status_code"] == 500
    # Upstream hop settled independently and is explicitly cleared.
    assert blame["not_at_fault"] == ["a"]
    # Downstream hop never ran — it is neither at fault nor cleared.
    assert blame["not_executed"] == ["c"]
    # The blame block is inside the SIGNED BoM (portable dispute evidence).
    assert bom["signature"]


def test_successful_pipeline_has_no_blame(tmp_path, monkeypatch):
    _stub(monkeypatch, tmp_path, fail_caps=set())
    out = _run(NODES)
    bom = out["bill_of_materials"]
    assert bom["blame"] is None
    assert [s["id"] for s in bom["steps"]] == ["a", "b", "c"]
