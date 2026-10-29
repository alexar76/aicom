"""The conductor — SKOPOS's orchestration of one remediation job.

It runs the state machine for a single MOMUS ticket: drive the Factory to patch, ask MOMUS to
re-test the patch (the gate), sign a DeployOrder embedding MOMUS's fixed-verdict, dispatch it to
the node agent on the target host, then ask MOMUS to re-test once more IN PLACE to confirm the live
container is clean. Bounded retries; anything touching the security core, or a job that can't be
fixed, escalates to a human.

The conductor signs DeployOrders with its OWN key and never redeploys anything itself — the
installed node agent does, and only after verifying the full chain. SKOPOS conducts; it does not
wield deploy authority directly.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from skopos.remediation.clients import FactoryClient, MomusClient
from skopos.remediation.deploy_order import (
    BuildOrder,
    DeployOrder,
    RollbackOrder,
    sign_build_order,
    sign_deploy_order,
    sign_rollback_order,
)
from skopos.remediation.git_push import GitPusher, provenance_record, valid_finding_id
from skopos.remediation.health import (
    FLAG_AGENT_NEVER_CLAIMED,
    FLAG_AGENT_REFUSED,
    FLAG_BREAKER_OPEN,
    FLAG_DEPLOYED,
    FLAG_DRY_RUN,
    FLAG_GATE_INCONCLUSIVE,
    FLAG_HEALTH_GATE_FAILED,
    FLAG_LIVE_REGRESSION,
    FLAG_REOPENED,
    FLAG_ROLLBACK_FAILED,
    FLAG_ROLLED_BACK,
)
from skopos.remediation.jobs import Job, JobState, JobStore

log = logging.getLogger(__name__)


def _utc_now() -> str:
    """Same shape as `Job.transition` writes, so a history read back is uniform."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

try:
    from oracle_core.signing import Signer
except Exception:  # pragma: no cover
    Signer = None  # type: ignore


@dataclass
class RemediationConfig:
    data_dir: str = "data/remediation"
    conductor_key_path: str = "data/remediation/conductor_key"
    momus_url: str = ""
    momus_pubkey: str = ""            # MOMUS's known scanner/verifier pubkey (for the agent's checks)
    # MOMUS's /retest is operator-gated in prod; the conductor must hold that token to use the gate.
    momus_operator_token: str = ""
    factory_url: str = ""
    dry_run: bool = True
    max_attempts: int = 3
    # Map a component/target → (node-agent url, host label). In dry-run the url may be blank.
    agent_hosts: dict[str, str] | None = None
    #: How long to wait for the node agent to claim an order and report on it. Must comfortably
    #: exceed the agent's poll interval plus its compose timeout plus its health wait — the
    #: conductor's re-test is meaningless until the agent has actually finished.
    deploy_result_timeout_s: float = 420.0
    component_hosts: dict[str, str] | None = None  # Operator routing to shared host agents.

    @classmethod
    def from_env(cls) -> "RemediationConfig":
        import json
        hosts_raw = os.environ.get("SKOPOS_AGENT_HOSTS", "").strip()
        agent_hosts = {}
        if hosts_raw:
            try:
                agent_hosts = json.loads(hosts_raw)
            except json.JSONDecodeError:
                agent_hosts = {}
        return cls(
            data_dir=os.environ.get("SKOPOS_REMEDIATION_DIR", "data/remediation"),
            conductor_key_path=os.environ.get("SKOPOS_CONDUCTOR_KEY_PATH", "data/remediation/conductor_key"),
            momus_url=os.environ.get("SKOPOS_MOMUS_URL", ""),
            momus_pubkey=os.environ.get("SKOPOS_MOMUS_PUBKEY", ""),
            momus_operator_token=os.environ.get("MOMUS_OPERATOR_TOKEN", ""),
            factory_url=os.environ.get("SKOPOS_FACTORY_URL", ""),
            dry_run=(os.environ.get("SKOPOS_REMEDIATION_DRY_RUN", "0").strip().lower()
                     not in ("0", "false", "no", "off")),
            max_attempts=int(os.environ.get("SKOPOS_REMEDIATION_MAX_ATTEMPTS", "3")),
            agent_hosts=agent_hosts,
            component_hosts=json.loads(os.environ.get("SKOPOS_COMPONENT_HOSTS", "{}")),
            deploy_result_timeout_s=float(
                os.environ.get("SKOPOS_DEPLOY_RESULT_TIMEOUT_S", "420") or 420),
        )


def _seen_after(ticket: dict[str, Any], when: str) -> bool:
    """Was the finding seen reproducing AFTER this job finished?

    Both timestamps are the same ISO-8601 UTC shape the whole loop uses, so a string comparison is
    the comparison — no parsing to get subtly wrong. Missing or malformed on either side means NO:
    an unknown age must never read as a regression, because the consequence is re-running a paid
    pipeline against something that was already fixed.
    """
    seen = str((ticket or {}).get("last_seen_at") or "").strip()
    done = str(when or "").strip()
    if not seen or not done or not seen.endswith("Z") or not done.endswith("Z"):
        return False
    return seen > done


class Conductor:
    def __init__(self, config: RemediationConfig | None = None):
        self.cfg = config or RemediationConfig.from_env()
        # How many times, and how long apart, to re-ask a gate that could not reach the candidate.
        # Six times five seconds is half a minute of startup slack — generous for a container the
        # agent has already reported as running, and bounded so a target that is genuinely gone
        # still escalates promptly.
        self.gate_retries = int(os.environ.get("SKOPOS_GATE_RETRIES", "6") or 6)
        self.gate_retry_delay_s = float(os.environ.get("SKOPOS_GATE_RETRY_DELAY_S", "5") or 5)
        os.makedirs(self.cfg.data_dir, exist_ok=True)
        self.store = JobStore(os.path.join(self.cfg.data_dir, "jobs.jsonl"))
        self._signer = Signer(self.cfg.conductor_key_path) if Signer else None
        self.momus = MomusClient(self.cfg.momus_url, operator_token=self.cfg.momus_operator_token)
        self.factory = FactoryClient(self.cfg.factory_url, dry_run=self.cfg.dry_run)
        # A2A wire observer — SKOPOS is the fleet's observability satellite, so agent↔agent
        # delegations are recorded here and surfaced in the dashboard.
        from skopos.remediation.a2a_observer import A2AObserver
        self.observer = A2AObserver(self.cfg.data_dir)
        self._locks: dict[str, asyncio.Lock] = {}   # one live remediation per finding
        # Published deploy orders. The fleet agents are PUSH-ONLY (no inbound port), so they poll
        # this queue instead of being called — see order_queue.py for why pull is the right shape.
        from skopos.remediation.order_queue import OrderQueue
        self.orders = OrderQueue(os.path.join(self.cfg.data_dir, "deploy_orders.jsonl"))
        # How a terminal outcome reaches the dashboard: a summary pushed over the fleet's existing
        # signed node-report channel. Opt-in, best-effort, and never able to change a job's outcome.
        from skopos.remediation.report_push import ReportPusher
        self.reporter = ReportPusher(data_dir=self.cfg.data_dir)
        # Health + the breaker that reads it. The breaker sits in the deploy path rather than in a
        # dashboard: a loop that ships bad patches has to be stopped, not merely graphed.
        from skopos.remediation.health import LoopHealth, breaker_from_env
        self.breaker = breaker_from_env(self.store, self.orders, data_dir=self.cfg.data_dir)
        self.health: LoopHealth = self.breaker.health
        # The git hand. A patch has to become a commit before anything can build it, and the branch
        # is both the transport to the builder and the artifact a human reviews.
        self.git = GitPusher()

    @property
    def conductor_pubkey(self) -> str:
        return self._signer.public_key_b64 if self._signer else ""

    def _host_for(self, component: str) -> str:
        return str((self.cfg.component_hosts or {}).get(component) or component)

    def _agent_url_for(self, component: str) -> str:
        return (self.cfg.agent_hosts or {}).get(component, "")

    async def _retest_observed(self, finding_id: str, phase: str, *,
                               candidate: bool = False) -> dict[str, Any]:
        """Ask MOMUS to re-test, and record the A2A round trip so an operator can watch it.

        ``candidate=True`` is the PRE-promotion gate: MOMUS probes the freshly built candidate
        container, so the verdict is about the image about to ship. Anything else is the live
        service."""
        import time as _t
        t0 = _t.monotonic()
        verdict = await self.momus.retest(finding_id, candidate=candidate)
        elapsed = int((_t.monotonic() - t0) * 1000)
        fixed = bool(verdict.get("fixed"))
        self.observer.record_outbound(
            peer="momus", skill="retest", finding_id=finding_id,
            state="completed" if verdict.get("outcome") != "inconclusive" else "failed",
            ok=verdict.get("outcome") != "inconclusive", latency_ms=elapsed,
            summary=f"{phase}: fixed={fixed} outcome={verdict.get('outcome')} "
                    f"gated={verdict.get('gated', 'live')}",
            artifacts=["fix-verdict"] if verdict.get("signature") else [])
        return verdict

    def _verify_ticket(self, ticket: dict[str, Any]) -> tuple[bool, str]:
        """Check the ticket's Blame attestation against MOMUS's KNOWN key.

        Without this the conductor believed whatever a caller posted. A peer could claim any
        finding_id and component and get a fix + redeploy driven on its behalf."""
        if not valid_finding_id(ticket.get("finding_id")):
            return False, "finding_id contains unsafe path or git-ref characters"
        pub = (self.cfg.momus_pubkey or "").strip()
        blame = ticket.get("blame") or {}
        if not pub:
            # Fail closed in prod: no key to check against means the ticket is unverifiable.
            if not self.cfg.dry_run:
                return False, ("SKOPOS_MOMUS_PUBKEY is unset — cannot verify the ticket's Blame "
                               "attestation; refusing to remediate on an unverified claim")
            return True, "dry-run: ticket signature not verified (no SKOPOS_MOMUS_PUBKEY)"
        sig = blame.get("signature") or {}
        if not sig.get("value"):
            return False, "ticket carries no signed Blame attestation"
        body = {k: v for k, v in blame.items() if k != "signature"}
        try:
            from momus.findings import verify_document_signature
            if not verify_document_signature(body, sig, pub):
                return False, "Blame signature does not verify under the known MOMUS key"
        except Exception as exc:  # noqa: BLE001
            return False, f"Blame verification error: {type(exc).__name__}"
        # The Blame must be about the SAME finding and component the ticket claims.
        if blame.get("finding_id") != ticket.get("finding_id"):
            return False, "Blame finding_id disagrees with the ticket"
        if blame.get("component") != ticket.get("component"):
            return False, "Blame component disagrees with the ticket"
        return True, "Blame verified under the known MOMUS key"

    async def handle_ticket(self, ticket: dict[str, Any]) -> Job:  # type: ignore[name-defined]
        """Entry point: an A2A 'remediate' task from MOMUS arrives here."""
        fid = ticket.get("finding_id", "")
        component = ticket.get("component", "")
        # Re-DERIVE the escalation route from the component, server-side. Reading `route` off the
        # ticket let a caller label a security-core finding as ordinary and walk it straight into
        # the automated fix→deploy path — the exact lever the escalation rule exists to remove.
        from momus.engine.remediation import escalation_for
        route = escalation_for(component, ticket.get("target_kind", ""))
        job = self.store.get(fid) or Job(
            finding_id=fid, component=component, probe=ticket.get("probe", ""),
            severity=ticket.get("severity", ""), route=route, ticket=ticket)
        job.route = route  # never let a stored/claimed value override the derived one

        ok, why = self._verify_ticket(ticket)
        if not ok:
            return await self._finish(job, JobState.ESCALATED, f"unverified ticket: {why}")

        # Security core → never auto-remediate; hand to a human.
        if route == "human-governance":
            return await self._finish(job, JobState.ESCALATED,
                                      f"security-core finding ({component}): routed to human "
                                      f"governance + external verifier, never auto-remediated")
        # One live job per finding: N concurrent posts used to spawn N loops mutating one Job, each
        # able to reach DEPLOYING and get an order signed while `attempts` was incremented by all.
        if job.state in (JobState.FIXING.value, JobState.RETESTING.value,
                         JobState.DEPLOYING.value, JobState.VERIFYING.value):
            return job
        # A NEW ticket for a job that already reached a terminal state re-opens it with a fresh
        # attempt budget. Without this a single transient failure (a patch that had not landed yet,
        # an unauthorised gate call) left the job ESCALATED for ever and the finding could never be
        # remediated even after the fix shipped — the same "temporary problem, permanent damage"
        # shape as consuming a dedup identity on an unsettled HELD payout. DONE is left alone: a
        # finished remediation should not be redone by a duplicate ticket.
        if job.state in (JobState.FAILED.value, JobState.ESCALATED.value):
            job.attempts = 0
            # A finding coming back is the whack-a-mole signal: the loop "closed" something that was
            # not closed. Counted so a rising reopen count is visible even while every individual
            # job looks like a success.
            job.flag(FLAG_REOPENED)
            job.transition(JobState.RECEIVED,
                           "re-opened by a new remediation ticket — the world may have changed "
                           "(e.g. the patch has since landed); attempt budget reset")
        elif job.state == JobState.DONE.value:
            # A DONE that was reached in DRY-RUN deployed nothing and verified nothing — it only
            # proved the plumbing. Treating it as a finished remediation silently swallowed the FIRST
            # live ticket after dry-run was switched off: the conductor accepted the A2A task, found
            # a DONE job, and returned it without making a single outbound call. So a dry-run DONE is
            # re-openable once the conductor is live; a DONE that really shipped is not.
            # The test is STRUCTURAL: did this job ever actually deploy anything? `FLAG_DEPLOYED` is
            # set only after a node agent reports a real deploy, so its absence means the completion
            # shipped nothing — whether because dry-run was on, or because the job predates flags
            # entirely. Keying on FLAG_DRY_RUN alone was not enough: the stale job that swallowed the
            # first live ticket had been closed by an OLDER build that never set that flag, so the
            # fix helped only future runs and left the one job that mattered stuck.
            shipped = FLAG_DEPLOYED in job.flags
            # A shipped remediation is not redone by a DUPLICATE ticket — but it must be redone by a
            # REGRESSION, and the two look identical from here unless something dates them. The
            # ticket carries when the corpus last saw the finding reproduce; if that is after this
            # job finished, the fix shipped and the bug came back. A loop that cannot re-heal that
            # is not self-healing, and the reopen counter is exactly where a rising regression rate
            # should become visible.
            if shipped and _seen_after(ticket, job.updated_at):
                job.attempts = 0
                job.flag(FLAG_REOPENED)
                job.flags = [f for f in job.flags if f != FLAG_DEPLOYED]
                job.transition(JobState.RECEIVED,
                               "re-opened: this remediation shipped, and the finding has been seen "
                               "reproducing since — a regression, not a duplicate ticket")
            elif not shipped and not self.cfg.dry_run:
                job.attempts = 0
                job.flags = [f for f in job.flags if f != FLAG_DRY_RUN]
                job.transition(JobState.RECEIVED,
                               "re-opened: the previous completion never deployed anything (dry run, "
                               "or a build that predates deploy flags) and this conductor is now live")
            else:
                return job
        async with self._lock_for(fid):
            return await self._run(job)

    def _lock_for(self, finding_id: str):
        lock = self._locks.get(finding_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[finding_id] = lock
        return lock

    async def _finish(self, job: Job, state: JobState, note: str) -> Job:
        """Reach a terminal state: record it, persist it, then tell the dashboard about it.

        The push is deliberately the LAST thing that happens and cannot change the outcome — a
        SKOPOS outage, a 401 or a seq conflict is logged and swallowed, so a remediation that worked
        is never recorded as failed because a dashboard was down."""
        job.transition(state, note)
        self.store.upsert(job)
        # The signed chain lands on the fix branch before the dashboard push, so the audit trail
        # exists in git even if SKOPOS is down. Both are best-effort and neither can change `state`.
        await self._record_provenance(job)
        await self._merge_if_enabled(job)
        await self.reporter.push_job_async(job, conductor_pubkey=self.conductor_pubkey,
                                           queued=self._queued_order_for(job))
        return job

    async def _merge_if_enabled(self, job: Job) -> None:  # type: ignore[name-defined]
        """EXPERIMENTAL: land a verified fix on the default branch, unattended.

        Deliberately narrow. It runs only for a job that reached DONE — which means the patch
        built, the component's own tests passed, MOMUS gated the candidate, both signatures
        verified, the node agent deployed it, and MOMUS confirmed the finding gone IN PLACE.
        Anything short of that leaves the branch for a person, which is what the loop did
        before this existed and what it does again the moment the flag is unset.

        The provenance commit is pushed FIRST (above), so whatever lands on the default branch
        already carries its signed chain. Best-effort and after the fact: a remediation that
        worked must not be recorded as failed because a merge was refused — and on this
        deployment it is expected to be refused, because the conductor holds a deploy key and
        the repository's default branch does not admit deploy keys.
        """
        if job.state != JobState.DONE.value:
            return
        branch = str((job.result or {}).get("fix_branch") or "")
        if not branch or self.cfg.dry_run:
            return
        try:
            result = await asyncio.to_thread(
                self.git.merge_to_main, finding_id=job.finding_id, branch=branch,
                component=job.component,
                summary=str((job.result or {}).get("fix", {}).get("summary") or ""))
        except Exception as exc:  # noqa: BLE001 — a merge must not change a job's outcome
            log.warning("auto-merge raised for %s: %s", job.finding_id, type(exc).__name__)
            return
        job.result["auto_merge"] = result.to_dict()
        if result.ok:
            log.info("auto-merge: %s landed on %s as %s (revert with `git revert -m 1 %s`)",
                     branch, result.branch, result.commit_sha[:12], result.commit_sha[:12])
            job.history.append({"ts": _utc_now(), "state": job.state,
                                "note": f"merged into {result.branch} as {result.commit_sha[:12]} "
                                        f"— revert with `git revert -m 1 {result.commit_sha[:12]}`"})
        else:
            # Not a failure of the repair. Said plainly so nobody reads a refused merge as a
            # broken fix, and so the branch-waits-for-review state is visible rather than assumed.
            log.info("auto-merge did not land %s: %s", branch, result.error)
            job.history.append({"ts": _utc_now(), "state": job.state,
                                "note": f"deployed and verified; branch {branch} NOT merged — "
                                        f"{result.error[:160]}"})
        self.store.upsert(job)

    def _queued_order_for(self, job: Job) -> dict[str, Any] | None:
        """The signed order, its claim, and what the node agent reported back.

        None of that is on the Job — the Job keeps only the order id — so the summary would otherwise
        stop at 'MOMUS says fixed' and never say whether the deploy actually happened."""
        order_id = str((job.result or {}).get("deploy_order_id") or "")
        queued = self.orders.get(order_id) if order_id else None
        return queued.to_dict() if queued else None

    async def _push_and_build(self, job: Job, patch: dict[str, Any]  # type: ignore[name-defined]
                              ) -> tuple[dict[str, Any] | None, str]:
        """Diff → commit on a fix branch → a real image built by the fleet.

        Returns ``(None, note)`` for something a retry cannot fix (escalate), or
        ``({"built": False}, note)`` for a build that failed and is worth another attempt.

        The order of these two steps is forced: the builder needs a commit, so the push comes first.
        That also means the branch exists before anything is built — which is the property that makes
        the whole thing reviewable, because a human can read the patch whether or not it ever ships.
        """
        diff = str(patch.get("diff") or "")
        summary = str(patch.get("summary") or "")

        # ── PUSHING ────────────────────────────────────────────────────────
        # Deliberately not naming the branch here: the name is chosen against a freshly fetched
        # mirror inside push_patch, because `attempts` resets on every re-open and cannot be
        # unique on its own. The BUILDING transition below reports the branch that was really used.
        job.transition(JobState.PUSHING, "committing the patch to a new fix branch")
        self.store.upsert(job)
        push = await asyncio.to_thread(
            # `attempt` so a re-opened job pushes to a NEW branch: the previous attempt still
            # occupies the unsuffixed one, and forcing over it is refused by design.
            self.git.push_patch, attempt=job.attempts, finding_id=job.finding_id,
            component=job.component,
            diff=diff, summary=summary)
        job.result["push"] = push.to_dict()
        if not push.ok:
            # An unpushable patch is not a patch the Factory should be asked to rewrite: the causes
            # are a missing credential, a protected branch, a diff that does not apply, or a diverged
            # branch — all of them an operator's, none of them fixed by another LLM round.
            return None, f"could not push the fix branch: {push.error}"
        job.result["fix_branch"] = push.branch
        job.result["fix_commit"] = push.commit_sha
        self.observer.record_outbound(
            peer="gitea", skill="push-fix", finding_id=job.finding_id, state="completed",
            summary=f"{push.branch} @ {push.commit_sha[:12]}", artifacts=["fix-branch"])

        # ── BUILDING ───────────────────────────────────────────────────────
        job.transition(JobState.BUILDING,
                       f"asking the node agent to build {push.commit_sha[:12]} from {push.branch}")
        self.store.upsert(job)
        order = BuildOrder(finding_id=job.finding_id, service=job.component, host=self._host_for(job.component),
                           commit_sha=push.commit_sha, branch=push.branch)
        if self._signer:
            sign_build_order(order, self._signer)
        self.orders.publish(host=self._host_for(job.component), service=job.component,
                            finding_id=job.finding_id, order=order.to_dict())
        self.observer.record_outbound(
            peer=f"agent:{job.component}", skill="build-order", finding_id=job.finding_id,
            state="working", summary=f"build {push.commit_sha[:12]}", artifacts=["build-order"])
        result = await self.orders.await_result(
            order.order_id, timeout_s=max(self.cfg.deploy_result_timeout_s, 14400 if job.component == "warden" else 0))
        job.result["build_order_id"] = order.order_id
        job.result["build"] = result

        if result is None:
            return None, ("the node agent never claimed the build order (agent not installed, "
                          "stopped, or the wrong host label) — nothing was built")
        if result.get("refused"):
            return None, f"the node agent refused the build: {result.get('reason')}"
        if not result.get("built"):
            # A patch that fails the component's own suite is a DIFFERENT failure from a build
            # that would not compile, and the next attempt needs to be told which. The suite's
            # output goes back verbatim: "1 failed: test_clock_rejects_future_stamps" is an
            # instruction, where "the build failed" is a shrug.
            tests = result.get("tests") or {}
            if tests.get("blocked"):
                detail = (tests.get("output") or tests.get("stderr") or "").strip()
                note = f"the patch failed {job.component}'s own tests: {tests.get('summary') or ''}"
                if detail:
                    note += f"\n{detail[-1200:]}"
                return {"built": False, "tests": tests}, note
            return {"built": False}, f"the build failed on the host: {result.get('reason')}"

        # Built, and the suite was not blocking. Say what the suite did anyway — a gate whose
        # verdict is never written down is a gate nobody can tell apart from an absent one.
        tests = result.get("tests") or {}
        if tests.get("ran") and not tests.get("passed"):
            return result, ("built — but the component's own tests FAILED and the gate is "
                            f"advisory on this host: {tests.get('summary') or ''}")
        if tests.get("ran"):
            return result, f"built, {job.component}'s own tests pass"
        return result, f"built (no test suite declared for {job.component})"

    async def _record_provenance(self, job: Job) -> None:  # type: ignore[name-defined]
        """Push the signed chain onto the fix branch, once the job has reached a terminal state.

        Best-effort and last, like the dashboard push: a remediation that worked must never be
        recorded as failed because git was unreachable. Written for ESCALATED jobs too — arguably
        especially for those, since a human is about to need exactly this record."""
        branch = str((job.result or {}).get("fix_branch") or "")
        if not branch or self.cfg.dry_run:
            return
        try:
            record = provenance_record(
                job=job, gate_verdict=(job.result or {}).get("gate_verdict") or {},
                deploy_order=(self._queued_order_for(job) or {}).get("order") or {},
                agent_result=(job.result or {}).get("agent_result"),
                conductor_pubkey=self.conductor_pubkey)
            await asyncio.to_thread(self.git.push_provenance, finding_id=job.finding_id,
                                    component=job.component, record=record)
        except Exception:  # noqa: BLE001 — provenance must not change a job's outcome
            pass

    @staticmethod
    def _classify_agent_result(result: dict[str, Any] | None) -> tuple[str, str, list[str]]:
        """What the agent's report means: ("proceed" | "retry" | "escalate", note, flags).

        Kept as a pure function because these are the cases that decide whether a live host is left
        broken, and each one wants a different answer. Collapsing them into "deployed or not" is what
        produced the old "regressed after deploy — will retry" path: a single branch that retried a
        patch three times whatever had actually gone wrong."""
        if result is None:
            # No agent picked the order up. Not a verdict on the patch — a Factory retry cannot
            # install an agent, fix a host label or restart a stopped one.
            return ("escalate",
                    "the node agent never claimed the deploy order (agent not installed, stopped, "
                    "wrong host label, or the order expired) — nothing was deployed",
                    [FLAG_AGENT_NEVER_CLAIMED])
        if result.get("refused"):
            return ("escalate",
                    f"the node agent verified the chain and REFUSED: {result.get('reason')}",
                    [FLAG_AGENT_REFUSED])
        if result.get("health_gate_failed"):
            # The agent already undid this itself — it does not wait for permission to stop a
            # crash-loop it can see locally. Retrying the same patch would just re-break the host.
            rollback = result.get("rollback") or {}
            if rollback.get("rolled_back"):
                # FLAG_DEPLOYED too: this patch DID reach the host. Leaving it off made the
                # rollback rate divide by zero-deploys and report None for its worst case.
                flags = [FLAG_DEPLOYED, FLAG_HEALTH_GATE_FAILED, FLAG_ROLLED_BACK]
                note = (f"patch deployed but the service did not come up "
                        f"({result.get('health')}); the agent ROLLED BACK to "
                        f"{str(rollback.get('restored_image'))[:19]}…")
                if rollback.get("needs_human"):
                    flags.append(FLAG_ROLLBACK_FAILED)
                    note += " — and the restored image is NOT healthy either: the host needs a human"
                return ("escalate", note, flags)
            return ("escalate",
                    f"patch deployed, the service did not come up ({result.get('health')}), AND the "
                    f"rollback failed ({rollback.get('reason')}) — the host is left broken and needs "
                    f"a human NOW",
                    [FLAG_DEPLOYED, FLAG_HEALTH_GATE_FAILED, FLAG_ROLLBACK_FAILED])
        if not result.get("deployed"):
            # The redeploy command itself failed, which usually means nothing was recreated and the
            # old container is still serving. That is the one genuinely retryable shape.
            return ("retry",
                    f"the redeploy command failed on the host (rc={result.get('returncode')}): "
                    f"{str(result.get('stderr') or result.get('error') or '')[:200]}",
                    [])
        return ("proceed", "the node agent reports the service redeployed and healthy", [])

    async def _roll_back(self, job: Job, order: DeployOrder, *, reason: str) -> Job:  # type: ignore[name-defined]
        """Undo a deploy the agent completed, then hand the job to a human.

        The rollback order carries no image: it names ``order.order_id``, and the agent restores what
        IT recorded as running before that deploy. So this cannot be used to ship anything, only to
        return a host to a state it was demonstrably in."""
        undo = RollbackOrder(finding_id=job.finding_id, service=job.component,
                             host=self._host_for(job.component), rollback_of=order.order_id, reason=reason[:500])
        if self._signer:
            sign_rollback_order(undo, self._signer)
        self.orders.publish(host=self._host_for(job.component), service=job.component,
                            finding_id=job.finding_id, order=undo.to_dict())
        self.observer.record_outbound(
            peer=f"agent:{job.component}", skill="rollback-order", finding_id=job.finding_id,
            state="working", summary=f"rollback of {order.order_id}: {reason[:80]}",
            artifacts=["rollback-order"])
        result = await self.orders.await_result(
            undo.order_id, timeout_s=self.cfg.deploy_result_timeout_s)
        job.result["rollback_order_id"] = undo.order_id
        job.result["rollback_result"] = result

        if result is None:
            job.flag(FLAG_ROLLBACK_FAILED)
            return await self._finish(job, JobState.ESCALATED,
                                      f"{reason} — AND the rollback order was never claimed by the "
                                      f"node agent, so the bad build is still live. Human needed NOW.")
        if not result.get("rolled_back"):
            job.flag(FLAG_ROLLBACK_FAILED)
            return await self._finish(job, JobState.ESCALATED,
                                      f"{reason} — AND the rollback FAILED "
                                      f"({result.get('reason')}). The bad build is still live. "
                                      f"Human needed NOW.")
        job.flag(FLAG_ROLLED_BACK)
        note = f"{reason} — rolled back to {str(result.get('restored_image'))[:19]}…"
        if result.get("needs_human"):
            job.flag(FLAG_ROLLBACK_FAILED)
            note += "; the restored image is NOT healthy either — the host needs a human"
        return await self._finish(job, JobState.ESCALATED, note)

    async def _run(self, job: Job) -> Job:  # type: ignore[name-defined]
        # Carried between attempts so a retry is a retry and not a repeat. At temperature 0 the
        # same prompt returns the same patch: a live run burned all three attempts on the
        # identical rejected diff in eight seconds, each refused for the same reason, and
        # escalated having learned nothing it was already told.
        previous_failure = ""
        while job.attempts < self.cfg.max_attempts:
            job.attempts += 1

            # 1. FIXING — the AI-Factory writes a patch.
            job.transition(JobState.FIXING, f"attempt {job.attempts}: requesting fix from AI-Factory")
            self.store.upsert(job)
            fix = await self.factory.request_fix(job.ticket, previous_failure=previous_failure,
                                                 attempt=job.attempts)
            if not fix.get("ok"):
                # A misconfigured Factory is not a patch that failed — retrying it three times and
                # then blaming the fix is the same mistake the inconclusive gate branch fixes above.
                if fix.get("config_error"):
                    return await self._finish(job, JobState.ESCALATED,
                                              f"cannot request a fix: {fix.get('error')}")
                previous_failure = str(fix.get("error") or "")
                job.transition(JobState.FAILED, f"factory error: {fix.get('error')}")
                self.store.upsert(job)
                continue
            patch = fix.get("patch") or {}

            # 2. PUSHING + BUILDING — turn the patch into a real, runnable image.
            #
            # This is the pair of steps whose absence made the loop unable to heal anything. The
            # Factory produces a DIFF, not an image; without a commit there was no reviewable
            # artifact, and without a build there was nothing new to ship — so the old code took the
            # Factory's *claimed* image name straight into a DeployOrder, and the agent recreated the
            # container from whatever was already on the host. `image` was never even read.
            #
            # `image` from here on is a digest THIS FLEET built from a commit in the repo, or the job
            # does not deploy at all.
            image = ""
            if self.cfg.dry_run:
                image = str(patch.get("image") or "")   # dry-run keeps its synthetic value
            else:
                built, note = await self._push_and_build(job, patch)
                if built is None:
                    return await self._finish(job, JobState.ESCALATED, note)
                if not built.get("built"):
                    job.transition(JobState.FAILED, note)
                    self.store.upsert(job)
                    continue
                image = str(built.get("image_digest") or "")
                if not built.get("candidate_running"):
                    # A candidate that will not start is a BAD PATCH — the one thing the next
                    # attempt exists to fix — so it is a failed attempt, not the end of the
                    # ladder. Ending here spent a job on the first patch that crashed at import
                    # and never let the later, stronger rungs try at all: measured, a run died
                    # on `ValueError: An Ed25519 private key is 32 bytes long` at attempt 2 and
                    # the council at attempt 3 was never asked.
                    #
                    # The container's own last words are the most useful thing we have, and the
                    # gate never sees them because there is nothing to probe.
                    detail = str(built.get("candidate_error") or built.get("candidate") or "")
                    previous_failure = (
                        "your previous patch built, but the container did not start — it "
                        f"failed at import or startup: {detail[:600] or 'no output captured'}. "
                        "Fix that first; a patch that cannot start cannot be tested.")
                    job.transition(
                        JobState.FAILED,
                        f"built {image[:19]}… but the candidate container did not start "
                        f"({built.get('candidate')}) — treating it as a failed attempt")
                    self.store.upsert(job)
                    continue

            # 3. RETESTING — MOMUS re-runs the exact probe on the CANDIDATE build (the real gate).
            #    Pre-promotion and against the new image, so a "fixed" verdict is about the thing
            #    that is about to ship rather than about the unpatched service still running.
            job.transition(JobState.RETESTING,
                           "asking MOMUS to gate the candidate build (pre-promotion)"
                           if not self.cfg.dry_run else
                           "asking MOMUS to re-test the patched build")
            self.store.upsert(job)
            verdict = await self._retest_observed(job.finding_id, "gate",
                                                  candidate=not self.cfg.dry_run)
            # A candidate that is RUNNING is not yet a candidate that is LISTENING. The agent
            # reports the build the moment the container is up, and the gate then asked a service
            # 21 seconds into its own startup and got "target unreachable" — escalating a job whose
            # patch was never examined. Retry the gate itself for a bounded window before believing
            # the target is really gone: an inconclusive verdict is explicitly not a verdict, so it
            # is the one outcome worth asking again.
            for _ in range(self.gate_retries):
                if str(verdict.get("outcome") or "") != "inconclusive":
                    break
                if "unreachable" not in str(verdict.get("detail") or "").lower():
                    break  # refusing or unresolvable — asking again will not change it
                await asyncio.sleep(self.gate_retry_delay_s)
                job.transition(JobState.RETESTING,
                               "candidate not answering yet — asking the gate again")
                self.store.upsert(job)
                verdict = await self._retest_observed(job.finding_id, "gate",
                                                      candidate=not self.cfg.dry_run)
            # An INCONCLUSIVE gate is not a verdict on the patch — MOMUS is unreachable, refusing, or
            # cannot resolve the finding. Another Factory attempt cannot fix a gate that will not
            # run, and looping would burn the budget and then escalate blaming the patch. So stop
            # here and escalate naming the real cause, which is an operator's to clear.
            if str(verdict.get("outcome") or "") == "inconclusive":
                job.flag(FLAG_GATE_INCONCLUSIVE)
                return await self._finish(job, JobState.ESCALATED,
                                          f"deploy gate could not run — not a verdict on the fix: "
                                          f"{verdict.get('detail', '')}")
            if not verdict.get("fixed"):
                # THE most informative failure there is, and it was the one the next attempt
                # never heard: `previous_failure` was set only when the FACTORY refused, so a
                # patch that built, deployed to a candidate and was rejected by the probe fed
                # nothing forward. The next attempt then got a byte-identical prompt — and at
                # temperature 0, through a response cache, a byte-identical patch. Measured:
                # attempt 3 was published three seconds after attempt 2 failed.
                previous_failure = (
                    "your previous patch applied, built and started, and the probe STILL "
                    f"reproduces the finding: {verdict.get('detail', '') or 'no detail given'}. "
                    "Whatever you changed did not address it — change your approach, not the "
                    "wording."
                )
                job.transition(JobState.FAILED,
                               f"retest not fixed ({verdict.get('outcome')}): {verdict.get('detail','')}")
                self.store.upsert(job)
                continue  # loop back to FIXING for another attempt

            # 3. DEPLOYING — sign a DeployOrder embedding MOMUS's fixed-verdict; the node agent ships it.
            # First, the last free moment to decline: the circuit breaker. A signed order is an
            # instruction a host will carry out, so the check belongs before the signature, not
            # after it. A breaker refusal is never "the patch was bad" — it is "the loop is not
            # currently trusted to ship", which is a human's to clear, so it escalates rather than
            # burning another Factory attempt.
            may_deploy, breaker_reason = self.breaker.check(job.component)
            if not may_deploy:
                job.flag(FLAG_BREAKER_OPEN)
                return await self._finish(job, JobState.ESCALATED,
                                          f"deploy withheld by the remediation circuit breaker: "
                                          f"{breaker_reason}")
            job.transition(JobState.DEPLOYING, "MOMUS confirms fixed; signing deploy order for the node agent")
            self.store.upsert(job)
            order = DeployOrder(finding_id=job.finding_id, service=job.component,
                                host=self._host_for(job.component), image=image, momus_verdict=verdict)
            if self._signer:
                sign_deploy_order(order, self._signer)
            # PUBLISH the order; the addressed agent claims it on its next poll and verifies the
            # chain locally before touching anything. The conductor never executes a deploy itself.
            # Publishing cannot be "rejected" — the agent's verdict arrives later, on
            # /agent/v1/result. The old `if not dispatch["accepted"]` here tested a literal
            # True and could never fire; the real rejection path is the agent's result.
            queued = self.orders.publish(host=self._host_for(job.component), service=job.component,
                                         finding_id=job.finding_id, order=order.to_dict())
            dispatch = {"accepted": True, "order_id": queued.order_id, "queued": True,
                        "note": f"signed order published for host '{self._host_for(job.component)}'; the node agent "
                                f"will claim it on its next poll and verify the chain locally"}

            # 4. WAIT for the hand to actually move. The agent polls on an interval, so re-testing
            #    "after the deploy" the instant an order is published tested the OLD container: every
            #    job outside dry-run would read as a post-deploy regression, burn its attempts and
            #    escalate — while judging a patch that had not been applied yet.
            job.transition(JobState.DEPLOYING,
                           f"order {order.order_id} published; waiting for the node agent to "
                           f"execute it (up to {int(self.cfg.deploy_result_timeout_s)}s)")
            self.store.upsert(job)
            agent_result = await self.orders.await_result(
                order.order_id, timeout_s=0 if self.cfg.dry_run else self.cfg.deploy_result_timeout_s)
            # UPDATE, never replace. A wholesale assignment here wiped everything `_push_and_build`
            # had recorded — `fix_branch`, `fix_commit`, the build order and its result — which meant
            # `_record_provenance` found no branch and silently skipped the signed sidecar. The first
            # real heal produced a correct patch, a correct branch and a correct deploy, and then no
            # audit record on the branch at all, because of one `=` that should have been an update.
            job.result.update({"fix": fix, "gate_verdict": verdict, "deploy": dispatch,
                               "deploy_order_id": order.order_id, "agent_result": agent_result})

            if self.cfg.dry_run:
                # Nothing was applied anywhere, so there is nothing to verify in place. Say that,
                # rather than dressing a dry run up as a confirmed live fix. FLAGGED, because the
                # duplicate-ticket guard below has to be able to tell this DONE apart from one that
                # actually fixed something.
                job.flag(FLAG_DRY_RUN)
                return await self._finish(job, JobState.DONE,
                                          "dry run: chain complete (fix → gate → signed order); "
                                          "nothing was deployed and nothing verified in place")
            decision, note, flags = self._classify_agent_result(agent_result)
            job.flag(*flags)
            if decision == "escalate":
                return await self._finish(job, JobState.ESCALATED, note)
            if decision == "retry":
                job.transition(JobState.FAILED, note)
                self.store.upsert(job)
                continue

            # 5. VERIFYING — a final IN-PLACE MOMUS retest confirms the LIVE container is clean.
            job.flag(FLAG_DEPLOYED)
            job.transition(JobState.VERIFYING, "deploy reported by the agent; final in-place MOMUS retest")
            self.store.upsert(job)
            post = await self._retest_observed(job.finding_id, "post-deploy")
            job.result["post_deploy_verdict"] = post
            if post.get("fixed"):
                return await self._finish(job, JobState.DONE, "fixed, deployed and verified in place")

            # The gate said fixed and the container is healthy, yet the finding still reproduces
            # against the live service. That is a disagreement between the gate and reality, not a
            # bad patch to re-attempt: another Factory round would be judged by the same gate that
            # was just wrong. Undo it and hand it over.
            job.flag(FLAG_LIVE_REGRESSION)
            return await self._roll_back(
                job, order,
                reason=f"live service still reproduces the finding after deploy "
                       f"({post.get('outcome')}): {str(post.get('detail', ''))[:200]}")

        # Retries exhausted.
        return await self._finish(job, JobState.ESCALATED,
                                  f"{job.attempts} attempts exhausted — escalated to a human")
