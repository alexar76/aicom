"""On-chain deposit verification for a hub that ships without the web app behind it.

The canonical verifier lives in ``web.backend.services.ai_market_protocol.on_chain``, and
a standalone hub image cannot import it: that package's ``__init__`` pulls in the whole
web stack (catalog, discovery, pricing, invoke, pipelines…). So on such a hub
``_shared_on_chain("verify_tx_payment_details")`` returns ``None``, ``_verify_tx_onchain``
answers "on-chain verification unavailable", and **every paid channel/open is refused**.

That is correct fail-closed behaviour and it is also a total revenue block on the
deposit-funded door. Measured on modelmarket.dev, 2026-09-07: ``AIFACTORY_PROD=1``, stub
off, verifier unimportable (``No module named 'web'``) — the escrow-funded door worked
(all 13 channels ever opened there came through it, ``tx_hash`` empty), and the deposit
door had never once succeeded.

This module is that door's verifier, self-contained: JSON-RPC in, a verdict out.

What it will and will not certify
---------------------------------
* **Stablecoin transfers only.** A deposit quoted in USD can only be checked against a
  token whose unit IS the dollar. This ecosystem deliberately has no price oracle (same
  stance as ``onchain_reads`` in the monitor and the web verifier), so a deposit paid in
  the chain's native coin is REFUSED rather than converted at a guessed rate.
* **The payer is the ERC-20 ``Transfer.from``**, not the transaction's origin: the caller
  binds the channel to it (PAYAUTH-003), and a transfer routed through a contract is paid
  by whoever the token moved from.
* **One payer per deposit.** Matching transfers from two different senders in one
  transaction are refused as ambiguous rather than credited to the first.
* Anything unreadable — no receipt, reverted status, too few confirmations, an
  unresolvable token address, an RPC that will not answer — is a refusal. A verifier that
  cannot see the chain must never say "verified".
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: keccak256("Transfer(address,address,uint256)") — the ERC-20 event, every token emits it.
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

#: Tokens whose unit is the dollar, so a USD amount is checkable without a price feed.
STABLECOINS = frozenset({"USDC", "USDT", "DAI", "USDBC", "PYUSD"})

#: `decimals()` — read once per token, because a wrong assumption here is a factor of 10^12.
_SEL_DECIMALS = "0x313ce567"

#: Fallback when `decimals()` cannot be read. Every stablecoin above is 6 except DAI (18),
#: and guessing wrong the OTHER way (assuming 18 for a 6-decimal token) would accept a
#: millionth of the expected payment — so a failed read is a refusal, not a guess.
_DECIMALS_BY_TOKEN = {"USDC": 6, "USDT": 6, "USDBC": 6, "PYUSD": 6, "DAI": 18}

_decimals_cache: dict[str, int] = {}


@dataclass
class DepositCheck:
    """A verdict, and enough detail for the refusal to be actionable in a log."""

    ok: bool
    sender: str = ""
    error: str = ""
    confirmations: int = 0
    paid_units: int = 0
    expected_units: int = 0
    token_address: str = ""
    details: dict[str, Any] = field(default_factory=dict)


#: (method, params) -> result. Injected so the decode logic is testable with no network.
RpcCaller = Callable[[str, list], Any]


def _hex_to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return 0
    return int(text, 16) if text.startswith("0x") else int(text)


def _same_address(left: str, right: str) -> bool:
    return (left or "").strip().lower() == (right or "").strip().lower()


def _topic_address(topic: str) -> str:
    """The 20-byte address out of a 32-byte log topic."""
    body = (topic or "").strip()
    if body.startswith("0x"):
        body = body[2:]
    return "0x" + body[-40:] if len(body) >= 40 else ""


def rpc_urls_for(chain: str) -> list[str]:
    """Where to ask about a deposit.

    An explicit override is EXCLUSIVE, not merely first. ``AIMARKET_RPC_BASE`` is what
    points the UNI bubble's hub at the bubble's own Anvil while it calls that chain "base"
    — same code, same door, a different network behind it — and appending the public Base
    endpoints after it would let a momentary blip on the bubble node fail the lookup over
    to REAL Base mainnet, where a bubble transaction does not exist. The refusal would be
    safe and completely misleading, and a sealed realm asking mainnet about its own money
    is precisely what the seal is for.

    ``AIMARKET_DEPOSIT_RPC_URL`` overrides even that, for a hub whose deposit node is not
    the one the rest of it uses.
    """
    for name in ("AIMARKET_DEPOSIT_RPC_URL", f"AIMARKET_RPC_{(chain or '').upper()}"):
        override = (os.environ.get(name) or "").strip()
        if override:
            return [part.strip() for part in override.split(",") if part.strip()]
    try:
        from aimarket_hub import chain_net

        return [u for u in chain_net.network(chain).rpc_urls if u]
    except Exception as exc:  # unknown chain / no registry — the caller reports it
        logger.debug("no chain_net rpc list for %r: %s", chain, exc)
        return []


_RPC_CHAIN_IDS: dict[str, int] = {}


def _rpc_chain_id(url: str, timeout: float = 5.0) -> int | None:
    """``eth_chainId`` of one RPC endpoint, remembered per URL (a node does not change chains)."""
    if url in _RPC_CHAIN_IDS:
        return _RPC_CHAIN_IDS[url]
    try:
        import httpx

        body = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
                          timeout=timeout).json()
        chain_id = int(str(body["result"]), 16)
    except Exception as exc:  # noqa: BLE001 - the caller fails closed on None
        logger.warning("cannot read eth_chainId from the deposit RPC: %s", exc)
        return None
    _RPC_CHAIN_IDS[url] = chain_id
    return chain_id


def registry_chain_id(chain: str) -> int | None:
    """The EVM chain a deposit labelled ``chain`` is really verified on, or None.

    The deposit-claim registry used to key a claim on the caller's label alone. But
    :func:`rpc_urls_for` answers an explicit override for EVERY label
    (``AIMARKET_DEPOSIT_RPC_URL``) or points a label at a node of another chain
    (``AIMARKET_RPC_BASE`` → the UNI bubble's Anvil), so one transaction verified under
    "base" and again under "ethereum" — two keys, two credits. The registry keys on the
    chain the verifier actually reads: the node's own ``eth_chainId`` when the label is
    overridden, the registry's chain id otherwise. None for a non-EVM chain or a node that
    cannot be read; the caller then claims under the label alone or fails closed.
    """
    label = (chain or "").strip().lower()
    for name in ("AIMARKET_DEPOSIT_RPC_URL", f"AIMARKET_RPC_{label.upper()}"):
        override = (os.environ.get(name) or "").strip()
        if override:
            # The same comma-separated list rpc_urls_for() verifies against. Read as one URL it
            # was always unreachable, and the claim then failed closed for every deposit. Every
            # node that answers must name the same chain; disagreement is as bad as silence.
            ids = {cid for cid in (_rpc_chain_id(u.strip()) for u in override.split(",") if u.strip()) if cid is not None}
            return ids.pop() if len(ids) == 1 else None
    try:
        from aimarket_hub import chain_net

        return chain_net.network(label).chain_id
    except Exception:  # noqa: BLE001 - unknown label
        return None


def token_address_for(chain: str, token: str) -> str:
    """The token contract, from an env override or the deployment registry."""
    name = (token or "").strip().upper()
    override = (os.environ.get(f"AIMARKET_TOKEN_{name}") or "").strip()
    if override:
        return override
    legacy = (os.environ.get(f"AIMARKET_{name}") or "").strip()
    if legacy.startswith("0x"):
        return legacy
    try:
        from aimarket_hub import chain_net

        return str((chain_net.network(chain).addresses or {}).get(name) or "")
    except Exception:
        return ""


def _post(url: str, body: dict, timeout: float) -> dict:
    import httpx

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=body, headers={"content-type": "application/json"})
    resp.raise_for_status()
    answer = resp.json()
    if isinstance(answer, dict) and answer.get("error"):
        # Raised, not returned: the pool then asks the next node, as this loop always did.
        raise RuntimeError(str(answer["error"])[:160])
    return answer if isinstance(answer, dict) else {"result": None}


def _make_rpc(urls: list[str], timeout: float) -> RpcCaller:
    from aimarket_hub import chain_net

    def call(method: str, params: list) -> Any:
        # In rotation over the same list: a node that refuses (429, a range cap) rests.
        try:
            pool = chain_net.pool_for_urls(urls, timeout=timeout, transport=_post)
            return pool.call(method, params)
        except chain_net.ChainNetError as exc:
            raise RuntimeError(f"no RPC endpoint answered {method}: {exc}") from exc

    return call


def token_decimals(rpc: RpcCaller, token_address: str, token: str) -> int | None:
    """``decimals()`` from the contract; None when it cannot be established."""
    key = (token_address or "").lower()
    if key in _decimals_cache:
        return _decimals_cache[key]
    try:
        raw = rpc("eth_call", [{"to": token_address, "data": _SEL_DECIMALS}, "latest"])
        value = _hex_to_int(raw)
        if 0 < value <= 36:
            _decimals_cache[key] = value
            return value
    except Exception as exc:
        logger.warning("decimals() unreadable for %s: %s", token_address[:12], exc)
    fallback = _DECIMALS_BY_TOKEN.get((token or "").strip().upper())
    if fallback is not None:
        _decimals_cache[key] = fallback
        return fallback
    return None


def verify_deposit(
    *,
    tx_hash: str,
    amount_usd: float,
    chain: str,
    token: str,
    recipient: str,
    min_confirmations: int = 2,
    rpc: RpcCaller | None = None,
    token_address: str = "",
    timeout: float = 8.0,
) -> DepositCheck:
    """Did ``tx_hash`` pay ``recipient`` at least ``amount_usd`` of ``token``?

    Returns the paying wallet on success — the caller cannot credit a deposit it cannot
    bind to a payer, and refuses when this is empty.
    """
    tx = (tx_hash or "").strip()
    if not (tx.startswith("0x") and len(tx) == 66):
        return DepositCheck(False, error="tx_hash is not a 32-byte transaction hash")
    if not (recipient or "").strip().startswith("0x"):
        return DepositCheck(False, error="no payment recipient configured on this hub")
    name = (token or "").strip().upper()
    if name not in STABLECOINS:
        return DepositCheck(
            False,
            error=(
                f"deposits are verified in stablecoins only; {name or 'the native coin'} "
                f"would need a price oracle this ecosystem deliberately does not have"
            ),
        )
    if amount_usd <= 0:
        return DepositCheck(False, error="deposit amount must be positive")

    address = (token_address or token_address_for(chain, name)).strip()
    if not address.startswith("0x"):
        return DepositCheck(
            False, error=f"no {name} contract address known for chain {chain!r}"
        )

    if rpc is None:
        urls = rpc_urls_for(chain)
        if not urls:
            return DepositCheck(False, error=f"no RPC endpoint configured for chain {chain!r}")
        rpc = _make_rpc(urls, timeout)

    try:
        receipt = rpc("eth_getTransactionReceipt", [tx])
    except Exception as exc:
        return DepositCheck(False, error=f"could not reach the chain to verify: {exc}")
    if not isinstance(receipt, dict):
        return DepositCheck(False, error="transaction not found or not yet mined")
    if _hex_to_int(receipt.get("status")) != 1:
        return DepositCheck(False, error="transaction reverted on chain")

    try:
        head = _hex_to_int(rpc("eth_blockNumber", []))
    except Exception as exc:
        return DepositCheck(False, error=f"could not read chain height: {exc}")
    mined_in = _hex_to_int(receipt.get("blockNumber"))
    confirmations = max(0, head - mined_in + 1) if mined_in else 0
    if confirmations < max(1, int(min_confirmations)):
        return DepositCheck(
            False,
            confirmations=confirmations,
            error=(
                f"insufficient confirmations ({confirmations}/{min_confirmations}) — "
                f"retry once the deposit has settled"
            ),
        )

    decimals = token_decimals(rpc, address, name)
    if decimals is None:
        return DepositCheck(False, error=f"could not establish {name} decimals")
    expected = int(round(float(amount_usd) * (10 ** decimals)))

    paid = 0
    senders: set[str] = set()
    for log in receipt.get("logs") or []:
        if not isinstance(log, dict):
            continue
        topics = log.get("topics") or []
        if len(topics) < 3 or not _same_address(str(topics[0]), TRANSFER_TOPIC):
            continue
        if not _same_address(str(log.get("address") or ""), address):
            continue
        if not _same_address(_topic_address(str(topics[2])), recipient):
            continue
        paid += _hex_to_int(log.get("data"))
        senders.add(_topic_address(str(topics[1])).lower())

    if not paid:
        return DepositCheck(
            False,
            confirmations=confirmations,
            expected_units=expected,
            token_address=address,
            error=f"transaction moved no {name} to the configured recipient",
        )
    # One base unit of slack absorbs the float→integer rounding of the USD amount; it is
    # worth 0.000001 USDC and cannot be farmed into anything.
    if paid < expected - 1:
        return DepositCheck(
            False,
            confirmations=confirmations,
            paid_units=paid,
            expected_units=expected,
            token_address=address,
            error=(
                f"deposit is short: paid {paid / 10 ** decimals:.6f} {name}, "
                f"expected {amount_usd:.6f}"
            ),
        )
    if len(senders) != 1:
        return DepositCheck(
            False,
            confirmations=confirmations,
            paid_units=paid,
            expected_units=expected,
            token_address=address,
            error=(
                f"{len(senders)} different wallets paid the recipient in this transaction "
                f"— refusing to credit an ambiguous payer"
            ),
        )

    sender = next(iter(senders))
    return DepositCheck(
        True,
        sender=sender,
        confirmations=confirmations,
        paid_units=paid,
        expected_units=expected,
        token_address=address,
        details={"decimals": decimals, "block": mined_in, "token": name, "chain": chain},
    )
