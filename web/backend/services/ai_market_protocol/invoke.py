"""Capability invoke with HTTP 402, channel debit, and LLM-powered execution."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import HTTPException

from web.backend.api import payment as payment_api
from web.backend.services.ai_market_protocol.catalog import (
    get_capability,
    list_shipped_products,
    parse_capability_ref,
)
from web.backend.services.ai_market_protocol.channels import deduct_channel, get_channel, refund_channel
from web.backend.services.ai_market_protocol.config import demo_payment_bypass, pilot_tuple
from web.backend.services.ai_market_protocol.pricing import quote_capability_price
from web.backend.services.ai_market_protocol.receipts import create_receipt
from web.backend.services.ai_market_protocol.stats import append_stat


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def _build_execution_prompt(
    cap: dict[str, Any], product: dict[str, Any], inp: dict[str, Any]
) -> str:
    """Build an LLM prompt from the capability schema and user input."""
    template = str(cap.get("prompt_template") or "")
    if template:
        try:
            return template.format(**inp, **{k: v for k, v in inp.items() if isinstance(v, (str, int, float))})
        except (KeyError, ValueError):
            pass

    cap_name = cap.get("name") or parse_capability_ref(str(cap.get("capability_id") or ""))[0]
    desc = cap.get("description") or ""
    pname = str(product.get("name") or product.get("idea") or "")[:120]
    input_schema = cap.get("input_schema") or {}

    # Render input as readable key-value pairs
    input_lines: list[str] = []
    for k, v in inp.items():
        if isinstance(v, str):
            input_lines.append(f"  {k}: {v[:2000]}")
        elif isinstance(v, (int, float, bool)):
            input_lines.append(f"  {k}: {v}")
        elif isinstance(v, list):
            input_lines.append(f"  {k}: [{', '.join(str(x) for x in v[:20])}]")
        elif isinstance(v, dict):
            input_lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)[:1000]}")
        else:
            input_lines.append(f"  {k}: {str(v)[:500]}")

    schema_hint = ""
    if input_schema:
        props = input_schema.get("properties") or {}
        required = input_schema.get("required") or []
        if props:
            schema_hint = "\nExpected input fields: " + ", ".join(
                f"{k}" + ("*" if k in required else "") for k in list(props.keys())[:10]
            )

    return (
        f"Execute capability '{cap_name}' for product '{pname}'.\n"
        f"Description: {desc}\n"
        f"{schema_hint}\n"
        f"Input:\n{chr(10).join(input_lines) if input_lines else '  (none)'}\n"
        f"Return a JSON object with the result."
    )


def _parse_llm_result(raw: str, cap: dict[str, Any]) -> dict[str, Any]:
    """Best-effort JSON parse from LLM output."""
    text = raw.strip()
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    import re
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try to find a JSON object in the text
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Fallback: wrap as result
    return {"result": text[:4000]}


# ---------------------------------------------------------------------------
# Execution (real LLM or mock fallback)
# ---------------------------------------------------------------------------

async def _execute_capability(
    cap: dict[str, Any],
    product: dict[str, Any],
    inp: dict[str, Any],
    llm_router: Any = None,
) -> dict[str, Any]:
    """Execute a capability, using the LLM router when available.

    Falls back to deterministic mock output when no LLM router is configured.
    """
    cap_name, _ = parse_capability_ref(str(cap["capability_id"]))
    pname = str(product.get("name") or product.get("idea") or "")[:120]

    # Real LLM path
    if llm_router is not None and (cap.get("agent") or cap.get("prompt_template")):
        prompt = _build_execution_prompt(cap, product, inp)
        try:
            from llm.provider import GenerationConfig

            raw = await llm_router.generate(
                prompt=prompt,
                task_type="ai_market_invoke",
                config=GenerationConfig(temperature=0.3, max_tokens=2048, json_mode=True),
            )
            return _parse_llm_result(raw, cap)
        except Exception:
            pass  # fall through to mock

    # Mock fallback — deterministic placeholder
    text = str(inp.get("text") or inp.get("task") or "")
    if cap_name.startswith("translate"):
        locales = inp.get("locales") or ["ru", "en", "de", "fr", "ja"]
        if isinstance(locales, str):
            locales = [locales]
        translations = {loc: f"[{loc}] {text[:500]}" for loc in locales[:8]}
        return {"translations": translations, "source_chars": len(text)}
    if cap_name.startswith("legal"):
        docs = inp.get("documents") or {}
        return {
            "issues": ["placeholder_review: verify counsel for production"],
            "risk_level": "low" if len(docs) < 3 else "medium",
            "documents_reviewed": len(docs),
        }
    if cap_name.startswith("summarize"):
        return {"summary": (text[:400] + "…") if len(text) > 400 else text}
    return {
        "result": f"Executed {cap_name} for {pname}",
        "echo": {k: v for k, v in list(inp.items())[:8]},
    }


# ---------------------------------------------------------------------------
# Continuation hints
# ---------------------------------------------------------------------------

def _continuation_hints(cap: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hint in cap.get("suggested_next") or []:
        if "/" not in hint:
            continue
        pid, cid = hint.split("/", 1)
        c2 = get_capability(pid, cid)
        if not c2:
            continue
        out.append({
            "capability_id": cid,
            "product_id": pid,
            "why": f"commonly follows {cap['capability_id']}",
            "est_price_usd": c2["price_per_call_usd"],
        })
    return out


# ---------------------------------------------------------------------------
# Payment required builder
# ---------------------------------------------------------------------------

def build_payment_required(
    *,
    product_id: str,
    capability_id: str,
    amount_usd: float,
    base_url: str,
) -> dict[str, Any]:
    cfg = pilot_tuple()
    nonce = f"pay_{uuid.uuid4().hex[:16]}"
    recipient = payment_api._get_address_for_chain(cfg["chain"])
    return {
        "amount": f"{amount_usd:.4f}",
        "token": cfg["token"],
        "chain": cfg["chain"],
        "recipient": recipient,
        "nonce": nonce,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 900)),
        "receipt_url": f"{base_url}/ai-market/receipt/{nonce}",
        "product_id": product_id,
        "capability_id": capability_id,
    }


def _verify_tx_payment(*, tx_hash: str, amount_usd: float, chain: str, token: str) -> bool:
    if demo_payment_bypass() and (tx_hash.startswith("demo-") or tx_hash.startswith("0xdemo")):
        return True
    recipient = payment_api._get_address_for_chain(chain)
    if chain == "solana":
        verify = payment_api._verify_solana_transaction(
            tx_hash=tx_hash,
            expected_recipient=recipient,
            expected_amount=amount_usd,
        )
    else:
        verify = payment_api._verify_evm_transaction(
            chain=chain,
            tx_hash=tx_hash,
            expected_recipient=recipient,
            expected_amount=amount_usd,
            expected_token=token,
        )
    return bool(verify.get("verified"))


# ---------------------------------------------------------------------------
# Main invoke entry point
# ---------------------------------------------------------------------------

async def invoke_capability_v1(
    *,
    product_id: str,
    capability_id: str,
    body_input: dict[str, Any],
    base_url: str,
    x_payment: str | None = None,
    x_payment_channel: str | None = None,
    x_ai_market_license: str | None = None,
    llm_router: Any = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    """Returns (status_code, json_body, extra_headers).

    402 when payment required; 200 on success.
    """
    cap = get_capability(product_id, capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="capability not found")

    products = {r["id"]: r["raw"] for r in list_shipped_products()}
    product = products.get(product_id) or {}

    quote = quote_capability_price(
        product_id=product_id,
        capability_id=capability_id,
        input_payload=body_input,
    )
    price = float(quote.get("price_usd") or cap["price_per_call_usd"])

    paid = False
    payment_kind = ""
    payment_ref = ""

    # --- Payment verification ---
    if x_payment_channel:
        ch = get_channel(x_payment_channel.strip())
        if not ch or ch.get("status") != "open":
            raise HTTPException(status_code=402, detail="invalid or closed payment channel")
        deduct = deduct_channel(x_payment_channel.strip(), price, ref=f"{product_id}/{capability_id}")
        if not deduct.get("ok"):
            pay_req = build_payment_required(
                product_id=product_id, capability_id=capability_id, amount_usd=price, base_url=base_url
            )
            return 402, {"payment_required": pay_req, "detail": deduct.get("error")}, {
                "X-Payment-Required": json.dumps(pay_req, separators=(",", ":")),
            }
        paid = True
        payment_kind = "channel"
        payment_ref = x_payment_channel.strip()
    elif x_payment:
        try:
            pay = json.loads(x_payment) if x_payment.strip().startswith("{") else {}
        except json.JSONDecodeError:
            pay = {"tx_hash": x_payment.strip()}
        tx_hash = str(pay.get("tx_hash") or "").strip()
        chain = str(pay.get("chain") or pilot_tuple()["chain"]).lower()
        token = str(pay.get("token") or pilot_tuple()["token"]).upper()
        if not tx_hash:
            raise HTTPException(status_code=400, detail="X-Payment missing tx_hash")
        if not _verify_tx_payment(tx_hash=tx_hash, amount_usd=price, chain=chain, token=token):
            raise HTTPException(status_code=402, detail="on-chain payment not verified")
        paid = True
        payment_kind = "on_chain"
        payment_ref = tx_hash
    elif x_ai_market_license:
        from core.paths import store_licenses_path

        licenses = {}
        lp = store_licenses_path()
        if lp.exists():
            try:
                licenses = json.loads(lp.read_text(encoding="utf-8"))
            except Exception:
                licenses = {}
        lic = licenses.get(x_ai_market_license) or {}
        if lic and str(lic.get("status") or "").lower() == "active" and str(lic.get("product_id")) == product_id:
            paid = True
            payment_kind = "license"
            payment_ref = x_ai_market_license[:24]
    else:
        pay_req = build_payment_required(
            product_id=product_id, capability_id=capability_id, amount_usd=price, base_url=base_url
        )
        return 402, {"payment_required": pay_req, "protocol_version": "v1"}, {
            "X-Payment-Required": json.dumps(pay_req, separators=(",", ":")),
        }

    # --- Execution ---
    t0 = time.time()
    try:
        result = await _execute_capability(cap, product, body_input, llm_router=llm_router)
        success = True
        err_type = None
    except Exception as exc:
        success = False
        result = {"error": str(exc)}
        err_type = "execution_failed"
        if paid and payment_kind == "channel" and x_payment_channel:
            refund_channel(x_payment_channel.strip(), price, ref=f"refund:{product_id}/{capability_id}")

    latency_ms = int((time.time() - t0) * 1000)
    receipt = create_receipt(
        product_id=product_id,
        capability_id=capability_id,
        amount_usd=price if success else 0.0,
        payment_kind=payment_kind,
        payment_ref=payment_ref,
        success=success,
        result_summary={"keys": list(result.keys())[:12]},
    )

    append_stat({
        "type": "invoke",
        "product_id": product_id,
        "capability_id": capability_id,
        "price_usd": price,
        "paid": paid,
        "success": success,
        "latency_ms": latency_ms,
        "agent": "external",
    })

    body: dict[str, Any] = {
        "success": success,
        "product_id": product_id,
        "capability_id": capability_id,
        "result": result,
        "receipt": receipt,
        "price_usd": price,
        "latency_ms": latency_ms,
        "continuation": {"suggested_next": _continuation_hints(cap)},
        "protocol_version": "v1",
    }
    if not success:
        body["error_type"] = err_type
    return 200, body, {}
