"""DAG pipeline execution with shared payment channel."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from web.backend.services.ai_market_protocol.channels import get_channel
from web.backend.services.ai_market_protocol.invoke import invoke_capability_v1
from web.backend.services.ai_market_protocol.paths import pipelines_path
from web.backend.services.ai_market_protocol.signing import sign_payload
from web.backend.services.ai_market_protocol.stats import append_stat


def _save_trace(trace_id: str, row: dict[str, Any]) -> None:
    p = pipelines_path()
    data: dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[trace_id] = row
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def execute_pipeline(
    *,
    nodes: list[dict[str, Any]],
    channel_id: str | None,
    base_url: str,
    authorization: str | None = None,
    llm_router: Any = None,
) -> dict[str, Any]:
    if channel_id:
        ch = get_channel(channel_id)
        if not ch or ch.get("status") != "open":
            return {"error": "invalid_channel", "channel_id": channel_id}

    # NB: this ``trace_id`` is the PIPELINE'S opaque id (``tr_<hex12>``) used
    # to look up the persisted BoM, NOT the OTel W3C trace id (32-hex) used by
    # UNI receipts (``core.uni.receipts.trace_id``). The two namespaces collide
    # by name only; we emit BOTH below so consumers don't conflate them.
    trace_id = f"tr_{uuid.uuid4().hex[:12]}"
    from core.tracing import current_trace_id_hex

    otel_trace_id = current_trace_id_hex()  # None when tracing is disabled
    t0 = time.time()
    steps_out: list[dict[str, Any]] = []
    total_usd = 0.0
    context: dict[str, Any] = {}

    # Topological order by depends_on ids
    by_id: dict[str, dict[str, Any]] = {}
    for i, n in enumerate(nodes):
        nid = n.get("id") or f"n{i}"
        by_id[nid] = n

    done: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while len(ordered) < len(by_id):
        progressed = False
        for nid, node in by_id.items():
            if nid in done:
                continue
            deps = node.get("depends_on") or []
            if all(d in done for d in deps):
                ordered.append(node)
                done.add(nid)
                progressed = True
        if not progressed:
            ordered = list(by_id.values())
            break

    for node in ordered:
        pid = str(node.get("product_id") or "")
        cid = str(node.get("capability_id") or "")
        inp = dict(node.get("input") or {})
        if node.get("input_from") and context:
            inp.setdefault("context", context)
        status, body, _ = await invoke_capability_v1(
            product_id=pid,
            capability_id=cid,
            body_input=inp,
            base_url=base_url,
            x_payment_channel=channel_id,
            authorization=authorization,
            llm_router=llm_router,
        )
        step = {
            "product_id": pid,
            "capability_id": cid,
            "status_code": status,
            "success": body.get("success", status == 200),
            "price_usd": body.get("price_usd"),
            "receipt_nonce": (body.get("receipt") or {}).get("nonce"),
        }
        steps_out.append(step)
        if status != 200 or not body.get("success"):
            break
        total_usd += float(body.get("price_usd") or 0)
        context = body.get("result") or {}

    bom = {
        "trace_id": trace_id,
        "channel_id": channel_id,
        "steps": steps_out,
        "total_usd": round(total_usd, 4),
        "duration_ms": int((time.time() - t0) * 1000),
        "completed_at": time.time(),
    }
    if otel_trace_id:
        bom["otel_trace_id"] = otel_trace_id
    bom["signature"] = sign_payload(bom)
    _save_trace(trace_id, bom)
    append_stat({"type": "pipeline", "trace_id": trace_id, "steps": len(steps_out), "total_usd": total_usd})
    return {"trace_id": trace_id, "bill_of_materials": bom, "final_result": context, "protocol_version": "v1"}
