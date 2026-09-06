"""Invoking a capability this factory does not host.

The pipeline executor resolved every hop against the factory's own nine capabilities and
answered ``404 capability not found`` for anything else. The studio composes from the
HUB's catalogue — seventy-six rows, every one of them a peer's — so no graph a visitor
could build was runnable. The shop window and the till were wired to different inventories.

Routing the miss through the hub's federated invoke fixes that, and the interesting part
is who pays:

* **Nothing of ours is spent on a stranger's behalf.** No payment credential of this
  factory is ever attached. A hop the hub serves free succeeds; one that needs money comes
  back 402 and fails as that hop, with the reason visible.
* **The visitor's own free trial is what makes a real run possible.** The hub meters a
  renewing per-visitor allowance keyed by ``X-AIMarket-Sandbox-Visitor``. Forwarding the
  visitor's id — not this factory's identity — is the whole difference between everyone
  sharing one exhausted bucket and each person getting their own three calls.
* **The receipt must not lie about the buyer.** Whoever paid is recorded per hop, so a
  trial run reads as a trial run rather than as a purchase by the factory.
"""

from __future__ import annotations

from typing import Any

SANDBOX_VISITOR_HEADER = "X-AIMarket-Sandbox-Visitor"


def federation_hub_url() -> str:
    """The hub this factory routes unknown capabilities to. Empty when unconfigured."""
    from core.aimarket_hub_url import resolve_federation_hub_url

    # fallback_on_invalid=False: an explicitly-set but malformed value is returned as-is so
    # the safety check below refuses it, rather than silently falling back to the public
    # default hub and invoking somewhere the operator did not name.
    return resolve_federation_hub_url(include_hub_url_var=True, fallback_on_invalid=False)


def _url_is_safe(url: str) -> bool:
    return bool(url) and url.startswith(("http://", "https://")) and not any(
        c in url for c in "\r\n\t"
    )


async def invoke_federated(
    *,
    product_id: str,
    capability_id: str,
    body_input: dict[str, Any],
    source_hub: str | None = None,
    sandbox_visitor: str | None = None,
    payment_channel: str | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any]]:
    """Invoke a capability through the configured hub. Returns (status, body).

    ``payment_channel`` is only ever a channel the CALLER supplied for this one request.
    There is no parameter for a factory-owned channel on purpose: an unauthenticated Run
    button that spends the operator's balance is an open faucet, and every receipt it
    produced would name the wrong buyer.
    """
    hub = federation_hub_url()
    if not hub:
        return 502, {
            "success": False,
            "error": "federation_not_configured",
            "detail": (
                "This capability is not hosted here and no federation hub is configured. "
                "Set AIMARKET_FEDERATION_HUB_URL to the hub that carries it."
            ),
        }
    if not _url_is_safe(hub):
        return 502, {
            "success": False,
            "error": "federation_url_unsafe",
            "detail": "AIMARKET_FEDERATION_HUB_URL must be an http(s) URL.",
        }

    headers = {"Content-Type": "application/json"}
    if sandbox_visitor:
        headers[SANDBOX_VISITOR_HEADER] = sandbox_visitor
    if payment_channel:
        headers["X-Payment-Channel"] = payment_channel

    payload = {
        "product_id": product_id,
        "capability_id": capability_id,
        "input": body_input,
    }
    if source_hub:
        payload["source_hub"] = source_hub

    # Imported here, not at module scope: `pipelines` must stay importable in a lean
    # environment (the pipeline tests rely on that), and httpx is only needed once a hop
    # actually leaves this process.
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{hub.rstrip('/')}/ai-market/v2/invoke", json=payload, headers=headers
            )
    except Exception as exc:  # noqa: BLE001 — the hub is a separate service
        return 502, {"success": False, "error": "federation_unreachable", "detail": str(exc)[:200]}

    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        return 502, {
            "success": False,
            "error": "federation_returned_non_json",
            "status_code": response.status_code,
        }
    return response.status_code, normalise_response(body if isinstance(body, dict) else {"result": body})


def normalise_response(body: dict[str, Any]) -> dict[str, Any]:
    """Speak the executor's shape, whatever the hub answered in.

    A local invoke returns ``{"success": ..., "result": ...}``; the hub's federated invoke
    returns ``{"ok": ..., "output": ...}``. The executor reads the first shape, so an
    un-normalised federated hop reported success with an EMPTY result — and the next hop's
    ``${read.reading}`` had nothing to read. The run looked fine and carried no data, which
    is the exact failure this whole feature exists to remove.
    """
    if not isinstance(body, dict):
        return {"success": False, "error": "federation_returned_non_object"}
    out = dict(body)
    if "success" not in out and "ok" in out:
        out["success"] = bool(out.get("ok"))
    if "result" not in out and "output" in out:
        out["result"] = out.get("output")
    return out


def payer_of(*, local: bool, sandbox_visitor: str | None, payment_channel: str | None) -> str:
    """How a hop was paid for, for the bill of materials.

    A signed document that says "the factory bought this" when a visitor's free trial
    covered it is worse than one that says nothing: it is evidence of the wrong fact.
    """
    if local:
        return "local"
    if payment_channel:
        return "channel"
    if sandbox_visitor:
        return "trial"
    return "unpaid"
