"""Verify the root and bill against the key pinned before payment signing."""
import hashlib

from aimarket_hub.signing import Signer
from aimarket_hub.studio_paid import _json


def verify_document(document, key, pq_key=None):
    if not isinstance(document, dict) or not Signer.verify_object_signature(
        document, key, pq_public_key_b64=pq_key, require_pq=bool(pq_key),
    ):
        raise ValueError("invalid Hub signature; result is not accepted")


def verify_result(answer, state):
    quote = state["quote"]
    key, pq_key = state["trusted_hub_key"], state.get("trusted_hub_pq_key")
    if answer.get("trace_id") != quote["run_id"]:
        raise ValueError("Hub returned a different run")
    bill = answer.get("bill_of_materials")
    verify_document(bill, key, pq_key)
    if any(bill.get(k) != quote.get(k) for k in ("graph_digest", "wallet")) or bill.get("trace_id") != quote["run_id"]:
        raise ValueError("bill differs from the prepared graph or buyer")
    if quote.get("gas_sponsorship") is not None and bill.get("gas_sponsorship") != quote["gas_sponsorship"]:
        raise ValueError("bill gas sponsorship differs from the prepared order")
    if bill.get("status") != answer.get("status"):
        raise ValueError("bill status differs from the result")
    if answer.get("status") not in ("completed", "failed"):
        return
    receipt = answer.get("receipt")
    verify_document(receipt, key, pq_key)
    expected = {"kind": "pipeline.run/1", "run_id": quote["run_id"],
                "graph_digest": quote["graph_digest"], "job_id": bill.get("job_id"),
                "product_id": "hephaestus", "capability_id": "pipeline.run@v1",
                "success": answer["status"] == "completed"}
    if any(receipt.get(k) != v for k, v in expected.items()):
        raise ValueError("root receipt differs from the prepared order")
    result = {"status": answer["status"], "final_result": answer.get("final_result"), "bill_of_materials": bill}
    if answer.get("result") != result or answer.get("success") != expected["success"]:
        raise ValueError("root response differs from its signed result")
    for field, value in (("result_digest", result), ("bill_digest", bill)):
        if receipt.get(field) != hashlib.sha256(_json(value).encode()).hexdigest():
            raise ValueError("root receipt digest mismatch")
