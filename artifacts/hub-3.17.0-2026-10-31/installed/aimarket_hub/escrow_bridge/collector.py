"""Unattended collection of authorized escrow debits.

KI-11's third consequence: a verified, collectable claim is captured on every paid
invoke against an escrow-bound channel, and *nothing collects it* unless an operator
remembers to run `python -m aimarket_hub.escrow_bridge.cli submit --yes`. An
unattended hub accrues claims it never presents — the three mainnet settlements in
the journal were made by hand, and the hub did not know it had been paid because it
was not the payer.

This is the missing trigger. It is a bounded background pass in the hub's own
lifespan rather than a host timer, because a timer is a second place to configure,
a second place to forget, and it drifts away from the image it was installed beside.

WHAT BOUNDS IT, in the order the bounds apply:

  1. **Off unless asked.** `AIMARKET_ESCROW_COLLECT_INTERVAL_S` defaults to 0, which
     is "never". A hub that has not opted in behaves exactly as before.
  2. **The bridge's own policy.** Nothing is broadcast unless `submit_policy()` says
     it may be — the plan-only strategy stays plan-only, and a hub with no signer
     stays incapable, from here as much as from the CLI.
  3. **The spend caps that already exist.** `AIMARKET_ESCROW_MAX_USD_PER_PASS` and
     `..._PER_DAY` are enforced inside `Mirror._budget_blocks`, so this loop cannot
     spend more by calling more often. That is deliberate: the caps are the real
     limit, and the interval is only how promptly the hub asks.
  4. **A row limit per pass**, so one cycle cannot run unboundedly long against a
     large backlog.

`confirm()` runs BEFORE `run()` on every cycle, and that order is load-bearing.
Submission is strictly nonce-ordered per channel, so a debit that was collected out
of band — by hand, by an operator, by the CLI — leaves a row that can never resolve
itself and blocks *every later row on its channel*. `confirm()` is the pass that
reads `usedReceipts()` and resolves those; running it second would let one stuck row
hold up the queue for a full interval each time.

Failures are logged and swallowed. A collection pass that raises must not take down
the hub that is serving calls: not collecting is a revenue problem, and crashing the
process is an availability one.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

logger = logging.getLogger(__name__)

#: One pass will not touch more rows than this, however long the backlog is.
DEFAULT_LIMIT = 200


def interval_s() -> int:
    """Seconds between passes. 0 (the default) disables unattended collection.

    Floored at 60 when enabled: the caps bound how much is spent, so a shorter
    interval buys nothing but RPC load against the same ceiling.
    """
    try:
        raw = int(os.getenv("AIMARKET_ESCROW_COLLECT_INTERVAL_S", "0"))
    except ValueError:
        return 0
    return 0 if raw <= 0 else max(60, raw)


def limit() -> int:
    try:
        return max(1, int(os.getenv("AIMARKET_ESCROW_COLLECT_LIMIT", str(DEFAULT_LIMIT))))
    except ValueError:
        return DEFAULT_LIMIT


def blocked_reason() -> str:
    """Why a pass would do nothing, or "" when it would run. Never raises."""
    if interval_s() <= 0:
        return "unattended collection is off (AIMARKET_ESCROW_COLLECT_INTERVAL_S=0)"
    try:
        from aimarket_hub.escrow_bridge import config as bridge_config
    except Exception as exc:  # pragma: no cover - import guard
        return f"escrow bridge is unavailable: {exc}"
    if not bridge_config.enabled():
        return "escrow bridge is disabled (AIMARKET_ESCROW_BRIDGE_ENABLED=0)"
    policy = bridge_config.submit_policy()
    if not policy.may_broadcast:
        return policy.reason or "submission strategy is 'plan'; nothing would be sent"
    return ""


def collect_once() -> dict[str, Any]:
    """One confirm-then-submit pass. Synchronous: call it off the event loop.

    Returns a summary rather than raising, so a caller can log it without a try block
    of its own. `skipped` means the pass declined to act and says why.
    """
    reason = blocked_reason()
    if reason:
        return {"skipped": reason}
    from aimarket_hub.escrow_bridge import mirror, store

    authorizations = store.AuthorizationStore()
    engine = mirror.Mirror(authorizations=authorizations)
    rows = limit()
    # Resolve out-of-band collections FIRST — see the module docstring on head-of-line.
    confirmed = engine.confirm(limit=rows).as_dict()
    submitted = engine.run(limit=rows).as_dict()
    return {"confirmed": confirmed, "submitted": submitted}


async def run_forever(*, sleep=asyncio.sleep) -> None:
    """The lifespan task. Returns immediately when collection is off.

    `sleep` is injectable so a test can drive the loop without wall-clock time.
    """
    interval = interval_s()
    if interval <= 0:
        return
    logger.info(
        "Escrow collection enabled: every %ds, up to %d row(s) per pass, "
        "inside the existing per-pass and per-day spend caps",
        interval, limit(),
    )
    while True:
        # Sleep FIRST: a hub that has just started has nothing new to collect, and a
        # pass during startup competes with the work that makes it serve requests.
        await sleep(interval + random.uniform(0, min(60.0, interval * 0.1)))
        try:
            result = await asyncio.to_thread(collect_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("escrow collection pass failed: %s", exc)
            continue
        if result.get("skipped"):
            # Config can change under a running process; say so once per pass rather
            # than silently doing nothing forever.
            logger.info("escrow collection skipped: %s", result["skipped"])
            continue
        logger.info(
            "escrow collection: confirmed=%s submitted=%s",
            (result.get("confirmed") or {}).get("outcomes"),
            (result.get("submitted") or {}).get("outcomes"),
        )
