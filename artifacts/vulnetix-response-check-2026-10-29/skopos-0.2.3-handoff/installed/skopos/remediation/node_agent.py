"""The deploy hand that runs ON a node agent — a constrained executor, not a fixer.

This is what the installed SKOPOS agent gains: the ability to *carry out* one redeploy that somebody
else authorised. It deliberately cannot do more than that.

Why the agent is a hand and not a brain — an agent that could AUTHOR fixes would need write access to
code and the ability to run arbitrary changes, replicated on every fleet host. That is the most
dangerous privilege in the system, and it buys nothing: a patch written in place on a host leaves no
reviewable artifact (no diff, no signature, nothing MOMUS can gate), and N agents fixing locally
produce N divergent fixes with no single verified result. So the division of labour is:

    AI-Factory authors  →  the conductor pushes a branch  →  the agent BUILDS that commit
      →  MOMUS gates the resulting image  →  SKOPOS orders  →  the agent promotes that digest

The agent does three kinds of work, and each is a fixed shape with its inputs split the same way:
the ORDER says *which* (which commit, which service, which prior order to undo), the HOST says
*what is permitted* (which services, which branch prefixes, which Dockerfile, which repo).

* **build** — fetch a named commit from the host's own repo, refuse any branch outside the host's
  own prefix list, refuse a commit that is not that branch's tip, build with the host's own recipe,
  report the image digest. Source arrives as a git reference, never inline, so a compromised
  conductor can only point at a commit a human can go and read.
* **deploy** — promote an image THIS agent built for THIS service (checked against its own build
  journal), gated on a MOMUS ``fixed`` verdict it has no key to forge, then health-gate it and
  verify the running container really is that digest.
* **rollback** — restore the digest this agent recorded as running before a given deploy.

It cannot invent work, cannot choose a different service, cannot supply its own source, and cannot
deploy an image it did not build. A fully compromised agent can rebuild and redeploy its own
allowlisted services from commits already in the repo, and nothing else.

Outbound only: the agent polls the conductor. Nothing here opens a port on a fleet host — the
existing agents are push-only and that property is preserved on purpose.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from skopos.remediation.agent_executor import NodeDeployExecutor
from skopos.remediation.agent_state import AgentStateStore
from skopos.remediation.recipes import DEFAULT_SERVICE_ALLOWLIST, merge_build_map


def _json_env(name: str) -> dict:
    """A malformed build map must leave the agent unable to build, never able to build wrongly."""
    import json
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass
class NodeAgentConfig:
    """Everything the hand needs. The allowlist is LOCAL: the host decides what may be touched,
    never the caller — so even a compromised conductor cannot widen it."""

    conductor_url: str
    host: str                        # this agent's host label, as the conductor addresses it
    #: Where the order API lives under `conductor_url`. The conductor itself serves `/agent/v1`;
    #: a hand on another host reaches the fleet relay instead, and that path had to be different
    #: because `/agent/` on the relay's vhost was already the AI assistant's. The hand does not
    #: care which it is talking to — the order is signed either way — so this is a path, not a mode.
    api_prefix: str = "/agent/v1"
    agent_token: str = ""            # the agent's enrolment credential
    conductor_pubkey: str = ""       # learned at enrolment; orders must be signed by it
    momus_pubkey: str = ""           # orders must embed a verdict signed by THIS key
    service_allowlist: tuple[str, ...] = ()
    compose_file: str = ""
    dry_run: bool = True             # constructor default for tests; from_env is live (0)
    #: Does a failing component test suite BLOCK the build, or only get reported?
    #:
    #: Off until the gate has been seen to run on this host. A gate that has never fired is
    #: not yet one you can trust to refuse, and a false refusal stops every repair here. Turn
    #: it on with ``SKOPOS_AGENT_REQUIRE_TESTS=1`` once its verdicts have been read a few times.
    require_tests: bool = False
    poll_interval_s: float = 30.0
    #: Where this agent journals what it deployed and what was running before. Without it there is
    #: no rollback target on the host, so the executor refuses to undo anything.
    state_dir: str = "data/agent"
    health_wait_s: float = 20.0
    #: Where machine-authored source may come from, and which branches are acceptable. Both are the
    #: HOST's to decide: an order names a commit, never a repository and never a branch rule.
    repo_url: str = ""
    branch_prefixes: tuple[str, ...] = ("momus/fix-",)
    #: service → {"dockerfile": …, "context": …, "image_ref": …}, relative to the repo root.
    #: How each service is built and which tag compose resolves for it. Local for the same reason
    #: as the allowlist — a caller that could supply a Dockerfile could build anything.
    build_map: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "NodeAgentConfig":
        raw = os.environ.get("SKOPOS_AGENT_SERVICE_ALLOWLIST")
        if raw is None:
            allow = DEFAULT_SERVICE_ALLOWLIST
        else:
            allow = tuple(s.strip() for s in raw.split(",") if s.strip())
        return cls(
            conductor_url=os.environ.get("SKOPOS_CONDUCTOR_URL", "").strip().rstrip("/"),
            api_prefix=("/" + os.environ.get("SKOPOS_AGENT_API_PREFIX", "/agent/v1").strip().strip("/")),
            host=os.environ.get("SKOPOS_AGENT_HOST", "").strip(),
            agent_token=os.environ.get("SKOPOS_AGENT_TOKEN", "").strip(),
            conductor_pubkey=os.environ.get("SKOPOS_CONDUCTOR_PUBKEY", "").strip(),
            momus_pubkey=os.environ.get("SKOPOS_MOMUS_PUBKEY", "").strip(),
            service_allowlist=allow,
            compose_file=os.environ.get("SKOPOS_AGENT_COMPOSE_FILE", "").strip(),
            dry_run=(os.environ.get("SKOPOS_AGENT_DRY_RUN", "0").strip().lower()
                     not in ("0", "false", "no", "off")),
            require_tests=(os.environ.get("SKOPOS_AGENT_REQUIRE_TESTS", "0").strip().lower()
                           not in ("0", "false", "no", "off", "")),
            poll_interval_s=float(os.environ.get("SKOPOS_AGENT_POLL_S", "30") or 30),
            state_dir=os.environ.get("SKOPOS_AGENT_STATE_DIR", "data/agent").strip() or "data/agent",
            health_wait_s=float(os.environ.get("SKOPOS_AGENT_HEALTH_WAIT_S", "20") or 20),
            repo_url=os.environ.get("SKOPOS_AGENT_REPO_URL", "").strip(),
            branch_prefixes=tuple(
                p.strip() for p in os.environ.get(
                    "SKOPOS_AGENT_BRANCH_PREFIXES", "momus/fix-").split(",") if p.strip()
            ) or ("momus/fix-",),
            build_map=merge_build_map(_json_env("SKOPOS_AGENT_BUILD_MAP")),
        )


class NodeAgentDeployHand:
    def __init__(self, config: NodeAgentConfig | None = None, *, transport: Any = None,
                 executor: NodeDeployExecutor | None = None):
        self.cfg = config or NodeAgentConfig.from_env()
        self._transport = transport   # test hook (httpx.ASGITransport)
        self.state = AgentStateStore(os.path.join(self.cfg.state_dir, "deploys.jsonl"))
        self._executor = executor or NodeDeployExecutor(
            conductor_pubkey=self.cfg.conductor_pubkey,
            momus_pubkey=self.cfg.momus_pubkey,
            service_allowlist=list(self.cfg.service_allowlist),
            compose_file=self.cfg.compose_file,
            dry_run=self.cfg.dry_run,
            state=self.state,
            health_wait_s=self.cfg.health_wait_s,
            repo_url=self.cfg.repo_url,
            repo_dir=os.path.join(self.cfg.state_dir, "repo.git"),
            work_dir=os.path.join(self.cfg.state_dir, "wt"),
            branch_prefixes=self.cfg.branch_prefixes,
            build_map=self.cfg.build_map,
            require_tests=self.cfg.require_tests,
            host=self.cfg.host,
        )

    def _client(self) -> httpx.AsyncClient:
        headers = {"x-agent-token": self.cfg.agent_token} if self.cfg.agent_token else {}
        kwargs: dict[str, Any] = {"base_url": self.cfg.conductor_url, "timeout": 30.0,
                                  "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def poll_once(self) -> dict[str, Any]:
        """Claim at most one order, verify it locally, execute it, report the outcome.

        Never raises: a conductor outage leaves the host untouched, which is the safe direction."""
        if not self.cfg.conductor_url or not self.cfg.host:
            return {"polled": False, "reason": "agent not configured (conductor url / host missing)"}
        try:
            async with self._client() as c:
                r = await c.get(f"{self.cfg.api_prefix}/orders", params={"host": self.cfg.host})
                r.raise_for_status()
                body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {"polled": False, "reason": f"conductor unreachable: {type(exc).__name__}"}

        order = (body or {}).get("order")
        if not order:
            return {"polled": True, "order": None, "reason": "no order for this host"}

        # LOCAL verification, then one fixed-shape command. This is the only place a deploy happens.
        # An order's `kind` selects the path, and each verifier rejects the other's kind — a rollback
        # carries no MOMUS verdict, so letting one fall through to `execute` would report the missing
        # verdict as a broken chain instead of as the wrong door.
        kind = str(order.get("kind") or "deploy")
        if kind == "rollback":
            result = self._executor.execute_rollback(order)
        elif kind == "build":
            result = self._executor.execute_build(order)
        else:
            result = self._executor.execute(order)
        result["host"] = self.cfg.host
        result["executed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            async with self._client() as c:
                await c.post(f"{self.cfg.api_prefix}/result",
                             json={"order_id": order.get("order_id"), "result": result})
        except (httpx.HTTPError, ValueError):
            pass  # the deploy already happened (or was refused); a lost report must not retry it
        return {"polled": True, "order_id": order.get("order_id"), "result": result}

    async def run_forever(self) -> None:  # pragma: no cover - long-running loop
        import asyncio
        while True:
            await self.poll_once()
            await asyncio.sleep(self.cfg.poll_interval_s)


def main() -> None:  # pragma: no cover - process entrypoint
    """Run the deploy hand as a long-lived service.

    Logs its own posture at start, because the two facts an operator most needs are exactly the two
    that are invisible from the outside: whether dry-run is on, and which services this host has
    authorised. A hand with an empty allowlist looks identical to a working one until an order
    arrives and is refused."""
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("skopos.deploy-hand")
    agent = NodeAgentDeployHand()
    cfg = agent.cfg
    log.info("component tests: %s",
             "ENFORCED — a failing suite blocks the build" if cfg.require_tests
             else "advisory — failures are reported, not blocking "
                  "(SKOPOS_AGENT_REQUIRE_TESTS=1 to enforce)")
    log.info("deploy hand starting: host=%s conductor=%s dry_run=%s", cfg.host,
             cfg.conductor_url or "(unset)", cfg.dry_run)
    log.info("authorised services: %s", ", ".join(cfg.service_allowlist) or "(NONE — will refuse "
             "every order)")
    log.info("branch prefixes: %s | build recipes for: %s",
             ", ".join(cfg.branch_prefixes), ", ".join(sorted(cfg.build_map)) or "(none)")
    # Said at STARTUP, because without it the hand looks perfectly healthy — it polls, it claims,
    # it reports — and refuses every order with "no signing backend available", a message that
    # describes the symptom and names nothing an operator can act on. Measured: the first real
    # autonomous cycle died here, after the model had already been paid and the image built.
    from skopos.remediation.deploy_order import Signer

    if Signer is None:
        log.error("NO SIGNING BACKEND: `oracle_core` is not importable, so every order will be "
                  "refused unverified. Put oracles/core on PYTHONPATH, or install "
                  "aimarket-oracle-core into this interpreter.")
    else:
        log.info("signing backend: oracle_core available — orders will be verified")
    if cfg.dry_run:
        log.warning("DRY-RUN: orders will be verified and the command printed, nothing executed")
    else:
        log.warning("LIVE: authorised services will be built and composed when MOMUS gates them")
    asyncio.run(agent.run_forever())


if __name__ == "__main__":  # pragma: no cover
    main()
