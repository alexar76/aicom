"""Private per-check evidence and opt-in independent failure recovery."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_REPO = Path(__file__).resolve().parents[1]
_PKG = "web.backend.services.ai_market_protocol"
try:
    import web.backend.services.ai_market_protocol.pipelines as pl
except Exception:  # same lean-environment import boundary as the existing pipeline tests
    import web.backend.services  # noqa: F401
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(_REPO / "web/backend/services/ai_market_protocol")]
    sys.modules[_PKG] = pkg
    channels = types.ModuleType(f"{_PKG}.channels")
    channels.get_channel = lambda _channel: {"status": "open"}
    sys.modules[channels.__name__] = channels
    invoke = types.ModuleType(f"{_PKG}.invoke")
    invoke.invoke_capability_v1 = None
    sys.modules[invoke.__name__] = invoke
    import web.backend.services.ai_market_protocol.pipelines as pl


def node(nid, *, depends_on=(), inp=None, **kwargs):
    return {"id": nid, "product_id": "counterparty", "capability_id": f"check.{nid}@v1",
            "input": inp or {}, "depends_on": list(depends_on), **kwargs}


def run(nodes, **kwargs):
    return asyncio.run(pl.execute_pipeline(nodes=nodes, channel_id=None, base_url="http://test", **kwargs))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    seen, responses = [], {}
    key = Ed25519PrivateKey.generate()

    async def invoke(**kwargs):
        cid = kwargs["capability_id"]
        seen.append(cid)
        return (*responses.get(cid, (200, {"success": True, "result": {"found": True},
                                          "price_usd": 0.001})), {})

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    monkeypatch.setattr(pl, "invoke_capability_v1", invoke)
    monkeypatch.setattr(pl, "hosted_here", lambda *_args: True)
    monkeypatch.setattr(pl, "append_stat", lambda *_args: None)
    monkeypatch.setattr(pl, "pipelines_path", lambda: tmp_path / "traces.json")
    monkeypatch.setattr(pl, "sign_payload", lambda value: key.sign(canonical(value)).hex())
    return seen, responses, key, canonical, tmp_path / "traces.json"


def test_all_source_results_and_signed_receipts_are_returned_but_not_published(setup):
    _, responses, key, canonical, path = setup
    source_result = {"name": "Private Counterparty Ω", "found": True,
                     "evidence": {"url": "https://registry.example/record/secret", "sha256": "a" * 64}}
    receipt = {"nonce": "receipt-company", "signature": {"algorithm": "ed25519", "value": "original"}}
    responses["check.company@v1"] = (200, {"success": True, "result": source_result,
                                            "receipt": receipt, "price_usd": 0.001})
    out = run([node("company"), node("domain")])
    assert out["step_results"] == {"company": {"result": source_result, "receipt": receipt},
                                    "domain": {"result": {"found": True}}}
    assert out["final_result"] == {"found": True}  # legacy final-result contract
    bill = out["bill_of_materials"]
    assert bill["steps"][0]["result_sha256"] == hashlib.sha256(canonical(source_result)).hexdigest()
    assert bill["steps"][0]["receipt_nonce"] == receipt["nonce"]
    signature = bytes.fromhex(bill["signature"])
    key.public_key().verify(signature, canonical({k: v for k, v in bill.items() if k != "signature"}))
    tampered = copy.deepcopy(bill)
    tampered["steps"][0]["result_sha256"] = "0" * 64
    with pytest.raises(InvalidSignature):
        key.public_key().verify(signature, canonical({k: v for k, v in tampered.items() if k != "signature"}))
    saved = json.loads(path.read_text())[out["trace_id"]]
    assert saved == bill
    assert "step_results" not in saved and "result" not in saved["steps"][0]
    assert "Private Counterparty" not in path.read_text() and "registry.example" not in path.read_text()
    assert "signature" not in saved["steps"][0]  # raw receipt stays in the response


def test_failure_preserves_its_evidence_and_defaults_to_stopping(setup):
    seen, responses, *_ = setup
    receipt = {"nonce": "rejected", "signature": {"value": "signed-rejection"}}
    result = {"source_status": "unavailable"}
    responses["check.company@v1"] = (503, {"success": False, "result": result,
        "receipt": receipt, "error": "registry unavailable"})
    out = run([node("company"), node("domain")])
    assert seen == ["check.company@v1"]
    assert out["step_results"] == {"company": {"result": result, "receipt": receipt}}
    assert out["bill_of_materials"]["steps"][0]["result_sha256"] == pl.result_sha256(result)
    assert out["bill_of_materials"]["blame"]["not_executed"] == ["domain"]


def test_continuation_executes_independent_checks_and_skips_failed_descendants(setup):
    seen, responses, *_ = setup
    responses["check.company@v1"] = (503, {"success": False, "error": "registry unavailable"})
    responses["check.vat@v1"] = (502, {"success": False, "error": "VIES unavailable"})
    out = run([node("company"), node("derived", depends_on=["company"], inp={"name": "${company.name}"}),
               node("descendant", depends_on=["derived"]), node("domain"), node("vat")],
              continue_on_error=True)
    assert seen == ["check.company@v1", "check.domain@v1", "check.vat@v1"]
    assert set(out["step_results"]) == {"company", "domain", "vat"}
    steps = {step["id"]: step for step in out["bill_of_materials"]["steps"]}
    assert steps["derived"]["status"] == steps["descendant"]["status"] == "skipped"
    assert steps["derived"]["blocked_by"] == ["company"]
    assert steps["descendant"]["blocked_by"] == ["derived"]
    assert steps["derived"]["price_usd"] == 0 and "result_sha256" not in steps["derived"]
    assert steps["domain"]["success"] is True
    bill = out["bill_of_materials"]
    assert bill["continue_on_error"] is True and bill["total_usd"] == 0.001
    assert bill["blame"]["not_at_fault"] == ["domain"]
    assert bill["blame"]["not_executed"] == ["derived", "descendant"]
    assert [item["id"] for item in bill["blame"]["failures"]] == ["company", "vat"]


def test_runtime_reference_failure_does_not_block_independent_checks(setup):
    seen, *_ = setup
    out = run([node("company"), node("derived", depends_on=["company"], inp={"name": "${company.name}"}),
               node("domain")], continue_on_error=True)
    assert seen == ["check.company@v1", "check.domain@v1"]
    assert "derived" not in out["step_results"]
    assert out["bill_of_materials"]["blame"]["failures"][0]["kind"] == "input"


@pytest.mark.parametrize("nodes", [
    [node("company"), node("company")],
    [node("company", depends_on=["absent"])],
    [node("company", depends_on=["domain"]), node("domain", depends_on=["company"])],
])
def test_continuation_never_treats_an_invalid_dependency_as_independent(setup, nodes):
    seen, *_ = setup
    assert run(nodes, continue_on_error=True)["error"] == "invalid_graph"
    assert seen == []


def test_result_digest_covers_unicode_key_order_and_nested_signatures():
    result = {"z": [False, None], "a": "Ω", "signature": {"value": "nested"}}
    expected = b'{"a":"\\u03a9","signature":{"value":"nested"},"z":[false,null]}'
    assert pl.result_sha256(result) == hashlib.sha256(expected).hexdigest()
    assert pl.result_sha256(result) != pl.result_sha256({"z": [False, None], "a": "Ω"})
