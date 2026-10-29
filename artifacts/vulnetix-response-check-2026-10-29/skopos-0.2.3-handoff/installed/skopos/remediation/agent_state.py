"""The node agent's LOCAL memory of what it deployed — the thing that makes rollback possible.

A deploy that cannot be undone is not a deploy, it is a one-way door. The remediation loop shipped
without one: the conductor published an order, the agent ran ``docker compose up``, and if the patch
turned out to be worse than the bug there was nothing on the host that remembered what had been
running a minute earlier.

This module is that memory, and *where* it lives is the whole design:

**The agent records it, not the conductor.** The rollback target is the image digest the agent read
off the running container with its own eyes, written to its own disk. A RollbackOrder therefore
carries no image at all — it names a prior order, and the agent looks up what *it* recorded for that
order. So rollback cannot be turned into an arbitrary-image deploy primitive: a fully compromised
conductor can ask a host to go back to a state that host was genuinely in before, and nothing else.

That property is why the rollback path is allowed to skip the MOMUS ``fixed`` verdict a forward
deploy requires. Requiring one would be incoherent — you roll back precisely *because* the verdict
turned out to be wrong — so the authorisation has to come from somewhere else. It comes from the
target being unforgeable rather than from a second signature.

Journal, not state: append-only JSONL, replayed on start, so an agent restarted mid-incident still
knows where to go back to.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DeployRecord:
    """One executed order, with everything rollback needs and nothing it does not."""

    order_id: str
    service: str
    #: Image digest (``sha256:…``) that was running BEFORE this deploy. Empty means there was no
    #: prior container — a first-ever start, which cannot be rolled back to anything.
    previous_image: str = ""
    #: The image reference the compose file names for this service (e.g. ``momus-backend:latest``).
    #: Rollback re-points this tag at ``previous_image``; without it the digest is unreachable,
    #: because ``compose up`` resolves the tag, not a digest we happen to know.
    compose_image_ref: str = ""
    #: What the container ran AFTER the deploy — recorded so a rollback is verifiable after the fact.
    deployed_image: str = ""
    finding_id: str = ""
    outcome: str = ""            # "deployed" | "refused" | "rolled_back" | "dry_run" | "error"
    rolled_back_at: float | None = None
    ts: float = field(default_factory=time.time)

    @property
    def can_roll_back(self) -> bool:
        return bool(self.previous_image and self.compose_image_ref)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["can_roll_back"] = self.can_roll_back
        return d


@dataclass
class BuildRecord:
    """An image this agent built itself, from a named commit, for one service.

    This is the forward twin of :class:`DeployRecord`, and it exists for the same reason: so the
    agent can refuse to act on anything it did not itself produce. A DeployOrder may name an image,
    but the agent will only deploy one that appears here, for the same service. That closes the
    obvious hole in "the order names an image" — otherwise a conductor could name any image on the
    host (a different service's, a stale one, or something an operator pulled by hand) and the agent
    would dutifully ship it.

    Together with the build step's own rule — source comes only as a commit pushed to a
    ``momus/fix-*`` branch, never inline — no link in the chain accepts arbitrary input:
    git under a protected prefix → built here → gated by MOMUS on this digest → deployed here.
    """

    order_id: str
    service: str
    commit_sha: str           # the commit the source came from (a momus/fix-* branch tip)
    image_tag: str = ""       # what we tagged it (e.g. momus-canary:momus-a1b2c3d)
    image_digest: str = ""    # sha256:… as built; what the gate binds to and the deploy names
    built_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentStateStore:
    """Append-only journal of this agent's own deploys and builds, replayed on start."""

    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, DeployRecord] = {}
        #: Indexed by BOTH digest and tag, because a DeployOrder may legitimately name either and
        #: the lookup must not depend on which one the conductor chose to carry.
        self._builds: dict[str, BuildRecord] = {}
        self._replay()

    def _replay(self) -> None:
        if not self._path.is_file():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec.pop("can_roll_back", None)   # derived, never stored back into the dataclass
            oid = rec.get("order_id")
            if not oid:
                continue
            if rec.get("kind") == "rollback":
                existing = self._records.get(oid)
                if existing is not None:
                    existing.rolled_back_at = float(rec.get("ts") or time.time())
                    existing.outcome = "rolled_back"
                continue
            if rec.get("kind") == "build":
                rec.pop("kind", None)
                try:
                    self._index_build(BuildRecord(**rec))
                except TypeError:
                    pass
                continue
            rec.pop("kind", None)
            try:
                self._records[oid] = DeployRecord(**rec)
            except TypeError:
                continue        # a record from a future//older schema is skipped, never fatal

    def _append(self, rec: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def record(self, rec: DeployRecord) -> DeployRecord:
        self._records[rec.order_id] = rec
        payload = rec.to_dict()
        payload.pop("can_roll_back", None)
        self._append({"kind": "deploy", **payload})
        return rec

    def mark_rolled_back(self, order_id: str) -> None:
        rec = self._records.get(order_id)
        if rec is None:
            return
        rec.rolled_back_at = time.time()
        rec.outcome = "rolled_back"
        self._append({"kind": "rollback", "order_id": order_id, "ts": rec.rolled_back_at})

    def _index_build(self, rec: BuildRecord) -> BuildRecord:
        for key in (rec.image_digest, rec.image_tag):
            if key:
                self._builds[key] = rec
        return rec

    def record_build(self, rec: BuildRecord) -> BuildRecord:
        self._index_build(rec)
        self._append({"kind": "build", **rec.to_dict()})
        return rec

    def built_image(self, image: str) -> BuildRecord | None:
        """The build this agent performed for ``image``, by digest or tag. None means "I did not
        build this", which is the only answer a deploy needs in order to refuse."""
        return self._builds.get((image or "").strip())

    def get(self, order_id: str) -> DeployRecord | None:
        return self._records.get(order_id)

    def latest_for(self, service: str) -> DeployRecord | None:
        """The most recent deploy of one service that has somewhere to go back to.

        Used when a rollback names a service rather than a specific order — the honest target is the
        newest deploy that is still rollbackable and has not already been rolled back."""
        candidates = [r for r in self._records.values()
                      if r.service == service and r.can_roll_back and r.rolled_back_at is None]
        return max(candidates, key=lambda r: r.ts) if candidates else None

    def all(self, limit: int = 50) -> list[dict[str, Any]]:
        return [r.to_dict() for r in sorted(self._records.values(),
                                            key=lambda r: r.ts, reverse=True)[:limit]]


def state_from_env(data_dir: str = "") -> AgentStateStore:
    d = data_dir or os.environ.get("SKOPOS_AGENT_STATE_DIR", "data/agent")
    return AgentStateStore(os.path.join(d, "deploys.jsonl"))
