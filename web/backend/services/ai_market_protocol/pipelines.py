"""DAG pipeline execution with shared payment channel."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from web.backend.services.ai_market_protocol.channels import get_channel
from web.backend.services.ai_market_protocol.invoke import invoke_capability_v1
from web.backend.services.ai_market_protocol.federated import invoke_federated, payer_of
from web.backend.services.ai_market_protocol.paths import pipelines_path
from web.backend.services.ai_market_protocol.references import (
    UnresolvedReference,
    resolve as resolve_references,
    validate_graph as validate_reference_graph,
)
from web.backend.services.ai_market_protocol.signing import sign_payload
from web.backend.services.ai_market_protocol.stats import append_stat


def _load_traces() -> dict[str, Any]:
    p = pipelines_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_trace(trace_id: str, row: dict[str, Any]) -> None:
    data = _load_traces()
    data[trace_id] = row
    pipelines_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_trace(trace_id: str) -> dict[str, Any] | None:
    """The full signed bill of materials for one pipeline run, verbatim.

    Verbatim matters: the signature covers the object as written, so anything filtered
    here would hand back something unverifiable. Reaching a trace requires knowing its
    opaque ``tr_<hex12>`` id — the same obscurity ``/receipt/{nonce}`` relies on. Listing,
    which turns that into a browsable feed of who bought what, is the projection below.
    """
    row = _load_traces().get(str(trace_id))
    return row if isinstance(row, dict) else None


# Fields a public listing must not enumerate. `channel_id` names the payment channel that
# funded the run, and `receipt_nonce` is the lookup key for a public receipt carrying an
# amount and a payment reference — both fine to hand to someone who already holds the
# trace id, neither fine to publish as a feed.
_PROJECTION_STEP_FIELDS = ("id", "product_id", "capability_id", "status_code", "success", "price_usd")


def _project_trace(trace_id: str, row: dict[str, Any]) -> dict[str, Any]:
    steps = [s for s in (row.get("steps") or []) if isinstance(s, dict)]
    blame = row.get("blame") if isinstance(row.get("blame"), dict) else None
    projected_blame = None
    if blame:
        at_fault = blame.get("at_fault") if isinstance(blame.get("at_fault"), dict) else {}
        projected_blame = {
            "policy": blame.get("policy"),
            "at_fault": {
                k: at_fault.get(k)
                for k in ("id", "product_id", "capability_id", "status_code")
            },
            "not_at_fault": list(blame.get("not_at_fault") or []),
            "not_executed": list(blame.get("not_executed") or []),
        }
    return {
        "trace_id": trace_id,
        "completed_at": row.get("completed_at"),
        "duration_ms": row.get("duration_ms"),
        "total_usd": row.get("total_usd"),
        "hops": len(steps),
        "steps": [{k: s.get(k) for k in _PROJECTION_STEP_FIELDS} for s in steps],
        "blame": projected_blame,
        "failed": projected_blame is not None,
        # The projection is not the signed object; say where the signed one lives rather
        # than shipping a signature that does not cover what is being shown.
        "signed": bool(row.get("signature")),
        "trace_path": f"/ai-market/pipelines/{trace_id}",
    }


def list_traces(limit: int = 20) -> list[dict[str, Any]]:
    """Recent pipeline runs as a redacted projection, newest first.

    Until this existed the signed bill of materials was write-only from outside: the
    executor persisted one per run and nothing could read it back, so hop-level blame —
    the evidence a dispute and any resulting slash rests on — was visible only to
    whoever made the original POST.
    """
    rows = [
        (tid, row) for tid, row in _load_traces().items() if isinstance(row, dict)
    ]
    rows.sort(key=lambda item: float(item[1].get("completed_at") or 0.0), reverse=True)
    return [_project_trace(tid, row) for tid, row in rows[: max(1, min(limit, 200))]]



def hosted_here(product_id: str, capability_id: str) -> bool:
    """Whether this factory serves the capability itself.

    A named function rather than an inline import so the routing decision is one visible
    thing that a test can state. Fails to the LOCAL path: if the catalogue cannot be
    consulted at all, the old behaviour (a 404 from the local invoke) is a better answer
    than silently sending a hop — and possibly money — to another service.
    """
    try:
        from web.backend.services.ai_market_protocol.catalog import get_capability
    except Exception:  # noqa: BLE001 — lean environments carry no catalogue
        return True
    try:
        return bool(get_capability(product_id, capability_id))
    except Exception:  # noqa: BLE001
        return True


async def execute_pipeline(
    *,
    nodes: list[dict[str, Any]],
    channel_id: str | None,
    channel_secret: str | None = None,
    base_url: str,
    authorization: str | None = None,
    llm_router: Any = None,
    sandbox_visitor: str | None = None,
) -> dict[str, Any]:
    if channel_id:
        ch = get_channel(channel_id)
        if not ch or ch.get("status") != "open":
            return {"error": "invalid_channel", "channel_id": channel_id}

    # A `${hop.field}` that can never resolve is a defect in the GRAPH, and half of a
    # pipeline that cannot complete is still billed. So this is checked before the first
    # invoke rather than discovered on the hop that needed the value.
    reference_problems = validate_reference_graph(nodes)
    if reference_problems:
        return {"error": "unresolvable_references", "problems": reference_problems}

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
    # Per-node results, so `input_from` can name the parent it means (see below).
    results: dict[str, dict[str, Any]] = {}

    # Topological order by depends_on ids
    by_id: dict[str, dict[str, Any]] = {}
    for i, n in enumerate(nodes):
        nid = n.get("id") or f"n{i}"
        by_id[nid] = n

    done: set[str] = set()
    ordered: list[tuple[str, dict[str, Any]]] = []
    while len(ordered) < len(by_id):
        progressed = False
        for nid, node in by_id.items():
            if nid in done:
                continue
            deps = node.get("depends_on") or []
            if all(d in done for d in deps):
                ordered.append((nid, node))
                done.add(nid)
                progressed = True
        if not progressed:
            ordered = list(by_id.items())
            break

    for nid, node in ordered:
        pid = str(node.get("product_id") or "")
        cid = str(node.get("capability_id") or "")
        inp = dict(node.get("input") or {})
        # `input_from` is declared as a node id (a 64-char string), and was implemented as
        # a boolean: any truthy value injected `context`, which held whichever hop ran
        # last. In a chain those are the same thing. In a DAG they are not — a node with
        # two parents got the result of whichever parent the topological sort happened to
        # finish second, so a fan-in graph could be drawn, priced and paid for while
        # feeding one hop data from the wrong one. Naming the parent makes the wiring say
        # what it means; an unrecognised value keeps the old last-result behaviour so
        # existing callers (and their boolean-ish flags) are unaffected.
        source = node.get("input_from")
        if source:
            upstream = results.get(str(source)) if str(source) in results else context
            if upstream:
                inp.setdefault("context", upstream)

        # `${hop.field}` → the value that hop actually returned. This is what makes a chain
        # a pipeline: `input_from` can only hand over a whole result under `context`, which
        # no provider reads, so before this the data never reached the field it was for.
        try:
            inp = resolve_references(inp, results)
        except UnresolvedReference as exc:
            # The upstream ran but did not return what this hop was promised. Refuse the
            # hop instead of posting the literal "${hop.field}" to a paid provider, which
            # would be either rejected as garbage or accepted and charged for.
            steps_out.append({
                "id": nid,
                "product_id": pid,
                "capability_id": cid,
                "status_code": 0,
                "success": False,
                "price_usd": 0,
                "receipt_nonce": None,
                "error": f"unresolved reference: {exc}",
            })
            break

        # A hop this factory does not host goes to the hub, carrying the VISITOR's trial
        # identity and no credential of ours. Before this, every capability the studio can
        # show — all of them peers' — answered 404 here.
        is_local = hosted_here(pid, cid)
        if is_local:
            status, body, _ = await invoke_capability_v1(
                product_id=pid,
                capability_id=cid,
                body_input=inp,
                base_url=base_url,
                x_payment_channel=channel_id,
                x_payment_channel_secret=channel_secret,
                authorization=authorization,
                llm_router=llm_router,
            )
        else:
            status, body = await invoke_federated(
                product_id=pid,
                capability_id=cid,
                body_input=inp,
                source_hub=str(node.get("source_hub") or "") or None,
                sandbox_visitor=sandbox_visitor,
                payment_channel=channel_id,
            )
        step = {
            "id": nid,
            "product_id": pid,
            "capability_id": cid,
            "status_code": status,
            "success": body.get("success", status == 200),
            "price_usd": body.get("price_usd"),
            "receipt_nonce": (body.get("receipt") or {}).get("nonce"),
            # Signed evidence must not claim the wrong buyer: a hop the visitor's free
            # trial covered is not a purchase by this factory.
            "payer": payer_of(
                local=is_local, sandbox_visitor=sandbox_visitor, payment_channel=channel_id
            ),
        }
        steps_out.append(step)
        if status != 200 or not body.get("success"):
            break
        total_usd += float(body.get("price_usd") or 0)
        context = body.get("result") or {}
        results[nid] = context

    # Hop-level blame attribution: a pipeline failure is the FAILING hop's fault,
    # never the whole graph's. Each successful upstream hop already settled its own
    # leg independently, so a dispute (and any resulting slash) must target only the
    # at-fault provider — this signed block is the portable evidence for that.
    failed_step = next((s for s in steps_out if not s["success"]), None)
    blame = None
    if failed_step is not None:
        blame = {
            "policy": "hop-level",
            "at_fault": {
                "id": failed_step["id"],
                "product_id": failed_step["product_id"],
                "capability_id": failed_step["capability_id"],
                "status_code": failed_step["status_code"],
                "receipt_nonce": failed_step["receipt_nonce"],
            },
            "not_at_fault": [s["id"] for s in steps_out if s["success"]],
            "not_executed": [nid for nid, _ in ordered if nid not in {s["id"] for s in steps_out}],
        }

    bom = {
        "trace_id": trace_id,
        "channel_id": channel_id,
        "steps": steps_out,
        "blame": blame,
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
