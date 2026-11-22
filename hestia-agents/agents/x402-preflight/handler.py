"""x402.preflight@v1: should an agent pay this 402? What it asks, to whom, and what is known about
them.

Give `url`, the paid resource (https), and how the agent would call it: `method` (GET, POST or HEAD;
default GET) and, for POST, a small JSON `body`. `max_usd` is the agent's budget for one call
(default 1.00). The agent makes that one unpaid request and reads the 402: x402 V1 (`accepts` in the
JSON body) or V2 (the base64 PAYMENT-REQUIRED header), as the AIMarket hub's own reader does. It
pays nothing and signs nothing.

For each offer it reports scheme, network, asset, amount (and USD for USDC), payTo, the resource it
binds and the timeout; then, for the first `exact` USDC offer on Base or Base Sepolia, it checks:
  - the asset is that chain's USDC, and the EIP-712 domain the offer names (extra.name and
    extra.version) is that token's ("USD Coin"/"2" on Base, "USDC"/"2" on Base Sepolia): with
    another domain a wallet's signature fails on chain;
  - the amount is within max_usd; payTo is a valid, non-zero address that is not the token itself;
  - the resource the offer binds is on the host that was called;
  - payTo on chain, at one block: a key or a contract (or an EIP-7702 delegate), and the USDC
    Transfer logs it received in the last `window_hours` (default 24): how many, from how many
    payers, how much;
  - whether the modelmarket.dev hub lists the seller as an observed x402 seller (with the seller's
    consent) and whether the payTo it pinned is this one.

Verdict: looks_payable, review_first (something an agent should not decide alone: a payee with no
payments in the window, a resource on another host, an unusual timeout), do_not_pay (over budget,
not USDC, a domain the token will refuse, an invalid payTo), no_payment_required, or not_x402.
"""

import base64
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

NETWORKS = {  # CAIP-2 -> (name, RPC, USDC, EIP-712 name, version)
    "eip155:8453": (
        "base",
        "https://base-rpc.publicnode.com",
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "USD Coin",
        "2",
    ),
    "eip155:84532": (
        "base-sepolia",
        "https://base-sepolia-rpc.publicnode.com",
        "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
        "USDC",
        "2",
    ),
}
NAMES = {"base": "eip155:8453", "base-sepolia": "eip155:84532"}
HUB = "https://modelmarket.dev/ai-market/v2/federation/observed-sellers"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BLOCK_SECONDS = 2  # Base and Base Sepolia
MAX_BODY = 8 * 1024
HEX = "0123456789abcdef"


def _address(value):
    text = str(value or "").strip().lower()
    return (
        text
        if text.startswith("0x") and len(text) == 42 and all(c in HEX for c in text[2:])
        else None
    )


def _usd(atomic):
    return str((Decimal(atomic) / Decimal(10**6)).normalize())


def header_offer(headers):
    raw = str((headers or {}).get("payment-required") or "").strip()
    if not raw or len(raw) > 64 * 1024:
        return None
    for alphabet in ("standard", "url"):
        try:
            text = raw + "=" * (-len(raw) % 4)
            data = base64.urlsafe_b64decode(text) if alphabet == "url" else base64.b64decode(text)
            doc = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            continue
        return doc if isinstance(doc, dict) else None
    return None


def read_402(status, headers, text):
    """(x402 version, accepts, resource of the challenge) or None."""
    try:
        body = json.loads(text) if text and text.strip()[:1] == "{" else {}
    except ValueError:
        body = {}
    accepts, version, resource = body.get("accepts"), body.get("x402Version"), body.get("resource")
    if not (isinstance(accepts, list) and accepts):
        header = header_offer(headers)
        if header:
            accepts, version, resource = (
                header.get("accepts"),
                header.get("x402Version"),
                header.get("resource"),
            )
    if not isinstance(accepts, list) or not accepts:
        return None
    return version, [a for a in accepts[:16] if isinstance(a, dict)], resource


def offer(accept, challenge_resource):
    network = str(accept.get("network") or "").strip()
    caip = NAMES.get(network, network)
    raw = accept.get("maxAmountRequired", accept.get("amount"))
    text = str(raw) if isinstance(raw, (str, int)) and not isinstance(raw, bool) else ""
    atomic = int(text) if re.fullmatch(r"[0-9]{1,78}", text) else None
    resource = accept.get("resource") or challenge_resource
    if isinstance(resource, dict):
        resource = resource.get("url")
    extra = accept.get("extra") if isinstance(accept.get("extra"), dict) else {}
    row = {
        "scheme": str(accept.get("scheme") or ""),
        "network": caip,
        "asset": str(accept.get("asset") or ""),
        "amount_atomic": text or None,
        "pay_to": str(accept.get("payTo") or ""),
        "resource": resource,
        "max_timeout_seconds": accept.get("maxTimeoutSeconds"),
        "eip712": {k: extra.get(k) for k in ("name", "version") if k in extra} or None,
        "description": str(accept.get("description") or "")[:300] or None,
    }
    known = NETWORKS.get(caip)
    if known and row["asset"].lower() == known[2]:
        row["asset_name"] = "USDC"
        if atomic is not None:
            row["amount_usd"] = _usd(atomic)
    row["_atomic"] = atomic
    return row


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


def _rpc(url, calls):
    reply = _post(
        url,
        [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)],
    )
    if not reply.ok:
        raise RuntimeError("the RPC answered HTTP " + str(reply.status))
    body = reply.json()
    if not isinstance(body, list):
        raise RuntimeError("the RPC refused the batch: " + str(body)[:160])
    by_id = {item.get("id"): item for item in body if isinstance(item, dict)}
    return [by_id.get(i, {}) for i in range(len(calls))]


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: url, optionally method, body, max_usd, window_hours")
    url = str(payload.get("url") or "").strip()
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.port not in (None, 443)
    ):
        raise ValueError("url must be an https URL on port 443 with no credentials")
    host = parts.hostname.lower()
    method = str(payload.get("method") or "GET").upper()
    if method not in ("GET", "POST", "HEAD"):
        raise ValueError("method must be GET, POST or HEAD")
    body = None
    if payload.get("body") is not None:
        if method != "POST":
            raise ValueError("a body goes with POST only")
        body = json.dumps(payload["body"], ensure_ascii=False, separators=(",", ":"))
        if len(body.encode("utf-8")) > MAX_BODY:
            raise ValueError("body must be at most 8 KiB of JSON")
    try:
        budget = Decimal(str(payload.get("max_usd", "1.00")))
    except InvalidOperation:
        raise ValueError("max_usd must be a decimal number such as 0.05") from None
    if not Decimal("0") < budget <= Decimal("10000"):
        raise ValueError("max_usd must be above 0 and at most 10000")
    hours = payload.get("window_hours", 24)
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 24:
        raise ValueError("window_hours must be a whole number from 1 to 24")

    out = {"url": url, "method": method}
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    reply = fetch(url, method=method, headers=headers, body=body)  # noqa: F821
    out["status"] = reply.status
    if 200 <= reply.status < 300:
        out.update(
            verdict="no_payment_required",
            detail="the resource answered " + str(reply.status) + " without payment",
        )
        return out
    parsed = read_402(reply.status, reply.headers, reply.text) if reply.status == 402 else None
    if parsed is None:
        out.update(
            verdict="not_x402",
            detail=(
                "a 402 with no x402 offer in its body or PAYMENT-REQUIRED header"
                if reply.status == 402
                else "the resource answered " + str(reply.status) + ", not 402"
            ),
        )
        return out
    version, accepts, resource = parsed
    out["x402_version"] = version
    offers = [offer(a, resource) for a in accepts]
    chosen = next((o for o in offers if o["scheme"] == "exact" and o["network"] in NETWORKS), None)
    out["offers"] = [
        {k: v for k, v in o.items() if not k.startswith("_") and v is not None} for o in offers
    ]
    checks, notes = [], []
    out["checks"] = checks

    def check(name, ok, detail, severity):
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "severity": severity})

    if chosen is None:
        out.update(
            verdict="review_first",
            detail="no exact-scheme offer on Base or Base Sepolia, which this agent checks; "
            "the offers are listed",
        )
        return out
    name, rpc, usdc, token_name, token_version = NETWORKS[chosen["network"]]
    out["checked_offer"] = offers.index(chosen)
    asset_ok = chosen["asset"].lower() == usdc
    check(
        "asset_is_usdc",
        asset_ok,
        ("USDC on " + name)
        if asset_ok
        else "asset " + chosen["asset"] + " is not " + name + "'s USDC (" + usdc + ")",
        "refuse",
    )
    eip712 = chosen["eip712"] or {}
    domain_ok = eip712.get("name") == token_name and str(eip712.get("version")) == token_version
    check(
        "eip712_domain",
        domain_ok,
        ("names the token's own EIP-712 domain " + token_name + " / " + token_version)
        if domain_ok
        else "names domain "
        + json.dumps(eip712)
        + "; USDC on "
        + name
        + " is "
        + json.dumps({"name": token_name, "version": token_version})
        + ", so a signature over it fails",
        "refuse",
    )
    atomic = chosen["_atomic"]
    within = atomic is not None and asset_ok and Decimal(atomic) / Decimal(10**6) <= budget
    check(
        "within_budget",
        within,
        ("$" + _usd(atomic) + " within $" + str(budget))
        if within
        else (
            "the amount is not a positive whole number"
            if atomic is None
            else "$" + _usd(atomic) + " is over the budget of $" + str(budget)
            if asset_ok
            else "not priced in USDC"
        ),
        "refuse",
    )
    pay_to = _address(chosen["pay_to"])
    pay_ok = pay_to is not None and pay_to != "0x" + "0" * 40 and pay_to != usdc
    check(
        "pay_to",
        pay_ok,
        "payTo "
        + chosen["pay_to"]
        + (" is a valid recipient" if pay_ok else " is not a usable recipient"),
        "refuse",
    )
    res_host = urlsplit(str(chosen["resource"] or "")).hostname
    same = res_host is None or res_host.lower() == host
    check(
        "resource_on_this_host",
        same,
        "the offer binds "
        + str(chosen["resource"])
        + (", on the host called" if same else ", on another host than " + host),
        "review",
    )
    timeout = chosen["max_timeout_seconds"]
    t_ok = isinstance(timeout, int) and not isinstance(timeout, bool) and 5 <= timeout <= 3600
    check(
        "timeout",
        t_ok,
        "maxTimeoutSeconds "
        + str(timeout)
        + (" is ordinary" if t_ok else " is outside 5 to 3600 s"),
        "review",
    )

    if pay_ok:
        payee = {"address": pay_to, "network": name}
        out["payee"] = payee
        try:
            head = _rpc(rpc, [("eth_chainId", []), ("eth_blockNumber", [])])
            chain = int(head[0].get("result", "0x0"), 16)
            if "eip155:" + str(chain) != chosen["network"]:
                raise RuntimeError("the RPC serves chain " + str(chain))
            block = int(head[1]["result"], 16)
            span = hours * 3600 // BLOCK_SECONDS
            topic = "0x" + "0" * 24 + pay_to[2:]
            facts = _rpc(
                rpc,
                [
                    ("eth_getCode", [pay_to, hex(block)]),
                    (
                        "eth_getLogs",
                        [
                            {
                                "address": usdc,
                                "topics": [TRANSFER, None, topic],
                                "fromBlock": hex(max(0, block - span)),
                                "toBlock": hex(block),
                            }
                        ],
                    ),
                ],
            )
            code = str(facts[0].get("result") or "0x")
            payee["block"] = block
            payee["kind"] = (
                "eip7702_delegated"
                if code.startswith("0xef0100") and len(code) == 48
                else "contract"
                if code not in ("0x", "0x0")
                else "key"
            )
            logs = facts[1].get("result")
            if isinstance(logs, list):
                payers = {
                    str(log["topics"][1])[-40:] for log in logs if len(log.get("topics") or []) == 3
                }
                total = sum(int(log.get("data") or "0x0", 16) for log in logs)
                payee.update(
                    window_hours=hours,
                    usdc_transfers_in=len(logs),
                    distinct_payers=len(payers),
                    usdc_received=_usd(total),
                )
                check(
                    "payee_has_payments",
                    len(logs) > 0,
                    str(len(logs))
                    + " USDC transfers in from "
                    + str(len(payers))
                    + " payers in the last "
                    + str(hours)
                    + " h"
                    if logs
                    else "no USDC received in the last " + str(hours) + " h",
                    "review",
                )
            else:
                notes.append(
                    "the RPC did not return the payee's logs: " + str(facts[1].get("error"))[:120]
                )
        except Exception as exc:  # never the fetch signal: that is a BaseException
            notes.append("chain facts not read: " + str(exc)[:160])
    try:
        hub = fetch(HUB, headers={"accept": "application/json"})  # noqa: F821
        sellers = (json.loads(hub.text) or {}).get("sellers") if hub.ok else None
        listing = None
        for seller in sellers or []:
            origin_host = urlsplit(str(seller.get("origin") or "")).hostname
            if origin_host and origin_host.lower() == host:
                listing = {
                    "listed": True,
                    "consent": bool((seller.get("consent") or {}).get("recorded")),
                    "observed_at": seller.get("observed_at"),
                    "pinned_pay_to": seller.get("pinned_pay_to"),
                }
                if pay_to and seller.get("pinned_pay_to"):
                    listing["pinned_pay_to_matches"] = (
                        str(seller["pinned_pay_to"]).lower() == pay_to
                    )
                break
        out["hub_listing"] = listing or {"listed": False}
        if listing and listing.get("pinned_pay_to_matches") is False:
            check(
                "hub_pinned_pay_to",
                False,
                "modelmarket.dev observed this seller paying to "
                + str(listing["pinned_pay_to"])
                + ", this 402 names "
                + str(pay_to),
                "review",
            )
    except Exception as exc:
        notes.append("hub listing not read: " + str(exc)[:160])
    if notes:
        out["notes"] = notes
    failed = [c for c in checks if not c["ok"]]
    if any(c["severity"] == "refuse" for c in failed):
        out["verdict"] = "do_not_pay"
    elif failed:
        out["verdict"] = "review_first"
    else:
        out["verdict"] = "looks_payable"
    return out
