"""The finger on the trigger — scheduled scans, and the rule that dispatches without a human.

Everything downstream of a remediation ticket has been live and proven for a while, and none of
it ever ran, because nothing started it: there was no scan schedule anywhere, and POST /remediate
is operator-gated with exactly one caller. The loop was a machine with nobody's hand on it.

This is that hand, and it is deliberately the smallest one that could work.

**Why it lives here and not in MOMUS.** MOMUS is the auditor; giving it the initiative to act on
its own findings is the same conflict the patch denylist already refuses one layer down. So the
component that decides *what to conduct* is the conductor's, and the auditor keeps answering only
when asked.

**Why it does not wait for status == "confirmed".** It cannot: nothing in production ever sets
that status. `Status.CONFIRMED` appears in the momus tree only in tests, so every finding stays
"raw" forever and a dispatcher gated on it would never fire once. The evidence that a finding is
real and not a flake is already in the corpus under a different name — `seen_count`, bumped per
dedup key on every scan that rediscovers the same bug — plus an independent verifier's verdict
when one exists. A bug that reproduced across N separate scans is the honest local meaning of
"confirmed", and it is stated here rather than smuggled into a status field that means something
else.

This USED to say the verdict short-circuit was unreachable because GET /findings did not carry
the verdicts table. That was true when it was written and is no longer: `MomusStore.recent()`
attaches them to every row, so a confirmed independent verdict does now lower the sighting bar
(to VERDICT_SIGHTING_FLOOR, never below it). Re-checked against the live corpus rather than
trusted — a stale "this cannot fire" note is worse than none, because it invites the next reader
to skip the branch that is now the one deciding.

**Fail closed, everywhere.** Off unless explicitly enabled. A component absent from the policy is
never dispatched — and the components that must never be touched are refused by a denylist rather
than by being absent, for the same reason the Factory's patch scope has one: omission is a
default, and a default is what someone widening a config overrides without noticing.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("skopos.autopilot")

#: Off until an operator says otherwise. Merging this file must not give the loop initiative.
ENABLED_ENV = "AUTOPILOT_ENABLED"

#: Never dispatched, whatever the policy says. The auditor, the payer and the conductor — the
#: same three the Factory's patch gate refuses, stated again here because this is the component
#: that would otherwise *ask* for it.
DENIED_COMPONENTS: frozenset[str] = frozenset({
    "momus", "momus-backend", "momus-self", "self",
    "treasury", "momus-treasury",
    "skopos", "skopos-remediation", "remediation-fixer",
})

#: What may be dispatched without a human, per component. Declared, never inferred: a component
#: that is not here is not dispatched, and adding one is a deliberate act.
#:
#: `min_sightings` is the conservatism dial. The canary exists to be broken and fixed, so two
#: sightings is enough; the hub is a revenue path, so it waits for three — a defect that shows up
#: in three separate scans is not a flake.
DEFAULT_POLICY: dict[str, dict[str, Any]] = {
    # The practice target: no consumers, a documented intent to be repaired, and a test gate
    # that decides whether the repair was real. Two sightings, same as the canary.
    "praxis": {"severities": ["critical", "high"], "min_sightings": 2},
    "canary": {"severities": ["critical", "high"], "min_sightings": 2},
    "gaia": {"severities": ["critical", "high"], "min_sightings": 2},
    "hub": {"severities": ["critical", "high"], "min_sightings": 3},
}

#: Which targets get scanned, in order. Scanning something with no policy entry is still useful —
#: the finding is recorded and a human can act on it — so this list is deliberately wider than
#: the policy.
DEFAULT_SCAN_ROTA = ["praxis", "canary", "gaia", "hub", "oracles"]


#: The lowest a confirmed independent verdict may take the sighting requirement. Two, not
#: one: a verdict is a second opinion, and a second opinion plus a single sighting is two
#: independent reasons to believe the finding — which is exactly what the default asks for.
VERDICT_SIGHTING_FLOOR = 2

#: Verdict scores below this are an opinion the verifier itself is unsure of. The verifier
#: returns `inconclusive` when it cannot reach a judgement, but a low-confidence `confirmed`
#: is the more dangerous shape: it reads as evidence and is not.
VERDICT_MIN_SCORE = 0.7


def _independently_confirmed(finding: dict) -> tuple[bool, str]:
    """Is there a confident, confirmed verdict from a verifier that is not the scanner?

    Returns (confirmed, a short note naming what confirmed it) — the note goes into the
    refusal text, because "needs 2" without saying why the bar moved is the kind of log
    line that costs somebody an afternoon.
    """
    scanner = str(finding.get("scanner_pubkey") or "")
    for v in (finding.get("verdicts") or []):
        if not isinstance(v, dict):
            continue
        if str(v.get("verdict") or "").lower() != "confirmed":
            continue
        try:
            score = float(v.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
        if score < VERDICT_MIN_SCORE:
            continue
        # A verdict signed by the scanner's own key is not independent evidence, whatever
        # it says. MOMUS refuses to build such a verifier; this is the second place that
        # cannot be talked out of it.
        pubkey = str(v.get("verifier_pubkey") or "")
        if pubkey and scanner and pubkey == scanner:
            continue
        return True, f"verdict from {v.get('verifier_id') or 'an independent verifier'}"
    return False, ""


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _iso_utc(epoch: float) -> str:
    """The loop's one timestamp shape, so job history and this journal compare as strings."""
    return datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _epoch_from_iso(value: str) -> float:
    """ISO-8601 UTC → epoch. Unparseable reads as *now*, i.e. fresh: see the caller for why an
    unknown age must not mute a finding."""
    try:
        text = value.strip().replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(text).timestamp()
    except (ValueError, AttributeError):
        return time.time()


def _refunded_keys(history: list[dict[str, Any]]) -> set[tuple[str, float]]:
    """Which dispatches have been refunded, keyed by FINDING **and** time.

    Keyed by time alone this was wrong in a way only production shows: one tick stamps every
    dispatch it makes with the same `now`, so two findings dispatched in the same pass share
    an `at`. Refunding one then struck out the other — and the survivor silently lost its
    cooldown and its slot in the day's budget. Caught on the live host within a minute of
    shipping, by a second finding going out three hours into a six-hour cooldown.
    """
    return {(str(h.get("finding_id") or ""), float(h.get("refund_of") or 0))
            for h in history if h.get("refund_of")}


def is_enabled() -> bool:
    return str(os.environ.get(ENABLED_ENV, "")).strip().lower() in ("1", "true", "yes", "on")


def policy() -> dict[str, dict[str, Any]]:
    """Operator JSON wins per component; denied components are dropped whatever it says."""
    raw = str(os.environ.get("AUTOPILOT_POLICY", "")).strip()
    merged = {k: dict(v) for k, v in DEFAULT_POLICY.items()}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            # A malformed policy must leave the dispatcher unable to dispatch anything new,
            # never able to dispatch everything, so the parse failure falls back to the default
            # rather than to an empty (= permissive-looking) map.
            merged = {str(k): dict(v) for k, v in parsed.items() if isinstance(v, dict)}
    return {k: v for k, v in merged.items() if k not in DENIED_COMPONENTS}


@dataclass
class DispatchDecision:
    finding_id: str
    component: str
    severity: str
    seen_count: int
    dispatch: bool
    reason: str


@dataclass
class Autopilot:
    momus_url: str = field(default_factory=lambda: os.environ.get(
        "AUTOPILOT_MOMUS_URL", "http://127.0.0.1:9400").rstrip("/"))
    operator_token: str = field(default_factory=lambda: os.environ.get(
        "MOMUS_OPERATOR_TOKEN", "").strip())
    state_path: str = field(default_factory=lambda: os.environ.get(
        "AUTOPILOT_STATE", "/var/lib/skopos-autopilot/dispatched.jsonl"))
    #: Read-only, and only to answer one question: did the ticket we sent actually start work?
    conductor_url: str = field(default_factory=lambda: os.environ.get(
        "AUTOPILOT_CONDUCTOR_URL", "http://127.0.0.1:9402").rstrip("/"))

    def __post_init__(self) -> None:
        self.scan_rota = [t.strip() for t in os.environ.get(
            "AUTOPILOT_SCAN_ROTA", ",".join(DEFAULT_SCAN_ROTA)).split(",") if t.strip()]
        self.cooldown_s = _float_env("AUTOPILOT_COOLDOWN_S", 6 * 3600)
        self.max_per_day = _int_env("AUTOPILOT_MAX_PER_DAY", 4)
        self.max_per_component_per_day = _int_env("AUTOPILOT_MAX_PER_COMPONENT_PER_DAY", 2)
        # How long a dispatch has to show up as work before we call it absorbed. Generous:
        # the conductor transitions within seconds, so ten minutes is slack, not a deadline.
        self.reconcile_window_s = _float_env("AUTOPILOT_RECONCILE_WINDOW_S", 600)
        # Clock skew between this process and the conductor's container, both ways.
        self.reconcile_grace_s = _float_env("AUTOPILOT_RECONCILE_GRACE_S", 120)
        # Two scan rounds of slack, so one missed scan never mutes a real defect.
        self.stale_after_s = _float_env(
            "AUTOPILOT_STALE_AFTER_S", 2 * _float_env("AUTOPILOT_INTERVAL_S", 900))

    # ── the journal: what this process has already set in motion ────────────────
    def _history(self) -> list[dict[str, Any]]:
        try:
            with open(self.state_path, encoding="utf-8") as fh:
                return [json.loads(line) for line in fh if line.strip()]
        except (OSError, ValueError):
            return []

    def _record(self, entry: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── reconciliation: a ticket nobody acted on cost nothing ───────────────────
    def _job_moved_after(self, finding_id: str, at: float) -> bool | None:
        """Did the conductor's job for this finding start work in response to OUR ticket?

        Bounded by a window, not open-ended, and that is the whole subtlety. The conductor
        acts the moment it accepts a ticket — the ingress spawns the job immediately and the
        first transition lands within seconds — so "nothing within the window" means nothing
        was ever going to happen. Asking the open-ended question instead ("did this job ever
        move after we dispatched?") lets a LATER ticket, hours afterwards, retroactively
        justify our dead one, which is exactly the case this reconciliation exists to catch.

        None means "could not tell" — the conductor was unreachable or answered something
        unexpected — and an unknown answer must NEVER become a refund: over-refunding turns
        the daily cap into no cap at all, which is the one failure mode a budget exists to
        prevent. Only a definite "nothing happened" refunds.
        """
        try:
            r = httpx.get(f"{self.conductor_url}/remediation/jobs/{finding_id}", timeout=20.0)
            if r.status_code == 404:
                # No job at all: the ticket never became work.
                return False
            r.raise_for_status()
            payload = r.json() or {}
        except (httpx.HTTPError, ValueError):
            return None
        job = payload.get("job") or payload
        history = job.get("history")
        if not isinstance(history, list):
            return None
        # Same ISO-8601 UTC shape the whole loop uses, so string order is time order.
        opened = _iso_utc(at - self.reconcile_grace_s)
        closes = _iso_utc(at + self.reconcile_window_s)
        for entry in history:
            ts = str((entry or {}).get("ts") or "")
            if ts.endswith("Z") and opened <= ts <= closes:
                return True
        return False

    #: Job states that mean "nobody is working on this any more".
    TERMINAL_JOB_STATES = frozenset({"done", "escalated", "failed", "cancelled"})

    def _job_state(self, finding_id: str) -> str | None:
        """The conductor's state for this finding, or None if it cannot be read."""
        try:
            r = httpx.get(f"{self.conductor_url}/remediation/jobs/{finding_id}", timeout=20.0)
            if r.status_code == 404:
                return ""
            r.raise_for_status()
            payload = r.json() or {}
        except (httpx.HTTPError, ValueError):
            return None
        job = payload.get("job") or payload
        state = job.get("state")
        return str(state).lower() if isinstance(state, str) else None

    def reconcile(self, history: list[dict[str, Any]], *, now: float) -> list[dict[str, Any]]:
        """Refund dispatches the conductor absorbed without starting any work.

        MOMUS answers 200 and the A2A ingress answers "working" the instant it accepts a
        ticket — it starts the job in the background, so the reply cannot say whether the
        conductor did anything with it. When a ticket lands on a job the conductor declines
        to re-open (a finished remediation, a duplicate), nothing runs, nothing is spent,
        and nobody was told: the slot was gone from the day's budget for a ticket that
        produced no patch, no build and no deploy. That is how a real dispatch of a real
        regression came to be refused by a cap that had been consumed by a ticket which did
        nothing at all.

        A refund clears the cooldown too, and for the same reason: the cooldown exists so we
        do not pile tickets onto work already in flight. There is no work.
        """
        refunded = _refunded_keys(history)
        day_ago = now - 86400
        out = list(history)
        for entry in history:
            at = float(entry.get("at") or 0)
            fid = str(entry.get("finding_id") or "")
            if not entry.get("dispatched") or at <= day_ago or (fid, at) in refunded or not fid:
                continue
            if now - at < self.reconcile_window_s:
                continue  # too soon to call it dead — the job may still be starting
            moved = self._job_moved_after(fid, at)
            if moved is not False:
                continue
            record = {"at": now, "finding_id": fid,
                      "component": entry.get("component"), "severity": entry.get("severity"),
                      "refund_of": at, "dispatched": False,
                      "reason": "refunded: the conductor started no work for this ticket "
                                "(absorbed as a duplicate of a finished remediation)"}
            self._record(record)
            out.append(record)
            refunded.add((fid, at))
        return out

    @staticmethod
    def effective(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """History with refunded dispatches struck out — what the caps and cooldown see."""
        refunded = _refunded_keys(history)
        return [h for h in history
                if not h.get("refund_of")
                and (str(h.get("finding_id") or ""), float(h.get("at") or 0)) not in refunded]

    # ── the rule ────────────────────────────────────────────────────────────────
    def decide(self, finding: dict[str, Any], *, history: list[dict[str, Any]],
               now: float, job_state=None) -> DispatchDecision:
        component = str(finding.get("target") or "")
        severity = str(finding.get("severity") or "").lower()
        seen = int(finding.get("seen_count") or 1)
        fid = str(finding.get("finding_id") or "")

        def no(reason: str) -> DispatchDecision:
            return DispatchDecision(fid, component, severity, seen, False, reason)

        if component in DENIED_COMPONENTS:
            return no("the loop does not act on its own auditor, payer or conductor")
        rule = policy().get(component)
        if not rule:
            return no(f"no dispatch policy for {component!r} — a human decides")
        if severity not in [s.lower() for s in rule.get("severities") or []]:
            return no(f"severity {severity!r} is below the policy for {component}")

        # Still reproducing? `seen_count` is cumulative and never falls, so a finding that was
        # fixed weeks ago still looks like evidence forever. The corpus bumps `last_seen_at` on
        # every rediscovery, so a finding the latest scans no longer reproduce is a closed bug
        # with a long memory, not a live one. Observed: a fixed canary defect was re-dispatched
        # on every tick, absorbed every time, and only the refund kept it from eating the budget.
        # Missing timestamp means dispatch: an unknown age must not silently mute a real defect,
        # and the refund makes an over-dispatch cheap while a missed repair is not.
        stale_after = self.stale_after_s
        last_seen = str(finding.get("last_seen_at") or "").strip()
        if stale_after > 0 and last_seen:
            age = now - _epoch_from_iso(last_seen)
            if age > stale_after:
                return no(f"last reproduced {age / 60:.0f} min ago — scans since then do not "
                          f"see it; not a live defect")

        min_sightings = int(rule.get("min_sightings") or 2)
        verified, verdict_note = _independently_confirmed(finding)
        # A verdict LOWERS the bar; it does not remove it.
        #
        # This branch was unreachable for as long as nothing wrote verdicts, so the day one
        # arrived it would silently have let a single model answer override the hub's
        # three-sighting conservatism. One opinion is better evidence than one sighting —
        # it is not better than three. So a confirmed verdict buys a floor of two, and a
        # component that asked for more than two still gets more than two.
        effective_min = min(min_sightings, VERDICT_SIGHTING_FLOOR) if verified else min_sightings
        if seen < effective_min:
            reason = f"seen {seen}x, needs {effective_min}"
            if verified and effective_min < min_sightings:
                reason += f" ({verdict_note} lowered it from {min_sightings})"
            elif not verified:
                reason += f" (or {VERDICT_SIGHTING_FLOOR} with an independent verdict)"
            return no(reason)

        recent = [h for h in history if h.get("finding_id") == fid]
        if recent and now - float(recent[-1].get("at") or 0) < self.cooldown_s:
            # The cooldown exists so we do not pile tickets onto work already in flight. When the
            # job has reached a terminal state there IS no work: the loop tried and stopped. A
            # finding still reproducing after that is precisely the case worth another go, and
            # making it wait six hours is how an infrastructure hiccup — a branch name, a missing
            # signing backend — costs an afternoon. Repeats stay bounded by the daily caps below,
            # which are the right instrument for "this keeps failing".
            state = job_state(fid) if job_state else None
            if state is None or state not in self.TERMINAL_JOB_STATES:
                return no("already dispatched recently — cooling down")

        day_ago = now - 86400
        today = [h for h in history if float(h.get("at") or 0) > day_ago and h.get("dispatched")]
        if len(today) >= self.max_per_day:
            return no(f"daily cap reached ({self.max_per_day}) — refusing to keep spending")
        same = [h for h in today if h.get("component") == component]
        if len(same) >= self.max_per_component_per_day:
            return no(f"daily cap for {component} reached ({self.max_per_component_per_day})")

        why = "verified by an independent verdict" if verified else f"reproduced {seen}x"
        return DispatchDecision(fid, component, severity, seen, True,
                                f"{severity} on {component}, {why}")

    # ── the network ─────────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {"X-Momus-Operator": self.operator_token} if self.operator_token else {}

    def scan(self, target: str) -> dict[str, Any]:
        try:
            r = httpx.post(f"{self.momus_url}/scan", json={"target": target},
                           headers=self._headers(), timeout=300.0)
            return {"target": target, "status": r.status_code,
                    "body": r.json() if r.headers.get("content-type", "").startswith(
                        "application/json") else {}}
        except (httpx.HTTPError, ValueError) as exc:
            return {"target": target, "status": None, "error": type(exc).__name__}

    def findings(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            r = httpx.get(f"{self.momus_url}/findings", params={"limit": limit},
                          headers=self._headers(), timeout=60.0)
            r.raise_for_status()
            return (r.json() or {}).get("findings") or []
        except (httpx.HTTPError, ValueError):
            return []

    def dispatch(self, finding_id: str) -> dict[str, Any]:
        try:
            r = httpx.post(f"{self.momus_url}/remediate", json={"finding_id": finding_id},
                           headers=self._headers(), timeout=120.0)
            body = r.json() if r.headers.get("content-type", "").startswith(
                "application/json") else {}
            return {"status": r.status_code, "body": body}
        except (httpx.HTTPError, ValueError) as exc:
            return {"status": None, "error": type(exc).__name__}

    def report_skopos_findings(self) -> list[dict[str, Any]]:
        """Forward SKOPOS's own security findings to MOMUS. Off unless asked for.

        Never raises: SKOPOS's database being unreadable, or MOMUS being down, must not stop
        the loop from doing the job it was already doing before this existed.
        """
        # The IMPORT is inside the try, and that is the whole point of this shape.
        # `skopos.security` pulls in the SSH probe stack, which is not installed on a
        # host that only conducts; when the import was one line higher it raised before
        # the try and took the ENTIRE tick with it, and `run_forever` swallows that —
        # so the loop would have gone on sleeping and dispatching nothing at all, with
        # nothing in the journal to say why. Reporting is an errand of this pass; it
        # must never be able to stop the pass.
        try:
            from skopos.security.momus_push import (
                EXPORT_URL_ENV, is_enabled as push_enabled, push_now, push_remote,
            )

            if not push_enabled():
                return []
            # SKOPOS's findings normally live on ANOTHER machine — this host runs the
            # conductor, not the dashboard — so the default path is to pull what SKOPOS
            # published and post it to MOMUS over loopback. The local-database path
            # stays for a single-host install, where there is nothing to pull from.
            remote = bool((os.environ.get(EXPORT_URL_ENV) or "").strip())
            results = push_remote() if remote else push_now()
            return [r.to_dict() for r in results]
        except Exception as exc:  # noqa: BLE001
            logger.warning("SKOPOS findings were not reported to MOMUS: %s: %s",
                           type(exc).__name__, exc)
            return [{"pushed": False, "reason": f"push failed: {type(exc).__name__}"}]

    # ── one pass ────────────────────────────────────────────────────────────────
    def tick(self, *, scan: bool = True) -> dict[str, Any]:
        # Before the dispatch gate, and under a gate of its OWN. Handing MOMUS what SKOPOS's
        # fleet scan found is reporting, not initiative: it writes a finding into the auditor's
        # corpus and changes nothing in production. It also has to happen while the autopilot is
        # still switched off, because the dispatch rule below asks how many separate scans
        # rediscovered a defect — evidence that can only accumulate over time. Running it only
        # once someone flips AUTOPILOT_ENABLED would mean starting from zero sightings on the
        # day the loop is armed. Its own env switch, so "does SKOPOS report to MOMUS" and "may
        # the loop act unasked" stay two decisions rather than one.
        reported = self.report_skopos_findings()
        if not is_enabled():
            return {"enabled": False, "reason": f"{ENABLED_ENV} is not set — nothing dispatched",
                    "skopos_findings": reported}
        scans = [self.scan(t) for t in self.scan_rota] if scan else []
        now = time.time()
        # Before spending anything, get back what was never spent.
        raw = self.reconcile(self._history(), now=now)
        history = self.effective(raw)
        decisions: list[DispatchDecision] = []
        for finding in self.findings():
            decision = self.decide(finding, history=history, now=now,
                                   job_state=self._job_state)
            decisions.append(decision)
            if not decision.dispatch:
                continue
            result = self.dispatch(decision.finding_id)
            # 200 is not "dispatched". MOMUS answers 200 with dispatched=false when the ticket
            # routes to human governance — the security core never auto-remediates — and reading
            # the status code alone would record that as a success AND spend one of the day's
            # slots on a ticket nobody picked up.
            body = result.get("body") or {}
            ok = result.get("status") == 200 and body.get("dispatched") is not False
            entry = {"at": now, "finding_id": decision.finding_id,
                     "component": decision.component, "severity": decision.severity,
                     "seen_count": decision.seen_count, "reason": decision.reason,
                     "dispatched": ok, "http": result.get("status"),
                     "error": result.get("error") or (body.get("note") if not ok else None)}
            self._record(entry)
            # Appended to the in-memory view too, so the caps and cooldown bind WITHIN a tick as
            # well as across ticks — three eligible findings in one pass must not all go out
            # under a cap of two.
            history.append(entry)
        return {
            "enabled": True,
            "skopos_findings": reported,
            "scans": scans,
            "considered": len(decisions),
            "dispatched": [d.finding_id for d in decisions if d.dispatch],
            "held": [{"finding_id": d.finding_id, "reason": d.reason}
                     for d in decisions if not d.dispatch],
        }

    def run_forever(self) -> None:  # pragma: no cover - long-running loop
        interval = _float_env("AUTOPILOT_INTERVAL_S", 900)
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a dispatcher that dies must not take the host
                pass
            time.sleep(interval)


def main() -> None:  # pragma: no cover - process entrypoint
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("skopos.autopilot")
    pilot = Autopilot()
    log.info("autopilot starting: momus=%s enabled=%s interval=%ss",
             pilot.momus_url, is_enabled(), _float_env("AUTOPILOT_INTERVAL_S", 900))
    log.info("scan rota: %s", ", ".join(pilot.scan_rota) or "(none)")
    for component, rule in sorted(policy().items()):
        log.info("  dispatch %-8s severities=%s min_sightings=%s", component,
                 ",".join(rule.get("severities") or []), rule.get("min_sightings"))
    log.info("caps: %s/day global, %s/day per component, cooldown %.0fs",
             pilot.max_per_day, pilot.max_per_component_per_day, pilot.cooldown_s)
    if not is_enabled():
        log.warning("%s is not set — scans will NOT run and nothing will be dispatched",
                    ENABLED_ENV)
    if not pilot.operator_token:
        log.warning("MOMUS_OPERATOR_TOKEN is unset — MOMUS will refuse both scan and remediate")
    pilot.run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
