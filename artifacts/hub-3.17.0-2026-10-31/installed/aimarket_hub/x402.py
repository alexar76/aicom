"""x402 interoperability — speak the payment dialect the rest of the agent web speaks.

Why this exists: x402 became a Linux Foundation standard in July 2026, and every official
SDK, every Bazaar index and a growing set of edge platforms speak it. This hub already
answers `402` with everything a payer needs — a price, a recipient, a chain — but in its own
shape, which no x402 client can read. Emitting the same facts in x402's format costs
nothing and makes the hub reachable by clients nobody here has to write.

**Version.** x402 shipped V2 (`x402Version: 2`) and moved its payload out of the response
body into a base64 `PAYMENT-REQUIRED` header; V1 kept it in the body under `accepts`. Live
facilitators still advertise V1 kinds, so this module emits BOTH: the V2 header, and the V1
fields merged additively into the body the hub already returns. An existing consumer reading
`success` / `error` / `detail` / `needed` sees no change.

**Accepting payment.** A `PAYMENT-SIGNATURE` / `X-PAYMENT` is honoured on the
market rail (`aimarket_hub.settle`): the buyer pays USDC on-chain to the
listing's `payout_address`, and this hub verifies the transfer. It never
custodies the funds, never books a receivable, and never silently credits
a publisher. A signed authorization without a chain receipt is not a
payment — only the chain is.

The `payTo` on a 402 and in `/discovery/resources` is the **seller**, not
the platform wallet. See `settle.seller_pay_to`.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

X402_VERSION = 2

# CAIP-2 is how V2 names a chain. V1 used bare strings ("base"), which is why both appear.
CAIP2_BY_CHAIN: dict[str, str] = {
    "base": "eip155:8453",
    "base-sepolia": "eip155:84532",
    "ethereum": "eip155:1",
    "arbitrum": "eip155:42161",
    "optimism": "eip155:10",
    "polygon": "eip155:137",
}

# Decimals and EIP-712 domain of the assets this hub prices in. `extra.name`/`extra.version`
# are the token's EIP-712 domain fields — a payer needs them to sign transferWithAuthorization,
# and getting them wrong produces a signature the token contract will not honour.
ASSET_PROFILES: dict[tuple[str, str], dict[str, Any]] = {
    # `extra.name` MUST be the token's own EIP-712 domain name, read from the contract —
    # NOT the ticker. Base mainnet USDC calls itself "USD Coin"; Base Sepolia USDC calls
    # itself "USDC". They differ, and the difference is invisible until a payer's
    # transferWithAuthorization signature is rejected by the token contract, which is the
    # last place anyone looks. Both values below were read on-chain via eth_call name()
    # and version() on 2026-08-28.
    ("base", "USDC"): {
        "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "decimals": 6,
        "extra": {"name": "USD Coin", "version": "2"},
    },
    ("ethereum", "USDC"): {
        "address": "0xA0b86991c6218b36c1d19d4a2e9Eb0cE3606eB48",
        "decimals": 6,
        "extra": {"name": "USD Coin", "version": "2"},
    },
    ("base-sepolia", "USDC"): {
        "address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "decimals": 6,
        "extra": {"name": "USDC", "version": "2"},
    },
}


def _flag(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def enabled() -> bool:
    """On unless switched off, and only when this hub can name an asset.

    A listing supplies its own ``payTo`` (the seller). The dialect can speak
    without a global platform recipient; an offer still needs a payee, which
    ``payment_requirements(pay_to=…)`` enforces.
    """
    if _flag("AIMARKET_X402_ENABLED", "1").lower() in ("0", "false", "no"):
        return False
    return asset_profile() is not None


def recipient() -> str:
    return _flag("AIMARKET_X402_PAY_TO") or _flag("AIMARKET_PAYMENT_RECIPIENT")


def chain() -> str:
    return (_flag("AIMARKET_X402_CHAIN") or _flag("AIMARKET_PAYMENT_CHAIN") or "base").lower()


def asset_symbol() -> str:
    return (_flag("AIMARKET_X402_ASSET_SYMBOL") or "USDC").upper()


def asset_profile() -> dict[str, Any] | None:
    from aimarket_hub import realm

    profile = ASSET_PROFILES.get((chain(), asset_symbol()))
    override = _flag("AIMARKET_X402_ASSET")
    if profile and override:
        profile = {**profile, "address": override}
    elif override:
        profile = {"address": override, "decimals": int(_flag("AIMARKET_X402_ASSET_DECIMALS", "6")), "extra": {}}
    if profile:
        profile = {**profile, 'extra': dict(profile.get('extra') or {})}
        if _flag('AIMARKET_X402_EIP712_NAME'): profile['extra']['name'] = _flag('AIMARKET_X402_EIP712_NAME')
        if _flag('AIMARKET_X402_EIP712_VERSION'): profile['extra']['version'] = _flag('AIMARKET_X402_EIP712_VERSION')
    if realm.is_uni():
        # The bubble may not advertise a real token. The table's default IS real Base USDC,
        # so an unconfigured UNI hub would hand every participant a payment offer that
        # settles on mainnet — an inside agent with a funded real key could sign it and the
        # money would leave the simulation. Refuse to advertise anything until the operator
        # names the bubble's own token.
        if profile is None or realm.names_real_asset(profile.get("address", "")):
            logger.warning(
                "x402: refusing to advertise payment terms in the UNI realm without a "
                "bubble-local asset — set AIMARKET_X402_ASSET to the simulated token",
            )
            return None
    return profile


def usd_to_atomic(price_usd: float, decimals: int) -> str:
    """USD price → atomic token units, as a decimal string.

    Assumes a 1:1 USD-pegged stablecoin, which is true for the USDC pricing this hub uses and
    is stated rather than hidden: a non-pegged asset would need a quote, and this function is
    the wrong place to invent one. Rounds up, so a sub-unit price is never advertised as free.
    """
    try:
        units = float(price_usd) * (10 ** decimals)
    except (TypeError, ValueError):
        return "0"
    return str(max(0, -(-int(units * 1_000_000) // 1_000_000)))


def caip2() -> str:
    """CAIP-2 id of the chain this hub settles on.

    In the bubble it is derived from the private chain id rather than read from the table:
    the table maps `base` to `eip155:8453`, and publishing that inside UNI would be an
    invitation to pay on a chain the bubble cannot reach — which is the same leak as the
    asset one, in the other field.
    """
    from aimarket_hub import realm

    if realm.is_uni():
        return f"eip155:{realm.uni_chain_id()}"
    return CAIP2_BY_CHAIN.get(chain(), "")


def payment_requirements(price_usd: float, pay_to: str | None = None) -> list[dict[str, Any]]:
    """The `accepts` array — how this listing will take money for one call.

    ``payTo`` is the seller. A missing payee is not replaced by the platform
    wallet: that would silently reroute a sale.

    ``pay_to`` distinguishes two different things, and conflating them was a hole:
    ``None`` means "this offer is not about one listing" — a bare hub 402 — and
    falls back to the operator's own wallet, while ``""`` means "this listing has
    NOBODY to pay" and must produce no offer at all. Treating both as falsy sent
    a buyer to the platform wallet for a sale the hub then refused to settle,
    because ``settle.terms_for`` returns None for the very same listing.
    """
    profile = asset_profile()
    payee = (recipient() if pay_to is None else pay_to).strip()
    if not profile or not payee:
        return []
    caip2_id = caip2()
    if not caip2_id:
        return []
    entry: dict[str, Any] = {
        "scheme": "exact",
        "network": caip2_id,
        "amount": usd_to_atomic(price_usd, profile["decimals"]),
        "asset": profile["address"],
        "payTo": payee,
        "maxTimeoutSeconds": int(_flag("AIMARKET_X402_TIMEOUT_S", "300")),
    }
    if profile.get("extra"):
        entry["extra"] = profile["extra"]
    return [entry]


def payment_required_v2(
    price_usd: float, resource_url: str, description: str = "", mime_type: str = "application/json",
    pay_to: str | None = None,
) -> dict[str, Any] | None:
    """The V2 `PaymentRequired` object carried in the PAYMENT-REQUIRED header."""
    accepts = payment_requirements(price_usd, pay_to=pay_to)
    if not accepts:
        return None
    return {
        "x402Version": X402_VERSION,
        "error": "Payment required",
        "resource": {
            "url": resource_url,
            "description": description or "AIMarket capability invocation",
            "mimeType": mime_type,
        },
        "accepts": accepts,
    }


def encode_header(payload: dict[str, Any]) -> str:
    """Base64 of the compact JSON — the wire form of PAYMENT-REQUIRED."""
    return base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")


def v1_body_fields(
    price_usd: float, resource_url: str, description: str = "", pay_to: str | None = None,
) -> dict[str, Any]:
    """V1 fields to merge into an existing 402 body, for clients still on V1.

    Purely additive: V1 named the amount `maxAmountRequired` and the chain by bare string,
    and carried resource/description per entry rather than hoisted.
    """
    profile = asset_profile()
    payee = (pay_to or recipient() or "").strip()
    if not profile or not payee:
        return {}
    entry = {
        "scheme": "exact",
        "network": chain(),
        "maxAmountRequired": usd_to_atomic(price_usd, profile["decimals"]),
        "asset": profile["address"],
        "payTo": payee,
        "resource": resource_url,
        "description": description or "AIMarket capability invocation",
        "mimeType": "application/json",
        "outputSchema": None,
        "maxTimeoutSeconds": int(_flag("AIMARKET_X402_TIMEOUT_S", "300")),
    }
    if profile.get("extra"):
        entry["extra"] = profile["extra"]
    return {"x402Version": 1, "accepts": [entry]}


def bazaar_item(cap: Any, hub_url: str, last_updated: str) -> dict[str, Any] | None:
    """One entry in a Bazaar-compatible `/discovery/resources` index.

    The six fields below are the interop contract every official x402 SDK deserializes:
    `resource`, `type`, `x402Version`, `accepts`, `lastUpdated`, and optional `metadata`.
    Live indexes add their own fields freely — Coinbase nests under `extensions.bazaar`,
    PayAI flattens presentation fields — so extras are safe, omissions are not.
    """
    from aimarket_hub.settle import seller_pay_to

    price = float(getattr(cap, "price_per_call_usd", 0) or 0)
    payee = seller_pay_to(cap, operator_pay_to=recipient())
    accepts = payment_requirements(price, pay_to=payee)
    if not accepts:
        return None
    cap_id = getattr(cap, "capability_id", "")
    return {
        "resource": f"{hub_url.rstrip('/')}/ai-market/v2/invoke#{cap_id}",
        "type": "http",
        "x402Version": X402_VERSION,
        "accepts": accepts,
        "lastUpdated": last_updated,
        "description": (getattr(cap, "description", "") or "")[:300],
        "metadata": {
            "capability_id": cap_id,
            "product_id": getattr(cap, "product_id", ""),
            "source_hub": getattr(cap, "source_hub", ""),
            "protocol": "aimarket/v2",
            "payout_address": payee,
        },
    }


# ── ERC-8004 identity declaration ────────────────────────────────────
# Separate concern from x402, kept here because both are "how this hub presents itself to
# standards it does not own". ERC-8004 gives an agent a portable on-chain identity: an
# ERC-721 token whose tokenId is the agentId and whose tokenURI is the agentURI.
#
# Registry addresses verified on-chain 2026-08-28 against Ethereum mainnet and Base mainnet
# public RPC — identical addresses on both (and on ~23 further chains per the canonical repo).
# ValidationRegistry is deliberately absent: it has NO published canonical deployment on any
# chain, and eth_getCode at the obvious vanity guess returns empty. Anyone needing validation
# attestations today must deploy their own instance.
ERC8004_REGISTRIES: dict[str, dict[str, str]] = {
    "mainnet": {
        "identity": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        "reputation": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
    },
    "testnet": {
        "identity": "0x8004A818BFB912233c491871b3d84c89A494BD9e",
        "reputation": "0x8004B663056A597Dffe9eCcC1965A193B7388713",
    },
}


def erc8004_declaration(hub_url: str) -> dict[str, Any] | None:
    """What this hub claims about its ERC-8004 identity, or None if it claims nothing.

    Declarative only: the hub reports an agentId its operator says it owns and the registry
    that id lives in. **This function performs no chain call and verifies nothing.** A reader
    who cares whether the claim is true must check the registry itself — which is the point
    of the identity being on-chain, and is why this hub does not pretend to have checked.

    Registration is an on-chain transaction from the operator's own wallet and is not
    something a server does on its owner's behalf.
    """
    from aimarket_hub import realm

    agent_id = _flag("AIMARKET_ERC8004_AGENT_ID")
    if not agent_id:
        return None
    if realm.is_uni():
        # An ERC-8004 declaration names registries on a real chain and an agentId a reader is
        # invited to resolve there. Publishing it from inside the bubble points outward — the
        # same leak as a mainnet asset, in an identity field instead of a money one.
        logger.warning(
            "x402: not publishing an ERC-8004 declaration in the UNI realm — its registries "
            "live on a real chain",
        )
        return None
    network = (_flag("AIMARKET_ERC8004_NETWORK", "mainnet")).lower()
    registries = ERC8004_REGISTRIES.get(network)
    if not registries:
        return None
    caip2 = CAIP2_BY_CHAIN.get(_flag("AIMARKET_ERC8004_CHAIN", "base").lower())
    declaration: dict[str, Any] = {
        "agent_id": agent_id,
        "chain": caip2 or _flag("AIMARKET_ERC8004_CHAIN", "base"),
        "identity_registry": registries["identity"],
        "reputation_registry": registries["reputation"],
        "agent_uri": _flag("AIMARKET_ERC8004_AGENT_URI") or f"{hub_url.rstrip('/')}/.well-known/ai-market.json",
        "verified_by_this_hub": False,
        "note": (
            "Self-declared. Read the identity registry to confirm this agentId resolves to "
            "this operator; this hub asserts the claim and does not check it."
        ),
    }
    return declaration


# ── Accepting a payment ──────────────────────────────────────────────────────

PAYMENT_HEADERS = ("PAYMENT", "X-PAYMENT", "PAYMENT-SIGNATURE")


def accept_enabled() -> bool:
    """On by default: verifying a seller-direct payment is not custody.

    ``AIMARKET_X402_ACCEPT=0`` keeps the old discovery-only mode for operators
    who want the catalogue to advertise terms without honouring a header.
    """
    return _flag("AIMARKET_X402_ACCEPT", "1").lower() in ("1", "true", "yes", "on")


def max_unsettled_usd() -> float:
    """Ceiling on receivables the hub will carry before refusing new x402 payments.

    A verified authorization is not settled money — the payer's balance is only knowable
    on chain — so this is the size of the bet the operator is willing to run.
    """
    try:
        return max(0.0, float(_flag("AIMARKET_X402_MAX_UNSETTLED_USD", "5")))
    except ValueError:
        return 5.0


def chain_id() -> int:
    """The numeric chain id used in the EIP-712 domain — realm-aware, so a signature made
    inside the bubble is only ever valid inside it."""
    try:
        return int(caip2().split(":", 1)[1])
    except (IndexError, ValueError):
        return 0


def decode_payment(raw: str) -> dict[str, Any] | None:
    """Base64 JSON → payload, or None when it is neither.

    x402 clients send the payload base64-encoded; some send bare JSON. Both are read,
    because refusing a well-formed payment over an encoding detail helps nobody.
    """
    text = (raw or "").strip()
    if not text:
        return None
    for attempt in (text, ""):
        if attempt:
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                pass
    try:
        decoded = base64.b64decode(text + "=" * (-len(text) % 4), validate=False)
        parsed = json.loads(decoded.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _payload_parts(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The authorization object and its signature, across the shapes clients send.

    V2 nests them under `payload`; V1 clients have been seen sending them at the top
    level. Reading both is three lines here and one fewer support thread later.
    """
    inner = payload.get("payload")
    if isinstance(inner, dict):
        auth = inner.get("authorization")
        if isinstance(auth, dict):
            return auth, str(inner.get("signature") or payload.get("signature") or "")
        return inner, str(inner.get("signature") or payload.get("signature") or "")
    auth = payload.get("authorization")
    if isinstance(auth, dict):
        return auth, str(payload.get("signature") or "")
    return payload, str(payload.get("signature") or "")


def verify_payment(
    payload: dict[str, Any], *, price_usd: float, now: int | None = None,
    pay_to: str | None = None,
) -> dict[str, Any]:
    """Check a PAYMENT-SIGNATURE against the seller this listing named.

    Returns ``{"ok": True, "payer": …, "nonce": …, "amount_usd": …}`` or
    ``{"ok": False, "error": …}``. Every refusal names the field that failed, because an
    opaque "payment invalid" against a signed object is unactionable for the payer.
    """
    import time as _time

    from aimarket_hub.escrow_bridge import eip712

    profile = asset_profile()
    payee = (pay_to or recipient() or "").strip()
    if not profile or not payee:
        return {"ok": False, "error": "this listing has no seller payout_address"}
    caip2_id = caip2()
    auth, signature = _payload_parts(payload)
    if not isinstance(auth, dict) or not signature:
        return {"ok": False, "error": "payment payload carries no signed authorization"}

    scheme = str(payload.get("scheme") or auth.get("scheme") or "exact").lower()
    if scheme != "exact":
        return {"ok": False, "error": f"unsupported scheme {scheme!r} — this hub takes 'exact'"}

    network = str(payload.get("network") or auth.get("network") or caip2_id or "")
    if network and network not in (caip2_id, chain()):
        return {"ok": False, "error": f"payment is for network {network!r}, this hub settles on {caip2_id}"}

    asset = str(payload.get("asset") or auth.get("asset") or profile["address"])
    if not eip712.addresses_equal(asset, profile["address"]):
        return {"ok": False, "error": f"payment is in asset {asset}, this hub prices in {profile['address']}"}

    to = str(auth.get("to") or "")
    if not eip712.addresses_equal(to, payee):
        return {"ok": False, "error": "payment is addressed to somebody else"}

    required = int(usd_to_atomic(price_usd, profile["decimals"]))
    try:
        value = int(str(auth.get("value") or "0"))
    except ValueError:
        return {"ok": False, "error": "value is not an integer amount of atomic units"}
    if value < required:
        return {"ok": False, "error": f"payment is {value} atomic units, the call costs {required}"}

    stamp = int(_time.time()) if now is None else int(now)
    try:
        valid_after = int(str(auth.get("validAfter") or 0))
        valid_before = int(str(auth.get("validBefore") or 0))
    except ValueError:
        return {"ok": False, "error": "validAfter/validBefore are not integers"}
    if valid_before and stamp >= valid_before:
        return {"ok": False, "error": "authorization has expired"}
    if valid_after and stamp < valid_after:
        return {"ok": False, "error": "authorization is not valid yet"}

    payer = str(auth.get("from") or "")
    nonce = str(auth.get("nonce") or "")
    if not payer or not nonce:
        return {"ok": False, "error": "authorization is missing from/nonce"}

    extra = profile.get("extra") or {}
    try:
        digest = eip712.transfer_authorization_digest(
            sender=payer, recipient=to, value=value,
            valid_after=valid_after, valid_before=valid_before, nonce=nonce,
            token_name=str(extra.get("name") or asset_symbol()),
            token_version=str(extra.get("version") or "2"),
            chain_id=chain_id(), token_address=profile["address"],
        )
        recovered = eip712.recover_transfer_signer(signature, digest)
    except eip712.CryptoUnavailable as exc:
        # Refuse rather than trust: a hub that cannot check a signature must not act on one.
        return {"ok": False, "error": f"cannot verify signatures on this deployment: {exc}"}
    except eip712.Eip712Error as exc:
        return {"ok": False, "error": f"malformed authorization: {exc}"}
    if not recovered or not eip712.addresses_equal(recovered, payer):
        return {"ok": False, "error": "signature does not match the stated payer"}

    return {
        "ok": True,
        "payer": eip712.normalize_address(payer),
        "nonce": nonce,
        "amount_atomic": value,
        "amount_usd": round(value / (10 ** profile["decimals"]), 6),
        "asset": profile["address"],
        "network": caip2_id or chain(),
        "pay_to": payee,
    }


class PaymentStore:
    """Settled seller-direct payments: the replay guard.

    These rows are on-chain facts the hub verified, not receivables. Credits
    are prepaid money the operator is holding; this table is money that
    already reached the seller.
    """

    def __init__(self, conn: Any):
        self._conn = conn

    def seen(self, nonce: str) -> bool:
        row = self._conn.execute(
            "SELECT nonce FROM x402_payments WHERE nonce = ?", (str(nonce),),
        ).fetchone()
        return row is not None

    def record(self, verified: dict[str, Any], *, receipt_id: str = "",
               capability_id: str = "") -> None:
        self._conn.execute(
            "INSERT INTO x402_payments "
            "(nonce, payer, amount_atomic, amount_usd, asset, network, receipt_id, capability_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(verified["nonce"]), str(verified["payer"]),
                str(verified.get("amount_atomic") or 0), float(verified.get("amount_usd") or 0),
                str(verified.get("asset") or ""), str(verified.get("network") or ""),
                receipt_id, capability_id,
            ),
        )
        self._conn.commit()

    def mark_settled(self, nonce: str, tx_hash: str) -> None:
        self._conn.execute(
            "UPDATE x402_payments SET status = 'settled', settle_tx_hash = ?, "
            "settled_at = datetime('now') WHERE nonce = ?",
            (str(tx_hash), str(nonce)),
        )
        self._conn.commit()

    def unsettled_usd(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) AS total FROM x402_payments "
            "WHERE status = 'accepted'",
        ).fetchone()
        return round(float(row["total"] or 0), 6) if row else 0.0

    def stats(self) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount_usd), 0) AS total, "
            "COALESCE(SUM(CASE WHEN status = 'accepted' THEN amount_usd ELSE 0 END), 0) AS owed "
            "FROM x402_payments",
        ).fetchone()
        if not row:
            return {
                "payments": 0, "x402_accepted_usd": 0.0,
                "x402_unsettled_usd": 0.0, "x402_settled_usd": 0.0,
            }
        settled = round(float(row["total"] or 0) - float(row["owed"] or 0), 6)
        return {
            "payments": int(row["n"] or 0),
            "x402_accepted_usd": round(float(row["total"] or 0), 6),
            "x402_unsettled_usd": round(float(row["owed"] or 0), 6),
            "x402_settled_usd": settled,
        }
