"""A hop this factory does not host is routed to the hub — on the VISITOR's terms.

The executor resolved every hop against the factory's own nine capabilities. The studio
composes from the hub's seventy-six, every one of them a peer's, so nothing a visitor could
build was runnable: the catalogue and the executor were wired to different inventories.

Routing the miss through the hub is the easy half. The half that needs pinning is money:

  * no credential of this factory is ever attached, so an unauthenticated Run button
    cannot spend the operator's balance;
  * the VISITOR's trial identity is forwarded, because the hub meters its free allowance
    per visitor — dropping the header merges every caller into one bucket and exhausts it
    for everyone, which is the metering bug this ecosystem has already been bitten by;
  * the bill of materials records who actually paid, so a trial run is never signed
    evidence that the factory bought something.

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

from web.backend.services.ai_market_protocol import federated as fed  # noqa: E402

LOCAL = {"id": "l", "product_id": "prod-local", "capability_id": "summarize@v1", "input": {}}
REMOTE = {
    "id": "r", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
    "input": {}, "source_hub": "https://iot.modelmarket.dev",
}


def _stub(monkeypatch, tmp_path, *, local_ids=frozenset(), federated=None):
    """Record what went where: the local invoke, and the federated one."""
    seen: dict[str, dict] = {"local": {}, "federated": {}}

    async def fake_local(**kw):
        seen["local"][kw["capability_id"]] = kw
        return 200, {"success": True, "price_usd": 0.05, "result": {"local": True},
                     "receipt": {"nonce": "rn_local"}}, {}

    async def fake_federated(**kw):
        seen["federated"][kw["capability_id"]] = kw
        return federated or (200, {"success": True, "price_usd": 0.001,
                                   "result": {"reading": {"c": 21.5}},
                                   "receipt": {"nonce": "rn_fed"}})

    monkeypatch.setattr(pl, "invoke_capability_v1", fake_local)
    # `pipelines.py` does `from ...channels import get_channel`, so patch it HERE.
    # The package shim below installs a channels stub only when the heavy
    # `ai_market_protocol.__init__` import fails, so in a venv that carries the
    # commerce stack the real lookup ran and every pipeline came back
    # `{"error": "invalid_channel"}` — these cases were green only where a dependency
    # was missing.
    monkeypatch.setattr(pl, "get_channel", lambda channel_id: {"status": "open"})
    monkeypatch.setattr(pl, "invoke_federated", fake_federated)
    monkeypatch.setattr(pl, "pipelines_path", lambda: tmp_path / "pipelines.json")
    monkeypatch.setattr(pl, "sign_payload", lambda b: "test-signature")
    monkeypatch.setattr(pl, "append_stat", lambda s: None)

    # Patched, not installed into sys.modules: a module planted there outlives this test
    # and re-routes every other suite in the session.
    monkeypatch.setattr(pl, "hosted_here", lambda pid, cid: cid in local_ids)
    return seen


def _run(nodes, **kw):
    return asyncio.run(
        pl.execute_pipeline(nodes=nodes, channel_id=kw.pop("channel_id", None),
                            base_url="http://t", **kw)
    )


class TestRouting:
    def test_a_capability_this_factory_hosts_stays_local(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path, local_ids={"summarize@v1"})
        _run([dict(LOCAL)])
        assert "summarize@v1" in seen["local"]
        assert seen["federated"] == {}

    def test_a_capability_it_does_not_host_goes_to_the_hub(self, tmp_path, monkeypatch):
        """The defect: every one of the studio's seventy-six rows used to 404 here."""
        seen = _stub(monkeypatch, tmp_path)
        out = _run([dict(REMOTE)])
        assert "gaia.weather.read@v1" in seen["federated"]
        assert seen["local"] == {}
        assert out["bill_of_materials"]["steps"][0]["success"] is True

    def test_the_source_hub_of_the_catalogue_row_is_carried(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path)
        _run([dict(REMOTE)])
        assert seen["federated"]["gaia.weather.read@v1"]["source_hub"] == "https://iot.modelmarket.dev"

    def test_a_mixed_graph_routes_each_hop_where_it_belongs(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path, local_ids={"summarize@v1"})
        _run([
            dict(REMOTE),
            {**LOCAL, "depends_on": ["r"], "input": {"text": "${r.reading.c}"}},
        ])
        assert "gaia.weather.read@v1" in seen["federated"]
        # A whole reference keeps the value's type: 21.5 stays a number, not "21.5".
        assert seen["local"]["summarize@v1"]["body_input"] == {"text": 21.5}


class TestMoney:
    def test_no_factory_credential_is_ever_attached(self, tmp_path, monkeypatch):
        """An unauthenticated Run button must not be able to spend the operator's balance."""
        seen = _stub(monkeypatch, tmp_path)
        _run([dict(REMOTE)])
        call = seen["federated"]["gaia.weather.read@v1"]
        assert call["payment_channel"] is None
        assert "authorization" not in call

    def test_the_visitor_s_trial_identity_is_forwarded(self, tmp_path, monkeypatch):
        """Per-visitor metering only works if the visitor's own id reaches the hub."""
        seen = _stub(monkeypatch, tmp_path)
        _run([dict(REMOTE)], sandbox_visitor="visitor-abc")
        assert seen["federated"]["gaia.weather.read@v1"]["sandbox_visitor"] == "visitor-abc"

    def test_a_caller_supplied_channel_is_passed_on(self, tmp_path, monkeypatch):
        seen = _stub(monkeypatch, tmp_path)
        _run([dict(REMOTE)], channel_id="ch_visitor_1")
        assert seen["federated"]["gaia.weather.read@v1"]["payment_channel"] == "ch_visitor_1"

    def test_a_paid_refusal_fails_that_hop_instead_of_paying(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path, federated=(402, {"success": False, "error": "payment_required"}))
        out = _run([dict(REMOTE)], sandbox_visitor="v1")
        step = out["bill_of_materials"]["steps"][0]
        assert step["success"] is False
        assert step["status_code"] == 402
        assert out["bill_of_materials"]["blame"]["at_fault"]["id"] == "r"

    def test_an_exhausted_trial_is_reported_as_such(self, tmp_path, monkeypatch):
        """The hub answers 429 for a spent allowance, not 402 — a different remedy."""
        _stub(monkeypatch, tmp_path,
              federated=(429, {"success": False, "error": "trial_quota_exhausted"}))
        out = _run([dict(REMOTE)], sandbox_visitor="v1")
        assert out["bill_of_materials"]["steps"][0]["status_code"] == 429


class TestTheReceiptNamesTheRealBuyer:
    def test_a_trial_hop_is_recorded_as_a_trial(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        out = _run([dict(REMOTE)], sandbox_visitor="v1")
        assert out["bill_of_materials"]["steps"][0]["payer"] == "trial"

    def test_a_channel_hop_is_recorded_as_paid(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        out = _run([dict(REMOTE)], channel_id="ch_1", sandbox_visitor="v1")
        assert out["bill_of_materials"]["steps"][0]["payer"] == "channel"

    def test_a_local_hop_is_recorded_as_local(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path, local_ids={"summarize@v1"})
        out = _run([dict(LOCAL)])
        assert out["bill_of_materials"]["steps"][0]["payer"] == "local"

    def test_a_hop_with_neither_is_not_called_paid(self, tmp_path, monkeypatch):
        _stub(monkeypatch, tmp_path)
        out = _run([dict(REMOTE)])
        assert out["bill_of_materials"]["steps"][0]["payer"] == "unpaid"


class TestFederatedClientItself:
    def test_it_refuses_when_no_hub_is_configured(self, monkeypatch):
        monkeypatch.setattr(fed, "federation_hub_url", lambda: "")
        status, body = asyncio.run(fed.invoke_federated(
            product_id="p", capability_id="c@v1", body_input={},
        ))
        assert status == 502
        assert body["error"] == "federation_not_configured"
        assert "AIMARKET_FEDERATION_HUB_URL" in body["detail"]

    @pytest.mark.parametrize("bad", ["ftp://hub", "not-a-url", "http://hub\r\nX: 1"])
    def test_it_refuses_a_malformed_hub_url(self, monkeypatch, bad):
        monkeypatch.setattr(fed, "federation_hub_url", lambda: bad)
        status, body = asyncio.run(fed.invoke_federated(
            product_id="p", capability_id="c@v1", body_input={},
        ))
        assert status == 502
        assert body["error"] == "federation_url_unsafe"

    def test_payer_of_never_calls_a_trial_a_purchase(self):
        assert fed.payer_of(local=False, sandbox_visitor="v", payment_channel=None) == "trial"
        assert fed.payer_of(local=False, sandbox_visitor="v", payment_channel="ch") == "channel"
        assert fed.payer_of(local=True, sandbox_visitor="v", payment_channel="ch") == "local"
        assert fed.payer_of(local=False, sandbox_visitor=None, payment_channel=None) == "unpaid"


class TestTheHubsShapeIsTranslated:
    """A local invoke answers `{success, result}`; the hub answers `{ok, output}`.

    Reporting a federated hop as successful while its result silently vanished is worse
    than failing: the next hop's `${read.reading}` finds nothing, and the run looks fine.
    """

    def test_ok_and_output_become_success_and_result(self):
        out = fed.normalise_response({"ok": True, "output": {"reading": {"c": 21.5}}})
        assert out["success"] is True
        assert out["result"] == {"reading": {"c": 21.5}}

    def test_a_refusal_translates_too(self):
        out = fed.normalise_response({"ok": False, "error": "unknown device"})
        assert out["success"] is False
        assert out["error"] == "unknown device"

    def test_the_executor_s_own_shape_is_left_alone(self):
        original = {"success": True, "result": {"a": 1}, "price_usd": 0.1}
        assert fed.normalise_response(original) == original

    def test_a_non_object_body_is_not_called_a_success(self):
        assert fed.normalise_response("nonsense")["success"] is False

    def test_a_federated_result_reaches_the_next_hop(self, tmp_path, monkeypatch):
        """The end the feature exists for: data flowing across a federated boundary."""
        seen = _stub(monkeypatch, tmp_path, local_ids={"summarize@v1"})

        async def hub_shaped(**kw):
            return 200, fed.normalise_response(
                {"ok": True, "output": {"reading": {"c": 21.5}}, "price_usd": 0.001}
            )

        monkeypatch.setattr(pl, "invoke_federated", hub_shaped)
        _run([
            dict(REMOTE),
            {**LOCAL, "depends_on": ["r"], "input": {"text": "${r.reading.c}"}},
        ])
        assert seen["local"]["summarize@v1"]["body_input"] == {"text": 21.5}
