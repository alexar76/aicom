"""Mandates (aimarket-protocol/mandates.md): registration, owners, revocation, and subcontract
job trees.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from aimarket_hub import credits, mandates
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.mandates import MandateStore
from aimarket_hub.subcontract import JobStore


def register(
    *,
    _TRUSTED_PROXIES: frozenset[str],
    _check_invoke_rate: Callable[..., Any],
    _is_admin_bearer: Callable[..., Any],
    hub_credits: CreditsLedger,
    hub_jobs: JobStore,
    hub_mandates: MandateStore,
    router: APIRouter,
) -> SimpleNamespace:
    """Attach the /mandates and /jobs routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _client_address,
    )

    # ── Mandates (aimarket-protocol/mandates.md §3-5) ────────────────────────
    def _mandate_refusal(exc: mandates.MandateError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body())

    async def _json_body(request: Request, limit: int = mandates.MAX_DOC_BYTES + 4096) -> Any:
        raw = await request.body()
        if len(raw) > limit:
            raise mandates.MandateError(413, "mandate_malformed", f"body exceeds {limit} bytes")  # §7 lists 413
        try:
            return json.loads(raw or b"null")
        except ValueError as exc:
            raise mandates.MandateError(400, "mandate_malformed", "body is not JSON") from exc

    def _api_key_account(x_api_key: str | None) -> str:
        if not credits.enabled() or not x_api_key:
            return ""
        return hub_credits.resolve(x_api_key)

    @router.post("/mandates")
    async def register_mandate(request: Request):
        """Register a mandate (§3.5). The document authenticates itself; the hub only
        refuses one whose root nobody on this hub has agreed to fund."""
        if not _check_invoke_rate(_client_address(request, _TRUSTED_PROXIES) or "anonymous"):
            return JSONResponse(status_code=429, content={"success": False, "error": "rate_limited"})
        try:
            document = await _json_body(request)
            return {**hub_mandates.register(document), "protocol_version": "v2"}
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)

    @router.get("/mandates/owners")
    async def list_mandate_owners(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        account = _api_key_account(x_api_key)
        if not account:
            return JSONResponse(status_code=401, content={"success": False, "error": "invalid_api_key"})
        return {"account_id": account, "owners": hub_mandates.owners_of(account), "protocol_version": "v2"}

    # ── Owner approvals (§5.6) ───────────────────────────────────────────────
    # Registered before /mandates/{digest:path}, which would otherwise take these paths.

    @router.get("/mandates/approvals")
    async def list_mandate_approvals(
        status: str = "",
        limit: int = 50,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """The funding account's approval requests, newest first — what its owner has to
        answer (``?status=pending``) and what was answered."""
        account = _api_key_account(x_api_key)
        if not account:
            return JSONResponse(status_code=401, content={"success": False, "error": "invalid_api_key"})
        if status and status not in (mandates.APPROVAL_PENDING, mandates.APPROVAL_APPROVED, mandates.APPROVAL_DENIED,
                                     mandates.APPROVAL_USED, mandates.APPROVAL_EXPIRED):
            return JSONResponse(status_code=400, content={
                "success": False, "error": "mandate_malformed",
                "detail": "status is pending, approved, denied, used or expired"})
        rows = hub_mandates.approvals_for(account, status=status, limit=limit)
        return {"account_id": account,
                "approvals": [mandates.approval_public(r, base_url=hub_mandates.hub_origin) for r in rows],
                "protocol_version": "v2"}

    @router.get("/mandates/approvals/{approval_id}")
    async def mandate_approval(approval_id: str):
        """One request. Its id is an unguessable capability (like a job id): the agent hands
        it to its owner, and either can read where it stands."""
        row = hub_mandates.approval(approval_id)
        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "approval_unknown"})
        return {**mandates.approval_public(row, base_url=hub_mandates.hub_origin), "protocol_version": "v2"}

    @router.post("/mandates/approvals/{approval_id}")
    async def decide_mandate_approval(
        approval_id: str,
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """An owner's answer: ``{decision, by, t, n, s}`` signed by an owner DID of the funding
        account, or ``{"decision": "deny"}`` with the account's API key."""
        if not _check_invoke_rate(_client_address(request, _TRUSTED_PROXIES) or "anonymous"):
            return JSONResponse(status_code=429, content={"success": False, "error": "rate_limited"})
        try:
            payload = await _json_body(request, limit=4096)
            if not isinstance(payload, dict):
                raise mandates.MandateError(400, "mandate_malformed", "body must be an object")
            signed = bool(payload.get("s"))
            account = "" if signed else _api_key_account(x_api_key)
            if not signed and not account:
                raise mandates.MandateError(
                    401, "mandate_proof_invalid",
                    "sign the decision with an owner key ({decision, by, t, n, s}), or deny with X-API-Key",
                )
            result = hub_mandates.decide_approval(
                approval_id, decision=str(payload.get("decision") or ""), by=str(payload.get("by") or ""),
                proof={"t": payload.get("t"), "n": payload.get("n"), "s": payload.get("s")} if signed else None,
                account_id=account,
            )
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)
        if not result.get("unchanged"):
            hub_mandates.notify_decision(result)
        return {**result, "url": f"{hub_mandates.hub_origin}/ai-market/v2/mandates/approvals/{approval_id}",
                "protocol_version": "v2"}

    # ── Where owners hear about approval requests (owner_notify.py) ─────────────
    from aimarket_hub import owner_notify

    hub_notify_store = owner_notify.NotifyStore(hub_mandates._conn)
    hub_notifier = owner_notify.OwnerNotifier(hub_notify_store, hub_mandates)
    hub_mandates.request_listeners.append(hub_notifier.on_requested)
    hub_mandates.decision_listeners.append(hub_notifier.on_decided)

    def _notify_account(x_api_key: str | None) -> str | JSONResponse:
        account = _api_key_account(x_api_key)
        if not account:
            return JSONResponse(status_code=401, content={
                "success": False, "error": "invalid_api_key",
                "detail": "notification channels belong to a funding account: send its X-API-Key"})
        return account

    @router.get("/mandates/notify")
    async def list_notify_channels(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        account = _notify_account(x_api_key)
        if isinstance(account, JSONResponse):
            return account
        return {"account_id": account, "channels": [owner_notify.public(c) for c in hub_notify_store.list(account)],
                "telegram_bot": owner_notify.hub_bot_name() or None, "protocol_version": "v2"}

    @router.post("/mandates/notify")
    async def add_notify_channel(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Add a channel: ``{"kind": "telegram", "chat_id": …}``, ``{"kind": "slack", "webhook_url": …}``,
        ``{"kind": "jira", "base_url", "email", "api_token", "project_key"}`` or
        ``{"kind": "webhook", "url", "secret"}``."""
        account = _notify_account(x_api_key)
        if isinstance(account, JSONResponse):
            return account
        try:
            payload = await _json_body(request, limit=8192)
            kind, target = owner_notify.parse_channel(payload)
            row = hub_notify_store.add(account, kind, target)
        except owner_notify.NotifyConfigError as exc:
            return JSONResponse(status_code=400, content={"success": False, "error": "channel_invalid",
                                                          "detail": str(exc)})
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)
        return JSONResponse(status_code=201, content={**owner_notify.public(row), "protocol_version": "v2"})

    @router.delete("/mandates/notify/{channel_id}")
    async def delete_notify_channel(channel_id: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        account = _notify_account(x_api_key)
        if isinstance(account, JSONResponse):
            return account
        if not hub_notify_store.delete(account, channel_id):
            return JSONResponse(status_code=404, content={"success": False, "error": "channel_unknown"})
        return {"deleted": channel_id, "protocol_version": "v2"}

    @router.post("/mandates/notify/{channel_id}/test")
    async def test_notify_channel(channel_id: str, request: Request,
                                  x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        """Send a test message now and answer what the channel said — set up and see."""
        if not _check_invoke_rate(_client_address(request, _TRUSTED_PROXIES) or "anonymous"):
            return JSONResponse(status_code=429, content={"success": False, "error": "rate_limited"})
        account = _notify_account(x_api_key)
        if isinstance(account, JSONResponse):
            return account
        channel = hub_notify_store.get(account, channel_id)
        if channel is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "channel_unknown"})
        from starlette.concurrency import run_in_threadpool

        ok, detail = await run_in_threadpool(hub_notifier.send_test, channel)
        return {"delivered": ok, "detail": detail, "channel": owner_notify.public(
            hub_notify_store.get(account, channel_id) or channel), "protocol_version": "v2"}

    @router.get("/mandates/{digest:path}")
    async def mandate_status(
        digest: str,
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_proof: str | None = Header(default=None, alias=mandates.PROOF_HEADER),
    ):
        """Validity and chain for anyone holding the digest; usage only for the chain's keys
        or the funding account (§3.5)."""
        row = hub_mandates.row(digest)
        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "mandate_unknown"})
        # Status of the mandate AS A CHAIN: one whose parent was revoked, or that has expired,
        # cannot be used however clean its own row looks.
        status, reason = hub_mandates.status_of(digest)
        chain_digests: list[str] = []
        cursor = digest
        while cursor and len(chain_digests) <= mandates.MAX_CHAIN:
            chain_digests.append(cursor)
            cursor = (hub_mandates.row(cursor) or {}).get("parent_digest") or ""
        out: dict[str, Any] = {
            "digest": digest,
            "status": status,
            "issuer": row["issuer"],
            "subject": row["subject"],
            "parent": row["parent_digest"] or None,
            "root": row["root_digest"],
            "chain": list(reversed(chain_digests)),
            "depth": row["depth"],
            "valid_from": row["valid_from"],
            "valid_until": row["valid_until"],
            "revoked_at": row["revoked_at"] or None,
            "protocol_version": "v2",
        }
        if reason:
            out["status_reason"] = reason
        try:
            entitled = False
            account = _api_key_account(x_api_key)
            if account:
                owner = hub_mandates.owner_account(row["root_issuer"])
                entitled = owner is not None and owner[0] == account
            elif x_proof:
                leaf = hub_mandates.get(digest)
                if leaf is not None:
                    # Any key in the chain may read its usage (§3.5): the owner and every
                    # re-delegating agent, not only the key the mandate was issued to.
                    hub_mandates.verify_request(leaf=leaf, proof_header=x_proof, method="GET",
                                                path=mandates.signed_path(request), body=b"",
                                                signers=hub_mandates.chain_keys(digest))
                    entitled = True
            if entitled:
                out["usage"] = hub_mandates.usage(digest)
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)
        return out

    @router.post("/mandates/owners")
    async def link_mandate_owner(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str = Header(default=""),
    ):
        """Link an owner DID to the credit account that pays for its mandates (§4).

        The first owner needs the account's API key and the DID's own signature. Every later
        change also needs an existing owner's signature (`authorization` in the body) — or the
        operator's admin token, the recovery path for an owner who has lost every key."""
        account = _api_key_account(x_api_key)
        if not account:
            return JSONResponse(status_code=401, content={
                "success": False, "error": "invalid_api_key",
                "detail": "linking an owner needs the funding account's X-API-Key",
            })
        try:
            payload = await _json_body(request)
            if not isinstance(payload, dict):
                raise mandates.MandateError(400, "mandate_malformed", "body must be an object")
            linked = hub_mandates.link_owner(
                account_id=account, did=str(payload.get("did") or ""), proof=payload.get("proof"),
                require_mandate=bool(payload.get("require_mandate", False)),
                authorization=payload.get("authorization"), admin=_is_admin_bearer(authorization),
            )
            return {**linked, "protocol_version": "v2"}
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)

    @router.post("/mandates/owners/unlink")
    async def unlink_mandate_owner(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str = Header(default=""),
    ):
        """Unlink an owner (§4): the account's API key AND an owner's signature (or the admin
        token). The key alone would let whoever holds a leaked key delete the row that carries
        require_mandate and pay with the bare key again."""
        account = _api_key_account(x_api_key)
        if not account:
            return JSONResponse(status_code=401, content={"success": False, "error": "invalid_api_key"})
        try:
            payload = await _json_body(request)
            if not isinstance(payload, dict):
                raise mandates.MandateError(400, "mandate_malformed", "body must be an object")
            return {**hub_mandates.unlink_owner(
                account_id=account, did=str(payload.get("did") or ""),
                authorization=payload.get("authorization"), admin=_is_admin_bearer(authorization),
            ), "protocol_version": "v2"}
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)

    @router.post("/mandates/revoke")
    async def revoke_mandate(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ):
        """Revoke a mandate and everything below it (§5.5): signed by an issuer in its chain,
        or by the funding account's API key as the owner's kill switch."""
        try:
            payload = await _json_body(request)
            if not isinstance(payload, dict) or not isinstance(payload.get("digest"), str):
                raise mandates.MandateError(400, "mandate_malformed", "body must be {digest, ...}")
            account = _api_key_account(x_api_key)
            if account and not payload.get("s"):
                result = hub_mandates.revoke(digest=payload["digest"], account_id=account)
            else:
                result = hub_mandates.revoke(
                    digest=payload["digest"], by=str(payload.get("by") or ""),
                    proof={"t": payload.get("t"), "n": payload.get("n"), "s": payload.get("s")},
                )
            return {**result, "protocol_version": "v2"}
        except mandates.MandateError as exc:
            return _mandate_refusal(exc)

    @router.get("/jobs/{job_id}")
    async def job_tree(job_id: str):
        """A subcontracting job's tree (§6.4). The id is an unguessable capability."""
        if not re.fullmatch(r"job_[0-9a-f]{24}", job_id or ""):
            return JSONResponse(status_code=404, content={"success": False, "error": "job_unknown"})
        tree = hub_jobs.tree(job_id)
        if tree is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "job_unknown"})
        return {**tree, "protocol_version": "v2"}

    return SimpleNamespace(
        _api_key_account=_api_key_account,
    )
