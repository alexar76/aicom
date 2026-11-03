"""Who may call what: the ecosystem policy, the publish token, and publisher and agent
credentials.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi import HTTPException

from aimarket_hub import credits, ecosystem
from aimarket_hub.channels import _is_production_mode
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger


def register(
    *,
    _ADMIN_TOKEN: str,
    config: HubConfig,
    hub_credits: CreditsLedger,
) -> SimpleNamespace:
    """Build the credential checks the routes use."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _parse_subject_tokens,
        logger,
    )

    # Who is "us" — ecosystem.json next to the hub database (or AIMARKET_ECOSYSTEM_FILE),
    # re-read on change. One accessor for the write sites, the feed and the home page.
    _ECOSYSTEM_PATH = ecosystem.policy_path(getattr(config, "db_path", None))

    def _ecosystem_policy() -> ecosystem.EcosystemPolicy:
        return ecosystem.current(_ECOSYSTEM_PATH)

    _PUBLISH_TOKEN = os.environ.get("AIMARKET_PUBLISH_TOKEN", "").strip()

    def _require_publish(authorization: str) -> None:
        """Developer catalog publish — token required in production."""
        import hmac
        if _PUBLISH_TOKEN:
            if not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing Bearer token")
            token = authorization[7:]
            if not hmac.compare_digest(token, _PUBLISH_TOKEN):
                raise HTTPException(status_code=403, detail="Invalid publish token")
        elif _is_production_mode():
            raise HTTPException(
                status_code=503,
                detail="Publish disabled: set AIMARKET_PUBLISH_TOKEN",
            )

    # Per-SUBJECT credentials (finding #12 residual, + its own two residuals).
    #
    # /supply/stake, /supply/register and /self-bond/register all act on a CALLER-NAMED
    # SUBJECT, and the shared publish token — held by every publisher on the hub —
    # cannot tell one caller from another. Under it, any holder could credit stake to an
    # arbitrary publisher, register a slashable spend ceiling against a rival agent, or
    # publish capabilities AS another publisher (which stamps the victim's publisher_id
    # onto the capability row, charges the victim's publish-rate budget, reads the
    # victim's stake as the capability's collateral, and points a later slash for that
    # capability at the victim's money).
    #
    # These routes cannot simply become admin-only: stake → register IS the documented
    # self-service community publish flow, and an operator-gated stake step breaks every
    # community publisher. So the subject must authenticate AS ITSELF.
    #
    # TWO NAMESPACES, not one. The registry used to be publisher-only, and
    # /self-bond/register authenticated an AGENT id against it: once an operator
    # configured a single publisher entry, that publisher registry became authoritative
    # for agent identities too, so an agent that is not a publisher was locked out —
    # and an agent id that happened to collide with a publisher id was authorised by an
    # unrelated namespace. They are now separate registries:
    #     AIMARKET_PUBLISHER_TOKENS="pub-a:secretA,..."     (publisher ids)
    #     AIMARKET_AGENT_TOKENS="agent-a:secretX,..."       (agent ids)
    # Configuring one says nothing about the other.
    #
    # WHAT OPERATORS MUST CONFIGURE, exactly:
    #   * community PUBLISHERS (stake + register): issue each publisher its own secret
    #     and list it in AIMARKET_PUBLISHER_TOKENS. The publisher then sends
    #     `Authorization: Bearer <its secret>` and may only touch its own publisher_id —
    #     the whole self-service flow (POST /supply/stake then POST /supply/register with
    #     the same publisher_id) keeps working for a publisher acting as ITSELF.
    #   * bonded AGENTS (self-bond): list each agent in AIMARKET_AGENT_TOKENS. An agent
    #     that also stakes uses the same secret on /supply/stake (the stake ledger is one
    #     account space — see _require_stake_subject).
    #   * or drive any of them with AIMARKET_ADMIN_TOKEN, accepted for any subject
    #     (operator-provisioned publishers/agents).
    # In production, with none of that configured, these routes refuse (503) with that
    # instruction instead of accepting the shared token — the point of the finding.
    _PUBLISHER_TOKENS = _parse_subject_tokens(
        os.environ.get("AIMARKET_PUBLISHER_TOKENS", ""), "AIMARKET_PUBLISHER_TOKENS"
    )
    _AGENT_TOKENS = _parse_subject_tokens(
        os.environ.get("AIMARKET_AGENT_TOKENS", ""), "AIMARKET_AGENT_TOKENS"
    )
    _NS_PUBLISHER = ("publisher", "AIMARKET_PUBLISHER_TOKENS", _PUBLISHER_TOKENS)
    _NS_AGENT = ("agent", "AIMARKET_AGENT_TOKENS", _AGENT_TOKENS)
    if _is_production_mode():
        if not _PUBLISHER_TOKENS:
            logger.warning(
                "AIMARKET_PUBLISHER_TOKENS not set — /supply/stake and /supply/register "
                "accept only AIMARKET_ADMIN_TOKEN in production (the shared publish "
                "token cannot prove which publisher is calling)"
            )
        if not _AGENT_TOKENS:
            logger.warning(
                "AIMARKET_AGENT_TOKENS not set — /self-bond/register accepts only "
                "AIMARKET_ADMIN_TOKEN in production (agent ids are a separate namespace "
                "from AIMARKET_PUBLISHER_TOKENS)"
            )

    def _require_subject_credential(
        authorization: str,
        subject_id: str,
        namespaces: tuple[tuple[str, str, dict[str, str]], ...] = (_NS_PUBLISHER,),
    ) -> str:
        """Authorize a mutation acting AS ``subject_id``. Returns the granting role.

        ``namespaces`` are the (role, env_name, registry) credential namespaces that may
        speak for this subject — one for a publisher-only or agent-only route, both where
        the subject space is genuinely shared (the stake ledger).

        Order matters: the admin token wins first (operators manage anyone), then the
        subject's own credential. A configured registry is authoritative FOR ITS OWN
        NAMESPACE — a subject that is not in it cannot fall back to the shared token,
        otherwise adding one credential would leave every other id in that namespace
        wide open — and says nothing about the other namespace.
        """
        import hmac

        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        # A missing token is only the caller's problem when SOME token could have worked.
        # Deciding that needs the registries, so the 401 is raised further down, once we
        # know a credential exists to present — answering 401 on a hub where nothing is
        # configured invites a retry loop no token can ever satisfy, and hides the fact
        # that the operator, not the caller, has to act (the route's pre-existing
        # contract for that state is 503).
        if token and _ADMIN_TOKEN and hmac.compare_digest(token, _ADMIN_TOKEN):
            return "admin"
        registered = [
            (role, env_name, registry[subject_id])
            for role, env_name, registry in namespaces
            if subject_id in registry
        ]
        if len({secret for _, _, secret in registered}) > 1:
            # The same id claimed by two namespaces with DIFFERENT secrets: the stake
            # ledger has exactly one account per id, so the registries disagree about who
            # owns that account and nothing here can pick a winner. Fail closed.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{subject_id} is registered with different credentials in "
                    + " and ".join(env for _, env, _ in registered)
                    + " — the stake ledger holds one account per id; reconcile the "
                    "registries (or use AIMARKET_ADMIN_TOKEN)"
                ),
            )
        if registered:
            # A credential for this subject EXISTS, so "no token" is genuinely the
            # caller's omission and 401 is the honest, actionable answer.
            if not token:
                raise HTTPException(status_code=401, detail="Missing Bearer token")
            for role, _env_name, secret in registered:
                if hmac.compare_digest(token, secret):
                    return role
            raise HTTPException(
                status_code=403,
                detail=f"token does not authenticate {subject_id}",
            )
        configured = [env_name for _, env_name, registry in namespaces if registry]
        if configured:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"no credential is registered for {subject_id} — ask the operator to "
                    f"add it to {' or '.join(configured)}"
                ),
            )
        if _is_production_mode():
            raise HTTPException(
                status_code=503,
                detail=(
                    "disabled: the shared publish token cannot prove which caller is "
                    "acting as " + subject_id + ". Set "
                    + " / ".join(f"{env}='<id>:<secret>,...'" for _, env, _ in namespaces)
                    + " or call with AIMARKET_ADMIN_TOKEN."
                ),
            )
        # Dev/relaxed: keep the documented self-service flow working unchanged.
        _require_publish(authorization)
        logger.warning(
            "mutation acting as %s authorized by the SHARED publish token "
            "(non-production only) — set %s before going live",
            subject_id, "/".join(env for _, env, _ in namespaces),
        )
        return "shared-publish-token"

    def _credits_publisher(x_api_key: str | None) -> str:
        """A credit account speaking as a publisher.

        Publisher identity used to exist only as `AIMARKET_PUBLISHER_TOKENS` — a
        comma-separated env map parsed once at app construction — so onboarding one
        community publisher meant editing .env and restarting the hub. That is not a
        signup flow, it is a maintenance window per customer, and it is why the reference
        deployment has never had a third-party publisher.

        A credit account is already an authenticated, self-serve, per-caller identity, so
        it can be one here too. The publisher id IS the account id: it cannot collide with
        an operator-configured name (those are chosen by the operator, these are minted
        `acct_…`), and the credential is the account's own key rather than a shared token.
        """
        if not x_api_key or not credits.enabled():
            return ""
        ledger = hub_credits
        return ledger.resolve(x_api_key) if ledger is not None else ""

    def _require_stake_subject(authorization: str, subject_id: str) -> str:
        """Authorize a stake-ledger mutation for ``subject_id``.

        ``supply_stakes`` is ONE account space keyed by id: publishers stake there to
        unlock community publish and bonded agents stake there to back a self-bond, so a
        credential from either namespace may speak for a stake subject. A collision (the
        same id in both registries with different secrets) is refused rather than
        resolved — see _require_subject_credential.
        """
        return _require_subject_credential(
            authorization, subject_id, (_NS_PUBLISHER, _NS_AGENT)
        )

    return SimpleNamespace(
        _AGENT_TOKENS=_AGENT_TOKENS,
        _NS_AGENT=_NS_AGENT,
        _NS_PUBLISHER=_NS_PUBLISHER,
        _credits_publisher=_credits_publisher,
        _ecosystem_policy=_ecosystem_policy,
        _require_stake_subject=_require_stake_subject,
        _require_subject_credential=_require_subject_credential,
    )
