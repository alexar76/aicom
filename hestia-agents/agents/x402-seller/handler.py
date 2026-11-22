"""x402.seller.record@v1: what an x402 payee has actually been paid on Base, before an agent pays it.

A 402 says what a seller asks; the chain says whether anyone pays it. Give `pay_to` (the address an
offer names) or `url` (a paid resource: the agent makes one unpaid request, reads the first exact USDC
offer on Base, V1 body or V2 PAYMENT-REQUIRED header, and takes its payTo and price). `hours` is the
window, 1 to 48 (default 24). `to_block` pins the window's last block, so a result can be checked again.
Base blocks are 0.2 s apart (18,000 an hour), so a window is counted in blocks and the timestamps of its
first and last block are read with the logs: the answer says the hours it actually covered.

The agent reads every USDC Transfer to that address in the window from Base's public RPC, in ranges
of at most 50,000 blocks, and reports what the transfers show and nothing more:
  - how many, how much, from how many payers; payers who came back (two or more payments) and the
    share of the busiest payer;
  - the most common amounts and, with a price, how many payments were exactly that price;
  - payments per UTC hour, the first and the last;
  - every range it read, with its blocks, and whether the window is complete.

`activity` is a label for those numbers, defined here so anyone can recompute it: none (no transfer),
one_payer (a single address paid), concentrated (the busiest payer made half the payments or more,
from three payments up), few_payers (two payers), spread (anything else). A transfer proves money
moved, not that a service was delivered or who controls the payers: a seller can pay itself from
other addresses. The address may also receive USDC for other reasons than x402 sales.
Reads Base through the hearth's RPC pool (base-rpc.hestia.modelmarket.dev), else
base-rpc.publicnode.com, and, with `url`, that URL's host.
"""
# ruff: noqa: E501 — the answer texts are kept whole

import base64
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

RPC = "https://base-rpc.publicnode.com"
CHAIN_ID = "0x2105"  # 8453, Base mainnet
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BLOCKS_PER_HOUR = 18000  # Base blocks are 0.2 s apart (2026-11-22: 3,024,000 blocks = 7 days)
MAX_HOURS = 48  # 864,000 blocks = 18 log reads, what fits the hearth's six requests
CONFIRMATIONS = 12
RANGE = 50000  # the most blocks base-rpc.publicnode.com serves in one eth_getLogs
ROUNDS = 6  # the hearth allows six requests per call
MAX_BODY = 8 * 1024
HEX = "0123456789abcdef"
TOP = 5


def _address(value, where):
    text = str(value or "").strip().lower()
    if not (text.startswith("0x") and len(text) == 42 and all(c in HEX for c in text[2:])):
        raise ValueError(where + " must be a 0x address of 40 hex digits")
    if int(text, 16) == 0:
        raise ValueError(where + " is the zero address")
    return text


def _usd(atomic):
    value = (Decimal(atomic) / Decimal(10**6)).quantize(Decimal("0.000001"))
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _int_field(payload, key, low, high, default):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(key + " must be a whole number from " + str(low) + " to " + str(high))
    return value


def _price(payload):
    if payload.get("amount") is not None:
        raw = str(payload["amount"]).strip()
        if isinstance(payload["amount"], bool) or not raw.isdigit() or int(raw) == 0:
            raise ValueError(
                "amount is USDC's smallest unit as a whole number, e.g. 10000 for $0.01"
            )
        return int(raw)
    if payload.get("amount_usd") is not None:
        try:
            value = Decimal(str(payload["amount_usd"]).strip())
        except InvalidOperation:
            raise ValueError("amount_usd must be a decimal number such as 0.01") from None
        units = value * 10**6
        if value <= 0 or units != units.to_integral_value():
            raise ValueError("amount_usd must be positive with at most 6 decimals")
        return int(units)
    return None


# -- the 402 (as x402.preflight@v1 reads it) ------------------------------------------------------


def _header_doc(headers):
    raw = str((headers or {}).get("payment-required") or "").strip()
    if not raw or len(raw) > 64 * 1024:
        return None
    for url_safe in (False, True):
        try:
            text = raw + "=" * (-len(raw) % 4)
            data = base64.urlsafe_b64decode(text) if url_safe else base64.b64decode(text)
            doc = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            continue
        return doc if isinstance(doc, dict) else None
    return None


def _offer(reply):
    try:
        body = json.loads(reply.text) if reply.text and reply.text.strip()[:1] == "{" else {}
    except ValueError:
        body = {}
    accepts = body.get("accepts") if isinstance(body, dict) else None
    resource = body.get("resource") if isinstance(body, dict) else None
    if not (isinstance(accepts, list) and accepts):
        doc = _header_doc(reply.headers) or {}
        accepts, resource = doc.get("accepts"), doc.get("resource")
    if not isinstance(accepts, list):
        return None
    for accept in accepts[:16]:
        if not isinstance(accept, dict) or str(accept.get("scheme") or "") != "exact":
            continue
        if str(accept.get("network") or "") not in ("base", "eip155:8453"):
            continue
        if str(accept.get("asset") or "").lower() != USDC:
            continue
        raw = str(accept.get("maxAmountRequired", accept.get("amount")) or "")
        where = accept.get("resource") or resource
        if isinstance(where, dict):
            where = where.get("url")
        return {
            "pay_to": _address(accept.get("payTo"), "the offer's payTo"),
            "amount_atomic": int(raw) if raw.isdigit() else None,
            "resource": str(where or "")[:500] or None,
        }
    return None


def _probe(payload):
    url = str(payload.get("url") or "").strip()
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.port not in (None, 443)
    ):
        raise ValueError("url must be an https URL on port 443 with no credentials")
    method = str(payload.get("method") or "GET").upper()
    if method not in ("GET", "POST"):
        raise ValueError("method must be GET or POST")
    body, headers = None, {"accept": "application/json"}
    if payload.get("body") is not None:
        if method != "POST":
            raise ValueError("a body goes with POST only")
        body = json.dumps(payload["body"], ensure_ascii=False, separators=(",", ":"))
        if len(body.encode("utf-8")) > MAX_BODY:
            raise ValueError("body must be at most 8 KiB of JSON")
        headers["content-type"] = "application/json"
    reply = fetch(url, method=method, headers=headers, body=body)  # noqa: F821 — the sandbox provides fetch()
    if reply.status != 402:
        raise ValueError("the url answered " + str(reply.status) + ", not 402: give pay_to instead")
    offer = _offer(reply)
    if offer is None:
        raise ValueError("the 402 has no exact USDC offer on Base: give pay_to instead")
    offer["url"] = url
    return offer


# -- the chain ------------------------------------------------------------------------------------


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


def _batch(calls):
    body = [
        {"jsonrpc": "2.0", "id": i + 1, "method": m, "params": p} for i, (m, p) in enumerate(calls)
    ]
    reply = _post(RPC, body)
    if not reply.ok:
        raise RuntimeError("the RPC answered HTTP " + str(reply.status))
    answers = reply.json()
    if not isinstance(answers, list):
        raise RuntimeError("the RPC did not answer the batch: " + str(answers)[:160])
    by_id = {a.get("id"): a for a in answers if isinstance(a, dict)}
    return [by_id.get(i + 1) or {"error": {"message": "no answer"}} for i in range(len(calls))]


def _logs_call(pay_to, start, stop):
    topic = "0x" + pay_to[2:].zfill(64)
    return (
        "eth_getLogs",
        [
            {
                "address": USDC,
                "fromBlock": hex(start),
                "toBlock": hex(stop),
                "topics": [TRANSFER, None, topic],
            }
        ],
    )


def _slices(start, end, count):
    """Split [start, end] into at most `count` slices; each slice is ranges of at most RANGE blocks."""
    total = end - start + 1
    size = -(-total // count)
    out, at = [], start
    while at <= end:
        stop = min(end, at + size - 1)
        ranges, r = [], at
        while r <= stop:
            ranges.append((r, min(stop, r + RANGE - 1)))
            r += RANGE
        out.append(ranges)
        at = stop + 1
    return out


def _day(ts):
    days = ts // 86400  # civil date from days since 1970-01-01 (Howard Hinnant's algorithm)
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = yoe + era * 400 + (1 if m <= 2 else 0)
    return f"{y:04d}-{m:02d}-{d:02d}"


def _iso(ts):
    rest = ts % 86400
    return f"{_day(ts)}T{rest // 3600:02d}:{rest // 60 % 60:02d}:{rest % 60:02d}Z"


def _read(pay_to, start, end, rounds, check_chain):
    """Every transfer to pay_to in [start, end], the window's first and last block times; ranges that
    could not be read are listed."""
    transfers, read, missing, seen = [], [], [], set()
    times = {}
    for n, ranges in enumerate(_slices(start, end, rounds)):
        calls = [("eth_chainId", [])] if check_chain and n == 0 else []
        if n == 0:
            calls += [("eth_getBlockByNumber", [hex(start), False]),
                      ("eth_getBlockByNumber", [hex(end), False])]
        calls += [_logs_call(pay_to, a, b) for a, b in ranges]
        try:
            answers = _batch(calls)
        except Exception as exc:  # a refused or failed round: the slice stays unread
            for a, b in ranges:
                missing.append({"from_block": a, "to_block": b, "reason": str(exc)[:160]})
            continue
        if calls[0][0] == "eth_chainId":
            chain = answers.pop(0)
            if chain.get("result") != CHAIN_ID:
                raise RuntimeError(
                    "the RPC is not Base mainnet (chain " + str(chain.get("result")) + ")"
                )
        if n == 0:
            for name in ("from", "to"):
                block = answers.pop(0).get("result")
                if isinstance(block, dict) and block.get("timestamp"):
                    times[name] = int(block["timestamp"], 16)
        for (a, b), answer in zip(ranges, answers, strict=False):
            logs = answer.get("result")
            if not isinstance(logs, list):
                reason = str((answer.get("error") or {}).get("message") or "no result")[:160]
                missing.append({"from_block": a, "to_block": b, "reason": reason})
                continue
            read.append({"from_block": a, "to_block": b, "transfers": len(logs)})
            for log in logs:
                topics = log.get("topics") or []
                if (
                    log.get("removed")
                    or len(topics) != 3
                    or str(log.get("address", "")).lower() != USDC
                ):
                    continue
                if topics[2].lower() != "0x" + pay_to[2:].zfill(64):
                    continue
                key = (log.get("transactionHash"), log.get("logIndex"))
                if key in seen:
                    continue
                seen.add(key)
                ts = log.get("blockTimestamp")
                transfers.append(
                    {
                        "payer": "0x" + topics[1][-40:].lower(),
                        "atomic": int(log.get("data") or "0x0", 16),
                        "block": int(log["blockNumber"], 16),
                        "ts": int(ts, 16) if ts else None,
                        "tx": log.get("transactionHash"),
                    }
                )
    return transfers, read, missing, times


def _summary(transfers, pay_to, price):
    count = len(transfers)
    total = sum(t["atomic"] for t in transfers)
    payers = {}
    for t in transfers:
        row = payers.setdefault(t["payer"], [0, 0])
        row[0] += 1
        row[1] += t["atomic"]
    ranked = sorted(payers.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
    amounts = {}
    for t in transfers:
        amounts[t["atomic"]] = amounts.get(t["atomic"], 0) + 1
    hours = {}
    for t in transfers:
        if t["ts"] is not None:
            row = hours.setdefault(_iso(t["ts"] - t["ts"] % 3600)[:13] + "Z", [0, 0])
            row[0] += 1
            row[1] += t["atomic"]
    stamped = sorted(t["ts"] for t in transfers if t["ts"] is not None)
    top_share = _pct(ranked[0][1][0], count) if ranked else 0.0
    if not count:
        activity = "none"
    elif len(payers) == 1:
        activity = "one_payer"
    elif count >= 3 and top_share >= 50.0:
        activity = "concentrated"
    elif len(payers) == 2:
        activity = "few_payers"
    else:
        activity = "spread"
    out = {
        "activity": activity,
        "transfers": count,
        "total_usd": _usd(total),
        "payers": len(payers),
        "returning_payers": sum(1 for _, (n, _a) in ranked if n >= 2),
        "busiest_payer_share_pct": top_share,
        "top_payers": [
            {"address": a, "transfers": n, "usd": _usd(s), "share_of_usd_pct": _pct(s, total)}
            for a, (n, s) in ranked[:TOP]
        ],
        "common_amounts": [
            {"usd": _usd(a), "transfers": n}
            for a, n in sorted(amounts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP]
        ],
        "by_hour": [
            {"hour": h, "transfers": n, "usd": _usd(s)} for h, (n, s) in sorted(hours.items())
        ],
        "first_at": _iso(stamped[0]) if stamped else None,
        "last_at": _iso(stamped[-1]) if stamped else None,
        "from_itself": sum(1 for t in transfers if t["payer"] == pay_to),
    }
    if price is not None:
        out["price_usd"] = _usd(price)
        out["at_price"] = amounts.get(price, 0)
    return out


def _notes(summary, covered, complete):
    notes = []
    n = summary["transfers"]
    if not complete:
        notes.append("Some block ranges could not be read (see missing): the counts are a floor.")
    if n == 0:
        notes.append("No USDC reached this address on Base in the window (" + covered + ").")
        return notes
    if summary["activity"] == "one_payer":
        notes.append("Every payment came from one address.")
    elif summary["activity"] == "concentrated":
        notes.append(
            "One address made "
            + str(summary["top_payers"][0]["transfers"])
            + " of "
            + str(n)
            + " payments."
        )
    if summary["returning_payers"] == 0 and summary["payers"] >= 3:
        notes.append("No payer paid twice in the window.")
    if "at_price" in summary and summary["at_price"] * 2 < n:
        notes.append(
            "Fewer than half the payments are exactly the price ("
            + str(summary["at_price"])
            + " of "
            + str(n)
            + "): the address also receives other USDC, or the price changed."
        )
    if summary["from_itself"]:
        notes.append(str(summary["from_itself"]) + " transfers came from the address itself.")
    return notes


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: pay_to or url, optionally hours, to_block, amount_usd")
    if payload.get("days") is not None and payload.get("hours") is None:
        days = payload["days"]
        if isinstance(days, bool) or days not in (1, 2):
            raise ValueError(
                "days is 1 or 2; give hours (1 to 48): Base blocks are 0.2 s apart, so a week would be "
                "61 log reads, more than one call can make"
            )
        hours = 24 * days
    else:
        hours = _int_field(payload, "hours", 1, MAX_HOURS, 24)
    price = _price(payload)
    used = 0
    offer = None
    if payload.get("pay_to"):
        pay_to = _address(payload["pay_to"], "pay_to")
    elif payload.get("url"):
        offer = _probe(payload)
        used += 1
        pay_to = offer["pay_to"]
        if price is None:
            price = offer.get("amount_atomic")
    else:
        raise ValueError(
            "give pay_to (the payee address) or url (a paid resource that answers 402)"
        )

    if payload.get("to_block") is not None:
        raw = payload["to_block"]
        text = str(raw).strip().lower()
        try:
            end = int(text, 16) if text.startswith("0x") else int(text)
        except ValueError:
            raise ValueError("to_block must be a block number") from None
        if isinstance(raw, bool) or end < BLOCKS_PER_HOUR * hours:
            raise ValueError("to_block must be a Base block number")
        check_chain = True
    else:
        head = _batch([("eth_chainId", []), ("eth_blockNumber", [])])
        used += 1
        if head[0].get("result") != CHAIN_ID:
            raise RuntimeError(
                "the RPC is not Base mainnet (chain " + str(head[0].get("result")) + ")"
            )
        latest = head[1].get("result")
        if not isinstance(latest, str):
            raise RuntimeError("the RPC did not give the latest block")
        end = int(latest, 16) - CONFIRMATIONS
        check_chain = False
    start = end - BLOCKS_PER_HOUR * hours + 1

    # One round stays in hand: on a hearth without the RPC pool, the first request is refused.
    transfers, read, missing, times = _read(pay_to, start, end, ROUNDS - used - 1, check_chain)
    complete = not missing
    covered_h = None
    if "from" in times and "to" in times:
        covered_h = round((times["to"] - times["from"]) / 3600, 2)
    covered = (str(covered_h) + " h by block time") if covered_h is not None else (str(hours) + " h at 0.2 s a block")
    summary = _summary(transfers, pay_to, price)
    out = {
        "pay_to": pay_to,
        "network": "eip155:8453",
        "asset": USDC,
        "window": {
            "hours": hours,
            "from_block": start,
            "to_block": end,
            "from_at": _iso(times["from"]) if "from" in times else None,
            "to_at": _iso(times["to"]) if "to" in times else None,
            "covered_hours": covered_h,
            "complete": complete,
            "read": read,
            "missing": missing,
        },
    }
    if offer is not None:
        out["offer"] = {
            "url": offer["url"],
            "resource": offer.get("resource"),
            "amount_usd": _usd(offer["amount_atomic"]) if offer.get("amount_atomic") else None,
        }
    out.update(summary)
    out["notes"] = _notes(summary, covered, complete)
    if covered_h is not None and abs(covered_h - hours) > 0.1 * hours:
        out["notes"].append(
            "Base's block time is not 0.2 s in this window: " + str(hours) + " h of blocks covered "
            + str(covered_h) + " h."
        )
    out["source"] = RPC + " (eth_getLogs, USDC Transfer logs to pay_to)"
    return out
