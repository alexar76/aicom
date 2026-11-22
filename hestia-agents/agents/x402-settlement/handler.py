"""x402.settlement.check@v1: did this x402 payment really settle on Base, to whom, for how much?

A seller who serves on the strength of a transaction hash should not take the buyer's (or a
facilitator's) word for it. Give `tx` (the settlement transaction hash), `pay_to` (the address that
should have been paid) and the price, `amount` in USDC's smallest unit (6 decimals: 10000 is
$0.01) or `amount_usd` ("0.01"). Optionally `payer` and `nonce`: the EIP-3009 authorization the
buyer signed, which binds this transfer to one invoice.

The agent reads the receipt through the hearth's Base RPC pool (else mainnet.base.org;
sepolia.base.org for `network: "base-sepolia"`), and checks, as the AIMarket hub's own settlement
check does:
  - the chain is the one asked for, the transaction succeeded, its block is canonical;
  - a USDC Transfer log from the token contract to `pay_to` for exactly the amount (more is
    reported, never counted as exact);
  - with `nonce`: an AuthorizationUsed log (payer, nonce) immediately before that Transfer, in the
    same transaction — the transfer is the one that authorization made, not a coincidence;
  - confirmations, and whether the block is at or below the chain's finalized block.
Verdicts: paid (and finalized), paid_not_final, not_paid (the receipt has no such transfer),
failed (reverted), pending (no receipt yet), wrong_chain.
"""

from decimal import Decimal, InvalidOperation

NETWORKS = {
    "base": (8453, "https://mainnet.base.org", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"),
    "base-sepolia": (
        84532,
        "https://sepolia.base.org",
        "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
    ),
}
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AUTHORIZATION_USED = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
HEX = "0123456789abcdef"


def _hex(value, where, size):
    text = str(value or "").strip().lower()
    if not (text.startswith("0x") and len(text) == 2 + size and all(c in HEX for c in text[2:])):
        raise ValueError(where + " must be 0x and " + str(size) + " hex digits")
    return text


def _amount(payload):
    if payload.get("amount") is not None:
        raw = payload["amount"]
        if isinstance(raw, bool) or not str(raw).strip().isdigit():
            raise ValueError(
                "amount is USDC's smallest unit as a whole number, e.g. 10000 for $0.01"
            )
        return int(str(raw).strip())
    if payload.get("amount_usd") is not None:
        try:
            value = Decimal(str(payload["amount_usd"]).strip())
        except InvalidOperation:
            raise ValueError("amount_usd must be a decimal number such as 0.01") from None
        units = value * 1_000_000
        if value <= 0 or units != units.to_integral_value():
            raise ValueError("amount_usd must be positive with at most 6 decimals")
        return int(units)
    raise ValueError("give the price: amount (smallest unit) or amount_usd")


def _topic(address):
    return "0x" + address[2:].zfill(64)


# The hearth's pool of free Base RPCs (hestia.rpc_pool) is tried first for Base mainnet. A hearth
# without it refuses that name, and the agent then reads the public RPC for the rest of the call.
POOL = "https://base-rpc.hestia.modelmarket.dev"
_POOL_FOR = {"https://mainnet.base.org"}
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


def _rpc(url, method, params):
    reply = _post(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if not reply.ok:
        raise RuntimeError("the RPC answered HTTP " + str(reply.status))
    body = reply.json()
    if "error" in body:
        raise RuntimeError("the RPC refused " + method + ": " + str(body["error"])[:160])
    return body.get("result")


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: tx, pay_to, amount or amount_usd")
    network = str(payload.get("network") or "base").strip().lower()
    if network not in NETWORKS:
        raise ValueError("network must be " + " or ".join(NETWORKS))
    chain_id, url, usdc = NETWORKS[network]
    tx = _hex(payload.get("tx"), "tx", 64)
    pay_to = _hex(payload.get("pay_to"), "pay_to", 40)
    amount = _amount(payload)
    payer = _hex(payload["payer"], "payer", 40) if payload.get("payer") else None
    nonce = _hex(payload["nonce"], "nonce", 64) if payload.get("nonce") else None
    if nonce and not payer:
        raise ValueError("a nonce binds an authorization by its payer: give payer too")

    out = {
        "network": network,
        "chain_id": chain_id,
        "tx": tx,
        "token": usdc,
        "pay_to": pay_to,
        "amount": amount,
        "amount_usd": str(Decimal(amount) / 1_000_000),
    }
    checks = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def done(verdict):
        out["verdict"] = verdict
        out["paid"] = verdict in ("paid", "paid_not_final")
        out["checks"] = checks
        return out

    served = int(str(_rpc(url, "eth_chainId", [])), 16)
    if not check("chain", served == chain_id, "the RPC serves chain " + str(served)):
        return done("wrong_chain")
    receipt = _rpc(url, "eth_getTransactionReceipt", [tx])
    if not receipt:
        check("receipt", False, "no receipt: the transaction is unknown or not mined yet")
        return done("pending")
    if not check(
        "succeeded",
        int(receipt.get("status", "0x0"), 16) == 1,
        "status " + str(receipt.get("status")),
    ):
        return done("failed")
    height = int(receipt["blockNumber"], 16)
    block_hash = str(receipt["blockHash"]).lower()
    block = _rpc(url, "eth_getBlockByNumber", [hex(height), False]) or {}
    canonical = (
        int(block.get("number", "0x0"), 16) == height
        and str(block.get("hash", "")).lower() == block_hash
    )
    check(
        "canonical_block",
        canonical,
        "block " + str(height) + (" is" if canonical else " is NOT") + " the canonical one",
    )
    out["block"] = height
    if block.get("timestamp"):
        out["block_time"] = int(block["timestamp"], 16)

    logs = [
        log
        for log in receipt.get("logs") or []
        if not log.get("removed") and str(log.get("address", "")).lower() == usdc
    ]
    moves = []
    for position, log in enumerate(logs):
        topics = [str(t).lower() for t in log.get("topics") or []]
        if len(topics) == 3 and topics[0] == TRANSFER and topics[2] == _topic(pay_to):
            moves.append((position, "0x" + topics[1][-40:], int(str(log.get("data") or "0x0"), 16)))
    exact = [m for m in moves if m[2] == amount and (payer is None or m[1] == payer)]
    if exact:
        found = "a USDC transfer of " + str(amount) + " to pay_to"
    elif moves:
        found = (
            "USDC to pay_to, but "
            + ", ".join(str(m[2]) + " from " + m[1] for m in moves)
            + ", not "
            + str(amount)
            + (" from " + payer if payer else "")
        )
    else:
        found = "no USDC transfer to pay_to in this transaction"
    check("transfer", exact, found)
    out["transfers_to_pay_to"] = [{"from": m[1], "amount": m[2]} for m in moves]
    if exact:
        out["payer"] = exact[0][1]
    if nonce:
        bound = False
        for position, _sender, _value in exact:
            if position > 0:
                before = logs[position - 1]
                topics = [str(t).lower() for t in before.get("topics") or []]
                bound = bound or (
                    topics == [AUTHORIZATION_USED, _topic(payer), nonce]
                    and int(before["logIndex"], 16) + 1 == int(logs[position]["logIndex"], 16)
                )
        check(
            "authorization",
            bound,
            "AuthorizationUsed(payer, nonce) right before the transfer"
            if bound
            else "no AuthorizationUsed for this payer and nonce right before the transfer: "
            "the transfer is not the one this authorization made",
        )
    if not all(c["ok"] for c in checks):
        return done("not_paid")

    latest = int(str(_rpc(url, "eth_blockNumber", [])), 16)
    final = _rpc(url, "eth_getBlockByNumber", ["finalized", False]) or {}
    finalized_at = int(final.get("number", "0x0"), 16)
    out["confirmations"] = max(0, latest - height + 1)
    out["finalized"] = height <= finalized_at
    out["finalized_block"] = finalized_at
    return done("paid" if out["finalized"] else "paid_not_final")
