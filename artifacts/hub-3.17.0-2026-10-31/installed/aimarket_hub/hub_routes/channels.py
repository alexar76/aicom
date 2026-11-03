"""Payment channels and the escrow bridge: open, close, status, plan and recorded obligations."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aimarket_hub.api_models import ChannelCloseRequest, ChannelOpenRequest
from aimarket_hub.channels import close_channel, open_channel
from aimarket_hub.config import HubConfig


def register(
    *,
    _INVOKE_RATE_WORKERS: int,
    _TRUSTED_PROXIES: frozenset[str],
    _require_admin: Callable[..., Any],
    config: HubConfig,
    router: APIRouter,
) -> None:
    """Attach the /channel and /escrow routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _client_address,
        _env_positive_int,
        _trim_rate_buckets,
        logger,
    )

    # ── Payment Channels ────────────────────────────────────────

    # Per-IP limit on channel open/close, paired with the ledger's per-wallet windows.
    # The ledger keys on the caller-supplied wallet, so it can only ration an identity
    # the attacker chooses; its bucket table now evicts LRU rather than refusing when
    # full (which had turned a flood into a total outage), and THIS is the cap that
    # actually bounds the flood, because the client address is not attacker-chosen.
    _channel_rate: dict[str, list[float]] = {}
    _CHANNEL_RATE_WINDOW_S = 60.0
    _CHANNEL_RATE_MAX_KEYS = 20_000
    _CHANNEL_RATE_CONFIGURED = _env_positive_int("AIMARKET_CHANNEL_RATE_PER_MIN", 30)
    if _CHANNEL_RATE_CONFIGURED <= 0:
        _CHANNEL_RATE_MAX = _CHANNEL_RATE_CONFIGURED  # 0 keeps the documented "disabled"
    else:
        # Same in-process-window residual as the invoke limiter above, closed the same
        # way: this budget is an AGGREGATE, so divide it across the declared worker
        # count (_INVOKE_RATE_WORKERS is that count, read once for the process).
        # Without the division an N-worker deploy silently admitted N x the configured
        # cap — and this cap is what the ledger's LRU eviction relies on to bound a
        # flood, so an unbounded version of it re-opens the DoS it was added to close.
        # Round up so a tiny budget never floors to zero requests per worker.
        _CHANNEL_RATE_MAX = max(1, -(-_CHANNEL_RATE_CONFIGURED // _INVOKE_RATE_WORKERS))
        if _INVOKE_RATE_WORKERS > 1:
            logger.info(
                "channel rate limit: %d/min configured across %d declared worker(s) "
                "→ %d/min per worker (in-memory window)",
                _CHANNEL_RATE_CONFIGURED, _INVOKE_RATE_WORKERS, _CHANNEL_RATE_MAX,
            )

    def _check_channel_ip_rate(client_ip: str) -> bool:
        """Return True if this client address is within the channel-endpoint budget.

        An address-less caller (ASGI transports without a peer, e.g. some test
        clients) shares one bucket rather than being exempt — "no address" must not
        read as "no limit".
        """
        if _CHANNEL_RATE_MAX <= 0:
            return True
        key = (client_ip or "").strip() or "\x00no-address"
        now = time.time()
        window = now - _CHANNEL_RATE_WINDOW_S
        bucket = [t for t in _channel_rate.get(key, []) if t > window]
        if len(bucket) >= _CHANNEL_RATE_MAX:
            _channel_rate[key] = bucket
            return False
        bucket.append(now)
        _channel_rate[key] = bucket
        if len(_channel_rate) > _CHANNEL_RATE_MAX_KEYS:
            _trim_rate_buckets(_channel_rate, window, _CHANNEL_RATE_MAX_KEYS, keep=key)
        return True

    def _channel_rate_limited() -> JSONResponse:
        return JSONResponse(status_code=429, content={
            "success": False,
            "error": "rate_limited",
            "detail": (
                f"channel endpoint rate limit exceeded — max {_CHANNEL_RATE_MAX} "
                "requests per minute per client address"
            ),
            "protocol_version": "v2",
        })

    @router.post("/channel/open")
    async def channel_open(body: ChannelOpenRequest, request: Request):
        if not config.crypto_enabled:
            return JSONResponse(status_code=503, content={
                "success": False, "error": "crypto_disabled",
                "detail": "payment channels disabled by operator (AIFACTORY_CRYPTO_ENABLED=0) — capabilities are served free",
            })
        if not _check_channel_ip_rate(_client_address(request, _TRUSTED_PROXIES)):
            return _channel_rate_limited()
        # payer_signature is what makes a production open possible AT ALL: the ledger
        # refuses an on-chain-verified deposit without proof the caller controls the
        # paying wallet, so a transport that dropped this field turned every real
        # channel open into "missing or invalid payer proof".
        result = open_channel(
            deposit_usd=body.deposit_usd,
            token=body.token,
            chain=body.chain,
            wallet=body.wallet,
            tx_hash=body.tx_hash,
            payer_signature=body.payer_signature,
            escrow_channel_id=body.escrow_channel_id,
        )
        if result.get("error"):
            return JSONResponse(status_code=400, content=result)
        return result

    @router.post("/channel/close")
    async def channel_close(
        body: ChannelCloseRequest,
        request: Request,
        x_payment_channel_secret: str | None = Header(default=None, alias="X-Payment-Channel-Secret"),
    ):
        if not config.crypto_enabled:
            return JSONResponse(status_code=503, content={
                "success": False, "error": "crypto_disabled",
                "detail": "payment channels disabled by operator (AIFACTORY_CRYPTO_ENABLED=0)",
            })
        if not _check_channel_ip_rate(_client_address(request, _TRUSTED_PROXIES)):
            return _channel_rate_limited()
        result = close_channel(
            channel_id=body.channel_id,
            settle_tx_hash=body.settle_tx_hash,
            wallet=body.wallet or "",
            secret=x_payment_channel_secret or "",
        )
        if result.get("error"):
            return JSONResponse(status_code=400, content=result)
        return result

    # ── Payout obligations (operator liability ledger, ACCT-001) ─
    #
    # Closing or expiring a channel records the unspent remainder as a DEBT rather
    # than transferring it (nothing in the hub can send value). Until these routes
    # existed the debt was recorded and then invisible: an operator had no way to see
    # who was owed what, and no way to write a payout off once they had made it.
    # Admin-gated because a row names a depositor's wallet, their balance and their
    # deposit tx — and because marking one paid destroys a customer's claim.

    def _bearer(authorization: str) -> str:
        return authorization[7:] if authorization.startswith("Bearer ") else ""

    # ── Escrow settlement bridge (opt-in, read-only surface) ─────────────────
    # Admin-gated for the same reasons the obligations ledger is: a row names a
    # depositor's wallet and the amount the hub intends to collect from them. There is
    # deliberately NO route that broadcasts — submission stays an operator CLI action
    # (`python -m aimarket_hub.escrow_bridge.cli submit --yes`), so nothing reachable
    # over HTTP can move funds.

    @router.get("/escrow/status")
    async def escrow_bridge_status(
        limit: int = 200,
        authorization: str = Header(default=""),
    ):
        """Bridge configuration, the pending authorization queue, and what it would submit."""
        _require_admin(authorization)
        try:
            from aimarket_hub.escrow_bridge import config as bridge_config
            from aimarket_hub.escrow_bridge import signer as bridge_signer
            from aimarket_hub.escrow_bridge import store as bridge_store
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"escrow bridge unavailable: {type(exc).__name__}"
            ) from exc

        snapshot: dict[str, Any] = {
            "config": bridge_config.describe(),
            "signer": bridge_signer.build_signer().name,
            "protocol_version": "v2",
        }
        try:
            # create=False: inspecting a hub that never enabled the bridge must not
            # materialise its schema as a side effect of asking.
            authorizations = bridge_store.AuthorizationStore(create=False)
        except bridge_store.StoreError:
            snapshot["store"] = "absent — no authorization has been recorded yet"
            snapshot["queue"] = []
            return snapshot
        snapshot["store"] = authorizations.stats()
        snapshot["queue"] = [
            row.as_dict() for row in authorizations.unresolved(limit=min(max(limit, 1), 1_000))
        ]
        return snapshot

    @router.get("/escrow/plan")
    async def escrow_bridge_plan(
        limit: int = 100,
        authorization: str = Header(default=""),
    ):
        """Simulate every pending authorization against the chain. Sends NOTHING.

        Forced into plan mode regardless of how submission is configured, so this route
        cannot broadcast even on a hub that is fully armed to.
        """
        _require_admin(authorization)
        try:
            from aimarket_hub.escrow_bridge import mirror as bridge_mirror
            from aimarket_hub.escrow_bridge import signer as bridge_signer
            from aimarket_hub.escrow_bridge import store as bridge_store
            from aimarket_hub.escrow_bridge.errors import BridgeError
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"escrow bridge unavailable: {type(exc).__name__}"
            ) from exc
        try:
            engine = bridge_mirror.Mirror(
                authorizations=bridge_store.AuthorizationStore(),
                signer=bridge_signer.PlanOnlySigner(),
            )
            report = engine.run(limit=min(max(limit, 1), 500))
        except BridgeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {**report.as_dict(), "protocol_version": "v2"}

    @router.get("/channel/obligations")
    async def channel_obligations_list(
        status: str = "owed",
        limit: int = 500,
        authorization: str = Header(default=""),
    ):
        _require_admin(authorization)
        from aimarket_hub.channels import channel_obligations, channel_obligations_total

        token = _bearer(authorization)
        allowed_status = {"owed", "paid", ""}
        if status not in allowed_status:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of {sorted(allowed_status)}",
            )
        return {
            "obligations": channel_obligations(
                status=status, limit=min(max(limit, 1), 5_000), operator_token=token,
            ),
            "totals": {
                state: channel_obligations_total(status=state, operator_token=token)
                for state in ("owed", "paid")
            },
            "note": (
                "Recorded debts to depositors. The hub never moves funds: pay them "
                "out-of-band, then POST /channel/obligations/{channel_id}/paid."
            ),
            "protocol_version": "v2",
        }

    @router.post("/channel/obligations/{channel_id}/paid")
    async def channel_obligation_mark_paid(
        channel_id: str,
        body: dict[str, Any],
        authorization: str = Header(default=""),
    ):
        """Attest that an obligation was settled out-of-band. Never sends value."""
        _require_admin(authorization)
        from aimarket_hub.channels import mark_obligation_paid

        payout_tx_hash = str(body.get("payout_tx_hash", "") or "").strip()
        result = mark_obligation_paid(
            channel_id, payout_tx_hash, operator_token=_bearer(authorization),
        )
        if result.get("error"):
            return JSONResponse(status_code=400, content={**result, "protocol_version": "v2"})
        return {**result, "protocol_version": "v2"}
