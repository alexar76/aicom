"""Capability invoke with HTTP 402, channel debit, and LLM-powered execution."""

from __future__ import annotations

import json
import os
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
from web.backend.services.ai_market_protocol.channels import (
    claim_payment_tx,
    deduct_channel,
    get_channel,
    mark_payment_tx_unfulfilled,
    refund_channel,
)
from web.backend.services.ai_market_protocol.config import pilot_tuple
from web.backend.services.ai_market_protocol.on_chain import (
    BIND_SENDER,
    is_evm_chain,
    normalize_tx_hash,
    recover_payer,
    require_payer_proof,
    verify_tx_transfer,
)
from web.backend.services.ai_market_protocol.pricing import quote_capability_price
from web.backend.services.ai_market_protocol.receipts import create_receipt
from web.backend.services.ai_market_protocol.stats import append_stat


def _is_production() -> bool:
    """Production when AIFACTORY_PROD=1 (matches security/prod_startup_guard.py)."""
    try:
        from security.prod_startup_guard import is_production_mode

        return is_production_mode()
    except Exception:
        return (os.environ.get("AIFACTORY_PROD") or "").strip() == "1"


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

class CapabilityExecutionError(RuntimeError):
    """Raised when LLM execution fails; the caller must NOT charge the user."""


async def _execute_capability(
    cap: dict[str, Any],
    product: dict[str, Any],
    inp: dict[str, Any],
    llm_router: Any = None,
) -> dict[str, Any]:
    """Execute a capability, using the LLM router when available.

    Returns a mock placeholder ONLY when no LLM router is configured at all
    (dev / smoke-test mode). When an LLM router IS configured but its call
    fails, we raise CapabilityExecutionError — the caller refunds the channel
    instead of charging the user for placeholder output.
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
        except Exception as exc:
            # LLM was configured and the call failed — refuse to bill the user
            # for the deterministic mock below. The invoke handler turns this
            # into a 503 + channel refund.
            raise CapabilityExecutionError(
                f"LLM execution failed for {cap_name}: {exc.__class__.__name__}"
            ) from exc
        return _parse_llm_result(raw, cap)

    # In production we must NEVER bill the user for a deterministic placeholder.
    # If no LLM router is configured (or the capability has no real implementation),
    # raise so the invoke handler returns 503 and refunds the channel instead of
    # charging for mock output. The mock below is reachable only in dev / smoke-test.
    if _is_production():
        raise CapabilityExecutionError(
            f"Capability '{cap_name}' has no executable implementation "
            "(no LLM router / agent configured); refusing to bill for placeholder output."
        )

    # Mock fallback — deterministic placeholder. Only reached when llm_router
    # is None or the capability has no agent/prompt_template (dev/test).
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
    x_payment_channel_secret: str | None = None,
    x_ai_market_license: str | None = None,
    authorization: str | None = None,
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
    # What the channel ledger actually charged (a sub-cent price rounds up to a
    # cent) — the receipt and any reversal must use this, not the quote.
    billed = price
    debit_ref = ""

    # --- Payment verification ---
    from core.crypto_config import crypto_enabled

    if not crypto_enabled():
        # Crypto (external blockchain) is OFF — the default. No real-money payment is
        # required or accepted: never return a 402 demanding an on-chain tx, never call
        # an RPC. The invoke runs and settles through the INTERNAL UNI ledger (if
        # enabled) below — the corporate, no-blockchain path. UNI stays independent of
        # this switch, so a real blockchain is never needed to deliver value.
        paid = True
        payment_kind = "uni"
        payment_ref = ""
    elif x_payment_channel:
        ch = get_channel(x_payment_channel.strip())
        if not ch or ch.get("status") != "open":
            raise HTTPException(status_code=402, detail="invalid or closed payment channel")
        owner = str(ch.get("customer_id") or "")
        if owner:
            from web.backend.services.customer_auth import decode_customer

            payload = decode_customer(authorization)
            if not payload or str(payload.get("sub") or "") != owner:
                raise HTTPException(status_code=403, detail="payment channel not owned by caller")
        from uuid import uuid4

        debit_ref = f"{product_id}/{capability_id}/{uuid4().hex[:8]}"
        deduct = deduct_channel(
            x_payment_channel.strip(),
            price,
            ref=debit_ref,
            secret=(x_payment_channel_secret or "").strip(),
        )
        if not deduct.get("ok"):
            debit_ref = ""
            pay_req = build_payment_required(
                product_id=product_id, capability_id=capability_id, amount_usd=price, base_url=base_url
            )
            return 402, {"payment_required": pay_req, "detail": deduct.get("error")}, {
                "X-Payment-Required": json.dumps(pay_req, separators=(",", ":")),
            }
        billed = float(deduct.get("billed_usd", price))
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
        declared_payer = str(pay.get("from") or pay.get("payer") or "").strip()
        payer_signature = str(pay.get("signature") or "").strip()
        if not tx_hash:
            raise HTTPException(status_code=400, detail="X-Payment missing tx_hash")
        tx_clean = normalize_tx_hash(tx_hash, chain=chain)
        # Bind the payment to the wallet that actually paid: verifying only
        # recipient+amount let anyone replay a stranger's hash (and, with no
        # single-use registry, replay their own hash for unlimited invokes).
        verified = verify_tx_transfer(
            tx_hash=tx_clean,
            amount_usd=price,
            chain=chain,
            token=token,
            expect_sender=declared_payer or BIND_SENDER,
        )
        if not verified["verified"]:
            raise HTTPException(
                status_code=402,
                detail=f"on-chain payment not verified ({verified['error']})",
            )
        payer = str(verified["from"] or "")
        if not verified["demo"]:
            if require_payer_proof():
                if not is_evm_chain(chain):
                    raise HTTPException(
                        status_code=402,
                        detail=f"payer proof is only implemented for EVM chains, not {chain}",
                    )
                recovered = recover_payer(
                    purpose="invoke payment",
                    subject=payer,
                    tx_hash=tx_clean,
                    chain=chain,
                    signature=payer_signature,
                )
                if not recovered or recovered.lower() != payer.lower():
                    raise HTTPException(
                        status_code=402,
                        detail=(
                            "X-Payment must include a signature proving control of the "
                            "paying wallet (challenge: 'AIMarket invoke payment')"
                        ),
                    )
            # One transfer buys exactly one invoke: claim the hash atomically.
            claim = claim_payment_tx(
                tx_hash=tx_clean,
                chain=chain,
                token=token,
                amount_usd=price,
                purpose=f"invoke:{product_id}/{capability_id}",
                sender=payer,
                claimant=payer,
            )
            if not claim.get("ok"):
                raise HTTPException(
                    status_code=402,
                    detail="on-chain payment already used for another invoke or order",
                )
        paid = True
        payment_kind = "on_chain"
        payment_ref = tx_clean
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
    refund_info: dict[str, Any] | None = None
    try:
        result = await _execute_capability(cap, product, body_input, llm_router=llm_router)
        success = True
        err_type = None
    except Exception as exc:
        success = False
        result = {"error": str(exc)}
        err_type = "execution_failed"
        if paid and payment_kind == "on_chain" and payment_ref:
            # The transfer stays consumed (else the hash buys unlimited retries),
            # so the unearned money becomes a recorded obligation.
            marked = mark_payment_tx_unfulfilled(
                tx_hash=payment_ref, reason=f"execution_failed:{product_id}/{capability_id}"
            )
            if marked.get("ok"):
                refund_info = {"status": "owed", "amount_usd": billed}
        if paid and payment_kind == "channel" and x_payment_channel and debit_ref and billed > 0:
            # Reverse exactly the debit this call made (idempotent, capped at it),
            # and surface the outcome: a reversal that could not be applied is a
            # debt to the customer, not something to swallow.
            reversal = refund_channel(
                x_payment_channel.strip(),
                billed,
                ref=f"refund:{debit_ref}",
                debit_ref=debit_ref,
            )
            refund_info = {
                "status": "credited" if reversal.get("ok") else "owed",
                "amount_usd": float(
                    reversal.get("credited_usd") or reversal.get("owed_usd") or billed
                ),
            }
            if not reversal.get("ok"):
                refund_info["error"] = reversal.get("error", "refund_failed")

    latency_ms = int((time.time() - t0) * 1000)
    receipt = create_receipt(
        product_id=product_id,
        capability_id=capability_id,
        amount_usd=billed if success else 0.0,
        payment_kind=payment_kind,
        payment_ref=payment_ref,
        success=success,
        result_summary={"keys": list(result.keys())[:12]},
    )

    uni_receipt = None
    if success and paid:
        from web.backend.services.uni_bridge import record_capability_settlement

        buyer_id = ""
        if payment_kind == "channel" and x_payment_channel:
            ch = get_channel(x_payment_channel.strip())
            buyer_id = str((ch or {}).get("customer_id") or "")
        elif authorization:
            from web.backend.services.customer_auth import decode_customer

            payload = decode_customer(authorization)
            buyer_id = str((payload or {}).get("sub") or "")
        uni_settle = record_capability_settlement(
            buyer_owner_id=buyer_id or "anonymous",
            product_id=product_id,
            capability_id=capability_id,
            price_usd=billed,
            payment_ref=payment_ref,
            hub_id=str(os.environ.get("AIFACTORY_PUBLIC_URL", "")).strip(),
            llm_tokens=0,
        )
        if uni_settle:
            if uni_settle.get("error"):
                success = False
                err_type = err_type or "uni_settlement_failed"
            else:
                uni_receipt = uni_settle.get("uni_receipt")

    append_stat({
        "type": "invoke",
        "product_id": product_id,
        "capability_id": capability_id,
        "price_usd": price,
        "billed_usd": billed,
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
    if abs(billed - price) > 1e-9:
        # Sub-cent prices bill up; say so rather than letting the receipt and the
        # quoted price disagree silently.
        body["billed_usd"] = billed
    if uni_receipt:
        body["uni_receipt"] = uni_receipt
    if refund_info:
        body["refund"] = refund_info
    if not success:
        body["error_type"] = err_type
    return 200, body, {}
