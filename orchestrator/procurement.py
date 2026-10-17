"""Buy bounded diagnostics before a third internal repair of the same file-bound defect.

No pipeline state is advanced, no gate is relaxed and no remote code is executed here.
HTTP failures are financially ambiguous: retain the reservation and do not retry them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx

from core.agent_roles import is_developer_agent
from core.factory_hold import is_factory_hard_stopped
from core.procurement_contract import (
    MAX_RESPONSE_BYTES,
    PurchasePolicy,
    accept_report,
    build_requests,
    digest,
)
from core.procurement_receipt import check_hub_document, checked_charge
from core.procurement_store import PurchaseStore, micros

logger = logging.getLogger(__name__)


async def _json_request(client, method: str, url: str, **kwargs) -> dict:
    async with asyncio.timeout(40), client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise ValueError("procurement response too large")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("procurement response must be an object")
        return result


def _candidates(body: dict, policy: PurchasePolicy, packet: dict) -> list[dict]:
    selected = []
    for match in body.get("matches", []):
        if not isinstance(match, dict):
            continue
        identity = (match.get("product_id"), match.get("capability_id"))
        if identity not in policy.providers or match.get("source_hub") != "local" \
                or match.get("demo") is not False or match.get("offerable") is not True \
                or match.get("credits_eligible") is not True \
                or match.get("input_independent") is True:
            continue
        required = match.get("input_required")
        if not isinstance(required, list) or any(k not in packet for k in required):
            continue
        try:
            amount = micros(match["routed_price_usd"])
        except (KeyError, ValueError, ArithmeticError):
            continue
        if amount > policy.per_call:
            continue
        selected.append({"product_id": identity[0], "capability_id": identity[1], "source_hub": "local",
                         "max_price_usd": amount / 1_000_000, "input": packet})
    # Operator-approved, compatible offers first; compare actual quoted price, not a default success rate.
    return sorted(selected, key=lambda p: (p["max_price_usd"], p["product_id"], p["capability_id"]))


async def prepare_diagnosis(*, root: Path, product: dict, task: dict, task_queue: list,
                            input_data: dict, client=None) -> dict | None:
    """Optional advice for a repair; an unavailable service leaves the original route intact."""
    if product.get("external_diagnostics_allowed") is False or product.get("pipeline_stuck_reason") \
            or product.get("operator_locked") \
            or product.get("budget_parked") or product.get("last_round_generated") is False \
            or is_factory_hard_stopped():
        return None
    try:
        policy = PurchasePolicy.load(root)
        if policy is None:
            return None
        pid = str(task["product_id"])
        if not pid or Path(pid).name != pid or pid in (".", ".."):
            return None
        code_root = root / "code" / pid
        if code_root.is_symlink():
            return None
        code_root.resolve().relative_to((root / "code").resolve())
        packets = build_requests(code_root, input_data.get("qa_findings"), policy)
        if not packets:
            return None
        # Only a successful internal developer attempt counts; retries/timeouts do not.
        developers = [t for t in task_queue if t.get("product_id") == pid
                      and is_developer_agent(t.get("agent_type")) and t.get("status") == "completed"]
        if not developers:
            return None
        latest = max(developers, key=lambda t: t.get("completed_at", 0))
        observation = str(latest["id"])
        store = PurchaseStore(root)
        orders = store.orders(pid)
        for packet in packets:
            count = store.observe(pid, packet["issue"], observation)
            # Initial generation + two completed internal repair attempts.
            if count < 3:
                continue
            cached = next((r for r in orders if r["issue"] == packet["issue"]
                           and r["fingerprint"] == packet["fingerprint"]
                           and r["status"] == "accepted" and not r["applied"]), None)
            if cached:
                report = accept_report(packet, json.loads(cached["report"]))
                return {"order_id": cached["id"], "report": report}
            if any(r["issue"] == packet["issue"] and r["status"] == "accepted" for r in orders):
                continue
            if any(r["payment"] == "unknown" for r in orders):
                product["procurement_status"] = "payment_unknown"
                return None
            if any(r["observation"] == observation for r in orders):
                return None  # Another purchase needs a newly completed internal repair.
            if client is None:
                async with httpx.AsyncClient(timeout=policy.timeout, follow_redirects=False,
                                             trust_env=False) as http:
                    return await _buy(http, policy, store, pid, packet, product, observation)
            return await _buy(client, policy, store, pid, packet, product, observation)
    except Exception as exc:
        # Do not log URLs, API keys, response bodies or source fragments from transport exceptions.
        logger.warning("External diagnosis skipped for %s (%s)", task.get("product_id"), type(exc).__name__)
        product["procurement_status"] = "unavailable"
    return None


async def _buy(client, policy: PurchasePolicy, store: PurchaseStore, pid: str,
               packet: dict, product: dict, observation: str) -> dict | None:
    document = await _json_request(client, "GET", policy.hub_url + "/.well-known/ai-market.json")
    check_hub_document(document, policy.hub_key, policy.hub_pq_key)
    offers = {}
    catalogues = await asyncio.gather(*(
        _json_request(client, "GET", policy.hub_url + "/ai-market/v2/search",
                      params={"intent": capability, "budget": policy.per_call / 1_000_000,
                              "include_demo": "false", "limit": 20})
        for capability in sorted({c for _, c in policy.providers})
    ))
    for catalogue in catalogues:
        for candidate in _candidates(catalogue, policy, packet):
            offers[(candidate["product_id"], candidate["capability_id"])] = candidate
    candidates = sorted(offers.values(), key=lambda c: (c["max_price_usd"], c["product_id"], c["capability_id"]))
    from core.pipeline_cost_guard import effective_max_pipeline_cost_usd, product_spend_usd

    for request in candidates:
        if is_factory_hard_stopped():
            return None
        supplier = request["product_id"] + ":" + request["capability_id"]
        order_id = "purchase_" + digest([pid, packet["issue"], packet["fingerprint"], supplier])
        amount = micros(request["max_price_usd"])
        reserved = store.reserve(
            order={"id": order_id, "product": pid, "issue": packet["issue"],
                   "fingerprint": packet["fingerprint"], "supplier": supplier, "request": request,
                   "observation": observation},
            amount=amount, llm_spent=micros(product_spend_usd(pid, reconcile_jsonl=True)),
            total_cap=micros(effective_max_pipeline_cost_usd()), external_cap=policy.per_product,
            daily_cap=policy.per_day, completion_reserve=policy.completion_reserve, max_attempts=policy.attempts,
        )
        if not reserved:
            continue
        product["procurement_status"] = "in_flight"
        created = time.time()
        try:
            body = await _json_request(client, "POST", policy.hub_url + "/ai-market/v2/invoke",
                                       headers={"X-API-Key": policy.api_key}, json=request)
            receipt = body.get("receipt")
            if not isinstance(receipt, dict):
                raise ValueError("missing billing receipt")
            charge = checked_charge(receipt, policy.hub_key, request, created, policy.hub_pq_key)
            # Reject a replay from an earlier purchase even if the supplier and price match.
            for row in store.orders():
                old = json.loads(row["response"] or "null")
                if isinstance(old, dict) and (old.get("receipt") or {}).get("nonce") == receipt["nonce"]:
                    raise ValueError("replayed billing receipt")
        except Exception:
            store.finish(order_id, status="unresolved", reason="payment outcome unknown; do not retry")
            product["procurement_status"] = "payment_unknown"
            return None
        # A valid bill is accounted even when delivery is unusable or the hub exceeded the ceiling.
        try:
            if body.get("success") is not True or body.get("sandbox") or receipt.get("sandbox") or charge > amount:
                raise ValueError("unexpected invoke outcome or price")
            report = accept_report(packet, body.get("result"))
            current = build_requests(store.path.parent.parent / "code" / pid, [packet["finding"]], policy)
            if not current or current[0]["fingerprint"] != packet["fingerprint"]:
                raise ValueError("source changed while the diagnosis was running")
        except ValueError as exc:
            store.finish(order_id, status="rejected", charged=charge, response=body, reason=str(exc))
            product["procurement_status"] = "rejected"
            # Do not issue another purchase in the same repair attempt.
            return None
        store.finish(order_id, status="accepted", charged=charge, response=body, report=report)
        product["procurement_status"] = "accepted"
        return {"order_id": order_id, "report": report}
    product["procurement_status"] = "no_eligible_offer_or_budget"
    return None


def record_diagnosis_outcome(root: Path, pid: str, qa_result: dict, *, gates_passed: bool) -> None:
    """Record what the next QA actually observed, without attributing causal improvement."""
    try:
        store = PurchaseStore(root)
        for row in store.orders(pid):
            if row["applied"] and row["outcome"] is None:
                store.record_outcome(row["id"], {"gates_passed": gates_passed,
                                                "bugs_remaining": len(qa_result.get("bugs_found") or []),
                                                "observed_at": time.time()})
    except Exception as exc:
        logger.warning("Could not record purchase outcome for %s (%s)", pid, type(exc).__name__)
