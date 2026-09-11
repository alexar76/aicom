"""Runtime AI-market participant — trial visitor or paid channel session.

Factory products that invoke Hub/ATLAS capabilities should use this (or the
``aimarket-agent`` SDK), not a hand-rolled ``X-Agent-Key`` client.

Tiers
-----
1. **Trial** — ``X-AIMarket-Sandbox-Visitor`` (no wallet). Free allowance on Hub/ATLAS.
2. **Paid** — when ``AIMARKET_WALLET_KEY`` is set, open (or reuse) a Hub payment channel
   at runtime and send ``X-Payment-Channel`` (+ secret). Prefer a pre-opened channel via
   ``AIMARKET_PAYMENT_CHANNEL`` to avoid locking escrow on every cold start.

This module is vendored into sandbox/Vercel bundles by the factory autofix and taught
to Dev via ``PARTICIPANT_CONTRACT`` / ``aimarket_native_agent.md``.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_HUB = "https://modelmarket.dev"
DEFAULT_ATLAS = "https://atlas.modelmarket.dev"
CACHE_NAME = "aimarket_runtime_channel.json"


def _env(*names: str, default: str = "") -> str:
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return default


def hub_url() -> str:
    return _env("AIMARKET_HUB_URL", "AIMARKET_BASE_URL", "AIFACTORY_AIMARKET_HUB_URL", default=DEFAULT_HUB).rstrip(
        "/"
    )


def invoke_base_url() -> str:
    """Prefer Hub for paid/trial settlement; ATLAS origin only when explicitly forced."""
    forced = _env("ATLAS_BASE_URL", "AIFACTORY_ATLAS_PUBLIC_URL")
    prefer_atlas = _env("AIMARKET_INVOKE_ATLAS", default="0").lower() in ("1", "true", "yes")
    if prefer_atlas and forced:
        return forced.rstrip("/")
    return hub_url() or forced.rstrip("/") or DEFAULT_HUB


def visitor_id() -> str:
    return _env(
        "AIMARKET_SANDBOX_VISITOR",
        "X_AIMARKET_SANDBOX_VISITOR",
        "AIFACTORY_AIMARKET_SANDBOX_VISITOR",
        default="aicom-product-demo",
    )


def wallet_key() -> str:
    return _env("AIMARKET_WALLET_KEY", "AIFACTORY_PRODUCT_WALLET_KEY", "SENTINEL_WALLET_KEY")


def _cache_path() -> Path:
    raw = _env("AIMARKET_CHANNEL_CACHE", default="")
    if raw:
        return Path(raw)
    return Path("/tmp") / CACHE_NAME


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 45.0,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "content-type": "application/json",
            "user-agent": "aicom-aimarket-participant/1.0",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read() or b"{}"
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, {"raw": body.decode("utf-8", "replace")[:800]}
    except urllib.error.HTTPError as exc:
        body = exc.read() or b"{}"
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"error": body.decode("utf-8", "replace")[:800]}
    except Exception as exc:  # noqa: BLE001 — surface to caller as mesh failure
        return 0, {"error": str(exc)}


class AimarketParticipant:
    """Demand-side session: visitor trial and/or runtime payment channel."""

    def __init__(
        self,
        *,
        hub: str | None = None,
        budget_usd: float | None = None,
        agent_key: str | None = None,
    ) -> None:
        self.hub = (hub or hub_url()).rstrip("/")
        self.base_url = invoke_base_url()
        self.budget_usd = float(
            budget_usd
            if budget_usd is not None
            else _env("AIMARKET_CHANNEL_DEPOSIT_USD", "SENTINEL_DAILY_INVOKE_BUDGET_USD", default="0.10")
            or "0.10"
        )
        self.agent_key = agent_key or _env("ATLAS_AGENT_KEY", default="")
        # RLock: ensure_session() is nested under invoke(); parallel advisory gathers must
        # serialize escrow signing so two calls never claim the same on-chain nonce.
        self._lock = threading.RLock()
        self._channel_id = _env("AIMARKET_PAYMENT_CHANNEL", "X_PAYMENT_CHANNEL", "AIFACTORY_AIMARKET_PAYMENT_CHANNEL")
        self._channel_secret = _env(
            "AIMARKET_PAYMENT_CHANNEL_SECRET",
            "X_PAYMENT_CHANNEL_SECRET",
            "AIFACTORY_AIMARKET_PAYMENT_CHANNEL_SECRET",
        )
        self._load_cache()

    def _load_cache(self) -> None:
        if self._channel_id:
            return
        path = _cache_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict) and data.get("channel_id"):
            self._channel_id = str(data["channel_id"])
            self._channel_secret = str(data.get("channel_secret") or self._channel_secret or "")

    def _save_cache(self) -> None:
        if not self._channel_id:
            return
        path = _cache_path()
        try:
            path.write_text(
                json.dumps(
                    {
                        "channel_id": self._channel_id,
                        "channel_secret": self._channel_secret,
                        "hub": self.hub,
                        "saved_at": int(time.time()),
                    }
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def ensure_session(self) -> dict[str, Any]:
        """Open a channel when a wallet is configured and no channel id is known yet.

        Hub may refuse unfunded ``tx_hash`` stubs on live crypto. In that case keep the
        visitor trial headers and surface ``channel_error`` for the operator — do not
        pretend the call is paid.

        Escrow channels expire after 24h on-chain. A stale ``AIMARKET_PAYMENT_CHANNEL``
        then yields Hub 402 ``not open on chain`` forever; drop it and fall back to the
        sandbox visitor so demos stay live until an operator reopens escrow.
        """
        with self._lock:
            if self._channel_id:
                escrow_ch = _env("AIMARKET_ESCROW_CHANNEL", "AIFACTORY_AIMARKET_ESCROW_CHANNEL")
                if escrow_ch and not _escrow_is_open(
                    _env("AIMARKET_RPC_URL", "BASE_RPC", default="https://mainnet.base.org"),
                    _escrow_contract(),
                    escrow_ch,
                ):
                    self._channel_id = ""
                    self._channel_secret = ""
                    try:
                        _cache_path().unlink(missing_ok=True)
                    except OSError:
                        pass
                    return {
                        "mode": "trial",
                        "visitor": visitor_id(),
                        "channel_error": {
                            "error": "escrow_channel_not_open",
                            "escrow_channel": escrow_ch,
                        },
                        "hint": (
                            "On-chain escrow is Settled/Refunded/Expired. Re-run "
                            "scripts/reopen_product_escrow_channel.py for this product, "
                            "then republish so Vercel gets the new channel env."
                        ),
                    }
                return {"mode": "channel", "channel_id": self._channel_id}
            key = wallet_key()
            if not key:
                return {"mode": "trial", "visitor": visitor_id()}
            status, body = _http_json(
                "POST",
                f"{self.hub}/ai-market/v2/channel/open",
                {
                    "deposit_usd": self.budget_usd,
                    "wallet": _env("AIMARKET_WALLET_ADDRESS", default=""),
                    "tx_hash": _env("AIMARKET_DEPOSIT_TX", default=f"runtime-{int(time.time())}"),
                    "chain": _env("AIMARKET_CHAIN", default="base"),
                    "token": _env("AIMARKET_TOKEN", default="USDC"),
                },
            )
            channel = (body.get("channel") if isinstance(body, dict) else None) or {}
            cid = str(channel.get("channel_id") or body.get("channel_id") or "")
            if status == 200 and cid:
                self._channel_id = cid
                self._channel_secret = str(channel.get("channel_secret") or body.get("channel_secret") or "")
                self._save_cache()
                return {"mode": "channel", "channel_id": cid, "opened": True}
            return {
                "mode": "trial",
                "visitor": visitor_id(),
                "channel_error": {"status": status, "body": body},
                "hint": (
                    "Live Hub needs a funded escrow/deposit. Set AIMARKET_PAYMENT_CHANNEL "
                    "after channel/open, or fund AIMARKET_WALLET_KEY and pass a verified tx."
                ),
            }

    def headers(self) -> dict[str, str]:
        info = self.ensure_session()
        out: dict[str, str] = {}
        # Hub rejects visitor + payment channel together (sandbox_conflict).
        if info.get("mode") == "channel" and self._channel_id:
            out["X-Payment-Channel"] = self._channel_id
            if self._channel_secret:
                out["X-Payment-Channel-Secret"] = self._channel_secret
        else:
            visitor = visitor_id()
            if visitor:
                out["X-AIMarket-Sandbox-Visitor"] = visitor
        # Legacy identity only — not billing.
        if self.agent_key:
            out["X-Agent-Key"] = self.agent_key
        return out

    def invoke(
        self,
        capability_id: str,
        input_data: dict[str, Any],
        *,
        product_id: str | None = None,
        source_hub: str | None = None,
        timeout: float = 40.0,
    ) -> dict[str, Any]:
        """POST /ai-market/v2/invoke with participant headers.

        Hub v2 requires ``product_id``. Federated ATLAS SKUs also need
        ``source_hub=https://atlas.modelmarket.dev``.
        """
        url = f"{self.base_url.rstrip('/')}/ai-market/v2/invoke"
        pid = (product_id or _env("AIMARKET_PRODUCT_ID") or "").strip()
        if not pid:
            # atlas.situation.brief@v1 → atlas.products (live catalogue product_id)
            if capability_id.startswith("atlas."):
                pid = "atlas.products"
            else:
                pid = capability_id.split(".", 1)[0]
        body: dict[str, Any] = {
            "product_id": pid,
            "capability_id": capability_id,
            "input": input_data,
        }
        sh = (source_hub or _env("AIMARKET_SOURCE_HUB") or "").strip()
        if not sh and capability_id.startswith("atlas."):
            sh = DEFAULT_ATLAS
        if sh:
            body["source_hub"] = sh
        # Serialize paid escrow invokes (advisory gathers 3 capabilities in parallel).
        with self._lock:
            return self._invoke_locked(url, body, timeout=timeout)

    def _invoke_locked(
        self,
        url: str,
        body: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        spent_nonce: int | None = None
        auth = self._payment_authorization(amount_usd=None)
        if auth:
            body["payment_authorization"] = auth
            spent_nonce = int(auth.get("nonce")) if auth.get("nonce") is not None else None
        status, body_out = _http_json(
            "POST",
            url,
            body,
            headers=self.headers(),
            timeout=timeout,
        )
        # Escrow 402s: wrong nonce / missing auth — re-sign up to twice.
        for _attempt in range(2):
            if not (
                status == 402
                and isinstance(body_out, dict)
                and body_out.get("error") == "payment_authorization_required"
            ):
                break
            needed = body_out.get("needed")
            detail = str(body_out.get("detail") or "")
            import re as _re

            m = _re.search(r"on-chain nonce\s+(\d+)", detail)
            if m:
                self._last_needed_nonce = int(m.group(1))
            try:
                needed_f = float(needed) if needed is not None else 0.06
            except (TypeError, ValueError):
                needed_f = 0.06
            auth = self._payment_authorization(amount_usd=needed_f)
            if not auth:
                break
            body["payment_authorization"] = auth
            spent_nonce = int(auth.get("nonce")) if auth.get("nonce") is not None else spent_nonce
            status, body_out = _http_json(
                "POST",
                url,
                body,
                headers=self.headers(),
                timeout=timeout,
            )
        if status == 200 and isinstance(body_out, dict):
            if spent_nonce is not None:
                # Only wait when explicitly needed (multi-call clients). Single advisory
                # invokes must stay inside Vercel/live-gate budgets.
                wait_s = float(_env("AIMARKET_NONCE_WAIT_S", default="0") or "0")
                if wait_s > 0:
                    self._await_nonce_past(spent_nonce, wait_s=wait_s)
            if hasattr(self, "_last_needed_nonce"):
                delattr(self, "_last_needed_nonce")
            return body_out
        return {
            "ok": False,
            "error": f"Status {status}",
            "detail": body_out,
            "url": url,
        }

    def _await_nonce_past(self, spent_nonce: int, *, wait_s: float = 12.0) -> None:
        """Block until on-chain nonce advances past a spent debit (or timeout)."""
        escrow_ch = _env("AIMARKET_ESCROW_CHANNEL", "AIFACTORY_AIMARKET_ESCROW_CHANNEL")
        if not escrow_ch:
            return
        escrow = _escrow_contract()
        rpc = _env("AIMARKET_RPC_URL", "BASE_RPC", default="https://1rpc.io/base")
        deadline = time.time() + wait_s
        while time.time() < deadline:
            try:
                if _escrow_nonce(rpc, escrow, escrow_ch) > int(spent_nonce):
                    return
            except Exception:
                pass
            time.sleep(0.6)

    def _payment_authorization(self, *, amount_usd: float | None) -> dict[str, Any] | None:
        """Sign EIP-712 DebitAuthorization when escrow channel + wallet key are present."""
        key = wallet_key()
        escrow_ch = _env("AIMARKET_ESCROW_CHANNEL", "AIFACTORY_AIMARKET_ESCROW_CHANNEL")
        if not key or not escrow_ch or not self._channel_id:
            return None
        try:
            from eth_account import Account
            from eth_account.messages import encode_typed_data
        except Exception:
            return None
        escrow = _escrow_contract()
        hub_addr = _env("AIMARKET_ESCROW_HUB_ADDRESS", default="0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1")
        token = _env("AIMARKET_USDC", default="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        rpc = _env("AIMARKET_RPC_URL", "BASE_RPC", default="https://mainnet.base.org")
        chain_id = int(_env("AIMARKET_CHAIN_ID", default="8453") or "8453")
        # Read on-chain nonce via eth_call (no cast dependency in serverless).
        try:
            nonce = _escrow_nonce(rpc, escrow, escrow_ch)
        except Exception:
            nonce = 0
        # Prefer hub-told nonce when a prior attempt already revealed it.
        if amount_usd is not None and hasattr(self, "_last_needed_nonce"):
            try:
                nonce = int(getattr(self, "_last_needed_nonce"))
            except (TypeError, ValueError):
                pass
        usd = float(amount_usd if amount_usd is not None else 0.06)
        amount_units = max(1, int(round(usd * 1_000_000)))
        import secrets as _secrets

        receipt_id = "0x" + _secrets.token_hex(32)
        deadline = int(time.time()) + 3600
        typed = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "DebitAuthorization": [
                    {"name": "channelId", "type": "bytes32"},
                    {"name": "hub", "type": "address"},
                    {"name": "token", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "receiptId", "type": "bytes32"},
                    {"name": "nonce", "type": "uint256"},
                    {"name": "deadline", "type": "uint256"},
                ],
            },
            "primaryType": "DebitAuthorization",
            "domain": {
                "name": "AIMarketEscrow",
                "version": "1",
                "chainId": chain_id,
                "verifyingContract": escrow,
            },
            "message": {
                "channelId": escrow_ch,
                "hub": hub_addr,
                "token": token,
                "amount": amount_units,
                "receiptId": receipt_id,
                "nonce": int(nonce),
                "deadline": deadline,
            },
        }
        signable = encode_typed_data(full_message=typed)
        signed = Account.from_key(key).sign_message(signable)
        sig = signed.signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig
        return {
            "channelId": escrow_ch,
            "hub": hub_addr,
            "token": token,
            "amount": int(amount_units),
            "receiptId": receipt_id,
            "nonce": int(nonce),
            "deadline": deadline,
            "signature": sig,
        }

    def close(self) -> dict[str, Any]:
        if not self._channel_id:
            return {"skipped": True}
        status, body = _http_json(
            "POST",
            f"{self.hub}/ai-market/v2/channel/close",
            {"channel_id": self._channel_id},
        )
        return {"status": status, "body": body}


def _eth_call(rpc: str, to: str, data: str) -> str:
    """JSON-RPC eth_call with Base public RPC fallbacks. Returns hex result or raises."""
    import json as _json

    payload = _json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]}
    ).encode()
    rpcs = [
        rpc,
        "https://1rpc.io/base",
        "https://mainnet.base.org",
        "https://base.llamarpc.com",
    ]
    last_err: Exception | None = None
    for endpoint in rpcs:
        if not endpoint:
            continue
        try:
            req = urllib.request.Request(
                endpoint,
                data=payload,
                method="POST",
                headers={
                    "content-type": "application/json",
                    "user-agent": "aicom-aimarket-participant/1.0",
                    "accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                parsed = _json.loads(resp.read())
            if parsed.get("error"):
                last_err = RuntimeError(str(parsed["error"])[:200])
                continue
            return str(parsed.get("result") or "0x")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if last_err:
        raise last_err
    return "0x"


def _escrow_nonce(rpc: str, escrow: str, channel_id: str) -> int:
    """channels(bytes32) → nonce is the 8th static word (index 7)."""
    try:
        from eth_utils import keccak

        sel = keccak(text="channels(bytes32)")[:4].hex()
    except Exception:
        sel = "7a7ebd7b"
    cid = channel_id[2:] if channel_id.startswith("0x") else channel_id
    data = "0x" + sel + cid.rjust(64, "0")
    result = _eth_call(rpc, escrow, data)
    raw = result[2:] if result.startswith("0x") else result
    if len(raw) < 64 * 8:
        return 0
    word = raw[64 * 7 : 64 * 8]
    return int(word, 16)


#: The canonical registry, read rather than repeated.
#:
#: This module used to carry the Base escrow address as a hardcoded DEFAULT in three
#: places. The 2026-08 audit moved every consumer onto config/deployments/base-mainnet.json
#: precisely so a redeploy is a ONE-file edit — but its drift test only ever scanned
#: chain_net.py, the monitor's copy and argus's networks.ts, so this fourth consumer kept a
#: stale address and nothing noticed. The 2026-09-04 escrow redeploy is what surfaced it.
_REGISTRY_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "config" / "deployments" / "base-mainnet.json",
    Path(__file__).resolve().parents[1] / "aimarket-hub" / "aimarket_hub" / "deployments" / "base-mainnet.json",
)


def _registry_address(name: str) -> str:
    """A deployed address from the registry, or "" when it cannot be read.

    Returns empty rather than guessing: a WRONG escrow address is worse than none — the
    caller's `_escrow_is_open` / `_escrow_nonce` probe would read a contract that is not
    the one holding the channel and conclude the channel had closed.
    """
    for candidate in _REGISTRY_CANDIDATES:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        addr = ((data.get("contracts") or {}).get(name) or "").strip()
        if addr:
            return addr
    return ""


def _escrow_contract() -> str:
    """The escrow this participant should talk to: env override, else the registry."""
    return _env("AIMARKET_ESCROW_CONTRACT", default="") or _registry_address("AIMarketEscrow")


def _escrow_is_open(rpc: str, escrow: str, channel_id: str) -> bool:
    """True when AIMarketEscrow.isChannelOpen(channelId) — Open and not past expiresAt.

    Only a conclusive on-chain ``false`` forces trial fallback. Empty/rate-limited RPC
    replies (common from Vercel IP ranges) must NOT drop a healthy paid session — that
    was shipping soft-mesh ``payment_required`` after a green live_gate.
    """
    if not channel_id:
        return False
    try:
        from eth_utils import keccak

        sel = keccak(text="isChannelOpen(bytes32)")[:4].hex()
    except Exception:
        sel = "5788680f"  # keccak("isChannelOpen(bytes32)")[:4]
    cid = channel_id[2:] if channel_id.startswith("0x") else channel_id
    data = "0x" + sel + cid.rjust(64, "0")
    try:
        result = _eth_call(rpc, escrow, data)
    except Exception:
        return True
    raw = (result[2:] if isinstance(result, str) and result.startswith("0x") else str(result or "")).strip()
    if not raw or set(raw) <= {"0"}:
        # Inconclusive (rate limit / empty eth_call) — keep the configured channel.
        return True
    try:
        return int(raw[-64:], 16) != 0
    except ValueError:
        return True


# Module-level helper used by autofixed atlas clients.
_default: AimarketParticipant | None = None
_default_lock = threading.Lock()


def get_participant() -> AimarketParticipant:
    global _default
    with _default_lock:
        if _default is None:
            _default = AimarketParticipant()
        return _default
