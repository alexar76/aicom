"""The hub app's lifespan: what runs in the background while it serves.

The periodic federation crawl (on its own thread and database connection), escrow debit
collection, the subcontracting-allowance and stale-hold sweeps, the A2A task sweep, the
deposit watch, the OpenAPI merge, the observed-seller cycle, and the Pay-on-Verified
reconcile at start; all cancelled,
and the settlement worker and plugins shut down, when the app stops. Moved out of
api.create_app, which builds it with `make_lifespan`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI

from aimarket_hub import (
    credits, deposit_watch, invoke_funding, observed_sellers, openapi_merge, peer_routing,
)
from aimarket_hub.database import HubDatabase
from aimarket_hub.trust import TrustScorer

logger = logging.getLogger(__name__)


def make_lifespan(
    *,
    config: Any,
    signer: Any,
    verify_svc: Any,
    plugins: Any,
    hub_credits: Any,
    hub_mandates: Any,
    hub_jobs: Any,
    late: SimpleNamespace,
    db: Any = None,
):
    """The lifespan context manager for one app.

    `late` carries what create_app binds after the app object exists and the background work
    reads once it runs: ``slash_registry`` (refreshed after each crawl) and
    ``deposit_watcher`` (the scanner factory of the accounts routes).
    """

    @contextlib.asynccontextmanager
    async def _lifespan(fastapi_app: FastAPI):
        """Run a periodic federation crawl so peers (e.g. Platon) are discovered
        and indexed automatically — honouring crawl_interval_s, which until now
        was advertised but never consumed. Opt out with AIMARKET_AUTO_CRAWL=0."""
        from aimarket_hub.mcp_gateway import install_access_log_redaction

        install_access_log_redaction()   # uvicorn has configured its loggers by now
        crawl_task: asyncio.Task | None = None
        collect_task: asyncio.Task | None = None
        sweep_task: asyncio.Task | None = None
        a2a_sweep_task: asyncio.Task | None = None
        openapi_task: asyncio.Task | None = None
        deposit_task: asyncio.Task | None = None
        observe_task: asyncio.Task | None = None

        def _run_crawl_blocking() -> dict:
            from aimarket_hub.crawler import Crawler
            from aimarket_hub.slash_sync import SlashRegistry
            # Own DB connection + trust scorer for this worker thread so the crawl's
            # synchronous SQLite work (per-peer trust scoring, per-tool upsert+commit)
            # never blocks the server event loop and no sqlite3 connection is shared
            # across threads. WAL lets the app's connection keep serving meanwhile.
            crawl_db = HubDatabase(config.db_path, database_url=config.database_url)
            # The slash registry is DB-backed, so it MUST also use the crawl-thread
            # connection — handing the app's registry here would make this worker thread
            # write the app's sqlite connection concurrently with request handlers. The
            # app registry is refreshed from disk after the crawl returns (see below).
            crawl_slash_registry = SlashRegistry(config.hub_url, db=crawl_db)
            crawler = Crawler(
                config=config, db=crawl_db, signer=signer,
                trust_scorer=TrustScorer(crawl_db),
                slash_registry=crawl_slash_registry,
            )

            async def _do() -> dict:
                try:
                    stats = await crawler.crawl(clear_first=False)
                finally:
                    await crawler.close()
                # A few free federated capabilities are asked whether their answer depends on the
                # input (answer_dependence.py), on this thread's own connection. Never fails the cycle.
                try:
                    from aimarket_hub import answer_dependence
                    from aimarket_hub.outbound_http import safe_post

                    probed = await answer_dependence.probe_free(
                        crawl_db, config, resolve_endpoint=peer_routing._peer_invoke_endpoint, post=safe_post,
                    )
                    if isinstance(stats, dict):
                        stats["answer_probe"] = probed
                except Exception as exc:
                    logger.warning("answer probe cycle failed: %s", exc)
                return stats

            try:
                return asyncio.run(_do())
            finally:
                with contextlib.suppress(Exception):
                    crawl_db.close()

        async def _periodic_crawl() -> None:
            # Stagger so the server is serving before the first crawl runs.
            await asyncio.sleep(max(0.0, config.crawl_initial_delay_s))
            interval = max(60, int(config.crawl_interval_s))
            while True:
                try:
                    # Offload the whole crawl (async HTTP + sync DB) to a worker
                    # thread so concurrent /invoke, /search, /.well-known never stall.
                    stats = await asyncio.to_thread(_run_crawl_blocking)
                    # The crawl persisted newly-ingested peer attestations via its own
                    # connection; refresh the app registry from disk (event-loop thread)
                    # so federated_penalty reflects them without a restart — no
                    # cross-thread write to the app connection.
                    late.slash_registry.reload()
                    logger.info("auto-crawl complete: %s", stats)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # a bad cycle must never kill the loop
                    logger.warning("auto-crawl cycle failed: %s", exc)
                # Jitter avoids a thundering herd across federated hubs.
                jitter = random.uniform(0, min(60.0, interval * 0.1))
                await asyncio.sleep(interval + jitter)

        if config.auto_crawl and config.seed_list:
            crawl_task = asyncio.create_task(_periodic_crawl())
            logger.info(
                "Auto-crawl enabled: %d seed(s), interval %ds",
                len(config.seed_list), max(60, int(config.crawl_interval_s)),
            )
        elif config.auto_crawl:
            logger.info("Auto-crawl enabled but seed list is empty — nothing to crawl.")
        # KI-11: an authorized escrow debit is captured on every paid invoke and, until
        # now, collected only when a person ran the CLI. Off unless an interval is set,
        # and bounded by the bridge's own policy and spend caps rather than by this loop.
        with contextlib.suppress(Exception):
            from aimarket_hub.escrow_bridge import collector as escrow_collector

            if escrow_collector.interval_s() > 0:
                collect_task = asyncio.create_task(escrow_collector.run_forever())
            else:
                logger.debug(
                    "escrow collection: %s", escrow_collector.blocked_reason()
                )
        # Subcontracting allowances a root call failed to settle (a crash mid-call, a
        # release that kept failing) are buyer money frozen in a hold. Sweeping only when
        # the next allowance is asked for would leave them frozen on a hub nobody asks
        # again; so the sweep also runs at start and on a timer.
        def _sweep_allowances_once() -> None:
            try:
                recovered = invoke_funding.sweep_stale_credit_holds(
                    credits_ledger=hub_credits, store=hub_mandates, limit=50,
                )
                if recovered:
                    logger.warning("credits: released %d abandoned invoke hold(s)", recovered)
                n = invoke_funding.sweep_stale_allowances(
                    credits_ledger=hub_credits, store=hub_mandates, jobs=hub_jobs, limit=50,
                )
                if n:
                    logger.warning("subcontract: settled %d stale allowance(s)", n)
                # After the allowances: a child released while its allowance still holds goes
                # back into it, so the order decides only where the money passes, not where it ends.
                orphans = invoke_funding.sweep_orphaned_child_holds(
                    credits_ledger=hub_credits, store=hub_mandates, limit=50,
                )
                if orphans:
                    logger.warning("subcontract: released %d orphaned child hold(s)", orphans)
            except Exception as exc:  # noqa: BLE001 - a bad cycle must never kill the loop
                logger.warning("subcontract: allowance sweep failed: %s", exc)

        async def _periodic_allowance_sweep(interval: float) -> None:
            while True:
                await asyncio.sleep(interval)
                _sweep_allowances_once()

        try:
            sweep_interval = float(os.getenv("AIMARKET_SUBCONTRACT_SWEEP_S", "120"))
        except ValueError:
            sweep_interval = 120.0
        if sweep_interval > 0 and hub_credits is not None and credits.enabled():
            # Once now — a restart after a crash is exactly when stranded allowances exist —
            # then on the timer.
            _sweep_allowances_once()
            sweep_task = asyncio.create_task(_periodic_allowance_sweep(max(10.0, sweep_interval)))
        # A2A tasks whose process died mid-call (a2a_tasks leases): recovered within a minute of
        # their lease lapsing, from the ledger — not left WORKING until somebody calls /a2a.
        a2a_sweep = getattr(fastapi_app.state, "a2a_sweep", None)
        if a2a_sweep is not None:
            async def _periodic_a2a_sweep() -> None:
                while True:
                    await asyncio.sleep(60.0)
                    try:
                        a2a_sweep()
                    except Exception as exc:  # noqa: BLE001 - a bad cycle must never kill the loop
                        logger.warning("a2a: periodic task sweep failed: %s", exc)

            a2a_sweep_task = asyncio.create_task(_periodic_a2a_sweep())
        # USDC landing in the top-up wallet becomes credit without anybody presenting it
        # (deposit_watch.py) — only on a wallet that receives top-ups and nothing else.
        if deposit_watch.enabled() and hub_credits is not None:
            async def _periodic_deposit_watch() -> None:
                from starlette.concurrency import run_in_threadpool

                while True:
                    # Wait first: a hub restarting in a loop must not hit the node on every start,
                    # and nothing is lost — the cursor resumes where the last scan stopped.
                    await asyncio.sleep(deposit_watch.interval_s())
                    try:
                        summary = await run_in_threadpool(late.deposit_watcher().scan_once)
                        if any(k in summary for k in ("credited", "unattributed")):
                            logger.warning("deposit watch: %s", summary)
                    except Exception as exc:  # noqa: BLE001 - a bad cycle must never kill the loop
                        logger.warning("deposit watch: scan failed, retried next cycle: %s", exc)

            deposit_task = asyncio.create_task(_periodic_deposit_watch())
        else:
            logger.info("deposit watch: %s", deposit_watch.unavailable_reason())
        # Same-origin paid routes served beside the hub (x402 sidecar) join /openapi.json,
        # where x402 indexers look for them. Fetched off the request path, on a timer.
        merge_urls = openapi_merge.merge_urls(config.hub_url)
        if merge_urls:
            async def _periodic_openapi_merge() -> None:
                while True:
                    await openapi_merge.refresh(merge_urls)
                    await asyncio.sleep(openapi_merge.REFRESH_S)

            openapi_task = asyncio.create_task(_periodic_openapi_merge())
        # x402 sellers that consented to be listed from their own discovery document
        # (observed_sellers.py, spec §2.7), re-read when due. With no consented seller a cycle
        # is one query. Small writes on the app's own connection, like the deposit watch.
        if db is not None and observed_sellers.enabled():
            async def _periodic_observe() -> None:
                await asyncio.sleep(max(0.0, float(config.crawl_initial_delay_s)) + 30.0)
                while True:
                    try:
                        summary = await observed_sellers.observe_due(db, hub_url=config.hub_url)
                        if summary.get("observed"):
                            logger.info("observed sellers: %s", summary)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - a bad cycle must never kill the loop
                        logger.warning("observed sellers: cycle failed: %s", exc)
                    await asyncio.sleep(600.0 + random.uniform(0, 60.0))

            observe_task = asyncio.create_task(_periodic_observe())
        # Pay-on-Verified: re-queue verifications left pending by a previous process
        # so a hub restart never strands an escrow hold.
        with contextlib.suppress(Exception):
            await verify_svc.reconcile()
        try:
            yield
        finally:
            for task in (crawl_task, collect_task, sweep_task, openapi_task, deposit_task,
                         a2a_sweep_task, observe_task):
                if task is None:
                    continue
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            with contextlib.suppress(Exception):
                await verify_svc.shutdown()
            with contextlib.suppress(Exception):
                plugins.shutdown_all()

    return _lifespan
