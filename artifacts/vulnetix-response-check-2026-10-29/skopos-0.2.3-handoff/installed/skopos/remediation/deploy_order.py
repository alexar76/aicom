"""The signed DeployOrder — the authorization a node agent needs before it will redeploy anything.

The order chains two signatures so no single party can make a deploy happen on its own:

  1. MOMUS signs a ``fixed`` retest verdict (finding no longer reproduces on the patched build).
  2. SKOPOS's conductor signs a DeployOrder that EMBEDS that verdict and names the exact service +
     host + image to ship.

A node agent runs ``verify_deploy_chain`` before touching anything: it checks the conductor's
signature under the SKOPOS pubkey it learned at enrollment, checks the embedded verdict's signature
under MOMUS's known pubkey, checks the verdict is actually ``fixed`` and bound to this finding, and
checks the service is on its OWN local allowlist. Any failure → refuse. This is the whole reason a
compromised conductor still cannot ship arbitrary code to a host: it cannot forge MOMUS's verdict,
and the agent will not deploy a service it was not pre-authorized to touch.

**Going back.** A forward deploy is gated on a MOMUS ``fixed`` verdict; a rollback cannot be, because
you roll back exactly when that verdict turned out to be wrong. Demanding one would make the undo
path unusable in the only situation it exists for. So :class:`RollbackOrder` drops the verdict and
replaces it with a different, stronger constraint: **it carries no image**. It names a prior order,
and the agent resolves the target from its OWN journal of what it saw running before that deploy
(see ``agent_state.py``). A compromised conductor can therefore ask a host to return to a state that
host provably occupied — and cannot use the undo path to ship anything new.

``kind`` is inside the signed body of both orders, and each verifier rejects the other's kind, so a
deploy order can never be replayed as a rollback (or the reverse) by relabelling it on the wire.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    from oracle_core.signing import Signer
except Exception:  # pragma: no cover - oracle-core always present in the ecosystem venv
    Signer = None  # type: ignore


def _canon(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class DeployOrder:
    """A conductor-signed instruction to redeploy ONE service, gated on a MOMUS fixed-verdict."""

    finding_id: str
    service: str              # the container/service to redeploy (must be on the agent's allowlist)
    host: str                 # which fleet host / which node agent
    image: str = ""           # image ref / tag to promote (empty → rebuild from source)
    momus_verdict: dict[str, Any] = field(default_factory=dict)  # the signed FixVerdict from MOMUS
    order_id: str = ""
    kind: str = "deploy"      # inside the signed body: a rollback can never be relabelled as this
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    conductor_pubkey: str = ""
    signature: dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("signature", None)
        return d

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BuildOrder:
    """A conductor-signed instruction to BUILD one service's image from one named commit.

    This is the step whose absence made the whole loop theatre: without it nothing ever turned a
    patch into a runnable image, so "deploy" could only ever recreate the container from the image
    already on the host.

    Like the other two orders, it carries no content — only a *reference*. The source is a commit
    that must already exist in the repo, on a branch whose prefix the AGENT (not the caller) decides
    is acceptable. So a compromised conductor cannot inject source; it can only point at a commit
    someone can go and read. The audit trail and the delivery mechanism are the same object.
    """

    finding_id: str
    service: str
    host: str
    commit_sha: str           # the exact commit to build; the agent verifies it is on `branch`
    branch: str               # e.g. momus/fix-mom-a1b2; the agent checks its own prefix rule
    order_id: str = ""
    kind: str = "build"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    conductor_pubkey: str = ""
    signature: dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("signature", None)
        return d

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RollbackOrder:
    """A conductor-signed instruction to UNDO one prior deploy on one host.

    Deliberately missing an ``image`` field. The target is whatever the agent recorded as running
    before ``rollback_of``, read from its own journal — so this order authorises a return to a
    known-past state and cannot express "run this image I chose"."""

    finding_id: str
    service: str
    host: str
    rollback_of: str          # order_id of the deploy being undone; the agent must have executed it
    reason: str = ""          # why, for the host's own audit trail
    order_id: str = ""
    kind: str = "rollback"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    conductor_pubkey: str = ""
    signature: dict[str, Any] = field(default_factory=dict)

    def canonical(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("signature", None)
        return d

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sign_deploy_order(order: DeployOrder, conductor_signer: "Signer") -> DeployOrder:
    if not order.order_id:
        order.order_id = f"deploy-{order.finding_id}-{int(time.time())}"
    order.conductor_pubkey = conductor_signer.public_key_b64
    order.signature = conductor_signer.sign_payload(_canon(order.canonical()))
    return order


def sign_build_order(order: BuildOrder, conductor_signer: "Signer") -> BuildOrder:
    if not order.order_id:
        order.order_id = f"build-{order.finding_id}-{int(time.time())}"
    order.conductor_pubkey = conductor_signer.public_key_b64
    order.signature = conductor_signer.sign_payload(_canon(order.canonical()))
    return order


def sign_rollback_order(order: RollbackOrder, conductor_signer: "Signer") -> RollbackOrder:
    if not order.order_id:
        order.order_id = f"rollback-{order.rollback_of or order.finding_id}-{int(time.time())}"
    order.conductor_pubkey = conductor_signer.public_key_b64
    order.signature = conductor_signer.sign_payload(_canon(order.canonical()))
    return order


def verify_deploy_chain(order: dict[str, Any], *, conductor_pubkey: str, momus_pubkey: str,
                        service_allowlist: list[str]) -> tuple[bool, str]:
    """Run ON the node agent before deploying. Returns (ok, reason). Fails closed on anything odd."""
    if Signer is None:
        return False, "no signing backend available"
    # 0. A rollback order carries no MOMUS verdict by design. It must never reach the forward-deploy
    #    path, where "no verdict" would read as a signature problem rather than as the wrong kind.
    if str(order.get("kind") or "deploy") != "deploy":
        return False, f"not a deploy order (kind={order.get('kind')!r})"
    # 1. The order must be signed by the conductor key the agent trusts (from enrollment).
    sig = order.get("signature") or {}
    body = {k: v for k, v in order.items() if k != "signature"}
    if not sig.get("value"):
        return False, "deploy order is unsigned"
    if order.get("conductor_pubkey") != conductor_pubkey:
        return False, "deploy order not signed by the enrolled conductor key"
    if not Signer.verify_signature_object(_canon(body), sig, conductor_pubkey):
        return False, "conductor signature does not verify"
    # 2. The embedded MOMUS verdict must verify under MOMUS's known key, and say fixed for THIS finding.
    verdict = order.get("momus_verdict") or {}
    vsig = verdict.get("signature") or {}
    vbody = {k: v for k, v in verdict.items() if k != "signature"}
    if not vsig.get("value"):
        return False, "no MOMUS retest verdict embedded"
    if not Signer.verify_signature_object(_canon(vbody), vsig, momus_pubkey):
        return False, "MOMUS verdict signature does not verify (forged fixed-verdict?)"
    if not verdict.get("fixed"):
        return False, "MOMUS verdict is not 'fixed' — deploy refused"
    if verdict.get("finding_id") != order.get("finding_id"):
        return False, "MOMUS verdict is for a different finding (transplanted)"
    # 2b. A verdict that examined the LIVE service says nothing about the image being promoted. So an
    #     order that promotes a new image must carry a PRE-PROMOTION verdict — one MOMUS produced
    #     against the candidate container built from that patch. Without this the gate is decorative:
    #     the old loop asked MOMUS about the running (unpatched) service and then shipped on the
    #     answer, which is how a "verified" deploy could ship a build nobody had examined.
    if str(order.get("image") or "").strip() and str(verdict.get("gated") or "live") != "candidate":
        return False, ("this order promotes a new image, but the MOMUS verdict examined the live "
                       f"service (gated={verdict.get('gated', 'live')!r}) — refusing to ship a "
                       "build the gate never looked at")
    if order.get("service") == "warden" and (not order.get("image") or verdict.get("artifact_digest") != order.get("image")):
        return False, "WARDEN quality verdict is not bound to this exact image"
    # 3. The agent only ships services it was pre-authorized to touch.
    if order.get("service") not in service_allowlist:
        return False, f"service '{order.get('service')}' not on this agent's deploy allowlist"
    return True, "chain verified: MOMUS-fixed + conductor-signed + service allowlisted"


#: A git commit id and nothing else — the agent resolves it itself, so anything that is
#: not a plain hex id (a ref name, a range, an option) has no business being accepted.
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def verify_build_chain(order: dict[str, Any], *, conductor_pubkey: str,
                       service_allowlist: list[str],
                       allowed_branch_prefixes: list[str]) -> tuple[bool, str]:
    """Run ON the node agent before building anything. Returns (ok, reason).

    No MOMUS verdict here either, and for a plain reason: the gate's whole job is to judge the image
    this step produces, so requiring its verdict first would be circular. What replaces it is that
    the order names a *commit on an allowed branch* rather than carrying code, and the prefix list
    is the AGENT's, from its own config — a caller cannot widen it, exactly as with the service
    allowlist. Whether that commit really is on that branch is a git question the agent answers
    locally after fetching; this function only refuses what is refusable from the order alone."""
    if Signer is None:
        return False, "no signing backend available"
    if str(order.get("kind") or "") != "build":
        return False, f"not a build order (kind={order.get('kind')!r})"
    sig = order.get("signature") or {}
    body = {k: v for k, v in order.items() if k != "signature"}
    if not sig.get("value"):
        return False, "build order is unsigned"
    if order.get("conductor_pubkey") != conductor_pubkey:
        return False, "build order not signed by the enrolled conductor key"
    if not Signer.verify_signature_object(_canon(body), sig, conductor_pubkey):
        return False, "conductor signature does not verify"
    if order.get("service") not in service_allowlist:
        return False, f"service '{order.get('service')}' not on this agent's build allowlist"
    sha = str(order.get("commit_sha") or "").strip().lower()
    if not _SHA_RE.match(sha):
        return False, f"commit_sha {sha!r} is not a hex commit id"
    branch = str(order.get("branch") or "").strip()
    if not any(branch.startswith(p) for p in allowed_branch_prefixes):
        # The prefix rule is what keeps machine-authored source in a namespace a human can protect
        # and grep for. A build from `main` would be a build of whatever anyone last merged.
        return False, (f"branch '{branch}' is not under an allowed prefix "
                       f"{allowed_branch_prefixes} — refusing to build it")
    return True, (f"build chain verified: conductor-signed + '{order.get('service')}' allowlisted "
                  f"+ branch '{branch}' under an allowed prefix")


def verify_rollback_chain(order: dict[str, Any], *, conductor_pubkey: str,
                          service_allowlist: list[str]) -> tuple[bool, str]:
    """Run ON the node agent before undoing a deploy. Returns (ok, reason).

    Three checks, and the absence of a fourth is the point. There is no MOMUS verdict to check —
    a rollback happens *because* the verdict was wrong — so safety rests on the order naming a prior
    order instead of an image: the caller cannot choose what gets run, only which of this agent's own
    past states to return to. Resolving ``rollback_of`` against the local journal is the agent's job
    (see ``AgentStateStore``); an order naming an order this agent never executed resolves to
    nothing and is refused there."""
    if Signer is None:
        return False, "no signing backend available"
    if str(order.get("kind") or "") != "rollback":
        return False, f"not a rollback order (kind={order.get('kind')!r})"
    sig = order.get("signature") or {}
    body = {k: v for k, v in order.items() if k != "signature"}
    if not sig.get("value"):
        return False, "rollback order is unsigned"
    if order.get("conductor_pubkey") != conductor_pubkey:
        return False, "rollback order not signed by the enrolled conductor key"
    if not Signer.verify_signature_object(_canon(body), sig, conductor_pubkey):
        return False, "conductor signature does not verify"
    if not str(order.get("rollback_of") or "").strip():
        return False, "rollback order names no prior deploy to undo"
    # The allowlist gates the undo path too: a host that never authorised a service being deployed
    # must not have it recreated by a rollback either.
    if order.get("service") not in service_allowlist:
        return False, f"service '{order.get('service')}' not on this agent's deploy allowlist"
    return True, "rollback chain verified: conductor-signed + names a prior order + allowlisted"
