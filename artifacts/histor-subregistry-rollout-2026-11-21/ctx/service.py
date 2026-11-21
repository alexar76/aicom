"""Wiring: one place that builds every component from settings, for the app, the CLI and tests."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from awr import SigningKey

from histor.check import Checker
from histor.classifier import Classifier
from histor.config import Settings
from histor.crawler import Crawler, CrawlInProgress
from histor.db import Backend, open_backend
from histor.keys import bind_key_to_log, issuer_key, load_or_create_seed
from histor.labels import LabelIssuer
from histor.logbook import Logbook
from histor.migrations import apply_migrations
from histor.receipts import ReceiptLog
from histor.scanner import Scanner
from histor.signed_revisions import RevisionIngest
from histor.signing import ProviderSigner
from histor.store import Store
from histor.witness import Witness, load_known_logs

log = logging.getLogger("histor")


@dataclass
class Services:
    settings: Settings
    backend: Backend
    store: Store
    key: SigningKey
    issuer: LabelIssuer
    logbook: Logbook
    scanner: Scanner
    crawler: Crawler
    checker: Checker
    provider: ProviderSigner
    receipts: ReceiptLog | None = None
    revisions: RevisionIngest | None = None
    witness: Witness | None = None
    stop: threading.Event = field(default_factory=threading.Event)
    # Stripe transport for histor.watch_paid; None = the real API (tests put a fake here).
    stripe: Callable[..., tuple[int, dict]] | None = None
    last_error: str | None = None
    remote_error: str | None = None

    def close(self) -> None:
        self.stop.set()
        self.backend.close()


def build(settings: Settings, *, crawler_kwargs: dict | None = None, backend: Backend | None = None,
          serving: bool = False) -> Services:
    """Wire everything. ``serving`` is for the one long-lived process: only it may declare an
    unfinished run dead — a CLI command next to a live service must not (audit F38)."""
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backend = backend or open_backend(settings.db_path, settings.database_url)
    apply_migrations(backend)
    store = Store(backend)
    if serving:
        store.mark_interrupted_runs(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # A missing key is created only for an empty log; otherwise it is an operator's mistake to fix.
    key = issuer_key(settings.issuer_key_path, create=store.tree_size() == 0)
    bind_key_to_log(store, key, settings.head_marker_path)
    issuer = LabelIssuer(key)
    logbook = Logbook(store, key, settings.head_marker_path)
    scanner = Scanner(settings.scanner_dir, settings.node_bin)
    kwargs = dict(crawler_kwargs or {})
    if settings.classifier_enabled and "classifier" not in kwargs:
        kwargs["classifier"] = Classifier(
            model=settings.classifier_model, api_key=settings.classifier_api_key,
            base_url=settings.classifier_base_url, timeout_s=settings.classifier_timeout_s,
            max_tools=settings.classifier_max_tools,
        )
    crawler = Crawler(settings, store, issuer, logbook, scanner, **kwargs)
    checker = Checker(store, key, scanner, settings.public_base,
                      classifier_model=settings.classifier_model if settings.classifier_enabled else "",
                      classifier_enabled=settings.classifier_enabled)
    provider = ProviderSigner(settings.provider_key_path, pqc=settings.pqc)
    receipts = ReceiptLog(store, key, set(settings.receipt_issuers))
    revisions = RevisionIngest(
        store, key, settings.revision_sources,
        allow_private=settings.allow_private_targets,
        verify_signatures=True,
    )
    # histor-tlog/2: the witness has its own key (created on first use) and knows only the
    # logs the operator listed.
    witness_key = SigningKey.from_seed(load_or_create_seed(settings.witness_key_path, create=True))
    witness = Witness(store, witness_key, settings.cosigner_name,
                      load_known_logs(Path(settings.witness_logs) if settings.witness_logs else None))
    return Services(settings, backend, store, key, issuer, logbook, scanner, crawler, checker, provider,
                    receipts=receipts, revisions=revisions, witness=witness)


def crawl_in_background(services: Services, *, include_remote: bool = True) -> bool:
    """Start one crawl on a thread. False when one is already running."""
    if services.crawler.running_since is not None:
        return False

    def work() -> None:
        try:
            stats = services.crawler.run(include_remote=include_remote)
            services.last_error = None
            log.warning("crawl finished: %s", {k: stats.get(k) for k in ("attempted", "changes", "tree_size")})
        except CrawlInProgress:
            pass
        except Exception as exc:  # noqa: BLE001 - the scheduler must survive one bad crawl
            services.last_error = f"{type(exc).__name__}: {exc}"[:500]
            log.exception("crawl failed")

    threading.Thread(target=work, name="histor-crawl", daemon=True).start()
    return True


def remote_worker(services: Services, *, idle_wait: float = 30.0) -> None:
    """Drain due remote work without waiting for the daily package run or its scheduler tick."""
    while not services.stop.is_set():
        wait = idle_wait
        try:
            result = services.crawler.poll_remote()
            services.remote_error = None
            if result is not None:
                wait = 0.1  # another batch may already be due; no multi-minute queue stall
        except Exception as exc:  # noqa: BLE001 - retry infrastructure failures, without spinning
            services.remote_error = f"{type(exc).__name__}: {exc}"[:500]
            log.exception("remote polling failed")
            wait = max(idle_wait, 60)
        if services.stop.wait(wait):
            return


def scheduler(services: Services, *, first_wait: float = 15.0, tick: float = 300.0) -> None:
    """Crawl every ``crawl_interval_s``, counted from the start of the last SUCCESSFUL crawl, and never sooner than
    ``crawl_min_gap_s`` after it finished: a cycle that outlasts the interval leaves that gap for the monthly snapshot.

    A crawl that failed (registry down, crash) is retried after at most an hour instead of
    waiting a full interval — otherwise one bad night costs a day of history. One interrupted by a
    restart continues at once: the new run skips what the interrupted cycle already read. With ``HISTOR_CRAWL_ON_START=0`` a fresh instance waits one interval before its first
    automatic crawl; an operator can still trigger one by hand.
    """
    interval = services.settings.crawl_interval_s
    remote = services.settings.remote_interval_s > 0
    # The subregistry's copy (histor.subregistry) has its own rhythm and needs no crawl: an instance that
    # only serves an organisation's list runs with both crawl intervals at 0.
    mirror = services.settings.subregistry_sync_s if services.settings.subregistry else 0
    if interval <= 0 and not remote and not mirror:
        return
    retry = min(interval, 3600)
    booted = datetime.now(UTC)

    def parse(ts: str) -> datetime:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

    def due() -> bool:
        now = datetime.now(UTC)
        ok = services.store.last_successful_run()
        last = services.store.last_run(finished_only=True)
        if last and last["stats"].get("error") and (ok is None or last["id"] > ok["id"]):
            if str(last["stats"]["error"]).startswith("interrupted"):
                # A restart, not a failure: the next run continues the cycle, re-dialling nothing.
                return True
            return (now - parse(last["finished_at"])).total_seconds() >= retry
        if ok:
            # A cycle longer than the interval would start the next one at once: wait a gap after it, the moment the
            # monthly snapshot (deploy/export_dataset.sh) needs to copy a finished cycle.
            if ok.get("finished_at") and (now - parse(ok["finished_at"])).total_seconds() < services.settings.crawl_min_gap_s:
                return False
            # Counted from the start of the cycle, so a resumed run keeps the daily rhythm.
            start = ok["stats"].get("cycle_started_at") or ok["started_at"]
            return (now - parse(start)).total_seconds() >= interval
        if services.settings.crawl_on_start:
            return True
        return (now - booted).total_seconds() >= interval

    refresh = services.settings.declaration_refresh_s
    refreshed = [time.monotonic()]  # the first crawl reads the files; the hourly reads start after it
    refreshing = threading.Lock()

    def refresh_declarations() -> None:
        with refreshing:
            try:
                result = services.crawler.refresh_declarations()
                if result.get("files"):
                    log.warning("declaration files read: %s", result)
            except Exception:  # noqa: BLE001 - a publisher's file must not end the schedule
                log.exception("declaration refresh failed")
            try:
                # MCP server cards, a day apart per endpoint (histor.cards).
                result = services.crawler.refresh_cards()
                if result.get("checked"):
                    log.warning("server cards read: %s", result)
            except Exception:  # noqa: BLE001 - a site's card must not end the schedule
                log.exception("server card refresh failed")

    mirrored = [time.monotonic() - mirror]  # due at the first tick: a new instance has nothing to serve yet
    mirroring = threading.Lock()

    def sync_subregistry() -> None:
        from histor import subregistry

        with mirroring:
            try:
                result = subregistry.sync_for(services)
                if result["stored"] or result["gone"] or result["mode"] != "incremental":
                    log.warning("subregistry sync: %s", result)
            except Exception:  # noqa: BLE001 - an upstream that is down must not end the schedule
                log.exception("subregistry sync failed")

    if services.stop.wait(first_wait):
        return
    if remote:
        threading.Thread(target=remote_worker, args=(services,), name="histor-remote", daemon=True).start()
    while True:
        try:
            if interval > 0 and due():
                crawl_in_background(services, include_remote=not remote)
            if refresh and time.monotonic() - refreshed[0] >= refresh and not refreshing.locked():
                refreshed[0] = time.monotonic()
                threading.Thread(target=refresh_declarations, name="histor-declared", daemon=True).start()
            if mirror and time.monotonic() - mirrored[0] >= mirror and not mirroring.locked():
                mirrored[0] = time.monotonic()
                threading.Thread(target=sync_subregistry, name="histor-subregistry", daemon=True).start()
        except Exception:  # noqa: BLE001 - a transient DB error must not end the schedule
            log.exception("scheduler tick failed")
        if services.stop.wait(tick):
            return
