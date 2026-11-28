"""One crawl: harvest the registry, observe every endpoint, issue labels, sign a tree head.

What gets a label, and when — chosen so the log records facts, not noise:

* **observation, pattern scan, name threat** — once per *new subject*, i.e. the first time a
  target advertises a given tool set. Re-issuing identical deterministic results daily would
  only bury the changes. A new WARDEN pattern set or record set re-issues the scan labels,
  because two scan labels are comparable only under the same set (MTL/1 section 7.3) — once per
  target, tracked in ``targets.scan_sets``, so an interrupted crawl neither skips nor repeats one.
* **continuity** — every crawl (at most once per ``CONTINUITY_MIN_INTERVAL_S``) for a target
  with a prior label. ``pass`` is the heartbeat behind "unchanged since"; ``fail`` is a change.
* **an unreachable server** gets one ``inconclusive`` continuity label when it stops answering,
  not one a day — and never a ``fail``: a server we cannot read has not been shown to change.

Endpoints are observed, scanned and committed in batches of ``crawl_batch``: a full crawl takes
one to two hours, and holding every observation until the end would lose all of it to one
restart and show no progress while it ran. The tree head is signed once, at the end.

The subject descriptor omits ``server.version`` on purpose (it is OPTIONAL in section 4.2): a
registry version bump with identical tools would otherwise change the subject digest, and the
continuity label would say "definitions changed" about definitions that did not.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from histor import cards, diffing, instructions
from histor import extras as extras_mod
from histor.classifier import Classifier, ClassifierError
from histor.config import Settings
from histor.declared import DeclarationError, DeclarationFetcher
from histor.exit_reasons import NODE_RUNTIMES, classify, excerpt
from histor.extras import extras_diff, tool_extras
from histor.labels import PROFILE_REVISION, LabelIssuer
from histor.launch_profiles import package_launch_defaults
from histor.logbook import Logbook, utcnow
from histor.mcpclient import USER_AGENT, McpReader, Observation
from histor.packages import (
    SANDBOX_ERROR,
    PackageReader,
    SandboxPool,
    launch_record,
    parse_package,
    sandbox_readers,
    version_signals,
)
from histor.registry import (
    OPT_OUT,
    Target,
    curated_rank,
    curated_targets,
    harvest,
    load_opt_out,
    opted_out,
    with_curated,
)
from histor.remote_schedule import RemoteSchedule
from histor.robots import Fetcher as RobotsFetcher
from histor.robots import Policy
from histor.scanner import RuleSets, Scanner, ScannerError
from histor.store import Store, dumps, sum_counts
from histor.subject import (
    MTL_SUBJ_001,
    REGISTRY_CURATED,
    MtlError,
    Subject,
    build_subject,
    fallback_subject,
    tool_set_digest,
)
from histor.untrusted import clean_text

CONTINUITY_MIN_INTERVAL_S = 20 * 3600
log = logging.getLogger("histor.crawler")


class CrawlInProgress(RuntimeError):
    pass


@dataclass
class OtherRevision:
    """One read that opened with ``initialize``, taken beside a 2026-07-28 reading of the same server."""

    beside_toolset: str        # the tool-set digest of the reading that goes into the log
    protocol: str              # what the handshake negotiated
    toolset: str | None        # this reading's digest; None when it failed or has none
    tool_count: int | None
    status: str                # the reader's status, or "undigestible"
    read_at: str


@dataclass
class Prepared:
    target: Target
    obs: Observation
    observed_at: str
    subject: Subject | None = None
    subject_error: MtlError | None = None
    # A package observation: the registry's facts about the version and what changed since the last one.
    signals: dict[str, Any] | None = None
    # For a server read in MCP 2026-07-28: what it listed to a handshake client right after (_other_revision).
    other_revision: OtherRevision | None = None


PACKAGE_SANDBOX = "package-sandbox"


# Revisions from this one on have no handshake: the reader asks server/discover (histor.mcpclient).
FIRST_STATELESS_REVISION = "2026-07-28"


def _older_than(stamp: str, now: str, days: int) -> bool:
    """Whether *stamp* is more than *days* before *now* (both as the crawl's clock writes them)."""
    try:
        return datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.fromisoformat(stamp.replace("Z", "+00:00")) \
            > timedelta(days=days)
    except ValueError:
        return True


def _host_of(endpoint: str) -> str:
    if parse_package(endpoint):
        # Every package goes through the sandbox pool, bounded by its total slots.
        return PACKAGE_SANDBOX
    try:
        return (urlsplit(endpoint).hostname or "").lower()
    except ValueError:  # an unparseable registry URL; netguard refuses it with a status later
        return ""


def _observer_of(record: str | None) -> str:
    try:
        return str(json.loads(record).get("observer") or "") if record else ""
    except (ValueError, AttributeError):
        return ""


# An observation that recorded a tool list, digestible or not (a failed run recorded none).
SERVED_A_LIST = "status IN ('ok', 'undigestible')"


def _server_version(p: Prepared) -> str | None:
    """The version the server reported about itself (serverInfo), as stored on the observation."""
    return clean_text(p.obs.server_info.get("version") or "", 100) or None


def _registry_version(t: Target) -> str | None:
    """The version the registry listed for the entry when this run was planned (none for curated ones)."""
    return clean_text(t.version or "", 100) or None


def _artifact(t: Target) -> dict[str, str]:
    """The subject descriptor's artifact members: what HISTOR connected to."""
    if parse_package(t.endpoint):
        return {"transport": "stdio", "package": t.endpoint}
    return {"transport": "streamable-http", "endpoint": t.endpoint}


def _interleave_by_host(targets: list[Target]) -> list[Target]:
    """Round-robin across hosts, so one host with 300 endpoints is not hit 12 at a time."""
    queues: dict[str, deque[Target]] = defaultdict(deque)
    for t in targets:
        queues[_host_of(t.endpoint)].append(t)
    out: list[Target] = []
    while queues:
        for host in list(queues):
            out.append(queues[host].popleft())
            if not queues[host]:
                del queues[host]
    return out


# A run that ended this way ends the same way next time unless something about it changes: a new
# version, a new observer, or configuration the package asked for that it was not given yet.
SETTLED = frozenset({"exited", "no-entry-point", "no-wheel", "not-found", "protocol"})
# Failures a newer observer may start where an older one could not (observer 4: the Python a
# package requires, ``python -m``, the mcp-named command, a passwd entry, a writable package):
# run again ahead of the never-observed queue, with at least half of what is left of a crawl.
RENEWABLE = frozenset({"exited", "no-entry-point", "install-failed", "timeout", "protocol"})
# Sandbox observer 5 before build bf8fe5b8 (on every sandbox host from 2026-11-16T04:37Z) failed some servers that
# observer 4 had read: an id echoed as a string, a late answer to a settled request, a version list of legacy revisions
# only ("protocol"), and Rust servers that exit on the discovery probe ("exited", naming server/discover). The observer
# number did not change, so SETTLED kept those failures until a new package version. Each is run once more.
OBSERVER5_FIXED_AT = "2026-11-16T04:37:00Z"
PROBE_EXIT = re.compile(r"server/discover|ExpectedInitialize", re.I)


def _early_observer5_failure(state: dict[str, Any], observer: str) -> bool:
    attempt = str(state.get("last_attempt") or "")
    if observer != "5" or not attempt or attempt >= OBSERVER5_FIXED_AT:
        return False
    status = state.get("last_status")
    return status == "protocol" or (status == "exited" and bool(PROBE_EXIT.search(state.get("last_detail") or "")))
# The sandbox's trace reader (behaviour.observer). gvisor-trace/2 listed the byte asyncio writes
# to its own socketpair as a send it could not place, which read as "reached out at startup" for
# nearly every Python server; a package it left with such sends is traced again, once.
TRACE_OBSERVER = "gvisor-trace/9"
UNPLACED_SEND = ("sendto(", "sendmsg(", "sendmmsg(")
# Evidence that cannot be this run's: another run's canary recipient, or a name only MOMUS's
# red-team fixtures use. gvisor-trace/3 and older matched trap records by address from before
# the container started, and once took in the previous holder's requests.
FOREIGN_CANARY = re.compile(r"^canary-[0-9a-f]{12}@histor-trap\.invalid$")


def _unplaced_sends(behaviour: Any) -> bool:
    """An older reader's trace that holds what gvisor-trace/3 reads differently: a send it could
    not place (asyncio's self-pipe), or a write it could not resolve — a relative path it
    counted as outside the sandbox, which WARDEN shows as persistence (node-gyp's
    buildcheck.gypi, a package's own cache)."""
    if not isinstance(behaviour, dict) or behaviour.get("observer") == TRACE_OBSERVER:
        return False
    if behaviour.get("observer") == "gvisor-trace/8":
        # 9 adds what 8 did not record at all (renames, links, creat; .pth and post-install code
        # writes as persistence): nothing in an 8 trace says which runs missed it. Its ok, complete
        # pages are traced once more by the planner (_missed_renames_and_links), behind the wrong
        # records here. Taking 9 for an older reader instead re-traced every 9 run with a relative
        # write on every crawl.
        return False
    phases = [behaviour[p] for p in ("installScripts", "startup", "calls") if isinstance(behaviour.get(p), dict)]
    foreign = any(isinstance(e, str) and FOREIGN_CANARY.match(e) for ph in phases for e in ph.get("unexpectedRecipients") or [])
    if behaviour.get("observer") == "gvisor-trace/7":
        # 8 reads only one thing differently: a trap record carrying another run's tag (a connection the
        # address's previous holder queued). A 7 trace is traced again only when it shows one.
        return foreign
    return (foreign or any(isinstance(e, str) and e.startswith(UNPLACED_SEND) for ph in phases for e in ph.get("network") or [])
            or any(isinstance(e, str) and not e.startswith("/") for ph in phases for e in ph.get("writes") or [])
            # gvisor-trace/4 read the container's start after removing it, so every run said so.
            or any("start-time-unknown" in (ph.get("incompleteReasons") or []) for ph in phases)
            or any(isinstance(e, str) and "momus-trap.invalid" in e for ph in phases
                   for e in [*(ph.get("lookups") or []), *(str(r.get("destination")) for r in ph.get("requests") or [] if isinstance(r, dict))]))
# The first trace reader that records renames, links and creat, and reports .pth files and code
# written into the installed package after install as persistence (Vulnetix GCVE-110-PYPI-2026-022091).
RENAMES_AND_LINKS_FROM = 9


def _missed_renames_and_links(behaviour: Any) -> bool:
    """A trace by a reader before gvisor-trace/9. Such a reader did not record renames, links or
    creat at all, so an ok, complete page it made can lack persistence done that way, and nothing
    in the trace says which pages do. Each such page is traced once more (owner, 2026-10-26); the
    new trace is by the current reader, so it is never picked again."""
    if not isinstance(behaviour, dict):
        return False
    prefix, _, number = str(behaviour.get("observer") or "").rpartition("/")
    return prefix == "gvisor-trace" and number.isdigit() and int(number) < RENAMES_AND_LINKS_FROM


# A PyPI server written for MCP SDK 1.x crashes on import once pip resolves mcp 2.x. Its status
# stays what a fresh install gets; a second run with this pin shows what it was before 2.0, kept
# beside the record (``legacy``) and never in the label chain.
LEGACY_PINS = {"sdk-incompatible": ["mcp<2"]}


def _config_for(t: Target, record: dict[str, Any]) -> dict[str, Any]:
    """Reviewed defaults, registry declarations, and configuration named by an earlier run.

    Explicit arguments take precedence over a profile; only placeholder variable names are merged.
    """
    defaults = package_launch_defaults(t.endpoint)
    declared = t.needs or {}
    asked = record.get("exit") if isinstance(record.get("exit"), dict) else {}
    # What the last run was given goes on: a new version of a package that started with a
    # placeholder key needs it too, and a name asked for later adds to the ones already given.
    given = record.get("supplied") if isinstance(record.get("supplied"), dict) else {}
    env = sorted({str(n) for n in [*(defaults.get("env") or []), *(declared.get("env") or []),
                                 *(asked.get("env") or []), *(given.get("env") or [])]})[:8]
    args = list(declared.get("args") or asked.get("args") or given.get("args") or defaults.get("args") or [])[:6]
    plan: dict[str, Any] = {k: v for k, v in (("env", env), ("args", args)) if v}
    if given.get("runtime") in NODE_RUNTIMES.values() and t.endpoint.startswith("npm:"):
        plan["runtime"] = given["runtime"]
    # "Node 24+ required": the current LTS image, the one such a package's users run it on.
    major = asked.get("node") if asked.get("kind") == "needs-newer-node" else None
    if isinstance(major, int) and t.endpoint.startswith("npm:"):
        runtime = next((name for m, name in sorted(NODE_RUNTIMES.items()) if m >= major), None)
        if runtime:
            plan["runtime"] = runtime
    return plan


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


@dataclass
class _Tally:
    """A crawl's counts, shared by the endpoint batches and the package lane."""

    classify_budget: int
    statuses: Counter[str] = field(default_factory=Counter)
    issued: Counter[str] = field(default_factory=Counter)
    internal: Counter[str] = field(default_factory=Counter)
    legacy_statuses: Counter[str] = field(default_factory=Counter)
    changes: int = 0
    classified: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    classify_lock: threading.Lock = field(default_factory=threading.Lock)


class Crawler:
    def __init__(self, settings: Settings, store: Store, issuer: LabelIssuer, logbook: Logbook,
                 scanner: Scanner, *, reader: McpReader | None = None,
                 harvest_fn: Callable[[str], list[Target]] | None = None,
                 classifier: Classifier | None = None,
                 packages: PackageReader | SandboxPool | None = None,
                 declarations: DeclarationFetcher | None = None,
                 clock: Callable[[], str] = utcnow) -> None:
        self.settings = settings
        self.store = store
        self.issuer = issuer
        self.logbook = logbook
        self.scanner = scanner
        self.classifier = classifier
        if reader is None:
            # RFC 9309: a path the site's robots.txt does not allow HISTOR is not read (histor.robots).
            robots = Policy(fetch=RobotsFetcher(user_agent=USER_AGENT, timeout=min(settings.crawl_timeout_s, 10.0),
                                                allow_private=settings.allow_private_targets), clock=clock)
            reader = McpReader(timeout=settings.crawl_timeout_s, allow_private=settings.allow_private_targets,
                               robots=robots)
        self.reader = reader
        self.robots: Policy | None = getattr(reader, "robots", None)
        if packages is None and settings.sandbox_enabled:
            readers = sandbox_readers(settings)
            packages = SandboxPool(readers, max_slots=settings.sandbox_max_slots) if len(readers) > 1 else readers[0][0]
        self.packages = packages
        self.declarations = declarations or DeclarationFetcher(allow_private=settings.allow_private_targets)
        # MCP server cards (histor.cards), read only where robots.txt allows; tests swap in their own reader.
        self.cards = cards.CardReader(robots=self.robots, allow_private=settings.allow_private_targets)
        # The crawl's sync and the hourly refresh both write the declared sets: one at a time.
        self._declarations_lock = threading.Lock()
        self._due_versions: dict[str, str] = {}
        self._due_config: dict[str, dict[str, list[str]]] = {}
        self._due_legacy: set[str] = set()
        self._seen_versions: dict[str, str] = {}
        # The other-revision reading: which targets have one (loaded on the crawl's own thread before
        # the workers start), and how many were taken today.
        self._revision_index: dict[str, tuple[str, str]] | None = None
        self._revision_day, self._revision_done = "", 0
        self._revision_lock = threading.Lock()
        self.harvest_fn = harvest_fn or self._harvest_with_curated
        self.clock = clock
        self._lock = threading.Lock()
        # Hold through observe, scan and commit: overlapping reads of one endpoint must not
        # commit in reverse order. Packages have their own lane and never take this lock.
        self._remote_lock = threading.Lock()
        self.remote_schedule = RemoteSchedule(store, settings)
        self.remote_running_since: str | None = None
        self.running_since: str | None = None
        self.progress: dict[str, Any] | None = None
        # What the cycle had done before this run (targets, packages), so progress counts the cycle.
        self._cycle_before = (0, 0)
        self._endpoints_done = self._lane_done = 0
        self._checkpoint_lock = threading.Lock()
        self._checkpoint_at = 0.0
        self._run_stats: dict[str, Any] | None = None   # the running crawl's stats; None outside run()

    def _harvest_with_curated(self, url: str) -> list[Target]:
        opt_out = load_opt_out(self.settings.opt_out, self.settings.opt_out_path)
        listed = harvest(url, allow_cleartext=self.settings.allow_private_targets, opt_out=opt_out,
                         observe_packages=self.packages is not None)
        return with_curated(listed, curated_targets(opt_out=opt_out, observe_packages=self.packages is not None))

    # -- orchestration ----------------------------------------------------------------

    def run(self, *, include_remote: bool = True) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise CrawlInProgress("a crawl is already running")
        try:
            self.running_since = self.clock()
            self.progress = None
            return self._run(include_remote=include_remote)
        finally:
            self.running_since = None
            self.progress = None
            self._run_stats = None
            # The registry ETags this crawl learned, so the next one (or the next process) asks
            # with If-None-Match instead of downloading every unchanged package again.
            save = getattr(self.packages, "save_versions", None)
            if save is not None:
                save()
            self._lock.release()

    def _run(self, *, include_remote: bool = True) -> dict[str, Any]:
        started = self.clock()
        with self.store.db.transaction() as tx:
            run_id = int(tx.one("INSERT INTO runs(started_at) VALUES(?) RETURNING id", (started,))["id"])
        stats: dict[str, Any] = {"started_at": started}
        # A restart used to cost the whole cycle: the next run dialled every server again, the
        # same day. Continue the interrupted cycle instead, and say so in the run's stats at once,
        # so a run interrupted in turn still names the cycle it belongs to. Only a process that was
        # down for a whole interval (a day with the scheduler off) starts afresh (Store.resume_point).
        resume = self.store.resume_point(run_id, started, self.settings.crawl_interval_s or 86400)
        cycle = resume["cycle_started_at"] if resume else started
        stats["cycle_started_at"] = cycle
        if resume:
            stats["resumed_from"] = resume["run_id"]
        self.store.set_run_stats(run_id, stats)
        self._cycle_before = (0, 0)
        self._endpoints_done = self._lane_done = 0
        self._checkpoint_at = time.monotonic()
        self._run_stats = stats
        tally: _Tally | None = None
        try:
            targets = self.harvest_fn(self.settings.registry_url)
            official = [t for t in targets if t.registry != REGISTRY_CURATED]
            curated = [t for t in targets if t.registry == REGISTRY_CURATED]
            is_package = lambda t: bool(parse_package(t.endpoint)) or t.transport == "stdio"  # noqa: E731
            stats["registry_servers"] = len({t.name for t in official})
            stats["registry_endpoints"] = sum(1 for t in official if not is_package(t))
            stats["registry_packages"] = sum(1 for t in official if is_package(t))
            stats["curated_endpoints"] = sum(1 for t in curated if not is_package(t))
            stats["curated_packages"] = sum(1 for t in curated if is_package(t))
            stats["not_attempted"] = dict(Counter(t.skip_reason for t in targets if t.skip_reason))
            pointing: dict[str, dict[str, Any] | None] = {}
            for t in targets:
                if t.declared_url and t.registry != REGISTRY_CURATED:
                    pointing.setdefault(t.declared_url, t.declared_pointer)
            files = self._read_declaration_files(pointing)
            declared = self._sync_targets(targets, started, files)
            if declared["servers"] or declared["withdrawn"] or declared.get("ignored"):
                stats["declared_tool_sets"] = declared

            rulesets = self.scanner.rulesets()
            sets = self._register_rulesets(rulesets)

            dialable = [t for t in targets if not t.skip_reason]
            if self.settings.crawl_limit:
                dialable = dialable[: self.settings.crawl_limit]
            if not include_remote:
                stats["remote_schedule"] = "independent"
                dialable = [t for t in dialable if parse_package(t.endpoint)]
            done: set[str] = set()
            if resume:
                done = self.store.attempted_since(cycle)
                before = len(dialable)
                dialable = [t for t in dialable if t.id not in done]
                stats["skipped_already_attempted"] = before - len(dialable)
            packages_before = sum(1 for t in targets if t.id in done and parse_package(t.endpoint))
            self._cycle_before = (stats.get("skipped_already_attempted", 0), packages_before)
            packages = [t for t in dialable if parse_package(t.endpoint)]
            if packages:
                due = self._cycle_packages(packages, stats, cycle, resumed=resume is not None, before=packages_before)
                dialable = [t for t in dialable if not parse_package(t.endpoint)] + due
            # Packages run in their own lane, started now: the sandboxes work from the first minute
            # instead of after a round over 15 000 endpoint hosts, and each result is committed as
            # soon as it is in, not when the slowest member of a 400-target batch is.
            lane_targets = [t for t in dialable if parse_package(t.endpoint)]
            endpoints = [t for t in dialable if not parse_package(t.endpoint)]
            # Interleave once over the whole list, so every batch carries its share of each host
            # instead of one batch spending an hour on a single host's 2 000 endpoints.
            endpoints = _interleave_by_host(endpoints)
            stats["attempted"] = len(endpoints) + len(lane_targets)
            # The classifier's budget is the cycle's: a restart must not buy a second day of model calls.
            budget = self.settings.classifier_max_per_crawl if self.classifier else 0
            tally = _Tally(max(0, budget - (resume["classified"] if resume else 0)))
            step = self.settings.crawl_batch
            take_counts = getattr(self.packages, "take_counts", None)
            if take_counts:
                take_counts()  # count this crawl only
            self._lane_done = 0
            self._endpoints_done = 0
            total = len(endpoints) + len(lane_targets)
            lane_error: list[BaseException] = []
            lane = None
            if lane_targets:
                def run_lane() -> None:
                    try:
                        self._package_lane(lane_targets, run_id, rulesets, sets, tally, total)
                    except BaseException as exc:  # noqa: BLE001 - surfaced by the crawl below
                        lane_error.append(exc)
                lane = threading.Thread(target=run_lane, name="histor-package-lane", daemon=True)
                lane.start()
            for start in range(0, len(endpoints), step):
                with self._remote_lock:
                    processed = self._remote_batch(endpoints[start : start + step], run_id, rulesets, sets, tally)
                with tally.lock:
                    self._endpoints_done = start + processed
                    self._set_progress(total, len(lane_targets))
                self._checkpoint(run_id, tally)
            if lane is not None:
                lane.join()
            if lane_error:
                raise lane_error[0]
            with tally.lock:
                self._set_progress(total, len(lane_targets))
            stats.update(self._tally_stats(tally))
            if take_counts:
                stats["sandbox_hosts"] = take_counts()
            if self.classifier:
                stats["classifier_model"] = self.classifier.model
            if resume:
                # What the whole cycle did, not only this run's tail: read back from what was committed.
                stats["cycle"] = {**self.store.cycle_totals(cycle), "runs": len(resume["runs"]) + 1,
                                  "labels_issued": sum_counts([resume["labels_issued"], stats["labels_issued"]])}
            sth = self.logbook.publish_sth()
            cutoff = (datetime.now(UTC) - timedelta(days=90)).strftime("%Y-%m-%d")
            stats["client_reports_pruned"] = self.store.prune_client_reports(cutoff)
            stats["tree_size"] = sth["treeSize"] if sth else 0
        except Exception as exc:
            stats["error"] = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            if tally is not None and "statuses" not in stats:
                # What it did before it failed or was stopped, as a checkpoint would have saved it.
                stats.update(self._tally_stats(tally), done=self._endpoints_done + self._lane_done,
                             progress_at=self.clock())
            stats["finished_at"] = self.clock()
            with self.store.db.transaction() as tx:
                tx.execute("UPDATE runs SET finished_at=?, stats=? WHERE id=?", (stats["finished_at"], dumps(stats), run_id))
            self.store.db.maintenance()
        return stats

    def _remote_batch(self, targets: list[Target], run_id: int, rulesets: RuleSets, sets: str,
                      tally: _Tally) -> int:
        processed = 0
        if self.robots is not None and not self.robots.loaded:
            self.robots.load(self.store.robots_rows())
        try:
            for prepared in self._observe(targets):
                scans, scan_failed = self._scan(prepared, sets)
                with tally.classify_lock:
                    classifications, tally.classify_budget = self._classify(prepared, tally.classify_budget)
                for item in prepared:
                    # A package failure in the parallel lane must not back off this remote.
                    status = self._settle(item, run_id, rulesets, scans, scan_failed, sets, classifications, tally)
                    self.remote_schedule.record(item.target.id, item.observed_at, status)
                processed += len(prepared)
        finally:
            if self.robots is not None:
                self.store.save_robots(self.robots.take_dirty())
        return processed

    def poll_remote(self) -> dict[str, Any] | None:
        """One short batch from the persistent queue, without registry or sandbox work."""
        if not self._remote_lock.acquire(blocking=False):
            return None
        run_id = None
        stats: dict[str, Any] = {"started_at": self.clock()}
        tally = _Tally(self.settings.classifier_max_per_crawl if self.classifier else 0)
        try:
            targets = self.remote_schedule.due(self.clock(), min(self.settings.crawl_batch, self.settings.crawl_workers * 2))
            opt_out = load_opt_out(self.settings.opt_out, self.settings.opt_out_path)
            excluded = [t for t in targets if opted_out(t.endpoint, opt_out)]
            if excluded:
                # Apply a new opt-out immediately and drain past it, rather than letting these
                # oldest entries hold the entire queue until the next registry harvest.
                with self.store.db.transaction() as tx:
                    for target in excluded:
                        tx.execute("UPDATE targets SET skip_reason=? WHERE id=?", (OPT_OUT, target.id))
                targets = [t for t in targets if t not in excluded]
            if not targets:
                return {"attempted": 0} if excluded else None
            self.remote_running_since = self.clock()
            with self.store.db.transaction() as tx:
                run_id = int(tx.one("INSERT INTO runs(started_at, kind) VALUES(?, 'remote') RETURNING id",
                                    (self.remote_running_since,))["id"])
            rulesets = self.scanner.rulesets()
            sets = self._register_rulesets(rulesets)
            self._remote_batch(targets, run_id, rulesets, sets, tally)
            stats.update(self._tally_stats(tally), attempted=len(targets))
            sth = self.logbook.publish_sth()
            stats["tree_size"] = sth["treeSize"] if sth else 0
            return stats
        except Exception as exc:
            stats["error"] = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            if run_id is not None:
                stats.update(self._tally_stats(tally), attempted=sum(tally.statuses.values()))
                stats["finished_at"] = self.clock()
                with self.store.db.transaction() as tx:
                    tx.execute("UPDATE runs SET finished_at=?, stats=? WHERE id=?",
                               (stats["finished_at"], dumps(stats), run_id))
            self.remote_running_since = None
            self._remote_lock.release()

    def _read_declaration_files(self, urls: dict[str, dict[str, Any] | None]) -> dict[str, tuple[Any, ...]]:
        """url → (sets, None) or (None, why it could not be read). *urls* maps each file to None, or, for
        a signed statement, to what its listing says (histor.signed_declaration); such an entry carries a
        third member, the detail of the check. Read before any transaction opens: a slow publisher site
        must never hold the database."""
        def one(url: str) -> tuple[str, tuple[Any, ...]]:
            listing = urls[url]
            try:
                if listing:
                    sets, _notes, detail = self.declarations.fetch_signed(listing)
                    return url, (sets, None, detail)
                sets, _ignored = self.declarations.fetch(url)
                return url, (sets, None)
            except DeclarationError as exc:
                if listing:
                    return url, (None, str(exc)[:300], getattr(exc, "detail", None))
                return url, (None, str(exc)[:300])
            except Exception as exc:  # noqa: BLE001 - one publisher's file must not stop a crawl
                return url, (None, f"internal: {type(exc).__name__}")
        if not urls:
            return {}
        with ThreadPoolExecutor(max_workers=min(8, len(urls)), thread_name_prefix="histor-declared") as pool:
            return dict(pool.map(one, sorted(urls)))

    def refresh_cards(self, limit: int = 3000) -> dict[str, Any]:
        """Read the server cards that are due (histor.cards) and record what they declare. Cards are read
        before any transaction opens, at most two at a time per host, each path only if robots.txt allows it."""
        now = self.clock()
        due, every = self.store.cards_due(now, limit)
        if not due:
            return {"checked": 0}
        if self.robots is not None and not self.robots.loaded:
            self.robots.load(self.store.robots_rows())
        per_host: Counter[str] = Counter(urlsplit(e).hostname or "" for e in every)
        locks: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(self.settings.crawl_per_host))
        guard = threading.Lock()

        def one(url: str) -> tuple[str, cards.Read]:
            with guard:
                sem = locks[urlsplit(url).hostname or ""]
            with sem:
                try:
                    return url, self.cards.read(url)
                except Exception as exc:  # noqa: BLE001 - one site's card must not stop the pass
                    return url, cards.Read("error", detail=f"internal: {type(exc).__name__}")

        def catalogue(url: str) -> tuple[str, cards.Listed]:
            try:
                return url, cards.walk_catalog(url, lambda u: one(u)[1])
            except Exception as exc:  # noqa: BLE001 - one site's catalogue must not stop the pass
                return url, cards.Listed("error", detail=f"internal: {type(exc).__name__}")

        # Each host's AI Catalog first: it says where that host's Server Cards are (SEP-2127 discovery).
        catalogues = sorted({cards.catalog_url(t["endpoint"]) for t in due})
        try:
            with ThreadPoolExecutor(max_workers=min(16, len(catalogues)), thread_name_prefix="histor-catalogs") as pool:
                listed = dict(pool.map(catalogue, catalogues))
            urls = sorted({u for t in due for u in cards.candidates(t["endpoint"])}
                          | {u for found in listed.values() for u in found.urls})
            with ThreadPoolExecutor(max_workers=min(16, len(urls)), thread_name_prefix="histor-cards") as pool:
                reads = dict(pool.map(one, urls))
        finally:
            if self.robots is not None:
                self.store.save_robots(self.robots.take_dirty())
        for found in listed.values():
            reads.update({key: cards.Read("ok", doc=doc) for key, doc in found.inline})
        results = []
        for t in due:
            found = listed[cards.catalog_url(t["endpoint"])]
            verdict = cards.judge(t["endpoint"], reads, per_host[urlsplit(t["endpoint"]).hostname or ""], found.cards)
            if (verdict.status == cards.ABSENT and found.status == "error" and t.get("card_url")
                    and t.get("card_status") not in (None, cards.ABSENT, cards.ROBOTS)
                    and t["card_url"] not in cards.candidates(t["endpoint"])):
                # The card recorded for this endpoint came from its host's AI Catalog, and the catalogue
                # could not be read this time: that is a failed read, which withdraws nothing.
                verdict = cards.Verdict(cards.ERROR, detail=f"the AI Catalog that listed the card: {found.detail}"[:300])
            digest = entries = None
            if verdict.status == cards.DECLARED:
                try:
                    digest, entries = tool_set_digest(verdict.tools)
                except Exception as exc:  # noqa: BLE001 - MTL refuses it: say so, declare nothing
                    verdict = cards.Verdict(cards.UNDIGESTIBLE, verdict.url, detail=f"{type(exc).__name__}: {exc}"[:300])
            results.append((t, verdict, digest, entries))
        counts = self.store.apply_cards(results, now)
        return {"checked": len(due), "urls": len(urls), **counts,
                "statuses": dict(Counter(v.status for _, v, _, _ in results)),
                "catalogs": dict(Counter(found.status for found in listed.values())),
                "catalog_cards": sum(len(found.cards) for found in listed.values())}

    def refresh_declarations(self) -> dict[str, Any]:
        """Read every declaration file again, between crawls: a publisher who ships a runner adds its
        set to the file, and HISTOR should know within the hour, not the next day."""
        rows = self.store.declaration_files()
        pointing: dict[str, dict[str, Any] | None] = {}
        for r in rows:
            pointing.setdefault(r["url"], json.loads(r["pointer"]) if r.get("pointer") else None)
        files = self._read_declaration_files(pointing)
        with self._declarations_lock:
            return self.store.refresh_declarations(rows, files, self.clock())

    def _sync_targets(self, targets: list[Target], now: str,
                      files: dict[str, tuple[list[dict[str, Any]] | None, str | None]] | None = None) -> dict[str, Any]:
        with self._declarations_lock, self.store.db.transaction() as tx:
            for t in targets:
                tx.execute(
                    "INSERT INTO targets(id, name, endpoint, transport, registry, title, description, version, "
                    "repository, website, first_listed, last_listed, delisted, skip_reason) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?) "
                    "ON CONFLICT(id) DO UPDATE SET transport=excluded.transport, title=excluded.title, "
                    "description=excluded.description, version=excluded.version, repository=excluded.repository, "
                    "website=excluded.website, last_listed=excluded.last_listed, delisted=0, "
                    "skip_reason=excluded.skip_reason",
                    (t.id, t.name, t.endpoint, t.transport, t.registry, t.title, t.description, t.version,
                     t.repository, t.website, now, now, t.skip_reason),
                )
                self.remote_schedule.add(tx, t, now)
            # Only after a successful harvest: a registry outage must not delist everything.
            tx.execute("UPDATE targets SET delisted=1 WHERE last_listed < ?", (now,))
            # Curated targets have no registry entry, so nothing of theirs is declared.
            return Store.sync_declarations(tx, [t for t in targets if t.registry != REGISTRY_CURATED], now, files)

    def reobserve(self, keys: list[str]) -> list[dict[str, Any]]:
        """Observe the named targets again now (``histor reobserve``), by endpoint or target id,
        through the path a crawl takes: the sandbox (or the MCP client), WARDEN, the commit, the
        label chain and a security event. Nothing is edited by hand, and the old observation
        stays in the history beneath the new one.

        It belongs to the crawl in progress, or else to the last one: a run row of its own would
        become the public "last run" with one target in it. A package is given what its record
        says it asked for (placeholders, start argument, runtime); its registry entry is not
        re-read. Written after a red-team request was credited to a real package on 2026-10-13
        and the only fix to hand was waiting for a crawl to reach it."""
        rows: list[dict[str, Any]] = []
        for key in keys:
            found = self.store.targets_by(endpoint=key) or [r for r in [self.store.target(key)] if r]
            if not found:
                raise KeyError(f"no target with endpoint or id {key!r}")
            rows.extend(r for r in found if r["id"] not in {x["id"] for x in rows})
        run = self.store.last_run(finished_only=False)
        if run is None:
            raise RuntimeError("no crawl has run yet: there is no run to attach an observation to")
        targets = [Target(id=r["id"], name=r["name"], endpoint=r["endpoint"], transport=r["transport"],
                          registry=r["registry"], title=r.get("title"), description=r.get("description"),
                          version=r.get("version"), repository=r.get("repository"), website=r.get("website"),
                          skip_reason=None) for r in rows]
        before = {r["id"]: (r.get("last_status"), r.get("last_attempt")) for r in rows}
        rulesets = self.scanner.rulesets()
        sets = self._register_rulesets(rulesets)
        tally = _Tally(0)
        self._endpoints_done = self._lane_done = 0
        packages = [t for t in targets if parse_package(t.endpoint)]
        endpoints = [t for t in targets if not parse_package(t.endpoint)]
        if packages:
            if self.packages is None:
                raise RuntimeError("no package sandbox is configured")
            states = self.store.package_states()
            self._due_versions, self._due_config, self._due_legacy, self._seen_versions = {}, {}, set(), {}
            for t in packages:
                registry, name = parse_package(t.endpoint) or ("", "")
                self._due_versions[t.id] = self.packages.latest_version(registry, name)
                state = states.get(t.id) or {}
                signals = state.get("package_signals") or {}
                if isinstance(signals, str):
                    try:
                        signals = json.loads(signals)
                    except ValueError:
                        signals = {}
                plan = _config_for(t, signals if isinstance(signals, dict) else {})
                if plan:
                    self._due_config[t.id] = plan
                if state.get("package_version"):
                    self._seen_versions[t.id] = state["package_version"]
            self._package_lane(packages, int(run["id"]), rulesets, sets, tally, len(packages))
        if endpoints:
            with self._remote_lock:
                self._remote_batch(endpoints, int(run["id"]), rulesets, sets, tally)
        out = []
        for t in targets:
            after = self.store.target(t.id) or {}
            signals = after.get("package_signals")
            try:
                behaviour = (json.loads(signals) if isinstance(signals, str) else signals or {}).get("behaviour") or {}
            except ValueError:
                behaviour = {}
            out.append({"endpoint": t.endpoint, "id": t.id, "run": int(run["id"]),
                        "before": {"status": before[t.id][0], "at": before[t.id][1]},
                        "after": {"status": after.get("last_status"), "at": after.get("last_attempt"),
                                  "tracer": behaviour.get("observer")}})
        return out

    def _register_rulesets(self, rulesets: RuleSets) -> str:
        """Publish both sets by digest; return the pair every target's scan labels are compared with."""
        with self.store.db.transaction() as tx:
            Store.put_blob(tx, rulesets.pattern_set_digest, "pattern-set", rulesets.pattern_set)
            Store.put_blob(tx, rulesets.record_set_digest, "record-set", rulesets.record_set)
            Store.set_meta(tx, "pattern_set", rulesets.pattern_set_digest)
            Store.set_meta(tx, "record_set", rulesets.record_set_digest)
            Store.set_meta(tx, "warden_package", rulesets.warden_package)
        return f"{rulesets.pattern_set_digest}|{rulesets.record_set_digest}"

    def _cycle_packages(self, packages: list[Target], stats: dict[str, Any], cycle: str, *, resumed: bool,
                        before: int) -> list[Target]:
        """The packages this run takes. A cycle plans its packages once and keeps the plan; a run that
        continues the cycle takes what is left of it. Planning asks npm and PyPI for every known
        package's version (59 minutes for 42,490 on 2026-10-19) and spends a whole budget: done again
        after every restart, it cost an hour each time and let a cycle with restarts run far more
        packages than the budget. A continued cycle with no plan (one started by older code) is
        planned now, with the budget its runs have not used."""
        plan = self.store.crawl_plan(cycle) if resumed else None
        if plan is not None:
            by_id = {t.id: t for t in packages}
            due = [by_id[i] for i in plan.get("due") or [] if i in by_id]
            ids = {t.id for t in due}
            self._due_versions = {i: v for i, v in (plan.get("versions") or {}).items() if i in ids}
            self._due_config = {i: c for i, c in (plan.get("config") or {}).items() if i in ids}
            self._due_legacy = {i for i in plan.get("legacy") or [] if i in ids}
            self._seen_versions = {i: v for i, v in (plan.get("seen") or {}).items() if i in ids}
            stats["packages"] = {**(plan.get("stats") or {}), "fromPlan": True, "doneBefore": before, "left": len(due)}
            return due
        cap = max(0, self.settings.sandbox_max_per_crawl - before) if resumed else None
        due = self._packages_due(packages, stats, cap=cap)
        if resumed:
            stats["packages"]["doneBefore"] = before
        self.store.save_crawl_plan(cycle, {
            "due": [t.id for t in due], "versions": self._due_versions, "config": self._due_config,
            "legacy": sorted(self._due_legacy), "seen": self._seen_versions, "stats": stats["packages"],
        }, self.clock())
        return due

    def _set_progress(self, total: int, packages: int) -> None:
        """Progress over the cycle, so a restart does not send it back to zero (caller holds the tally lock)."""
        before, packages_before = self._cycle_before
        here = self._endpoints_done + self._lane_done
        progress: dict[str, Any] = {"done": before + here, "of": before + total}
        if packages:
            progress["packages"] = {"done": packages_before + self._lane_done, "of": packages_before + packages}
        if before:
            progress["thisRun"] = {"done": here, "of": total}
        self.progress = progress

    def _tally_stats(self, tally: _Tally) -> dict[str, Any]:
        out: dict[str, Any] = {"statuses": dict(tally.statuses), "labels_issued": dict(tally.issued),
                               "changes": tally.changes}
        if self.classifier:
            out["classified"] = tally.classified
        if tally.internal:
            out["internal_errors"] = dict(tally.internal)
        if tally.legacy_statuses:
            out["legacy_statuses"] = dict(tally.legacy_statuses)
        return out

    CHECKPOINT_S = 30.0

    def _checkpoint(self, run_id: int, tally: _Tally) -> None:
        """Save the run's counts so far, at most every CHECKPOINT_S. An interrupted run used to keep
        nothing (its counts lived in memory until the end), so the desk showed an empty last run and
        the cycle's numbers were lost with every restart. ``progress_at`` tells the next run's resume
        rule that this cycle was still moving. Only a crawl's own run is saved: ``reobserve`` uses the
        package lane too, attached to a run that may have finished long ago."""
        stats = self._run_stats
        if stats is None or not self._checkpoint_lock.acquire(blocking=False):
            return
        try:
            now = time.monotonic()
            if now - self._checkpoint_at < self.CHECKPOINT_S:
                return
            self._checkpoint_at = now
            with tally.lock:
                counts = {**self._tally_stats(tally), "done": self._endpoints_done + self._lane_done}
            self.store.set_run_stats(run_id, {**stats, **counts, "progress_at": self.clock()})
        finally:
            self._checkpoint_lock.release()

    def _packages_due(self, targets: list[Target], stats: dict[str, Any], cap: int | None = None) -> list[Target]:
        """The packages to run in the sandbox this crawl: a version not observed yet.

        A published npm or PyPI version cannot change, so an observed version is not run again
        (unless its run timed out). New versions of packages HISTOR already knows go first — that
        is where a changed tool description reaches everyone running the package unpinned — then
        packages never observed, up to ``sandbox_max_per_crawl``; the rest wait for the next crawl.
        """
        assert self.packages is not None
        reader = self.packages
        cap = self.settings.sandbox_max_per_crawl if cap is None else cap
        unknown_by: Counter[str] = Counter()

        def latest(t: Target) -> tuple[Target, str | None]:
            registry, name = parse_package(t.endpoint) or ("", "")
            try:
                version = reader.latest_version(registry, name)
            except Exception:  # noqa: BLE001 - a registry hiccup skips this package for one crawl
                version = None
            if version is None:
                unknown_by[registry] += 1
            return t, version

        def lookup(batch: list[Target]) -> list[tuple[Target, str | None]]:
            with ThreadPoolExecutor(max_workers=16) as pool:
                return list(pool.map(latest, batch))

        clock = time.monotonic()
        known_states = self.store.package_states()
        states = {t.id: known_states.get(t.id) or {} for t in targets}
        state_seconds = round(time.monotonic() - clock)
        attempted_at = {t.id: str(states[t.id].get("last_attempt") or "") for t in targets}
        known = [t for t in targets if states[t.id].get("package_version")]
        never = [t for t in targets if not states[t.id].get("package_version")]
        updates, first = [], []
        # The same version again with what it asked for (a placeholder key, a start argument, mcp<2):
        # a known, finite set, run right after new versions — behind 40 000 never-observed
        # packages it would wait for days.
        configured: list[tuple[Target, str]] = []
        seen_by_id: dict[str, str] = {}
        config: dict[str, dict[str, list[str]]] = {}
        unchanged = refresh = outdated = incomplete_retries = with_config = settled = with_pins = retraced = rereadable = 0
        undigested_again = 0
        current = self.settings.sandbox_observer
        # An ok, complete observation by an observer listed here stands: what changed since is how a
        # failing package is started, not what a running one reports.
        still_valid = {current, *self.settings.sandbox_observers_valid}
        renewed: list[tuple[Target, str]] = []
        # A record an older trace reader got wrong is a public mistake about someone else's
        # package: it goes ahead of everything but new versions.
        retrace: list[tuple[Target, str]] = []
        # An ok, complete page by a reader that could not see renames and links: run once more.
        reread: list[tuple[Target, str]] = []
        legacy_ids: set[str] = set()
        # A package observed before is looked up every crawl: a new version of it goes first.
        clock = time.monotonic()
        known_versions = lookup(known)
        known_seconds = round(time.monotonic() - clock)
        clock = time.monotonic()
        for t, version in known_versions:
            if version is None:
                continue
            state = states[t.id]
            seen = state.get("package_version")
            seen_by_id[t.id] = seen
            observer = _observer_of(state.get("package_signals"))
            signals = state.get("package_signals") or {}
            if isinstance(signals, str):
                try:
                    signals = json.loads(signals)
                except ValueError:
                    signals = {}
            if not isinstance(signals, dict):
                signals = {}
            if not isinstance(signals.get("exit"), dict) and state.get("last_status") == "exited":
                # Recorded before exits were read: read the stored text now, so a package that has been
                # asking for a key (or for mcp<2, or Node 24) since then is rerun with it, not settled.
                reason = classify("exited", state.get("last_detail"))
                if reason:
                    signals = {**signals, "exit": reason}
            complete = (signals.get("behaviour") or {}).get("complete") is True
            if (seen == version and state.get("current_subject") and not state.get("current_toolset")
                    and signals.get("mtl") != PROFILE_REVISION):
                # Read, and declined by an older revision of MTL/1 (1.0 refused fractions, empty sets
                # and repeated names; 1.1 digests them). The version did not change, so nothing else
                # would run it again, and its record would keep a "not digestible" the current rules
                # may not give. Once per revision: the run records the revision that judged it.
                plan = _config_for(t, signals)
                if plan:
                    config[t.id] = plan
                undigested_again += 1
                renewed.append((t, version))
                continue
            if seen == version and _unplaced_sends(signals.get("behaviour")):
                # Traced again with what started it the last time (a placeholder key, a start
                # argument): without it a server that needs a key exits, and a page that was right
                # about its tools turns into a failure. Whatever the run's status: a package that
                # times out or exits still shows what it did before, and until 10-14 only "ok" pages
                # were re-read — 31 failing ones kept 170 sends gvisor-trace/2 could not place.
                plan = _config_for(t, signals)
                if plan:
                    config[t.id] = plan
                retraced += 1
                retrace.append((t, version))
                continue
            if seen == version and state.get("last_status") == "ok" and complete and observer in still_valid:
                if _missed_renames_and_links(signals.get("behaviour")):
                    plan = _config_for(t, signals)
                    if plan:
                        config[t.id] = plan
                    rereadable += 1
                    reread.append((t, version))
                    continue
                unchanged += 1
                continue
            exit_kind = (signals.get("exit") or {}).get("kind") if isinstance(signals.get("exit"), dict) else None
            if (seen == version and state.get("last_status") == "exited" and exit_kind in LEGACY_PINS
                    and observer in still_valid and t.endpoint.startswith("pypi:")):
                legacy = signals.get("legacy") if isinstance(signals.get("legacy"), dict) else {}
                lplan = {"pins": LEGACY_PINS[exit_kind], **_config_for(t, legacy if legacy.get("version") == version else {})}
                if legacy.get("version") == version and lplan == (legacy.get("supplied") or {}):
                    settled += 1  # the pinned run happened with everything it asked for
                    continue
                config[t.id] = lplan
                legacy_ids.add(t.id)
                with_pins += 1
                configured.append((t, version))
                continue
            plan = _config_for(t, signals)
            if plan:
                config[t.id] = plan
            judged_now = state.get("last_status") == "undigestible" and signals.get("mtl") == PROFILE_REVISION
            if (seen == version and (state.get("last_status") in SETTLED or judged_now) and observer == current
                    and not _early_observer5_failure(state, observer)):
                if not plan or plan == (signals.get("supplied") or {}):
                    settled += 1  # nothing new to try until the package or the observer changes
                    continue
                with_config += 1
                configured.append((t, version))
                continue
            if seen == version:
                refresh += 1
                if observer != current:
                    outdated += 1
                    if state.get("last_status") in RENEWABLE:
                        renewed.append((t, version))
                        continue
                else:
                    incomplete_retries += 1
                first.append((t, version))
            else:
                updates.append((t, version))
        # Never-observed packages in curated order (most downloaded first), wherever they are listed:
        # what people actually run is covered before the long tail of the registry.
        try:
            rank = curated_rank()
        except (OSError, ValueError):
            rank = {}
        # Never let a permanently incomplete popular package occupy the budget every crawl.
        # Unobserved entries come first; retries rotate by oldest attempt, with popularity as a tie-breaker.
        order = sorted([(t, v) for t, v in first] + [(t, None) for t in never],
                       key=lambda tv: (attempted_at[tv[0].id], rank.get(tv[0].endpoint, len(rank))))
        # A never-observed package is not asked about at all: the sandbox installs the latest version
        # and reports which one it ran. Asking first cost ~16 minutes of npm's pace per crawl, every
        # crawl, while the sandboxes waited (and a burst of it once got npm to refuse us).
        configured.sort(key=lambda tv: rank.get(tv[0].endpoint, len(rank)))
        retrace.sort(key=lambda tv: rank.get(tv[0].endpoint, len(rank)))
        retrace = retrace[: max(0, cap - len(updates))]
        configured = configured[: max(0, cap - len(updates) - len(retrace))]
        left = max(0, cap - len(updates) - len(retrace) - len(configured))
        renewable = len(renewed)
        renewed.sort(key=lambda tv: rank.get(tv[0].endpoint, len(rank)))
        # Work an older observer or reader left (failures to run again, pages to trace again) gets at
        # least half of what is left, never-observed packages the rest: ~3,900 pages to re-read must
        # not stop new packages for days, nor wait behind 40,000 of them.
        older_share = max(left // 2, left - len(order))
        renewed = renewed[: min(renewable, older_share)]
        reread.sort(key=lambda tv: rank.get(tv[0].endpoint, len(rank)))
        reread = reread[: max(0, older_share - len(renewed))]
        room = left - len(renewed) - len(reread)
        chosen: list[tuple[Target, str | None]] = [(t, v) for t, v in order[:room]]
        looked_up = 0
        never_seconds = round(time.monotonic() - clock)
        for t in never:
            plan = _config_for(t, {})
            if plan:
                config[t.id] = plan
        due = (updates + retrace + configured + renewed + reread + chosen)[:cap]
        unknown = sum(unknown_by.values())
        if unknown:
            log.warning("package versions unknown this crawl: %s", dict(unknown_by))
        self._due_versions = {t.id: v for t, v in due}
        self._due_config = {t.id: config[t.id] for t, _ in due if config.get(t.id)}
        self._due_legacy = {t.id for t, _ in due if t.id in legacy_ids}
        self._seen_versions = {t.id: seen_by_id[t.id] for t, _ in due if seen_by_id.get(t.id)}
        stats["packages"] = {"dialable": len(targets), "due": len(due), "newVersions": len(updates),
                             "neverObserved": len(never), "olderObserver": outdated, "incompleteRetries": incomplete_retries, "unchanged": unchanged,
                             "withConfig": with_config, "withPins": with_pins, "settled": settled,
                             "renewed": len(renewed), "renewable": renewable, "retraced": len(retrace), "retraceable": retraced,
                             "reread": len(reread), "rereadable": rereadable, "undigestedAgain": undigested_again,
                             "versionUnknown": unknown, "versionUnknownBy": dict(unknown_by),
                             "versionsAsked": len(known) + looked_up,
                             "lookupSeconds": {"state": state_seconds, "known": known_seconds, "neverObserved": never_seconds}}
        log.warning("package versions: state %d s, %d known in %d s, %d more in %d s; %d due", state_seconds,
                    len(known), known_seconds, looked_up, never_seconds, len(due))
        return [t for t, _ in due]

    def _signals(self, package: tuple[str, str], version: str, previous: str | None) -> dict[str, Any] | None:
        """Registry facts for the observed version and the one observed before it; None if the
        registry does not answer — the observation stands without them."""
        reader = self.packages
        facts = getattr(reader, "version_facts", None)
        if facts is None:
            return None
        try:
            current = facts(*package, version)
            prior = facts(*package, previous) if previous and previous != version else None
            return version_signals(current, prior)
        except Exception:  # noqa: BLE001 - metadata is a bonus; a registry hiccup must not cost the observation
            log.warning("registry facts unavailable for %s:%s@%s", package[0], package[1], version)
            return None

    def _observe(self, targets: list[Target]) -> Iterator[list[Prepared]]:
        """Yield only completed observations, without waiting for the slowest endpoint.

        Batch results already ready together for WARDEN; do not start a Node subprocess for
        every fast response. Bound outstanding results as well as network concurrency.
        """
        per_host: dict[str, threading.Semaphore] = defaultdict(
            lambda: threading.Semaphore(self.settings.crawl_per_host)
        )
        per_host[PACKAGE_SANDBOX] = threading.Semaphore(getattr(self.packages, "capacity", self.settings.sandbox_concurrency))
        guard = threading.Lock()
        if self._revision_index is None and self.settings.revision_reads_per_day:
            # Read here, on the crawl's thread, before any worker starts.
            try:
                self._revision_index = self.store.revision_reading_index()
            except Exception:  # noqa: BLE001 - without the index no second reading is taken; the crawl goes on
                log.exception("the other-revision index could not be read")

        def one(t: Target) -> Prepared:
            return self._observe_one(t, per_host, guard)

        remaining = iter(enumerate(targets))
        with ThreadPoolExecutor(max_workers=self.settings.crawl_workers) as pool:
            pending = {}

            def refill() -> None:
                while len(pending) < self.settings.crawl_workers * 2:
                    entry = next(remaining, None)
                    if entry is None:
                        break
                    index, target = entry
                    pending[pool.submit(one, target)] = index

            refill()
            while pending:
                ready, _ = wait(pending, return_when=FIRST_COMPLETED)
                # Preserve input order among results ready together; never wait for a missing one.
                ordered = sorted(ready, key=pending.__getitem__)
                prepared = []
                for future in ordered:
                    del pending[future]
                    prepared.append(future.result())
                del ready, ordered, future
                yield prepared
                del prepared
                refill()

    def _observe_one(self, t: Target, per_host: Any, guard: threading.Lock) -> Prepared:
        with guard:
            sem = per_host[_host_of(t.endpoint)]
        package = parse_package(t.endpoint)
        try:
            with sem:
                if package and self.packages is not None:
                    obs = self.packages.observe(*package, self._due_versions.get(t.id), **self._due_config.get(t.id, {}))
                else:
                    obs = self.reader.list_tools(t.endpoint)
        except Exception as exc:  # noqa: BLE001 - the reader promises not to raise; belt and braces
            obs = Observation(status=SANDBOX_ERROR if package else "client-error", detail=type(exc).__name__)
        item = Prepared(target=t, obs=obs, observed_at=self.clock())
        if package and self.packages is not None and obs.status != SANDBOX_ERROR and obs.package_version:
            item.signals = self._signals(package, obs.package_version, self._seen_versions.get(t.id))
        if obs.status == "ok":
            try:
                item.subject = build_subject(server_name=t.name, registry=t.registry, tools=obs.tools or [],
                                             **_artifact(t))
            except MtlError as exc:
                item.subject_error = exc
            except Exception as exc:  # noqa: BLE001 - hostile input the canonicalizer chokes on
                item.subject_error = MtlError(MTL_SUBJ_001, f"the tool set cannot be processed ({type(exc).__name__})")
            if not package and item.subject is not None and item.subject.tool_set_digest:
                try:
                    item.other_revision = self._other_revision(t, obs, item.subject.tool_set_digest, sem)
                except Exception:  # noqa: BLE001 - a second look must never cost the observation itself
                    log.exception("other-revision reading failed for target %s", t.id)
        return item

    def _other_revision(self, t: Target, obs: Observation, beside: str, sem: Any) -> OtherRevision | None:
        """What a server just read in MCP 2026-07-28 lists to a client that opens with ``initialize``.

        Most servers that answer 2026-07-28 still answer the handshake, and a few list other definitions
        there: an outputSchema wrapped in ``{result: …}``, a draft-07 ``$schema``, more or fewer tools
        (4 of 277 in a sample of 2026-11-27). A handshake client that asks /check about such a server holds
        a set the log has never seen. So the crawl takes that second reading too: read-only, through the
        same reader and robots rules, one at a time per host, when the server's list changed or the stored
        reading is older than ``revision_reread_days``, and at most ``revision_reads_per_day`` a day."""
        limit = self.settings.revision_reads_per_day
        if not limit or self._revision_index is None or obs.protocol_version < FIRST_STATELESS_REVISION:
            return None
        now = self.clock()
        with self._revision_lock:
            known = self._revision_index.get(t.id)
            if known and known[0] == beside and not _older_than(known[1], now, self.settings.revision_reread_days):
                return None
            if self._revision_day != now[:10]:
                self._revision_day, self._revision_done = now[:10], 0
            if self._revision_done >= limit:
                return None
            self._revision_done += 1
            self._revision_index[t.id] = (beside, now)   # claimed, so no second worker reads it again
        with sem:
            second = self.reader.list_tools(t.endpoint, handshake_only=True)
        out = OtherRevision(beside_toolset=beside, protocol=second.protocol_version, toolset=None, tool_count=None,
                            status=second.status, read_at=self.clock())
        if second.status == "ok":
            try:
                out.toolset, entries = tool_set_digest(second.tools or [])
                out.tool_count = len(entries)
            except Exception:  # noqa: BLE001 - MtlError, or hostile input the canonicalizer chokes on
                out.status = "undigestible"
        return out

    def _settle(self, item: Prepared, run_id: int, rulesets: RuleSets, scans: dict[str, dict[str, Any]],
                scan_failed: set[str], sets: str, classifications: dict[str, dict[str, Any]], tally: _Tally) -> str:
        """Record one observation. One target must never take the crawl down: whatever a stranger's
        server made us do, it is recorded against that target and the crawl moves on."""
        with tally.lock:
            tally.statuses[item.obs.status] += 1
        if item.obs.status == SANDBOX_ERROR:
            # Our sandbox failed, not the package: no label may say the package did.
            with tally.lock:
                tally.internal["sandbox"] += 1
            self._commit_internal(item, run_id, item.obs.detail or "the package sandbox failed")
            return "internal-error"
        if item.target.id in self._due_legacy:
            with tally.lock:
                tally.legacy_statuses[item.obs.status] += 1
            self._commit_legacy(item, scans, run_id)
            return item.obs.status
        if item.target.id in scan_failed:
            with tally.lock:
                tally.internal["scan-failed"] += 1
            self._commit_internal(item, run_id, "the WARDEN sidecar failed on this tool set")
            return "internal-error"
        try:
            result = self._commit(item, run_id, rulesets, scans, sets, classifications)
        except Exception as exc:  # noqa: BLE001
            log.exception("commit failed for target %s", item.target.id)
            with tally.lock:
                tally.internal[type(exc).__name__] += 1
            self._commit_internal(item, run_id, f"internal error ({type(exc).__name__})")
            return "internal-error"
        with tally.lock:
            tally.issued.update(result["labels"])
            tally.changes += result["changed"]
            tally.classified += result.get("classified", 0)
        if item.other_revision is not None:
            other = item.other_revision
            try:
                self.store.put_revision_reading(
                    item.target.id, beside_toolset=other.beside_toolset, protocol=other.protocol, toolset=other.toolset,
                    tool_count=other.tool_count, status=other.status, read_at=other.read_at)
            except Exception:  # noqa: BLE001 - side data: never the crawl's problem
                log.exception("storing the other-revision reading failed for target %s", item.target.id)
        return item.obs.status

    def _package_lane(self, targets: list[Target], run_id: int, rulesets: RuleSets, sets: str,
                      tally: _Tally, total: int) -> None:
        """Every due package, as many at once as the sandboxes have slots, each committed when done."""
        capacity = max(1, int(getattr(self.packages, "capacity", self.settings.sandbox_concurrency)))
        per_host: dict[str, threading.Semaphore] = {PACKAGE_SANDBOX: threading.Semaphore(capacity)}
        guard = threading.Lock()
        with ThreadPoolExecutor(max_workers=capacity, thread_name_prefix="histor-sandbox") as pool:
            # A set we discard from, not a list we keep: every finished Future holds its result —
            # the tool set, the sandbox trace, the detail — and a list of all 8 000 kept every one
            # of them alive until the lane ended. The process grew to its 1 GiB limit and was
            # OOM-killed 26 h into crawl 33, near the end, losing the crawl (2026-10-12).
            pending = {pool.submit(self._observe_one, t, per_host, guard) for t in targets}
            for future in as_completed(pending):
                pending.discard(future)
                item = future.result()
                del future
                scans, scan_failed = self._scan([item], sets)
                with tally.classify_lock:
                    classifications, tally.classify_budget = self._classify([item], tally.classify_budget)
                self._settle(item, run_id, rulesets, scans, scan_failed, sets, classifications, tally)
                with tally.lock:
                    self._lane_done += 1
                    self._set_progress(total, len(targets))
                self._checkpoint(run_id, tally)

    def _scan(self, prepared: list[Prepared], sets: str) -> tuple[dict[str, dict[str, Any]], set[str]]:
        """Scan results by target id, and the targets whose scan failed.

        A sidecar failure on one tool set used to raise out of the batch and end the crawl. The
        batch is retried one set at a time, so only the sets the sidecar cannot handle are held
        back — committed as an internal error, and rescanned by the next crawl.
        """
        jobs = []
        for p in prepared:
            if p.subject is None or p.subject.tool_set_digest is None:
                continue
            state = self.store.target(p.target.id) or {}
            if p.subject.digest != state.get("current_subject") or state.get("scan_sets") != sets:
                jobs.append({
                    "id": p.target.id,
                    "server": {"id": p.target.name, "name": p.target.name, "url": p.target.endpoint},
                    "tools": p.subject.entries,
                })
        if not jobs:
            return {}, set()
        try:
            scans = self.scanner.scan(jobs)
        except ScannerError as exc:
            log.warning("WARDEN scan of a batch of %d failed (%s); retrying one by one", len(jobs), exc)
            scans = {}
            for job in jobs:
                try:
                    scans.update(self.scanner.scan([job]))
                except ScannerError:
                    pass
        return scans, {job["id"] for job in jobs if job["id"] not in scans}

    def _classify(self, prepared: list[Prepared], budget: int) -> tuple[dict[str, dict[str, Any]], int]:
        """Advisory classifier verdicts by target id, and the budget left.

        Runs OUTSIDE the write transaction (a network call must never hold the DB open) and only on a
        new/changed subject this model has not judged. A verdict already stored for the exact tool set
        and model — from another target sharing it, or an earlier crawl — is reused without a call, so
        the budget buys distinct tool sets, not duplicate work. Any failure skips that target.
        """
        # Note: an exhausted budget does NOT stop the pass — reuse of an already-stored verdict is
        # free and must keep working, or targets sharing a judged tool set would render "not
        # classified" forever. Only the paid classify() call below is gated on the budget.
        if not self.classifier:
            return {}, budget
        model = self.classifier.model
        out: dict[str, dict[str, Any]] = {}
        # Tool sets already judged in THIS pass: commits happen after the whole batch, so a fresh
        # verdict's stored row is not visible yet. A same-batch reuse carries no `stored` flag — its
        # row only exists once the holder commits, so the sibling waits for the next crawl to claim
        # the badge rather than pointing at a row that a failed commit never wrote.
        seen: dict[str, int] = {}
        for p in prepared:
            if p.subject is None or p.subject.tool_set_digest is None or p.subject.entries is None:
                continue
            state = self.store.target(p.target.id) or {}
            new_subject = p.subject.digest != state.get("current_subject")
            if not new_subject and state.get("classifier_model") == model:
                continue
            digest = p.subject.tool_set_digest
            existing = self.store.classification(digest, model)
            if existing is not None:
                out[p.target.id] = {"flags": len(existing.get("findings", []))}
                continue
            if digest in seen:
                out[p.target.id] = {"flags": seen[digest]}  # same-batch reuse; row committed by the holder
                continue
            if budget <= 0:
                continue
            if self.settings.remote_interval_s > 0:
                # With independent runs, a per-run budget would be spent again each short batch.
                # Reserve before the network call, shared with packages and durable across restarts.
                with self.store.db.transaction() as tx:
                    day = self.clock()[:10]
                    tx.execute("INSERT INTO classifier_daily_budget(day) VALUES(?) ON CONFLICT(day) DO NOTHING", (day,))
                    reserved = tx.one("UPDATE classifier_daily_budget SET used=used+1 WHERE day=? AND used<? RETURNING used",
                                      (day, self.settings.classifier_max_per_crawl))
                if not reserved:
                    continue
            try:
                verdict = self.classifier.classify(p.subject.entries)
            except ClassifierError as exc:
                log.warning("classifier skipped target %s: %s", p.target.id, exc)
                continue
            except Exception:  # noqa: BLE001 — belt and braces: nothing a model answers may end the crawl
                log.exception("classifier failed unexpectedly on target %s; skipped", p.target.id)
                continue
            budget -= 1
            flags = len(verdict.get("findings", []))
            seen[digest] = flags
            out[p.target.id] = {"verdict": verdict, "flags": flags}
        return out, budget

    @staticmethod
    def _launch(p: Prepared) -> str | None:
        """The observation's launch record (histor.packages.launch_record): only a package run has one."""
        if p.target.transport != "stdio" or not (p.obs.package_version or p.obs.package_observer):
            return None
        return dumps(launch_record(p.obs.package_observer, p.obs.package_conditions, p.obs.package_supplied))

    def _commit_internal(self, p: Prepared, run_id: int, why: str) -> None:
        """Record an observation OUR side could not process, without touching the target's chain."""
        try:
            with self.store.db.transaction() as tx:
                Store.record_attempt(tx, p.target.id, run_id, p.observed_at)
                tx.execute(
                    "INSERT INTO observations(target_id, run_id, observed_at, status, detail, pages, package_version, launch, "
                    "registry_version) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (p.target.id, run_id, p.observed_at, "internal-error", clean_text(why, 300), p.obs.pages,
                     clean_text(p.obs.package_version or "", 64) or None, self._launch(p), _registry_version(p.target)),
                )
                tx.execute("UPDATE targets SET last_attempt=? WHERE id=?", (p.observed_at, p.target.id))
        except Exception:  # noqa: BLE001 - even the record of a failure must not end the crawl
            log.exception("could not record the internal error for target %s", p.target.id)

    def _commit_legacy(self, p: Prepared, scans: dict[str, dict[str, Any]], run_id: int) -> None:
        """A run with a legacy pin (mcp<2): kept beside the record, never a label or the target's status.

        What a fresh install gets stays the observation; this says what the same version did when
        it could still start — its tools, what WARDEN matched in them, and what it did in the sandbox.
        """
        t = p.target
        try:
            with self.store.db.transaction() as tx:
                Store.record_attempt(tx, t.id, run_id, p.observed_at)
                state = tx.one("SELECT package_signals, last_status, last_detail FROM targets WHERE id=?", (t.id,)) or {}
                try:
                    previous = json.loads(state.get("package_signals") or "{}")
                except ValueError:
                    previous = {}
                record = dict(previous) if isinstance(previous, dict) else {}
                if not isinstance(record.get("exit"), dict) and state.get("last_status") == "exited":
                    # The fresh install's reason is what the page and WARDEN show this pinned run under.
                    reason = classify("exited", state.get("last_detail"))
                    if reason:
                        record["exit"] = reason
                legacy: dict[str, Any] = {"version": p.obs.package_version or None, "observedAt": p.observed_at,
                                          "status": p.obs.status, "supplied": p.obs.package_supplied or {}}
                if p.obs.package_conditions:
                    legacy["conditions"] = p.obs.package_conditions
                if p.obs.status != "ok":
                    legacy["detail"] = clean_text(excerpt(p.obs.detail, 300))
                    reason = classify(p.obs.status, p.obs.detail)
                    if reason:
                        legacy["exit"] = reason
                subject = p.subject
                if subject is not None and subject.tool_set_digest:
                    Store.put_blob(tx, subject.tool_set_digest, "toolset", subject.entries)
                    legacy.update(toolSetDigest=subject.tool_set_digest, toolCount=len(subject.entries or []),
                                  tools=[clean_text(str(e.get("name", "")), 100) for e in (subject.entries or [])][:200])
                    scan = scans.get(t.id)
                    if scan is not None:
                        matches = scan.get("patternMatches") or []
                        legacy["patternMatches"] = {"block": sum(1 for m in matches if m.get("tier") == "block"),
                                                    "advise": sum(1 for m in matches if m.get("tier") == "advise"),
                                                    "matches": matches[:20]}
                elif p.obs.status == "ok":
                    # A run that started but has no subject still has a count. An empty tool set is
                    # refused as a subject (MTL-SUBJ-002), and without this the record said nothing
                    # where "0 tools" was the finding; the code says which case it was.
                    listed = [e for e in (p.obs.tools or []) if isinstance(e, dict)]
                    legacy.update(toolCount=len(listed),
                                  tools=[clean_text(str(e.get("name", "")), 100) for e in listed][:200])
                    if p.subject_error is not None:
                        legacy["subjectError"] = p.subject_error.code
                if p.obs.behaviour is not None:
                    legacy["behaviour"] = p.obs.behaviour
                record["legacy"] = legacy
                tx.execute("UPDATE targets SET package_signals=?, last_attempt=? WHERE id=?", (dumps(record), p.observed_at, t.id))
                from histor.security_events import append_event
                append_event(tx, self.logbook.key, t.id, p.observed_at, previous, record)
        except Exception:  # noqa: BLE001 - a side observation must not end the crawl
            log.exception("could not record the pinned run for target %s", t.id)

    # -- per-target commit -----------------------------------------------------------

    def _commit(self, p: Prepared, run_id: int, rulesets: RuleSets, scans: dict[str, dict[str, Any]],
                sets: str, classifications: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        issued_at = self.clock()
        labels: list[str] = []
        changed = 0
        classified = 0
        t = p.target
        with self.store.db.transaction() as tx:
            Store.record_attempt(tx, t.id, run_id, p.observed_at)
            state = tx.one("SELECT * FROM targets WHERE id=?", (t.id,)) or {}
            subject = p.subject
            # Annotations, _meta and the other members MTL/1 does not digest (histor.extras).
            # "" is "observed, and no tool carries any"; NULL is "not observed by this code" (failed
            # observations, and every row from before migration 011).
            extras_digest: str | None = None
            extras_body: dict[str, Any] | None = None
            instructions_digest: str | None = None
            if p.obs.status == "ok":
                found, extras_body = tool_extras(p.obs.tools, Store.extras_scheme(tx))
                extras_digest = found or ""
                if found:
                    Store.put_blob(tx, found, "toolextras", extras_body)
                if p.obs.instructions_read:
                    instructions_digest, instructions_body = instructions.stored(p.obs.instructions)
                    if instructions_body is not None:
                        Store.put_blob(tx, instructions_digest, instructions.KIND, instructions_body)
            tx.execute(
                "INSERT INTO observations(target_id, run_id, observed_at, status, detail, subject, toolset, "
                "tool_count, pages, protocol, server_name, server_version, extras, package_version, launch, registry_version, "
                "instructions) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t.id, run_id, p.observed_at, p.obs.status if not p.subject_error else "undigestible",
                 clean_text(excerpt(p.obs.detail, 1000) if not p.subject_error else p.subject_error.code, 1000),
                 subject.digest if subject else None, subject.tool_set_digest if subject else None,
                 len(p.obs.tools) if p.obs.tools is not None else None, p.obs.pages,
                 clean_text(p.obs.protocol_version, 40),
                 clean_text(p.obs.server_info.get("name") or "", 200) or None,
                 clean_text(p.obs.server_info.get("version") or "", 100) or None, extras_digest,
                 clean_text(p.obs.package_version or "", 64) or None, self._launch(p), _registry_version(t),
                 instructions_digest),
            )
            update: dict[str, Any] = {
                "last_attempt": p.observed_at,
                "observations": int(state.get("observations") or 0) + 1,
            }
            if p.obs.package_version:
                # The version this observation is about; the next crawl reruns the sandbox only
                # when the registry publishes another.
                update["package_version"] = clean_text(p.obs.package_version, 64)
            if p.obs.package_version:
                # Facts about the version, the observer that ran it, and what the package did.
                record = dict(p.signals or {})
                record["observer"] = p.obs.package_observer
                # The MTL revision this run's tool set was judged under: a set an older revision
                # declined is run once more under a newer one (_plan_packages, MTL/1.2 section 7.4).
                record["mtl"] = PROFILE_REVISION
                if p.obs.behaviour is not None:
                    record["behaviour"] = p.obs.behaviour
                if p.obs.package_conditions:
                    record["conditions"] = p.obs.package_conditions
                if p.obs.package_supplied:
                    record["supplied"] = p.obs.package_supplied
                reason = classify(p.obs.status, p.obs.detail)
                if reason:
                    record["exit"] = reason
                update["package_signals"] = dumps(record)
                from histor.security_events import append_event
                append_event(tx, self.logbook.key, t.id, p.observed_at,
                             json.loads(state.get("package_signals") or "{}"), record)

            def append(doc: dict[str, Any]) -> dict[str, Any]:
                row = self.logbook.append(tx, doc, target_id=t.id)
                labels.append(row["method"].rsplit(":", 1)[-1])
                return row

            if p.obs.status != "ok":
                update.update(last_status=p.obs.status, last_detail=clean_text(excerpt(p.obs.detail, 300)))
                if state.get("chain_label") and not state.get("failure_reported"):
                    prior = self._label_doc(tx, state["chain_label"])
                    append(self.issuer.continuity(
                        current=None, prior_label=prior,
                        prior_subject_ref=prior["credentialSubject"]["verifiedWork"],
                        prior_tool_digest=None, unchanged_since=None,
                        observed_at=p.observed_at, issued_at=issued_at,
                        failure={"status": p.obs.status, "detail": p.obs.detail[:200]},
                    ))
                    update["failure_reported"] = 1
                self._update_target(tx, t.id, update)
                return {"labels": labels, "changed": 0}

            if p.subject_error is not None:
                code = p.subject_error.code
                update.update(last_status="undigestible",
                              last_detail=clean_text(f"{code}: {p.subject_error.detail}", 300))
                fallback = fallback_subject(server_name=t.name, registry=t.registry, tools=p.obs.tools or [],
                                            **_artifact(t))
                if fallback.digest != state.get("current_subject"):
                    # A set we cannot digest is still a set the server showed, and not the one it
                    # showed before. It breaks the chain: no badge, /check answer or later
                    # continuity label may vouch for "unchanged" across it (MTL/1 7.2, 7.4).
                    Store.put_blob(tx, fallback.digest, "descriptor", fallback.descriptor)
                    link = append(self.issuer.undigestible(
                        subject_ref=fallback.reference(),
                        server={"name": t.name, "registry": t.registry},
                        count=len(p.obs.tools or []), code=code, message=p.subject_error.detail,
                        observed_at=p.observed_at, issued_at=issued_at,
                    ))
                    prior_id = state.get("chain_label")
                    if prior_id:
                        prior = self._label_doc(tx, prior_id)
                        link = append(self.issuer.continuity(
                            current=fallback, prior_label=prior,
                            prior_subject_ref=prior["credentialSubject"]["verifiedWork"],
                            prior_tool_digest=prior["credentialSubject"]["mcpTrustLabel"].get("toolSet", {}).get("digestSRI"),
                            unchanged_since=None, observed_at=p.observed_at, issued_at=issued_at, no_digest_code=code,
                            prior_no_digest_code=(self._no_digest_reason(tx, prior, prior["credentialSubject"]["verifiedWork"])
                                                  if not prior["credentialSubject"]["mcpTrustLabel"].get("toolSet", {}).get("digestSRI")
                                                  else None),
                        ))
                    if state.get("current_subject"):
                        changed = 1
                        self._record_change(tx, t.id, state, fallback, p.observed_at, link["id"], run_id,
                                            p.obs.package_version, _server_version(p), _registry_version(t))
                        update["changes"] = int(state.get("changes") or 0) + 1
                    update.update(
                        chain_label=link["id"], last_continuity_at=p.observed_at, current_subject=fallback.digest,
                        current_toolset=None, current_count=fallback.count, unchanged_since=p.observed_at,
                        failure_reported=0, block_matches=None, advise_matches=None, record_matches=None,
                        scan_sets=None,
                    )
                self._update_target(tx, t.id, update)
                return {"labels": labels, "changed": changed, "classified": 0}

            assert subject is not None
            new_subject = subject.digest != state.get("current_subject")
            scan = scans.get(t.id)
            obs_row = None
            if new_subject:
                Store.put_blob(tx, subject.digest, "descriptor", subject.descriptor)
                if subject.entries is not None and subject.tool_set_digest:
                    Store.put_blob(tx, subject.tool_set_digest, "toolset", subject.entries)
                obs_row = append(self.issuer.observation(subject, observed_at=p.observed_at, issued_at=issued_at))
            if scan is not None and (new_subject or state.get("scan_sets") != sets):
                matches = scan["patternMatches"]
                tx.execute(
                    "INSERT INTO scans(toolset, pattern_set, matches) VALUES(?, ?, ?) "
                    "ON CONFLICT(toolset, pattern_set) DO UPDATE SET matches=excluded.matches",
                    (subject.tool_set_digest, rulesets.pattern_set_digest, dumps(matches)),
                )
                append(self.issuer.pattern_scan(
                    subject, observed_at=p.observed_at, issued_at=issued_at,
                    pattern_set_id=rulesets.pattern_set_id, pattern_set_digest=rulesets.pattern_set_digest,
                    matches=matches,
                ))
                append(self.issuer.name_threat(
                    subject, observed_at=p.observed_at, issued_at=issued_at,
                    record_set_id=rulesets.record_set_id, record_set_digest=rulesets.record_set_digest,
                    matches=scan["recordMatches"],
                ))
                update.update(
                    scan_sets=sets,
                    block_matches=sum(1 for m in matches if m["tier"] == "block"),
                    advise_matches=sum(1 for m in matches if m["tier"] == "advise"),
                    record_matches=len(scan["recordMatches"]),
                )

            # Advisory classifier verdict — stored beside the log, never a label in it.
            if new_subject:
                # A verdict on yesterday's tools cannot mark a new, budget-deferred set judged.
                update.update(classifier_model=None, classifier_flags=None)
            cls = (classifications or {}).get(t.id)
            if cls is not None and self.classifier is not None and subject.tool_set_digest:
                model = self.classifier.model
                if "verdict" in cls:
                    Store.put_classification(tx, subject.tool_set_digest, model, cls["verdict"], p.observed_at)
                    classified = 1
                    update.update(classifier_model=model, classifier_flags=cls.get("flags", 0))
                # A reuse points the target at an existing verdict row. Set the columns only when the
                # row is really there — a prior crawl's, or this batch's holder, which commits earlier
                # in the loop. If the holder's commit failed, the row is absent and this target waits
                # for the next crawl rather than claiming a verdict that was never written.
                elif tx.one("SELECT 1 AS x FROM classifications WHERE toolset=? AND model=?",
                            (subject.tool_set_digest, model)) is not None:
                    update.update(classifier_model=model, classifier_flags=cls.get("flags", 0))

            prior_id = state.get("chain_label")
            if prior_id and (new_subject or self._continuity_due(state.get("last_continuity_at"), p.observed_at)):
                prior = self._label_doc(tx, prior_id)
                prior_detail = prior["credentialSubject"]["mcpTrustLabel"]
                prior_tool_digest = prior_detail.get("toolSet", {}).get("digestSRI")
                prior_ref = prior["credentialSubject"]["verifiedWork"]
                cont = self.issuer.continuity(
                    current=subject, prior_label=prior, prior_subject_ref=prior_ref,
                    prior_tool_digest=prior_tool_digest,
                    unchanged_since=None if new_subject else state.get("unchanged_since"),
                    observed_at=p.observed_at, issued_at=issued_at,
                    prior_no_digest_code=(self._no_digest_reason(tx, prior, prior_ref) if not prior_tool_digest else None),
                )
                row = append(cont)
                update.update(chain_label=row["id"], last_continuity_at=p.observed_at)
                # A new subject after an old one is a change whatever the verdict: `fail` for two
                # digests that differ, `inconclusive` when one side had none (NUM-001, or the
                # undigestible set this one replaces) — the diff then compares names only.
                # Except when the descriptor only gained its digest: the same names and server,
                # first digested now (MTL/1.1 digests what 1.0 refused). Nothing is known to have
                # changed, so no change is recorded; the label above still says the prior had none.
                if (new_subject and state.get("current_subject")
                        and not self._only_gains_digest(tx, state, subject)):
                    changed = 1
                    self._record_change(tx, t.id, state, subject, p.observed_at, row["id"], run_id,
                                        p.obs.package_version, _server_version(p), _registry_version(t))
                    update["changes"] = int(state.get("changes") or 0) + 1
            elif not prior_id and obs_row is not None:
                # The observation starts the chain and counts as its first link: the next
                # continuity label is due one interval after it, not on the next crawl.
                update.update(chain_label=obs_row["id"], last_continuity_at=p.observed_at)

            self._settle_extras(tx, t.id, state, extras_digest, extras_body, p.observed_at, update)
            update.update(
                last_status="ok", last_detail="", last_ok=p.observed_at,
                current_subject=subject.digest, current_toolset=subject.tool_set_digest,
                current_count=subject.count, ok_observations=int(state.get("ok_observations") or 0) + 1,
                failure_reported=0,
            )
            if not state.get("first_pinned"):
                update["first_pinned"] = p.observed_at
            if new_subject:
                update["unchanged_since"] = p.observed_at
            self._update_target(tx, t.id, update)
        return {"labels": labels, "changed": changed, "classified": classified}

    @staticmethod
    def _continuity_due(last: str | None, now: str) -> bool:
        last_dt, now_dt = _parse_ts(last), _parse_ts(now)
        return last_dt is None or now_dt is None or now_dt - last_dt >= timedelta(seconds=CONTINUITY_MIN_INTERVAL_S)

    @staticmethod
    def _label_doc(tx, label_id: str) -> dict[str, Any]:
        row = tx.one("SELECT body FROM labels WHERE id=?", (label_id,))
        if row is None:
            raise RuntimeError(f"chain label {label_id} is missing from the log")
        return json.loads(row["body"])

    @staticmethod
    def _no_digest_reason(tx, label: dict[str, Any], subject_ref: dict[str, str], steps: int = 64) -> str | None:
        """The reason code the chain gave for the subject at *subject_ref* having no digest.

        Walks back from *label* through ``priorLabel`` to a label about that subject that carries
        an ``MTL-NUM`` or ``MTL-SUBJ`` code: the observation or undigestible label that started
        the chain, or the continuity label issued when that subject became current. A failed
        observation's label names no such code and is walked past. ``None`` when none is found.
        """
        doc: dict[str, Any] | None = label
        for _ in range(steps):
            if doc is None:
                return None
            mtl = doc["credentialSubject"]["mcpTrustLabel"]
            if doc["credentialSubject"]["verifiedWork"].get("digestSRI") == subject_ref.get("digestSRI"):
                for reason in mtl.get("reasons") or []:
                    code = str(reason.get("code") or "")
                    if code.startswith(("MTL-NUM-", "MTL-SUBJ-")):
                        return code
            prior_id = (mtl.get("priorLabel") or {}).get("id")
            row = tx.one("SELECT body FROM labels WHERE id=?", (prior_id,)) if prior_id else None
            doc = json.loads(row["body"]) if row is not None else None
        return None

    @staticmethod
    def _only_gains_digest(tx, state: dict[str, Any], subject: Subject) -> bool:
        """True when the current descriptor had no tool-set digest and this one differs only by having one."""
        if state.get("current_toolset") or not subject.tool_set_digest:
            return False
        row = tx.one("SELECT body FROM blobs WHERE digest=? AND kind='descriptor'", (state["current_subject"],))
        if row is None:
            return False
        prior = json.loads(row["body"])
        now = json.loads(json.dumps(subject.descriptor))
        now.get("toolSet", {}).pop("digestSRI", None)
        return prior == now

    def _record_change(self, tx, target_id: str, state: dict[str, Any], subject: Subject, observed_at: str,
                       label_id: str, run_id: int, package_version: str | None = None,
                       server_version: str | None = None, registry_version: str | None = None) -> None:
        old_toolset = state.get("current_toolset")
        # For a package, the change lies between two versions: the last one that served the old list
        # (an unchanged release keeps the list, so the newest such observation) and the one just run.
        # NULL for a remote server, and for an old list last served before migration 014.
        from_version = None
        if package_version and old_toolset:
            row = tx.one("SELECT package_version FROM observations WHERE target_id=? AND toolset=? AND status='ok' "
                         "ORDER BY id DESC LIMIT 1", (target_id, old_toolset))
            from_version = row["package_version"] if row else None
        # Every change also carries the version the server reported and the one the registry listed, on
        # both sides: the "before" side is the newest run before this one that served a list, which was
        # the old list (another list in between would have been a change). A list that moved while both
        # stayed the same is a redefinition at an unchanged version (migration 016).
        before = tx.one(f"SELECT server_version, registry_version FROM observations WHERE target_id=? AND observed_at<? "
                        f"AND {SERVED_A_LIST} ORDER BY observed_at DESC, id DESC LIMIT 1", (target_id, observed_at))
        old_entries = None
        if old_toolset:
            row = tx.one("SELECT body FROM blobs WHERE digest=?", (old_toolset,))
            old_entries = json.loads(row["body"]) if row else None
        old_descriptor = None
        if state.get("current_subject"):
            row = tx.one("SELECT body FROM blobs WHERE digest=?", (state["current_subject"],))
            old_descriptor = json.loads(row["body"]) if row else None
        old_names = old_descriptor["toolSet"]["names"] if old_descriptor else []
        from histor.security_events import append_event
        append_event(tx, self.logbook.key, target_id, observed_at, {"toolSetDigest": old_toolset},
                     {"toolSetDigest": subject.tool_set_digest, "subjectDigest": subject.digest}, kind="definitions")
        summary = diffing.tool_set_diff(old_entries, subject.entries, old_names, subject.names)
        tx.execute(
            "INSERT INTO changes(target_id, observed_at, from_subject, to_subject, from_toolset, to_toolset, summary, label_id, "
            "run_id, from_package_version, to_package_version, from_server_version, to_server_version, "
            "from_registry_version, to_registry_version) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (target_id, observed_at, state.get("current_subject"), subject.digest, old_toolset,
             subject.tool_set_digest, dumps(summary), label_id, run_id, from_version,
             clean_text(package_version or "", 64) or None,
             before["server_version"] if before else None, server_version,
             before["registry_version"] if before else None, registry_version),
        )

    @staticmethod
    def _previous_tool_names(tx, state: dict[str, Any]) -> set[str] | None:
        """The tool names of the target's previous tool set; None when it had no digested set."""
        digest = state.get("current_toolset")
        if not digest:
            return None
        row = tx.one("SELECT body FROM blobs WHERE digest=? AND kind='toolset'", (digest,))
        return extras_mod.tool_names(row["body"]) if row else None

    @staticmethod
    def _settle_extras(tx, target_id: str, state: dict[str, Any], digest: str | None, body: dict[str, Any] | None,
                       observed_at: str, update: dict[str, Any]) -> None:
        """Point the target at this observation's extras and record a change when they moved.

        ``digest`` is ``""`` when no tool carries an extra member. A target whose ``current_extras``
        is still NULL was never observed by this code: its first ok observation starts the record
        and is not a change. Without that rule the first crawl after migration 011 would report
        every server at once.
        """
        if digest is None:
            return
        previous = state.get("current_extras")
        if digest == previous:
            return
        update["current_extras"] = digest
        if previous is None:
            return
        old_body = None
        if previous:
            row = tx.one("SELECT body FROM blobs WHERE digest=? AND kind='toolextras'", (previous,))
            old_body = json.loads(row["body"]) if row else None
            # The same body under the other extras scheme: the log changed how it writes the digest
            # (histor.extras_rekey), the server changed nothing. Not a change.
            if old_body is not None and digest and any(
                    extras_mod.digest_of(old_body, scheme) == digest for scheme in extras_mod.SCHEMES):
                return
        tx.execute(
            "INSERT INTO extras_changes(target_id, observed_at, from_extras, to_extras, summary) VALUES(?, ?, ?, ?, ?)",
            (target_id, observed_at, previous or None, digest or None,
             dumps(extras_diff(old_body, body, Crawler._previous_tool_names(tx, state)))),
        )

    @staticmethod
    def _update_target(tx, target_id: str, fields: dict[str, Any]) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        tx.execute(f"UPDATE targets SET {cols} WHERE id=?", (*fields.values(), target_id))
