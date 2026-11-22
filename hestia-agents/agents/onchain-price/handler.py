"""crypto.price.onchain@v1: the price of ETH, BTC or any Base token, from Uniswap v3 pools on Base.

No exchange, data vendor or price API is asked. The agent reads public chain state through the
hearth's Base RPC pool (base-rpc.hestia.modelmarket.dev; else base-rpc.publicnode.com) and does the
arithmetic itself:

  - `asset` "ETH" or "BTC": the four Uniswap v3 pools of WETH/USDC or cbBTC/USDC (fee tiers 0.01 %,
    0.05 %, 0.3 %, 1 %), each confirmed by the Uniswap v3 factory's getPool at the same block. The
    price comes from the pool with the most in-range liquidity among those whose price moved in the
    window (a deep pool nobody traded only repeats its last trade); the others are a cross-check.
  - or `token`: any ERC-20 on Base. Whether the address holds a contract, the token's own name,
    symbol, decimals and supply on Base, and its Uniswap v3 pools with USDC and with WETH (four fee
    tiers each, found through the factory's getPool). Depth is the token side of a pool's in-range
    liquidity at the current price, counted in the token itself, so USDC and WETH pools compare;
    the price comes from the deepest pool whose price moved in the window (a WETH pool times the
    ETH price above). Each pool says how many dollars of the token one swap would sell into it to
    lower its price by 1 %; pools under 1 % of the chosen one's depth are marked as no market
    price. When no pool's price moved, the price is the deepest pool's last trade; when no pool's
    oracle reaches back that far, it is the spot price, and the answer says so. The token's reads
    go through Multicall3 (one eth_call per step), each giving what a direct eth_call at that
    block would.
  - or `pool`: any Uniswap v3 pool on Base; the agent checks the factory deployed it and prices
    token0 in token1 and back.

The price is the time-weighted average over `window_s` seconds (default 1800): the pool's own
oracle, observe([window, 0]), gives two tick accumulators; their difference over the window is the
mean tick, and the price is 1.0001 ** mean_tick, scaled by the tokens' decimals. The spot price
(slot0) is given beside it. Every read is pinned to one block (`block`, or the latest when the call
starts), so the same input with the same block gives the same numbers.

What it is not: a market-wide price. It is what these pools priced, in USDC, which the agent takes
as one dollar; no volume, no market capitalisation, no other venues.
"""

from decimal import Decimal, getcontext

getcontext().prec = 60

# Without the hearth's pool: base-rpc.publicnode.com. A token is priced from up to eight pools
# plus the ETH leg, about fifty reads, more than mainnet.base.org allows a second.
RPC = "https://base-rpc.publicnode.com"
TOKEN_RPC = RPC
CHAIN_ID = 8453
FACTORY = "0x33128a8fc17869897dce68ed026d694621f6fdfd"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
ASSETS = {
    # asset: (token, decimals, symbol, {fee: pool})
    "ETH": ("0x4200000000000000000000000000000000000006", 18, "WETH", {
        100: "0xb4cb800910b228ed3d0834cf79d697127bbb00e5",
        500: "0xd0b53d9277642d899df5c87a3966a349a798f224",
        3000: "0x6c561b446416e1a00e8e93e221854d6ea4171372",
        10000: "0x0b1c2dcbbfa744ebd3fc17ff1a96a1e1eb4b2d69",
    }),
    "BTC": ("0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf", 8, "cbBTC", {
        100: "0xe9e25e35aa99a2a60155010802b81a25c45ba185",
        500: "0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef",
        3000: "0xec558e484cc9f2210714e345298fdc53b253c27d",
        10000: "0x3e7586d52a9d07f8611b8ecf6ccc8a689c34a659",
    }),
}
# Function selectors (first four bytes of keccak-256 of the signature).
LIQUIDITY = "0x1a686502"  # liquidity()
SLOT0 = "0x3850c7bd"  # slot0()
OBSERVE = "0x883bdbfd"  # observe(uint32[])
GET_POOL = "0x1698ee82"  # getPool(address,address,uint24)
TOKEN0 = "0x0dfe1681"  # token0()
TOKEN1 = "0xd21220a7"  # token1()
FEE = "0xddca3f43"  # fee()
FACTORY_OF = "0xc45a0155"  # factory()
DECIMALS = "0x313ce567"  # decimals()
SYMBOL = "0x95d89b41"  # symbol()
NAME = "0x06fdde03"  # name()
TOTAL_SUPPLY = "0x18160ddd"  # totalSupply()
AGGREGATE3 = "0x82ad56cb"  # aggregate3((address,bool,bytes)[])
MULTICALL = "0xca11bde05977b3631167028862be2a173976ca11"  # Multicall3, same address on every chain
HEX = "0123456789abcdef"
Q96 = Decimal(2) ** 96
BASE = Decimal("1.0001")
DEFAULT_WINDOW = 1800
MAX_WINDOW = 86400
MIN_WINDOW = 60
# A tier whose in-range liquidity is under this share of the deepest one is listed but left out of
# the cross-check: a thin pool can sit far from the market without anyone trading it back.
CROSS_CHECK_SHARE = Decimal("0.01")


def _address(value, where):
    text = str(value or "").strip().lower()
    if not (text.startswith("0x") and len(text) == 42 and all(c in HEX for c in text[2:])):
        raise ValueError(where + " must be a 0x address (40 hex digits)")
    return text


def _word(address):
    return address[2:].zfill(64)


def _u(n):
    return format(n, "064x")


def _words(data):
    text = str(data or "")[2:]
    return [text[i:i + 64] for i in range(0, len(text), 64)]


def _int(word, bits=256, signed=False):
    value = int(word, 16)
    if signed and value >= 1 << (bits - 1):
        value -= 1 << bits
    return value


# The hearth's pool of free Base RPCs (hestia.rpc_pool) is tried first for Base mainnet. A hearth
# without it refuses that name, and the agent then reads the public RPC for the rest of the call.
POOL = "https://base-rpc.hestia.modelmarket.dev"
_POOL_FOR = {"https://base-rpc.publicnode.com"}
_no_pool = []


def _post(url, body):
    if url in _POOL_FOR and not _no_pool:
        try:
            reply = fetch(POOL, method="POST", json=body)  # noqa: F821 — the sandbox provides fetch()
        except Exception:  # noqa: BLE001 — the hearth refused the name: no pool on this hearth
            reply = None
        if reply is not None and reply.status not in (0, 429) and reply.status < 500:
            return reply
        _no_pool.append(True)
    return fetch(url, method="POST", json=body)  # noqa: F821


def _batch(calls, rpc=RPC):
    """One JSON-RPC batch: the sandbox allows six fetches per call, so reads go together."""
    body = [{"jsonrpc": "2.0", "id": i + 1, "method": m, "params": p}
            for i, (m, p) in enumerate(calls)]
    reply = _post(rpc, body)
    if not reply.ok:
        raise RuntimeError("the RPC answered HTTP " + str(reply.status))
    answers = reply.json()
    if not isinstance(answers, list):
        raise RuntimeError("the RPC did not answer the batch: " + str(answers)[:160])
    by_id = {a.get("id"): a for a in answers if isinstance(a, dict)}
    return [by_id.get(i + 1) or {"error": {"message": "no answer"}} for i in range(len(calls))]


def _result(answer):
    return None if "error" in answer else answer.get("result")


def _strict(answers, may_revert=()):
    """A revert is an answer (observe beyond the oracle's reach, a token without symbol()); any
    other RPC error (rate limit, timeout, no answer) is not, and must not read as zero."""
    for i, answer in enumerate(answers):
        error = answer.get("error")
        if not error:
            continue
        text = str(error.get("message") if isinstance(error, dict) else error)
        if i in may_revert and "revert" in text.lower():
            continue
        raise RuntimeError("the RPC did not answer a read (" + text[:120] + "); call again")
    return answers


def _call(to, data, block):
    return ("eth_call", [{"to": to, "data": data}, block])


def _observe_data(window):
    return OBSERVE + _u(32) + _u(2) + _u(window) + _u(0)


def _mean_tick(observed, window):
    """Mean tick over the window from observe([window, 0]); None if the pool refused (too old)."""
    words = _words(observed)
    if len(words) < 6:
        return None
    start = _int(words[0]) // 32
    count = _int(words[start])
    if count != 2:
        return None
    old = _int(words[start + 1], signed=True)
    new = _int(words[start + 2], signed=True)
    return Decimal(new - old) / Decimal(window)


def _raw_price(tick):
    """token1 per token0, in the tokens' smallest units."""
    return BASE ** tick


def _spot(slot0):
    words = _words(slot0)
    if len(words) < 2:
        return None, None
    sqrt_price = Decimal(_int(words[0])) / Q96
    return sqrt_price * sqrt_price, _int(words[1], signed=True)


def _fmt(value, places=6):
    if value is None:
        return None
    if value >= 1:
        return str(value.quantize(Decimal(1).scaleb(-places)))
    return format(value, "." + str(max(8, places)) + "g")


def _pct(a, b):
    return str(((a - b) / b * 100).quantize(Decimal("0.0001")))


def _block(payload):
    raw = payload.get("block")
    if raw is None or raw == "latest":
        return "latest"
    if isinstance(raw, bool) or not str(raw).strip().isdigit():
        raise ValueError("block is a block number (or \"latest\")")
    return hex(int(str(raw).strip()))


def _window(payload):
    raw = payload.get("window_s", DEFAULT_WINDOW)
    if isinstance(raw, bool) or not str(raw).strip().isdigit():
        raise ValueError("window_s is a whole number of seconds")
    window = int(str(raw).strip())
    if not MIN_WINDOW <= window <= MAX_WINDOW:
        raise ValueError("window_s must be between " + str(MIN_WINDOW) + " and " + str(MAX_WINDOW))
    return window


def _head(block, rpc=RPC):
    chain, head = _batch([("eth_chainId", []), ("eth_getBlockByNumber", [block, False])], rpc)
    served = _result(chain)
    if served is None or int(served, 16) != CHAIN_ID:
        raise RuntimeError("the RPC does not serve Base (chain " + str(served) + ")")
    head = _result(head)
    if not head:
        raise ValueError("Base has no block " + str(int(block, 16) if block != "latest" else block))
    return {"number": int(head["number"], 16), "hash": head["hash"],
            "timestamp": int(head["timestamp"], 16)}


def _asset(asset, window, head, checks, rpc=RPC):
    token, decimals, symbol, pools = ASSETS[asset]
    at = hex(head["number"])
    calls = []
    for fee, pool in sorted(pools.items()):
        calls += [_call(FACTORY, GET_POOL + _word(token) + _word(USDC) + _u(fee), at),
                  _call(pool, LIQUIDITY, at), _call(pool, SLOT0, at),
                  _call(pool, _observe_data(window), at)]
    answers = _strict(_batch(calls, rpc), may_revert=set(range(3, len(calls), 4)))
    usdc_first = USDC < token  # Uniswap orders token0 < token1 by address
    scale = Decimal(10) ** (decimals - 6 if not usdc_first else 6 - decimals)
    tiers = []
    for i, (fee, pool) in enumerate(sorted(pools.items())):
        got, liq, slot0, observed = (_result(a) for a in answers[4 * i:4 * i + 4])
        listed = got is not None and "0x" + got[-40:] == pool
        checks.append({"check": "factory_pool_" + str(fee), "ok": listed,
                       "detail": "getPool(" + symbol + ", USDC, " + str(fee) + ") = "
                                 + ("0x" + got[-40:] if got else "no answer")})
        if not listed:
            continue
        row = {"fee": fee, "fee_pct": str(Decimal(fee) / 10000), "pool": pool,
               "liquidity": _int(liq[2:]) if liq else 0}
        spot_raw, spot_tick = _spot(slot0)
        mean = _mean_tick(observed, window)
        twap_raw = _raw_price(mean) if mean is not None else None
        for key, raw in (("spot_usd", spot_raw), ("twap_usd", twap_raw)):
            if raw is None or raw == 0:
                row[key] = None
                continue
            price = raw * scale
            row[key] = (1 / price) if usdc_first else price
        row["spot_tick"] = spot_tick
        row["mean_tick"] = str(mean.quantize(Decimal("0.0001"))) if mean is not None else None
        # A tick held for the whole window means no swap moved this pool's price: its average is
        # the last trade before the window, however deep the pool is.
        row["traded"] = mean is not None and mean != spot_tick
        if mean is None:
            row["note"] = ("observe refused this window (the pool's oracle does not reach back "
                           "that far)")
        tiers.append(row)
    usable = [t for t in tiers if t["twap_usd"] is not None and t["liquidity"] > 0]
    if not usable:
        raise RuntimeError("no " + symbol + "/USDC pool could price this window; "
                           "try a shorter window_s")
    traded = [t for t in usable if t["traded"]]
    best = max(traded or usable, key=lambda t: t["liquidity"])
    checks.append({"check": "deepest_traded_pool", "ok": bool(traded),
                   "detail": ("fee " + best["fee_pct"] + " % has the most in-range liquidity of "
                              "the pools whose price moved in the window") if traded else
                             ("no pool's price moved in the window; fee " + best["fee_pct"]
                              + " % is the deepest, its average is its last trade before it")})
    floor = Decimal(best["liquidity"]) * CROSS_CHECK_SHARE
    peers = [t for t in traded if t is not best and Decimal(t["liquidity"]) >= floor]
    spread = max((abs((t["twap_usd"] - best["twap_usd"]) / best["twap_usd"] * 100) for t in peers),
                 default=None)
    if spread is not None:
        checks.append({"check": "tiers_agree", "ok": spread <= 1,
                       "detail": "the other deep tiers' averages are within "
                                 + str(spread.quantize(Decimal("0.0001"))) + " % of it"})
    out = {
        "asset": asset,
        "token": token,
        "quote": "USDC",
        "price_usd": _fmt(best["twap_usd"]),
        "spot_usd": _fmt(best["spot_usd"]),
        "spot_vs_twap_pct": _pct(best["spot_usd"], best["twap_usd"]) if best["spot_usd"] else None,
        "pool": best["pool"],
        "fee_pct": best["fee_pct"],
        "tiers": [{**t, "spot_usd": _fmt(t["spot_usd"]), "twap_usd": _fmt(t["twap_usd"])}
                  for t in tiers],
    }
    return out


def _string(data):
    words = _words(data)
    if len(words) == 1:  # bytes32 symbol (older tokens)
        return bytes.fromhex(words[0]).rstrip(b"\0").decode("utf-8", "replace")
    if len(words) < 3:
        return None
    length = _int(words[1])
    return bytes.fromhex("".join(words[2:])[:2 * length]).decode("utf-8", "replace")


def _pool(pool, window, head, checks):
    at = hex(head["number"])
    factory, t0, t1, fee, liq, slot0, observed = (_result(a) for a in _strict(_batch([
        _call(pool, FACTORY_OF, at), _call(pool, TOKEN0, at), _call(pool, TOKEN1, at),
        _call(pool, FEE, at), _call(pool, LIQUIDITY, at), _call(pool, SLOT0, at),
        _call(pool, _observe_data(window), at)]), may_revert={0, 1, 2, 3, 4, 5, 6}))
    if not (factory and t0 and t1 and fee):
        raise ValueError(pool + " does not answer as a Uniswap v3 pool at block "
                         + str(head["number"]))
    t0, t1, fee = "0x" + t0[-40:], "0x" + t1[-40:], _int(fee[2:])
    got, d0, d1, s0, s1 = (_result(a) for a in _strict(_batch([
        _call(FACTORY, GET_POOL + _word(t0) + _word(t1) + _u(fee), at),
        _call(t0, DECIMALS, at), _call(t1, DECIMALS, at),
        _call(t0, SYMBOL, at), _call(t1, SYMBOL, at)]),
        may_revert={3, 4}))
    deployed = "0x" + factory[-40:] == FACTORY and got is not None and "0x" + got[-40:] == pool
    checks.append({"check": "factory_pool", "ok": deployed,
                   "detail": "the Uniswap v3 factory " + ("lists" if deployed else "does NOT list")
                             + " this pool for its tokens and fee"})
    if not deployed:
        raise ValueError(pool + " is not a pool the Uniswap v3 factory on Base deployed")
    if not (d0 and d1):
        raise RuntimeError("a token of this pool does not answer decimals()")
    dec0, dec1 = _int(d0[2:]), _int(d1[2:])
    scale = Decimal(10) ** (dec0 - dec1)
    mean = _mean_tick(observed, window)
    if mean is None:
        raise RuntimeError("observe refused this window: the pool's oracle does not reach back "
                           + str(window) + " s; try a shorter window_s")
    spot_raw, spot_tick = _spot(slot0)
    twap = _raw_price(mean) * scale
    spot = spot_raw * scale if spot_raw else None
    sym0, sym1 = _string(s0) or t0, _string(s1) or t1
    return {
        "pool": pool, "fee_pct": str(Decimal(fee) / 10000),
        "token0": {"address": t0, "symbol": sym0, "decimals": dec0},
        "token1": {"address": t1, "symbol": sym1, "decimals": dec1},
        "price": _fmt(twap, 12), "price_unit": sym1 + " per " + sym0,
        "inverse": _fmt(1 / twap, 12), "inverse_unit": sym0 + " per " + sym1,
        "spot": _fmt(spot, 12),
        "spot_vs_twap_pct": _pct(spot, twap) if spot else None,
        "liquidity": _int(liq[2:]) if liq else 0,
        "mean_tick": str(mean.quantize(Decimal("0.0001"))), "spot_tick": spot_tick,
    }


FEES = (100, 500, 3000, 10000)
WETH = ASSETS["ETH"][0]
# Two routes priced the same token this far apart (percent) do not agree.
ROUTES_AGREE_PCT = Decimal(2)


def _in_quote(raw, token, decimals, quote, quote_decimals):
    """Quote units per token from a pool's raw price (token1 per token0, smallest units)."""
    if raw is None or raw == 0:
        return None
    if token < quote:  # the token is token0
        return raw * Decimal(10) ** (decimals - quote_decimals)
    return 1 / (raw * Decimal(10) ** (quote_decimals - decimals))


# Selling x of a token into a pool lowers its price by 1 % when x = virtual reserve *
# (1/sqrt(0.99) - 1), as long as the in-range liquidity stays what it is (it can change at a nearby
# tick).
ONE_PERCENT = Decimal(1) / Decimal("0.99").sqrt() - 1
MAX_TEXT = 64


def _amount(value, places):
    return None if value is None else ("0" if value == 0 else _fmt(value, places))


def _aggregate(reads, at):
    """eth_call of Multicall3.aggregate3, allowFailure on every read: one call instead of many."""
    heads, tails, offset = [], [], 32 * len(reads)
    for target, data in reads:
        raw = data[2:]
        body = (_word(target) + _u(1) + _u(96) + _u(len(raw) // 2)
                + raw + "0" * ((64 - len(raw) % 64) % 64))
        heads.append(_u(offset))
        tails.append(body)
        offset += len(body) // 2
    return _call(MULTICALL, AGGREGATE3 + _u(32) + _u(len(reads)) + "".join(heads) + "".join(tails),
                 at)


def _unpack(result, count):
    """aggregate3's (bool success, bytes returnData)[]: each read's data, None if it reverted."""
    text = str(result or "")[2:]

    def word(i):
        return _int(text[64 * i:64 * i + 64] or "0")

    start = word(0) // 32
    if word(start) != count:
        raise RuntimeError("Multicall3 answered " + str(word(start)) + " reads of " + str(count))
    out = []
    for k in range(count):
        item = start + 1 + word(start + 1 + k) // 32
        data = item + word(item + 1) // 32
        length = word(data)
        value = text[64 * (data + 1):64 * (data + 1) + 2 * length]
        out.append("0x" + value if word(item) == 1 else None)
    return out


def _text(data):
    """A token's own name or symbol: printable characters only, at most 64 of them."""
    try:
        value = _string(data) if data and len(data) > 2 else None
    except ValueError:
        return None
    value = "".join(c for c in (value or "") if c.isprintable())
    return value[:MAX_TEXT] or None


def _pick(rows):
    """The deepest pool whose price moved, among pools at least 1 % as deep as the deepest one;
    else the deepest pool with an average (its last trade); else the deepest pool's spot price.
    A pool far thinner than the deepest one can trade at a price nobody else pays."""
    live = [r for r in rows if r["liquidity"] > 0 and r["depth"] > 0]
    floor = max((r["depth"] for r in live), default=Decimal(0)) * CROSS_CHECK_SHARE
    traded = [r for r in live if r["traded"] and r["twap"] is not None and r["depth"] >= floor]
    averaged = [r for r in live if r["twap"] is not None]
    for group, basis in ((traded, "twap"), (averaged, "last_trade"), (live, "spot")):
        if group:
            return max(group, key=lambda r: r["depth"]), basis, traded
    return None, None, traded


BASIS = {
    "twap": "the deepest pool whose price moved in the window",
    "last_trade": "no pool at least 1 % as deep as the deepest one moved in the window: the "
                  "deepest pool's average is its last trade before it",
    "spot": "no pool's oracle reaches back that far: this is the deepest pool's spot price, which "
            "one swap can move",
}


def _token(token, window, head, checks):
    """Any ERC-20 on Base: what the contract says it is, and its Uniswap v3 pools (USDC, WETH)."""
    for asset, (address, _d, _s, _p) in ASSETS.items():
        if token == address:
            return _asset(asset, window, head, checks, TOKEN_RPC)
    if token == USDC:
        raise ValueError("USDC is the quote here; it is taken as one dollar")
    at = hex(head["number"])
    pairs = [(quote, fee) for quote in (USDC, WETH) for fee in FEES]
    reads = [(FACTORY, GET_POOL + _word(min(token, q)) + _word(max(token, q)) + _u(fee))
             for q, fee in pairs]
    reads += [(token, DECIMALS), (token, SYMBOL), (token, NAME), (token, TOTAL_SUPPLY)]
    code, multi = (_result(a) for a in _strict(_batch(
        [("eth_getCode", [token, at]), _aggregate(reads, at)], TOKEN_RPC)))
    if not code or code == "0x":
        raise ValueError("there is no contract at " + token + " on Base at block "
                         + str(head["number"]))
    got = _unpack(multi, len(reads))
    n = len(pairs)
    dec = got[n]
    if not dec or len(_words(dec)) != 1 or _int(_words(dec)[0]) > 77:
        raise ValueError(token + " does not answer decimals() as an ERC-20 at block "
                         + str(head["number"]))
    decimals = _int(_words(dec)[0])
    symbol = _text(got[n + 1]) or token
    name = _text(got[n + 2])
    supply = got[n + 3]
    pools = [(q, fee, "0x" + g[-40:]) for (q, fee), g in zip(pairs, got[:n], strict=True)
             if g and len(g) >= 42 and int(g, 16) != 0]
    checks.append({"check": "factory_pools", "ok": bool(pools),
                   "detail": str(len(pools)) + " Uniswap v3 pools of " + symbol
                             + " with USDC or WETH, from the factory's getPool"})
    if not pools:
        raise ValueError("no Uniswap v3 pool of " + symbol + " with USDC or WETH on Base at block "
                         + str(head["number"]))
    reads = []
    for _q, _fee, pool in pools:
        reads += [(pool, LIQUIDITY), (pool, SLOT0), (pool, _observe_data(window))]
    answers = _unpack(_result(_strict(_batch([_aggregate(reads, at)], TOKEN_RPC))[0]), len(reads))
    rows = []
    for i, (quote, fee, pool) in enumerate(pools):
        liq, slot0, observed = answers[3 * i:3 * i + 3]
        qdec = 6 if quote == USDC else 18
        spot_raw, spot_tick = _spot(slot0)
        mean = _mean_tick(observed, window)
        liquidity = _int(liq[2:]) if liq and len(liq) > 2 else 0
        depth = Decimal(0)
        if spot_raw:  # the token side of the in-range liquidity at the current price
            root = spot_raw.sqrt()
            virtual = Decimal(liquidity) / root if token < quote else Decimal(liquidity) * root
            depth = virtual / Decimal(10) ** decimals
        rows.append({
            "quote": "USDC" if quote == USDC else "WETH", "fee_pct": str(Decimal(fee) / 10000),
            "pool": pool, "liquidity": liquidity,
            "twap": _in_quote(_raw_price(mean) if mean is not None else None, token, decimals,
                              quote, qdec),
            "spot": _in_quote(spot_raw, token, decimals, quote, qdec),
            "traded": mean is not None and spot_tick is not None and mean != spot_tick,
            "depth": depth,
            **({} if mean is not None or spot_raw is None else
               {"note": "observe refused this window (the pool's oracle does not reach back "
                        "that far)"}),
        })
    eth = None
    if any(r["quote"] == "WETH" and r["liquidity"] > 0 for r in rows):
        eth_checks = []
        eth = _asset("ETH", window, head, eth_checks, TOKEN_RPC)
        checks.extend({**c, "check": "eth_" + c["check"]} for c in eth_checks)
    for r in rows:
        rate = Decimal(1) if r["quote"] == "USDC" else (Decimal(eth["price_usd"]) if eth else None)
        r["usd"] = r["twap"] * rate if r["twap"] is not None and rate else None
        r["spot_usd"] = r["spot"] * rate if r["spot"] is not None and rate else None
        r["depth_1pct"] = r["depth"] * ONE_PERCENT
        r["depth_1pct_usd"] = r["depth_1pct"] * r["spot_usd"] if r["spot_usd"] else None
    best, basis, traded = _pick([r for r in rows if r["spot_usd"] is not None])
    if best is None:
        raise RuntimeError("no pool of " + symbol + " holds liquidity at its current price")
    checks.append({"check": "traded_pool", "ok": basis == "twap", "detail": BASIS[basis]})
    floor = best["depth"] * CROSS_CHECK_SHARE
    for r in rows:
        if r is not best and r["depth"] < floor and not r.get("note"):
            r["note"] = ("under 1 % of the chosen pool's depth: its price is whatever the last "
                         "swap left, not a market price")
    other = [r for r in traded if r["quote"] != best["quote"] and r["depth"] >= floor]
    if basis == "twap" and other:
        peer = max(other, key=lambda r: r["depth"])
        gap = abs(peer["usd"] - best["usd"]) / best["usd"] * 100
        checks.append({"check": "routes_agree", "ok": gap <= ROUTES_AGREE_PCT,
                       "detail": "the deepest " + peer["quote"] + " pool is "
                                 + str(gap.quantize(Decimal("0.0001"))) + " % from it"})
    price = best["usd"] if basis != "spot" else best["spot_usd"]
    out = {
        "token": token, "name": name, "symbol": symbol, "decimals": decimals,
        "supply_on_base": (str((Decimal(_int(supply[2:])) / Decimal(10) ** decimals).normalize())
                           if supply and len(supply) > 2 else None),
        "quote": "USDC",
        "price_usd": _fmt(price, 12), "price_basis": basis,
        "spot_usd": _fmt(best["spot_usd"], 12),
        "spot_vs_twap_pct": (_pct(best["spot_usd"], best["usd"])
                             if best["spot_usd"] and best["usd"] else None),
        "route": "direct USDC pool" if best["quote"] == "USDC" else "WETH pool x ETH/USDC",
        "pool": best["pool"], "fee_pct": best["fee_pct"],
        "depth_1pct_usd": _amount(best["depth_1pct_usd"], 2),
        "pools": [{"pool": r["pool"], "quote": r["quote"], "fee_pct": r["fee_pct"],
                   "liquidity": r["liquidity"], "traded": r["traded"],
                   "twap": _fmt(r["twap"], 12), "spot": _fmt(r["spot"], 12),
                   "price_unit": r["quote"] + " per " + symbol,
                   "depth_1pct_tokens": _amount(r["depth_1pct"], 6),
                   "depth_1pct_usd": _amount(r["depth_1pct_usd"], 2),
                   **({"note": r["note"]} if r.get("note") else {})} for r in rows],
    }
    if eth is not None:
        out["eth_usd"] = eth["price_usd"]
    return out


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: asset (\"ETH\" or \"BTC\"), token or pool")
    window = _window(payload)
    block = _block(payload)
    asset = str(payload.get("asset") or "").strip().upper()
    token = None
    if payload.get("pool"):
        pool = _address(payload["pool"], "pool")
    elif payload.get("token"):
        pool, token = None, _address(payload["token"], "token")
    elif asset in ASSETS:
        pool = None
    else:
        raise ValueError("give asset: " + " or ".join(ASSETS)
                         + ", token: an ERC-20 address on Base, or pool: a Uniswap v3 pool "
                           "address on Base")
    head = _head(block, TOKEN_RPC if token else RPC)
    checks = [{"check": "chain", "ok": True, "detail": "the RPC serves Base (8453)"}]
    if pool:
        out = _pool(pool, window, head, checks)
    elif token:
        out = _token(token, window, head, checks)
    else:
        out = _asset(asset, window, head, checks)
    out.update({
        "window_s": window,
        "block": head["number"],
        "block_hash": head["hash"],
        "block_time": head["timestamp"],
        "source": "Uniswap v3 pools on Base, read from " + (RPC if _no_pool else POOL)
                  + " at this block",
        "method": "time-weighted average of the pool's oracle ticks over window_s; spot from slot0",
        "limits": "what these pools priced, not a market-wide price; Uniswap v3 on Base only (not "
                  "Aerodrome or other venues); USDC is taken as one dollar; no volume or market "
                  "capitalisation" + ("; supply_on_base is what the contract reports here (for "
                  "a bridged token, only the bridged part); name and symbol are the contract's "
                  "own words: anyone can deploy a token called USDC" if token else ""),
        "checks": checks,
    })
    return out
