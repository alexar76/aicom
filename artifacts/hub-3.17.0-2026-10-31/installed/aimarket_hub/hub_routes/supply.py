"""Supply side: stake policy, staking, provider registration and self-bonds."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from aimarket_hub import credits
from aimarket_hub.channels import _is_production_mode
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.database import HubDatabase
from aimarket_hub.mandates import MandateStore
from aimarket_hub.supply_chain_admission import SupplyChainAdmission
from aimarket_hub.supply_security import SupplySecurity


def register(
    *,
    _NS_AGENT: tuple[str, str, dict[str, str]],
    _credits_publisher: Callable[..., Any],
    _require_admin: Callable[..., Any],
    _require_stake_subject: Callable[..., Any],
    _require_subject_credential: Callable[..., Any],
    config: HubConfig,
    db: HubDatabase,
    hub_credits: CreditsLedger,
    hub_mandates: MandateStore,
    router: APIRouter,
    supply_chain_admission: SupplyChainAdmission,
    supply_security: SupplySecurity,
) -> None:
    """Attach the /supply and /self-bond routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _money_arg,
        logger,
    )

    # ── Developer publish ─────────────────────────────────────

    @router.get("/supply/policy")
    async def supply_policy(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Read current admission requirements, optionally for the caller's own account."""
        policy = supply_security.policy
        result = {
            "min_stake_usd": policy.min_stake_usd,
            "require_response_signature": policy.require_response_signature,
            "product_allowlist": list(policy.product_allowlist),
            "publish_per_hour": policy.publish_per_hour,
            "admission_mode": supply_chain_admission.mode,
            "credits_enabled": credits.enabled(),
            "open_signup": credits.enabled() and credits.signup_open(),
            "protocol_version": "v2",
        }
        if x_api_key is not None:
            account_id = _credits_publisher(x_api_key)
            if not account_id:
                raise HTTPException(status_code=401, detail="valid X-API-Key required")
            account = hub_credits.account(account_id)
            stake = db.supply_stake_get(account_id)
            minimum = 0.0 if account_id in policy.operator_publishers else policy.min_stake_usd
            result.update({
                "publisher_id": account_id,
                "min_stake_usd": minimum,
                "stake_usd": stake,
                "additional_stake_usd": max(0.0, round(minimum - stake, 6)),
                "balance_usd": account["balance_usd"],
                "collateral_usd": account["collateral_usd"],
                "requires_mandate": hub_mandates.account_requires_mandate(account_id),
            })
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @router.post("/supply/stake")
    async def supply_stake(
        body: dict[str, Any],
        authorization: str = Header(default=""),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """Deposit stake (USD bookkeeping) to unlock community publish.

        Auth is PER-SUBJECT (_require_stake_subject): the caller must present the stake
        subject's own credential — from either credential namespace, because the stake
        ledger is one account space shared by publishers and bonded agents — or the
        operator token. Under the shared publish token this endpoint could not tell one
        publisher from another, so any token holder could credit stake to an arbitrary
        ``publisher_id`` — inflating a colluding publisher's trust score and stake gate.
        See the gate's docstring for exactly what operators must configure.

        Stake credit raises the target's trust score and unlocks the stake gate, so the
        number must be backed by a real deposit rather than by the caller's word: in
        production we require a ``tx_hash`` for EVERY positive amount here
        (SupplySecurity.stake then verifies it on-chain regardless of size, closing the
        old sub-minimum drip-feed bypass) AND a ``payer_signature`` proving control of
        the wallet that paid it — every deposit lands in the same settlement wallet, so
        recipient+amount alone let a publisher claim a stranger's inbound transfer as its
        own collateral. The refusal carries the exact challenge text to sign.

        The amount is also range-checked before it reaches the ledger. ``float()`` alone
        accepted ``"inf"`` / a bare ``Infinity`` literal, and ``stake()``'s only size
        guard is ``amount_usd <= 0`` — which infinity passes. The credit was written and
        the hub trust-anchor edge updated BEFORE the 500 that non-finite JSON produced,
        so a dev/relaxed hub ended up with a publisher holding infinite stake.
        """
        credit_account = _credits_publisher(x_api_key)
        publisher_id = str(body.get("publisher_id", "")).strip() or credit_account
        if not publisher_id:
            # Named before the auth check on purpose: the credential is scoped TO the
            # publisher_id, so there is nothing to authorize without one.
            raise HTTPException(status_code=400, detail="publisher_id required")
        if credit_account:
            # The key IS the credential, and it speaks for exactly one publisher.
            if publisher_id != credit_account:
                raise HTTPException(
                    status_code=403,
                    detail="an API key may only stake for its own account id",
                )
        else:
            _require_stake_subject(authorization, publisher_id)
        amount = _money_arg(body.get("amount_usd", 0), "amount_usd")
        tx_hash = str(body.get("tx_hash", "")).strip()
        payer_signature = str(body.get("payer_signature", "") or "").strip()
        if (
            amount > 0
            and not tx_hash
            and not credit_account
            and _is_production_mode()
            and not supply_security.policy.relaxed
        ):
            raise HTTPException(
                status_code=400,
                detail="tx_hash required for stake deposits in production "
                       "(AIMARKET_SUPPLY_SECURITY_RELAXED=1 to bypass for dev)",
            )
        settled_ref = ""
        if credit_account and amount > 0 and hub_mandates.account_requires_mandate(credit_account):
            # require_mandate promises that a leaked API key cannot move this balance. A stake
            # would not pay the thief, but it would freeze the owner's money as collateral
            # and expose it to slashing — on the key alone.
            raise HTTPException(
                status_code=403,
                detail="this account spends only under a mandate (require_mandate): its API key "
                       "alone cannot move the balance into stake; an owner can lift the policy "
                       "with a signed change (mandates.md §4)",
            )
        if credit_account and amount > 0:
            # Take the collateral BEFORE recording it. The debit is the whole reason this
            # counts as stake rather than as the caller's word: the money leaves the
            # publisher's spendable balance and the operator holds it, which is exactly
            # what a later slash needs to be able to burn.
            ledger = hub_credits
            debit = ledger.debit(
                credit_account, amount,
                receipt_id=f"stake_{secrets.token_hex(8)}", note="supply stake",
                as_collateral=True,
            ) if ledger is not None else {"error": "credits unavailable"}
            if debit.get("error"):
                raise HTTPException(
                    status_code=402,
                    detail=f"stake not posted: {debit['error']}",
                )
            settled_ref = f"credits:{credit_account}:{secrets.token_hex(6)}"
        try:
            return {
                **supply_security.stake(
                    publisher_id, amount, tx_hash, payer_signature=payer_signature,
                    settled_ref=settled_ref,
                ),
                "protocol_version": "v2",
            }
        except BaseException as exc:
            # ANY failure, not just ValueError. The debit above has already moved the
            # publisher's money out of their spendable balance into collateral; the stake
            # is only real once `supply_security.stake` has written `supply_stake_add`,
            # `trust_add_edge` and `refresh_publisher_trust`. A sqlite error, a lock
            # timeout, a disconnected Postgres or a cancelled request in the middle of
            # those three left the money taken and no stake recorded, with no path back —
            # `return_collateral` is called from here and nowhere else.
            #
            # Compensating first and re-raising afterwards keeps the original error, which
            # is what the caller needs; the refund is a side effect, not the answer.
            if settled_ref:
                ledger = hub_credits
                if ledger is not None:
                    try:
                        ledger.return_collateral(
                            credit_account, amount, note="stake refused",
                        )
                    except Exception as give_back:  # noqa: BLE001
                        # Never mask the real failure with the failure to undo it — but
                        # never lose it either: this is money nobody else will notice.
                        logger.error(
                            "stake: returning $%.6f collateral to %s after a failed stake "
                            "raised: %s (original failure: %s)",
                            amount, credit_account, give_back, exc,
                        )
            if isinstance(exc, ValueError):
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            raise

    @router.post("/supply/register")
    async def supply_register(
        body: dict[str, Any],
        authorization: str = Header(default=""),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """Register a community capability with a direct invoke URL.

        PER-SUBJECT gated (_require_subject_credential, publisher namespace). This route
        moves no money directly, which is why it kept the shared publish token for one
        pass too long — but the manifest NAMES the publisher it registers as, and every
        holder of the shared token could name someone else. Registering as a rival:
          * stamps the victim's ``publisher_id`` on the capability row and reads the
            victim's stake balance as that capability's collateral, so a later
            failure-driven slash for it burns the VICTIM'S money;
          * spends the victim's publish-rate budget (5/hour), locking them out of their
            own publish flow;
          * attaches an attacker-controlled ``invoke_url`` to the victim's identity and
            trust score.
        So the caller must authenticate as the publisher it claims to be. A publisher
        acting as ITSELF is unaffected: it presents its own credential from
        AIMARKET_PUBLISHER_TOKENS (the same one /supply/stake takes) and the documented
        stake → register flow works end to end. Operators who provision publishers
        centrally can keep using AIMARKET_ADMIN_TOKEN for any publisher_id.
        """
        from aimarket_hub.publish import validate_manifest
        from aimarket_hub.supply_security import manifest_publisher_id

        # Resolved with the SAME helper validate_publish uses, and named before the auth
        # check: the credential is scoped to this publisher_id, so authorizing against a
        # different reading of the manifest than the ledger writes would be no gate at all.
        credit_account = _credits_publisher(x_api_key)
        publisher_id = manifest_publisher_id(body) or credit_account
        if not publisher_id:
            raise HTTPException(
                status_code=400,
                detail="publisher_id is required (wallet address or stable publisher slug)",
            )
        if credit_account:
            # Self-serve publishing: the key authenticates exactly one publisher, so there
            # is no shared token that could name somebody else's id.
            if publisher_id != credit_account:
                raise HTTPException(
                    status_code=403,
                    detail="an API key may only publish as its own account id",
                )
            body = {**body, "publisher_id": publisher_id}
        else:
            _require_subject_credential(authorization, publisher_id)
        try:
            cap = validate_manifest(body)
            publisher_id, pubkey = supply_security.validate_publish(body)
            cap.publisher_id = publisher_id
            cap.provider_pubkey = pubkey
            cap.stake_usd = db.supply_stake_get(publisher_id)
            # Admission is a publish-time gate, never a per-invoke tax.  The external
            # auditor returns its deterministic verdict immediately; its optional Metis
            # second opinion remains asynchronous and is refreshed from the telemetry
            # path without holding this request open.
            admission = await supply_chain_admission.evaluate(body)
            if admission.get("blocked"):
                decision = admission.get("decision") or "unavailable"
                raise HTTPException(
                    status_code=403 if decision in {"review", "reject"} else 503,
                    detail={
                        "code": "supply_chain_admission_denied",
                        "decision": decision,
                        "audit_id": admission.get("audit_id"),
                        "score": admission.get("score"),
                        "risk_tier": admission.get("risk_tier"),
                        "findings": admission.get("findings") or [],
                    },
                )
            trust = supply_security.after_publish(cap, publisher_id)
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "published": True,
            "product_id": cap.product_id,
            "capability_id": cap.capability_id,
            "invoke_url": cap.invoke_url,
            "publisher_id": publisher_id,
            "trust_score": trust,
            "stake_usd": cap.stake_usd,
            "price_per_call_usd": cap.price_per_call_usd,
            "supply_chain_admission": admission,
            "search_hint": f"{config.hub_url}/ai-market/v2/search?intent={cap.name}",
            "protocol_version": "v2",
        }

    # ── Self-bond (consumer cost/conduct bond → self-slash enforcement) ──
    @router.post("/self-bond/register")
    async def self_bond_register(body: dict[str, Any], authorization: str = Header(default="")):
        """Register a staked consumer cost/conduct bond (ceiling + client commitment).

        PER-SUBJECT gated in the AGENT namespace (AIMARKET_AGENT_TOKENS): the agent's own
        credential, or the operator token. It used to authenticate agent ids against the
        PUBLISHER registry, so one configured publisher entry made that registry
        authoritative over agent identities — an agent that was not a publisher was locked
        out, and an agent id colliding with a publisher id was authorised by an unrelated
        namespace. Registering a bond encumbers the named agent's already-staked
        collateral and, worse, SETS THE CEILING that /self-bond/slash later measures
        breaches against — under the shared publish token any holder could register a
        hair-thin ceiling on a rival agent and have the operator slash it for ordinary
        spending. Setting another party's slashing threshold is stake-state mutation, so
        it gets the same gate as /supply/stake.

        Both amounts are finiteness-checked here rather than in the callee: the callee's
        guards are ``bond_usd <= 0`` / ``ceiling_usd < 0``, and infinity passes both. An
        infinite ceiling can never be overspent, so it would durably neuter the bond it
        pretends to register.
        """
        agent_id = str(body.get("agent_id", "")).strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="agent_id required")
        _require_subject_credential(authorization, agent_id, (_NS_AGENT,))
        ceiling_usd = _money_arg(body.get("ceiling_usd", 0), "ceiling_usd")
        bond_usd = _money_arg(body.get("bond_usd", 0), "bond_usd", allow_zero=False)
        try:
            return {
                **supply_security.register_self_bond(
                    agent_id,
                    str(body.get("evm_address", "")),
                    ceiling_usd,
                    bond_usd,
                    str(body.get("commitment", "")),
                ),
                "protocol_version": "v2",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/self-bond/slash")
    async def self_bond_slash(body: dict[str, Any], authorization: str = Header(default="")):
        """Slash an agent's self-bond on a declared-ceiling-vs-observed-spend breach.

        ADMIN-only, and grounded in hub-recorded settlement. This endpoint destroys
        ANOTHER party's staked collateral, so the shared publish token — held by every
        publisher on the hub — was the wrong gate: any publisher could burn a rival's
        bond (and, via the federated slash log, its reputation across the mesh) up to
        the spend the ledger happened to have recorded. Moving stake belongs with the
        operator token, like every other slash/settlement route in this file.

        The claimed overspend is additionally capped at the spend the hub ledger
        actually debited for the bonded wallet; if the hub holds no settlement record
        for it, we refuse rather than slash on an unverified number.
        """
        _require_admin(authorization)
        agent_id = str(body.get("agent_id", "")).strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="agent_id required")
        bond = db.self_bond_get(agent_id)
        if not bond:
            raise HTTPException(status_code=404, detail="no self-bond registered")
        # Finiteness-checked like the other money arguments: a garbage string here used
        # to raise out of float() as an unhandled 500 instead of a 400.
        claimed = _money_arg(body.get("observed_spend_usd", 0) or 0, "observed_spend_usd")
        from aimarket_hub.channels import wallet_recorded_spend_usd
        recorded = wallet_recorded_spend_usd(str(bond.get("evm_address", "")))
        if recorded is None:
            raise HTTPException(
                status_code=422,
                detail="cannot slash: no hub-recorded settlement for the bonded wallet "
                       "to validate observed_spend_usd against",
            )
        # Cap the claim at what the hub itself observed — a forged/inflated
        # observed_spend cannot slash beyond recorded settlement.
        observed = min(claimed, recorded)
        try:
            return {
                **supply_security.slash_self_bond(
                    agent_id,
                    observed,
                    str(body.get("evidence", "")),
                ),
                "observed_spend_claimed_usd": claimed,
                "observed_spend_recorded_usd": recorded,
                "protocol_version": "v2",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/self-bond/{agent_id}")
    async def self_bond_get(agent_id: str):
        bond = db.self_bond_get(agent_id)
        if not bond:
            raise HTTPException(status_code=404, detail="no self-bond registered")
        return {**bond, "protocol_version": "v2"}
