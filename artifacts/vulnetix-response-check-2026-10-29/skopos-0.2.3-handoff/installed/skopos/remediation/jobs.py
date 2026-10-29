"""Remediation jobs — the tracked state machine behind each MOMUS ticket.

    RECEIVED ─▶ FIXING ─▶ PUSHING ─▶ BUILDING ─▶ RETESTING ─▶ DEPLOYING ─▶ VERIFYING ─▶ DONE
                   │          │           │           │            │            │
                   └─ FAILED ◀┴───────────┴───────────┴────────────┴────────────┘
                                          (bounded retries loop back to FIXING)
    ESCALATED  (security-core findings, retries exhausted, or a rollback → human)

PUSHING and BUILDING are the steps whose absence made this loop unable to heal anything: without a
commit there was no reviewable artifact, and without a build there was no patched image, so
"deploying" recreated the container from the image already on the host and the gate had nothing new
to judge.

Persisted as JSONL so the SKOPOS dashboard can render a live board and a restart loses nothing.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from skopos.atomic_io import write_text_atomic


class JobState(str, Enum):
    RECEIVED = "received"
    FIXING = "fixing"          # AI-Factory is producing a patch
    PUSHING = "pushing"        # the conductor is committing the patch to a momus/fix-* branch
    BUILDING = "building"      # a node agent is building an image from that commit
    RETESTING = "retesting"    # MOMUS is re-running the probe on the patched build
    DEPLOYING = "deploying"    # a node agent is redeploying the service
    VERIFYING = "verifying"    # final in-place MOMUS retest after deploy
    DONE = "done"              # fixed + deployed + verified
    FAILED = "failed"          # gave up (bounded retries exhausted)
    ESCALATED = "escalated"    # routed to a human (security core, or repeated failure)


@dataclass
class Job:
    finding_id: str
    component: str
    probe: str
    severity: str
    route: str                 # "auto" | "human-governance"
    state: str = JobState.RECEIVED.value
    attempts: int = 0
    ticket: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    #: Structured facts about HOW a job went, for the health monitor to count.
    #: Deliberately not derived from ``history`` note text: a monitor that greps prose breaks the
    #: first time someone rewords a message, and a degradation signal that quietly stops counting is
    #: worse than one that was never built. See ``health.py`` for the vocabulary and what reads it.
    flags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def transition(self, state: JobState, note: str = "") -> None:
        self.state = state.value
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.history.append({"ts": self.updated_at, "state": state.value, "note": note})

    def flag(self, *flags: str) -> None:
        """Record a fact about this job, once. Idempotent so a retried attempt does not inflate the
        counters the circuit breaker reads."""
        for f in flags:
            if f and f not in self.flags:
                self.flags.append(f)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        # Tie-breaker for ``all()``. ``updated_at`` has one-second resolution, so several jobs
        # touched in the same second sort as equal — and a stable sort then hands them back in
        # INSERTION order, i.e. oldest first, from a method whose contract is newest first. Anything
        # walking that list to find the most recent state (the breaker's consecutive-failure streak)
        # reads it backwards during a burst, which is exactly when it matters.
        self._seq: dict[str, int] = {}
        self._next_seq = 0
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                self._jobs[d["finding_id"]] = Job(**d)
                self._next_seq += 1
                self._seq[d["finding_id"]] = self._next_seq
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    def _persist(self) -> None:
        # Rewrite the whole file (job count is small; keeps one line per current job state),
        # atomically: a crash mid-rewrite must not drop every job but the ones already written.
        write_text_atomic(
            self._path,
            "".join(json.dumps(job.to_dict(), ensure_ascii=False) + "\n" for job in self._jobs.values()),
        )

    def get(self, finding_id: str) -> Job | None:
        return self._jobs.get(finding_id)

    def upsert(self, job: Job) -> Job:
        self._jobs[job.finding_id] = job
        self._next_seq += 1
        self._seq[job.finding_id] = self._next_seq
        self._persist()
        return job

    def all(self) -> list[Job]:
        """Newest first — and actually newest first within a single second, see ``_seq``."""
        return sorted(self._jobs.values(),
                      key=lambda j: (j.updated_at, self._seq.get(j.finding_id, 0)), reverse=True)
