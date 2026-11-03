"""Pinned Base/Ethereum ETH/USD feeds, checked through two RPC endpoints before spending.

Feed addresses: https://data.chain.link/feeds/base/base/eth-usd and
https://docs.chain.link/data-feeds/l2-sequencer-feeds . The price heartbeat is
1200s (Base) or 3600s (Ethereum); maximum ages are 1500s/3900s. RPCs remain a trust dependency (not light clients).
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from urllib.parse import urlsplit

ETH_USD = "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"
ETHEREUM_ETH_USD = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
SEQUENCER = "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433"
MAX_AGE_S = 1500
BLOCK_MAX_AGE_S = 120
GRACE_S = 3600
MARGIN = Decimal("1.25")
MAX_DISAGREEMENT = Decimal("0.02")


def check_rpc(primary, secondary=None, *, chain_id=8453):
    """Avoid counting the same hostname as two independent observations."""
    host = urlsplit(primary).hostname
    choices = {8453: ("https://mainnet.base.org", "https://base-rpc.publicnode.com"),
               1: ("https://ethereum-rpc.publicnode.com", "https://eth.drpc.org")}
    if chain_id not in choices: raise ValueError("unsupported native-price chain")
    first, second = choices[chain_id]
    secondary = secondary or (first if host == urlsplit(second).hostname else second)
    other = urlsplit(secondary)
    if not host or not other.hostname or other.hostname == host:
        raise ValueError("price verification requires a second RPC hostname")
    if other.scheme not in ("https", "http"):
        raise ValueError("invalid price verification RPC URL")
    return secondary


def _words(value, count):
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 2 + count * 64:
        raise ValueError("malformed price oracle response")
    try:
        return [int(value[i:i+64], 16) for i in range(2, len(value), 64)]
    except ValueError as exc:
        raise ValueError("malformed price oracle response") from exc


def _round(value):
    round_id, answer, started, updated, answered = _words(value, 5)
    if answer >= 2**255:
        answer -= 2**256
    if not 0 < round_id < 2**80 or not round_id <= answered < 2**80:
        raise ValueError("incomplete price oracle round")
    return round_id, answer, started, updated


async def _observation(client, url, rpc, *, chain_id=8453):
    feed, max_age = (ETH_USD, MAX_AGE_S) if chain_id == 8453 else (ETHEREUM_ETH_USD, 3900)
    # Bound the entire observation even when the supplied HTTP client has no timeout.
    async with asyncio.timeout(20):
        if int(await rpc(client, url, "eth_chainId", []), 16) != chain_id:
            raise ValueError("price RPC differs from the approved chain")
        block = await rpc(client, url, "eth_getBlockByNumber", ["latest", False])
        stamp, number = int(block["timestamp"], 16), block["number"]
        now = time.time()
        if not now - BLOCK_MAX_AGE_S <= stamp <= now + 30:
            raise ValueError("price RPC returned a stale or future block")

        async def call(address, selector):
            return await rpc(client, url, "eth_call", [{"to": address, "data": selector}, number])

        # Read each feed at the same block. Uptime timestamps change only on status
        # transitions; unlike a price round, a long-standing UP status is not stale.
        seq = None
        if chain_id == 8453:
            seq = _round(await call(SEQUENCER, "0xfeaf968c"))
            if seq[1] != 0 or not 0 < seq[2] <= seq[3] <= stamp or stamp - seq[2] <= GRACE_S:
                raise ValueError("Base sequencer unavailable or recovery grace period active")
        if _words(await call(feed, "0x313ce567"), 1)[0] != 8:
            raise ValueError("unexpected ETH/USD oracle decimals")
        round_id, answer, started, updated = _round(await call(feed, "0xfeaf968c"))
        if answer <= 0 or not 0 < started <= updated <= stamp or stamp - updated > max_age:
            raise ValueError("ETH/USD oracle price is invalid, stale or from the future")
        return {"price_usd": str(Decimal(answer) / 10**8), "round_id": str(round_id),
                "updated_at": updated, "block_number": int(number, 16), "block_timestamp": stamp,
                "sequencer_up_since": seq[2] if seq else None}


async def native_price(client, primary, rpc, *, secondary=None, floor=None, chain_id=8453):
    secondary = check_rpc(primary, secondary, chain_id=chain_id)
    observations = await asyncio.gather(_observation(client, primary, rpc, chain_id=chain_id),
                                        _observation(client, secondary, rpc, chain_id=chain_id))
    low, high = sorted(Decimal(row["price_usd"]) for row in observations)
    if high / low - 1 > MAX_DISAGREEMENT:
        raise ValueError("ETH/USD RPC observations disagree by more than 2%; payment paused")
    ceiling = high * MARGIN
    if floor is not None:
        manual = Decimal(str(floor))
        if not manual.is_finite() or manual <= 0:
            raise ValueError("native_usd_ceiling must be positive and finite")
        ceiling = max(ceiling, manual)
    return {"source": "chainlink_base_eth_usd" if chain_id == 8453 else "chainlink_ethereum_eth_usd",
            "feed": ETH_USD if chain_id == 8453 else ETHEREUM_ETH_USD,
            "sequencer_feed": SEQUENCER if chain_id == 8453 else None,
            "observations": observations, "margin_percent": 25, "max_age_s": MAX_AGE_S if chain_id == 8453 else 3900,
            "manual_floor_usd": str(floor) if floor is not None else None,
            "native_usd_ceiling": str(ceiling), "checked_at": time.time()}
