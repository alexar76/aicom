"""Port the receipt-binding change onto a LIVE (pre-split) hub tree.

usage: python3 port_patch.py <live_dir> <out_dir>
<live_dir> holds api.py, api_models.py, hub_routes_invoke.py and (optionally) prov_plugin.py
as copied out of a running hub. Every replacement must match exactly once, or nothing is written.
"""

import pathlib
import sys

live, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def sub(text, old, new, name):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{name}: anchor found {n} times:\n{old[:200]}")
    return text.replace(old, new)


# ── hub_routes/invoke.py (monolith) ───────────────────────────────────────────
t = (live / "hub_routes_invoke.py").read_text()
t = sub(t, "from fastapi.responses import JSONResponse\n",
        "from fastapi.encoders import jsonable_encoder\nfrom fastapi.responses import JSONResponse\n"
        "import logging as _rb_logging\n\nfrom aimarket_hub import receipt_binding\n", "invoke imports")
t = sub(t, '''        prepare opened — on every exit, including an exception — and completes the answer.
        """
''', '''        prepare opened — on every exit, including an exception — and completes the answer.
        """
        client_nonce, nonce_error = receipt_binding.read_client_nonce(request.headers)
        if nonce_error:
            return JSONResponse(status_code=400, content={
                "success": False, "error": "client_nonce_invalid", "detail": nonce_error})
''', "invoke nonce check")
t = sub(t, '''        finally:
            finished = invoke_funding.finish(
                funding, result, credits_ledger=ledger, store=hub_mandates, jobs=hub_jobs,
            )
        return finished
''', '''        finally:
            finished = invoke_funding.finish(
                funding, result, credits_ledger=ledger, store=hub_mandates, jobs=hub_jobs,
            )
        return _bind_receipt(finished, body, client_nonce)

    def _bind_receipt(result: Any, body: InvokeRequest, client_nonce: str | None) -> Any:
        """Sign what was asked and what was answered next to the receipt (receipt_binding.py).

        Last, after finish(), so the digest covers the answer exactly as the buyer gets it.
        Never fails the call: a delivered answer without a binding is what every hub sent
        before this existed."""
        status, content = invoke_funding._body_of(result)
        if status != 200 or not isinstance(content, dict) or not content.get("success"):
            return result
        try:
            content = jsonable_encoder(content)
            binding = receipt_binding.build(
                content, input_payload=jsonable_encoder(body.input), client_nonce=client_nonce,
                hub_url=config.hub_url, signer=signer)
        except Exception as exc:  # noqa: BLE001
            _rb_logging.getLogger(__name__).error("receipt binding failed: %s", exc)
            return result
        if binding is None:
            return result
        content["receipt_binding"] = binding
        headers = {} if isinstance(result, dict) else {
            k: v for k, v in result.headers.items() if k.lower() not in ("content-length", "content-type")}
        if client_nonce:
            headers[receipt_binding.CLIENT_NONCE_ECHO_HEADER] = client_nonce
        return JSONResponse(status_code=status, content=content, headers=headers)
''', "invoke bind")
t = sub(t, '''    receipt_artifacts = plugins.run_receipt_hooks(result, {
        "product_id": body.product_id,''', '''    receipt_artifacts = plugins.run_receipt_hooks(result, {
        # The answer carries this value as `result`; the signed subject says so.
        "output_digest_of": "result",
        "product_id": body.product_id,''', "local hook")
t = sub(t, '''    # The routing hub now issues the same portable AWR class for peer work as
    # for local work.  It signs the peer envelope (including its own gateway
    # receipt/attestation) while naming the actual provider hub.  Charged price
    # is the amount THIS hub settled, never the peer's self-reported list price.
    if bool(result_data.get("success", False)):
        fed_elapsed_ms = int((time.time() - fed_started) * 1000)
        receipt_artifacts = plugins.run_receipt_hooks(result_data, {''', '''    # The routing hub now issues the same portable AWR class for peer work as
    # for local work, naming the actual provider hub. Charged price is the amount
    # THIS hub settled, never the peer's self-reported list price.
    #
    # outputDigest covers the member of this answer that carries the work, named in
    # the signed subject as `outputDigestOf`; the peer's own receipt is committed to
    # separately (`gatewayReceiptDigest`). It used to digest the whole envelope at this
    # point — which then grew (provenance_receipt, mandate, subcontracting), so no
    # buyer could recompute it from the answer they received.
    if bool(result_data.get("success", False)):
        fed_elapsed_ms = int((time.time() - fed_started) * 1000)
        output_member = "output" if "output" in result_data else "result"
        receipt_artifacts = plugins.run_receipt_hooks(result_data.get(output_member), {
            "output_digest_of": output_member,
            "routed": True,''', "federated hook")
(out / "hub_routes_invoke.py").write_text(t)

# ── api.py ────────────────────────────────────────────────────────────────────
t = (live / "api.py").read_text()
t = sub(t, '''        signer=signer,
        verify_svc=verify_svc,
    )
''', '''        signer=signer,
        verify_svc=verify_svc,
        db=db,
    )
''', "api verification register")
(out / "api.py").write_text(t)

# ── api_models.py ─────────────────────────────────────────────────────────────
t = (live / "api_models.py").read_text()
t = sub(t, '''    becoming a JSON amplification surface.
    """

    receipt: dict[str, Any]
''', '''    becoming a JSON amplification surface.

    A receipt signed by a federation peer is checked against the key this Hub pinned for
    that peer, never one taken from the request. `receipt_binding` (spec §7.3.9) is
    checked against the key of the Hub that answered — this one or a pinned peer — and,
    when `response`, `input` or `client_nonce` are sent, against them as well.
    """

    receipt: dict[str, Any]
    receipt_binding: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    input: Any = None
    client_nonce: str | None = Field(default=None, max_length=128)
''', "api_models")
(out / "api_models.py").write_text(t)

# ── provenance plugin.py ──────────────────────────────────────────────────────
if (live / "prov_plugin.py").exists():
    t = (live / "prov_plugin.py").read_text()
    t = sub(t, '''                status=context.get("status", "succeeded"),
                invocation_nonce=context.get("nonce"),
                settlement=settlement,''', '''                status=context.get("status", "succeeded"),
                invocation_nonce=context.get("nonce"),
                settlement=settlement,
                output_digest_of=context.get("output_digest_of"),
                # Only a routed call has a receipt signed by someone else to commit to.
                gateway_receipt=context.get("gateway_receipt") if context.get("routed") else None,''',
            "provenance plugin")
    (out / "prov_plugin.py").write_text(t)
print("ported into", out)
