"""Live market statistics, supply permission violations and supply audits."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from aimarket_hub import credits, ecosystem, terminal_ssr, x402
from aimarket_hub.api_models import PermissionViolationRequest
from aimarket_hub.channels import channel_stats
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.database import HubDatabase
from aimarket_hub.public_cache import PublicDocumentCache
from aimarket_hub.supply_chain_admission import SupplyChainAdmission
from aimarket_hub.supply_security import SupplySecurity
from aimarket_hub.x402 import PaymentStore as X402PaymentStore


def register(
    *,
    _NS_AGENT: tuple[str, str, dict[str, str]],
    _NS_PUBLISHER: tuple[str, str, dict[str, str]],
    _TRUSTED_PROXIES: frozenset[str],
    _ecosystem_policy: Callable[..., Any],
    _require_subject_credential: Callable[..., Any],
    config: HubConfig,
    db: HubDatabase,
    hub_credits: CreditsLedger,
    hub_x402: X402PaymentStore,
    router: APIRouter,
    supply_chain_admission: SupplyChainAdmission,
    supply_security: SupplySecurity,
) -> None:
    """Attach /stats/live and the supply violation and audit routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _catalogue_snapshot,
        _client_address,
        _trim_rate_buckets,
    )

    # Every caller gets the same page for a given limit, so it is built once per TTL and
    # in a worker thread: on 2026-10-16 a monitor asking for this every 1.5 s, at 0.25 s a
    # build on the event loop, kept /health queued until hub.attestedmemory.net went down.
    _live_stats_cache = PublicDocumentCache("AIMARKET_STATS_LIVE_CACHE_S", 30.0)

    @router.get("/stats/live")
    async def live_stats(limit: int = 50):
        # Stays on the loop: it schedules a task there.
        supply_chain_admission.schedule_refresh()
        page = min(limit, 200)
        return await run_in_threadpool(
            _live_stats_cache.get, page, lambda: _build_live_stats(page)
        )

    def _build_live_stats(limit: int) -> dict[str, Any]:
        stats = db.recent_stats(limit=limit)
        summary = db.stats_summary()
        public_caps = _catalogue_snapshot(db, config)
        summary["capabilities_count"] = len(public_caps)
        summary["offerable_capabilities_count"] = len(public_caps)
        summary["federated_capabilities_count"] = sum(
            1 for c in public_caps if (c.source_hub or "local") != "local"
        )
        ch = channel_stats()
        summary["open_channels"] = ch.get("open_channels", 0)
        # Volume that has FINISHED flowing through channels = settled + expired.
        # Reading channels.stats()["settled_volume_usd"] here counted only rows in
        # state 'settled', so every dollar spent through a channel that timed out
        # instead of being closed vanished from the live metric — which was the
        # original defect, re-introduced one layer up when the ledger was fixed.
        # The name stays for consumers; the breakdown below makes it unambiguous.
        summary["settled_volume_usd"] = ch.get("closed_volume_usd", 0)
        summary["settled_only_volume_usd"] = ch.get("settled_volume_usd", 0)
        summary["expired_volume_usd"] = ch.get("expired_volume_usd", 0)
        # Money the operator owes depositors but has not paid out (ACCT-001). No
        # depositor is named here — the detail view is admin-only — but the total is
        # public on purpose: it is the solvency number.
        summary["outstanding_obligations_usd"] = ch.get("outstanding_obligations_usd", 0)
        summary["outstanding_obligations"] = ch.get("outstanding_obligations", 0)
        # Whether this hub can take money at all. A hub that refuses every deposit looks
        # exactly like a hub nobody has paid yet — modelmarket.dev sat in the first state
        # for weeks with 0 refusals in its log, because the deposit door had never once
        # been knocked on. Published next to the volume it governs.
        from aimarket_hub.channels import payment_readiness

        summary["payment_readiness"] = payment_readiness()
        hub_url = (config.hub_url or "").rstrip("/")
        policy = _ecosystem_policy()
        events = terminal_ssr.public_events(stats, hub_url, policy=policy)
        summary["operator_self_events_in_page"] = sum(
            1 for ev in events if ev["traffic_class"] == ecosystem.TRAFFIC_SELF)
        summary["external_events_in_page"] = len(events) - summary["operator_self_events_in_page"]
        # Same split over the whole table, so the public card can print a breakdown
        # that actually adds up to `total_invocations` instead of one page of it.
        lifetime_split = db.consumer_traffic_totals(policy=policy, hub_url=hub_url)
        summary["external_invocations"] = lifetime_split["external"]
        summary["operator_self_invocations"] = lifetime_split["operator_self"]
        # How many entries decide SELF, and whether the file loaded — never the entries.
        summary["traffic_policy"] = policy.public_summary()
        # The credits rail's own P&L, published for the same reason the channel ledger's
        # obligations are: `credits_earned_usd` is what this node has actually taken, and
        # `outstanding_credit_usd` is prepaid money it is holding for somebody else.
        if credits.enabled():
            _cl = hub_credits
            if _cl is not None:
                summary["credits"] = _cl.stats()
        if x402.accept_enabled():
            # On-chain transfers to sellers this hub verified. Not a receivable.
            summary["x402"] = hub_x402.stats()
        summary["hub_url"] = hub_url
        summary["supply_chain_admission"] = supply_chain_admission.public_summary()
        return {
            "events": events,
            "summary": summary,
            "supply_chain_audits": db.supply_audits_recent(limit=min(limit, 50)),
            "protocol_version": "v2",
        }

    _violation_rate: dict[str, list[float]] = {}
    _VIOLATION_RATE_MAX = 12
    _VIOLATION_RATE_WINDOW_S = 60.0

    def _check_violation_rate(client_ip: str) -> bool:
        key = (client_ip or "").strip() or "\x00no-address"
        now = time.time()
        window = now - _VIOLATION_RATE_WINDOW_S
        bucket = [t for t in _violation_rate.get(key, []) if t > window]
        if len(bucket) >= _VIOLATION_RATE_MAX:
            _violation_rate[key] = bucket
            return False
        bucket.append(now)
        _violation_rate[key] = bucket
        if len(_violation_rate) > 4096:
            _trim_rate_buckets(_violation_rate, window, 4096, keep=key)
        return True

    @router.post("/supply/permission-violation")
    async def supply_permission_violation(
        body: PermissionViolationRequest,
        request: Request,
        authorization: str = Header(default=""),
    ):
        """Report, with a signature, that a capability broke its own declaration.

        This is the runtime half of publish-time admission: a declared permission
        is only a claim until somebody who watched the capability run can
        contradict it in a way a third party can re-check. The signature is
        verified against the declaration on record, so this endpoint cannot be
        used to invent a declaration.

        The signature proves the reporter committed to the declaration digest on
        record — not that it ever ran the capability, and ``reporter_pubkey`` is
        free to mint. So the slash threshold counts only reporters whose identity
        this hub AUTHENTICATED: present ``Authorization: Bearer <token>`` for the
        ``consumer_id`` you claim (AIMARKET_AGENT_TOKENS / AIMARKET_PUBLISHER_TOKENS,
        or the admin token). An unauthenticated report is still recorded and still
        returned in ``distinct_reporters``, but it cannot take a publisher's stake.
        """
        if not _check_violation_rate(_client_address(request, _TRUSTED_PROXIES)):
            return JSONResponse(status_code=429, content={
                "success": False, "error": "rate_limited",
                "detail": (
                    f"permission-violation reports limited to {_VIOLATION_RATE_MAX} "
                    "per minute per client address"
                ),
                "protocol_version": "v2",
            })
        # A Bearer token, when offered, must actually authorize the claimed consumer_id
        # (raises 401/403/409 otherwise — see _require_subject_credential). No token is
        # not an error: the report is accepted as an unbound observation.
        reporter_bound = False
        if authorization.startswith("Bearer ") and body.consumer_id.strip():
            _require_subject_credential(
                authorization, body.consumer_id.strip(), (_NS_PUBLISHER, _NS_AGENT)
            )
            reporter_bound = True
        outcome = supply_chain_admission.record_permission_violation(
            product_id=body.product_id,
            capability_id=body.capability_id,
            permission=body.permission,
            reporter_pubkey=body.reporter_pubkey,
            signature=body.signature,
            consumer_id=body.consumer_id,
            consumer_bound=reporter_bound,
        )
        if not outcome.get("accepted"):
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": outcome.get("reason", "rejected"),
                "protocol_version": "v2",
            })
        ladder = supply_security.record_permission_violation(
            publisher_id=outcome["publisher_id"],
            product_id=body.product_id,
            capability_id=body.capability_id,
            permission=outcome["permission"],
            # The AUTHENTICATED count, not the key count — see the docstring above.
            distinct_reporters=outcome["bound_reporters"],
            threshold=outcome["threshold"],
            consumer_id=body.consumer_id if reporter_bound else "",
            reporter_bound=reporter_bound,
        )
        return {
            "success": True,
            "recorded": not outcome["duplicate"],
            "permission": outcome["permission"],
            "distinct_reporters": outcome["distinct_reporters"],
            "bound_reporters": outcome["bound_reporters"],
            "reporter_authenticated": outcome["reporter_bound"],
            "threshold": outcome["threshold"],
            "contradicted": outcome["contradicted"],
            "slashed": ladder.get("slashed", False),
            "protocol_version": "v2",
        }

    @router.get("/supply/audits")
    async def supply_audits(limit: int = 20):
        """Public, dossier-free admission receipts for Monitor and operators."""
        supply_chain_admission.schedule_refresh()
        return {
            "summary": supply_chain_admission.public_summary(),
            "audits": db.supply_audits_recent(limit=min(max(limit, 1), 50)),
            "protocol_version": "v2",
        }
