"""Loop health and the circuit breaker — what stops an autonomous fixer from degrading quietly.

Two different jobs live here, and keeping them apart matters:

* :class:`LoopHealth` **observes**. It turns the job store and the order queue into the handful of
  numbers that actually say whether the loop is working, and exposes them for the dashboard, LOGOS
  and Prometheus.
* :class:`CircuitBreaker` **enforces**. It reads those numbers and refuses to let the conductor sign
  another deploy order once they look wrong.

Observation alone is not a safeguard. A dashboard nobody is looking at, at 3am, in front of a loop
that ships one bad patch every twenty minutes, is decoration. So the breaker is in the deploy path.

**The signal that matters is the rollback rate, not the failure rate.** A patch that fails the gate
costs nothing — MOMUS refuses it and the loop retries. A patch that passes the gate, deploys, and then
has to be undone is the dangerous shape: it means the gate's opinion and reality disagree, and the
loop cannot tell the difference on its own. Every other counter here is secondary to that one.

**A tripped breaker stays tripped across a restart.** The trip is persisted, and only an operator
clears it. A breaker that reset itself when the process bounced would be defeated by the very
crash-loop it exists to stop — and "it recovered on its own" is indistinguishable from "nobody ever
found out".
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from skopos.remediation.jobs import JobState

# ── the flag vocabulary ────────────────────────────────────────────────────────
# Set by the conductor on a Job; counted here. One string per fact worth alerting on.
FLAG_GATE_INCONCLUSIVE = "gate_inconclusive"        # MOMUS could not render a verdict at all
FLAG_AGENT_NEVER_CLAIMED = "agent_never_claimed"    # order published, no agent picked it up
FLAG_AGENT_REFUSED = "agent_refused"                # agent verified the chain and said no
FLAG_HEALTH_GATE_FAILED = "health_gate_failed"      # deployed, container did not come up
FLAG_ROLLED_BACK = "rolled_back"                    # a shipped patch had to be undone
FLAG_ROLLBACK_FAILED = "rollback_failed"            # ...and the undo did not work → human, now
FLAG_LIVE_REGRESSION = "live_regression"            # gate said fixed; live service says otherwise
FLAG_REOPENED = "reopened"                          # a finding came back after being closed
FLAG_BREAKER_OPEN = "breaker_open"                  # refused because the loop is quarantined
FLAG_DEPLOYED = "deployed"                          # a real (non-dry-run) deploy happened
FLAG_DRY_RUN = "dry_run"                            # closed without touching anything

TERMINAL = {JobState.DONE.value, JobState.FAILED.value, JobState.ESCALATED.value}


def _parse_ts(ts: str) -> float:
    try:
        return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return 0.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 1)


@dataclass
class BreakerThresholds:
    """Deliberately tight defaults. This loop is allowed to be *slow*; it is not allowed to be busy
    and wrong. An operator who wants more throughput raises these knowingly."""

    #: Hard ceiling on real deploys, whatever else the numbers say. A loop that wants to ship 40
    #: times today is not fixing 40 things; it is thrashing.
    max_deploys_per_day: int = 6
    max_deploys_per_component_per_day: int = 2
    #: THE signal. Two undos in a window means the gate and reality disagree twice — stop.
    max_rollbacks_in_window: int = 2
    max_rollback_rate: float = 0.34
    #: Rates are meaningless on tiny samples: 1-of-1 is not a 100% failure rate worth tripping on.
    min_sample_for_rate: int = 5
    max_consecutive_component_failures: int = 3
    window_s: float = 86400.0

    @classmethod
    def from_env(cls) -> "BreakerThresholds":
        def _i(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "") or default)
            except ValueError:
                return default

        def _f(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, "") or default)
            except ValueError:
                return default

        return cls(
            max_deploys_per_day=_i("SKOPOS_MAX_DEPLOYS_PER_DAY", 6),
            max_deploys_per_component_per_day=_i("SKOPOS_MAX_DEPLOYS_PER_COMPONENT_PER_DAY", 2),
            max_rollbacks_in_window=_i("SKOPOS_MAX_ROLLBACKS", 2),
            max_rollback_rate=_f("SKOPOS_MAX_ROLLBACK_RATE", 0.34),
            min_sample_for_rate=_i("SKOPOS_BREAKER_MIN_SAMPLE", 5),
            max_consecutive_component_failures=_i("SKOPOS_MAX_CONSECUTIVE_FAILURES", 3),
            window_s=_f("SKOPOS_BREAKER_WINDOW_S", 86400.0),
        )


@dataclass
class TripState:
    tripped: bool = False
    reason: str = ""
    tripped_at: float = 0.0
    cleared_at: float = 0.0
    cleared_by: str = ""
    trips_total: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LoopHealth:
    """The numbers that say whether the remediation loop is healthy — derived, never stored."""

    def __init__(self, job_store: Any, order_queue: Any, *,
                 window_s: float = 86400.0):
        self.jobs = job_store
        self.orders = order_queue
        self.window_s = window_s

    def _recent_jobs(self) -> list[dict[str, Any]]:
        cutoff = time.time() - self.window_s
        return [j.to_dict() for j in self.jobs.all() if _parse_ts(j.updated_at) >= cutoff]

    def deploys_today(self) -> tuple[int, dict[str, int]]:
        """Real deploys in the window, globally and per component.

        Counted from the ORDER QUEUE's agent results rather than from job states: a job reaching DONE
        in dry-run has deployed nothing, and counting those toward a deploy cap would throttle a loop
        that never touched a host."""
        cutoff = time.time() - self.window_s
        total = 0
        per: dict[str, int] = {}
        for order in self.orders.all(limit=10_000):
            if float(order.get("published_at") or 0) < cutoff:
                continue
            result = order.get("result") or {}
            # A deploy that was reverted still touched the host, so it counts against the cap.
            # Counting only `deployed` let a loop that broke and reverted a service all day sit
            # at zero deploys and never hit its own throttle.
            if order.get("kind") != "deploy":
                continue
            if not (result.get("deployed") or result.get("health_gate_failed")):
                continue
            total += 1
            svc = str(order.get("service") or "?")
            per[svc] = per.get(svc, 0) + 1
        return total, per

    def consecutive_failures(self, component: str) -> int:
        """How many times in a row this component's remediation has ended badly.

        A component that cannot be fixed is a component the loop should stop trying to fix — the
        third identical failure is not information, it is noise with a deploy attached."""
        streak = 0
        for job in self.jobs.all():          # newest first
            if job.component != component or job.state not in TERMINAL:
                continue
            if job.state == JobState.DONE.value:
                break
            streak += 1
        return streak

    def snapshot(self) -> dict[str, Any]:
        recent = self._recent_jobs()
        by_state: dict[str, int] = {}
        flag_counts: dict[str, int] = {}
        durations: list[float] = []
        for job in recent:
            by_state[job.get("state", "unknown")] = by_state.get(job.get("state", "unknown"), 0) + 1
            for f in job.get("flags") or []:
                flag_counts[f] = flag_counts.get(f, 0) + 1
            if job.get("state") == JobState.DONE.value:
                started, ended = _parse_ts(job.get("created_at", "")), _parse_ts(job.get("updated_at", ""))
                if started and ended >= started:
                    durations.append(ended - started)

        terminal = sum(by_state.get(s, 0) for s in TERMINAL)
        done = by_state.get(JobState.DONE.value, 0)
        deployed = flag_counts.get(FLAG_DEPLOYED, 0)
        rolled_back = flag_counts.get(FLAG_ROLLED_BACK, 0)
        deploys_total, deploys_per_component = self.deploys_today()
        return {
            "window_s": self.window_s,
            "jobs_in_window": len(recent),
            "by_state": by_state,
            "flags": flag_counts,
            # Win rate over TERMINAL jobs only. Including in-flight ones would make the loop look
            # worse every time it got busy, which is the opposite of a health signal.
            "win_rate": round(done / terminal, 3) if terminal else None,
            "terminal": terminal,
            "deployed": deployed,
            "rolled_back": rolled_back,
            # The headline number. Undos per shipped patch — the rate at which the gate is wrong.
            "rollback_rate": round(rolled_back / deployed, 3) if deployed else None,
            "real_deploys_in_window": deploys_total,
            "real_deploys_by_component": deploys_per_component,
            "time_to_fix_s": {"p50": _percentile(durations, 50), "p95": _percentile(durations, 95),
                              "n": len(durations)},
            "orders": self.orders.stats(),
            # Anything here is a standing invitation for a human to look.
            "needs_attention": {
                "rollback_failed": flag_counts.get(FLAG_ROLLBACK_FAILED, 0),
                "live_regressions": flag_counts.get(FLAG_LIVE_REGRESSION, 0),
                "reopened": flag_counts.get(FLAG_REOPENED, 0),
                "agent_never_claimed": flag_counts.get(FLAG_AGENT_NEVER_CLAIMED, 0),
                "gate_inconclusive": flag_counts.get(FLAG_GATE_INCONCLUSIVE, 0),
            },
        }


class CircuitBreaker:
    """Refuses to let the loop keep deploying once its own numbers say it is misbehaving.

    Checked immediately before a DeployOrder is signed — the last point where declining is free."""

    def __init__(self, health: LoopHealth, *, thresholds: BreakerThresholds | None = None,
                 state_path: str = "data/remediation/breaker.json",
                 enabled: bool = True):
        self.health = health
        self.t = thresholds or BreakerThresholds.from_env()
        self._path = Path(state_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        #: Master switch, separate from the breaker's own trip state: an operator can stand the loop
        #: down without that reading as "the loop broke".
        self.enabled = enabled
        self.state = self._load()

    def _load(self) -> TripState:
        if not self._path.is_file():
            return TripState()
        try:
            return TripState(**json.loads(self._path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError, OSError):
            # An unreadable breaker file must fail CLOSED. The alternative — treating corruption as
            # "not tripped" — makes deleting one file enough to re-arm a quarantined loop.
            return TripState(tripped=True, reason="breaker state file is unreadable — failing closed",
                             tripped_at=time.time())

    def _persist(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def trip(self, reason: str) -> TripState:
        if not self.state.tripped:
            self.state.tripped = True
            self.state.reason = reason
            self.state.tripped_at = time.time()
            self.state.trips_total += 1
            self.state.history.append({"ts": self.state.tripped_at, "event": "trip", "reason": reason})
            self.state.history = self.state.history[-50:]
            self._persist()
        return self.state

    def clear(self, by: str = "operator") -> TripState:
        """Only a human clears a trip. Nothing in this package calls it."""
        self.state.tripped = False
        self.state.reason = ""
        self.state.cleared_at = time.time()
        self.state.cleared_by = by
        self.state.history.append({"ts": self.state.cleared_at, "event": "clear", "by": by})
        self.state.history = self.state.history[-50:]
        self._persist()
        return self.state

    def check(self, component: str) -> tuple[bool, str]:
        """(may_deploy, reason). Trips itself as a side effect when a threshold is crossed, so the
        refusal survives the restart that a crash-looping deploy tends to cause."""
        if not self.enabled:
            return False, ("autonomous remediation is switched off "
                           "(SKOPOS_REMEDIATION_ENABLED=0) — no deploy orders will be signed")
        if self.state.tripped:
            return False, (f"circuit breaker is OPEN since "
                           f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.state.tripped_at))}: "
                           f"{self.state.reason}. An operator must clear it.")

        snap = self.health.snapshot()
        rolled_back = snap.get("rolled_back") or 0
        deployed = snap.get("deployed") or 0
        deploys_total, per_component = self.health.deploys_today()

        if rolled_back >= self.t.max_rollbacks_in_window:
            return False, self.trip(
                f"{rolled_back} rollbacks in the last {int(self.t.window_s)}s "
                f"(limit {self.t.max_rollbacks_in_window}) — the deploy gate's verdicts are not "
                f"matching reality, so no further patch should be trusted until a human looks"
            ).reason
        rate = (rolled_back / deployed) if deployed else 0.0
        if deployed >= self.t.min_sample_for_rate and rate > self.t.max_rollback_rate:
            return False, self.trip(
                f"rollback rate {rate:.0%} over {deployed} deploys exceeds "
                f"{self.t.max_rollback_rate:.0%}").reason
        if deploys_total >= self.t.max_deploys_per_day:
            return False, (f"daily deploy cap reached ({deploys_total}/"
                           f"{self.t.max_deploys_per_day}) — not a fault, a throttle; "
                           f"the job stays open and can proceed in the next window")
        if per_component.get(component, 0) >= self.t.max_deploys_per_component_per_day:
            return False, (f"per-component deploy cap reached for '{component}' "
                           f"({per_component.get(component)}/"
                           f"{self.t.max_deploys_per_component_per_day}) — repeatedly redeploying "
                           f"one service is thrashing, not remediation")
        streak = self.health.consecutive_failures(component)
        if streak >= self.t.max_consecutive_component_failures:
            return False, (f"'{component}' has failed remediation {streak} times in a row — "
                           f"handing it to a human instead of trying again")
        return True, "breaker closed: within all limits"

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "thresholds": asdict(self.t), **self.state.to_dict()}


def breaker_from_env(job_store: Any, order_queue: Any, *, data_dir: str = "") -> CircuitBreaker:
    d = data_dir or os.environ.get("SKOPOS_REMEDIATION_DIR", "data/remediation")
    thresholds = BreakerThresholds.from_env()
    health = LoopHealth(job_store, order_queue, window_s=thresholds.window_s)
    enabled = os.environ.get("SKOPOS_REMEDIATION_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off")
    return CircuitBreaker(health, thresholds=thresholds,
                          state_path=os.path.join(d, "breaker.json"), enabled=enabled)
