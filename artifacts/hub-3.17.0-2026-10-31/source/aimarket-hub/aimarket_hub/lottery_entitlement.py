"""Hub-signed proof that an authenticated local agent may request a lottery work seat."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .signing import Signer

_EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_MAX_TTL_S = 600


def normalize_hub_url(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("hub URL must be absolute HTTP(S)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("hub URL must not contain credentials, query, or fragment")
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = f"{host}:{port}" if port else host
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path.rstrip("/"), "", ""))


def participant_id(hub_url: str, agent_id: str) -> str:
    subject = (agent_id or "").strip()
    if not subject or len(subject) > 160 or any(c in subject for c in "\r\n\t"):
        raise ValueError("agent_id must be a non-empty stable Hub subject")
    raw = f"{normalize_hub_url(hub_url)}\n{subject}".encode("utf-8")
    return "0x" + hashlib.sha256(raw).hexdigest()


def entitlement_canonical(entitlement: dict[str, Any]) -> str:
    claims = {
        "agent_id": str(entitlement.get("agent_id") or ""),
        "expires_at": int(entitlement.get("expires_at") or 0),
        "hub_url": normalize_hub_url(str(entitlement.get("hub_url") or "")),
        "issued_at": int(entitlement.get("issued_at") or 0),
        "nonce": str(entitlement.get("nonce") or ""),
        "participant_id": str(entitlement.get("participant_id") or "").lower(),
        "purpose": "ai-agent-lottery-work-seat-v1",
        "wallet": str(entitlement.get("wallet") or "").lower(),
    }
    return json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def issue_entitlement(
    *, signer: Signer, hub_url: str, agent_id: str, wallet: str, now: int | None = None
) -> dict[str, Any]:
    if not _EVM_ADDRESS.fullmatch(wallet or ""):
        raise ValueError("wallet must be a 20-byte 0x EVM address")
    issued_at = int(time.time()) if now is None else int(now)
    entitlement: dict[str, Any] = {
        "purpose": "ai-agent-lottery-work-seat-v1",
        "hub_url": normalize_hub_url(hub_url),
        "agent_id": (agent_id or "").strip(),
        "participant_id": participant_id(hub_url, agent_id),
        "wallet": wallet.lower(),
        "issued_at": issued_at,
        "expires_at": issued_at + _MAX_TTL_S,
        "nonce": secrets.token_urlsafe(18),
    }
    entitlement["signature"] = {
        "algorithm": "ed25519",
        "public_key": signer.public_key_b64,
        "value": signer.sign_canonical(entitlement_canonical(entitlement)),
    }
    return entitlement
