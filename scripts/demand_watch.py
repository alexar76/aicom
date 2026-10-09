#!/usr/bin/env python3
"""The demand test (2026-10-05 .. 2026-10-26): does anyone outside the ecosystem use
x402.authorization.check or mcp.tools.diff?

The two HESTIA agents were put where their audience already looks — the x402 Bazaar,
x402scan and Agentic.Market (POST https://modelmarket.dev/x402/x402-check and /mcp-diff,
$0.003, paid to the treasury) and the hub's MCP endpoint (direct tool x402_check). This
counts what happens, from two public sources, so it needs no access to any server:

  - Base itself: USDC Transfer logs into the treasury since the start, read with eth_getLogs
    through free public gateways (CHAIN_RPCS, AICOM_DEMAND_RPCS first), a cursor in the state
    so a run that fails leaves the gap to the next one. The payer of an x402 `exact` payment
    is the `from` of its transfer. $0.003 is what both agents cost. (Until 2026-10-09 this
    was Blockscout's API, which Cloudflare answered 403 in 72 of 82 runs: every outside
    payment of those days went unseen, and nothing said so. A source that falls behind now
    sends a message, and the summary says how far the chain was read.)
  - https://verify.modelmarket.dev/mcp-demand.json (scripts/mcp_demand_export.py on the hub's
    host): every call of the two agents that reached them through the hub — MCP trial visitors
    and credit accounts, callers hashed — plus the raw MCP tools/call counters for context. A
    scanner that calls every tool with {} is refused before the agent: it is in the raw counter,
    not in the calls, and is not counted.

Callers already present at the first look are the baseline (our own checks); our own credit
accounts on the apex hub are listed in OWN_ACCOUNTS (sign-up there is open since 2026-10-06). A payer outside OWN_WALLETS is external. One whose own latest transfers went to many
different payees is labelled crawler-like: a bot sweeping a directory, paying every new
endpoint once, is a visitor, not a customer — and before the test the only outside payer
the treasury ever had (0xc9c7…1670, $0.001 on 2026-10-03) was exactly that.

Sends a message on each new external payment or MCP caller, and one summary a day.
Telegram/e-mail come from the alerter's own settings (ecosystem_alert.channels_from_env);
state in AICOM_DEMAND_STATE. --dry-run prints instead of sending and saves nothing.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ecosystem_alert import _get, _post, channels_from_env

TREASURY = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BLOCKSCOUT = "https://base.blockscout.com/api/v2"
MCP_DEMAND = "https://verify.modelmarket.dev/demand.json"
TEST_CAPABILITIES = ("x402.authorization.check@v1", "mcp.tools.diff@v1")
START = "2026-10-05T14:00:00Z"
END = "2026-10-26T23:59:59Z"
TEST_PRICE_UNITS = 3000          # $0.003 in USDC's 6 decimals: x402-check and mcp-diff
CRAWLER_PAYEES = 8               # distinct payees in a payer's latest transfers
CRAWLER_ASKS = 6                 # Blockscout lookups per run, 10 s each at most
# Free public Base gateways that answer eth_getLogs over CHUNK blocks of history without a key
# (measured 2026-10-09 from the alerter's host; mainnet.base.org mostly answers 429, publicnode
# only the last ~20k blocks). AICOM_DEMAND_RPCS (comma-separated) goes first, for a keyed one.
CHAIN_RPCS = ("https://base.gateway.tenderly.co", "https://base-rpc.publicnode.com",
              "https://mainnet.base.org")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CHUNK = 500                      # blocks per eth_getLogs: the gateways' common ceiling
CONFIRMATIONS = 3                # read this far behind the head
BLOCK_SECONDS = 2                # Base
SCAN_BUDGET = 100.0              # seconds of scanning per run; the unit allows 300
PACE = 0.25                      # seconds between reads: Tenderly's gateway rate-limits a burst
LAG_ALERT = 6 * 3600             # the chain read this far behind: one message, and one when back


def _registry() -> dict[str, Any]:
    """config/deployments/base-mainnet.json — beside the script where it is deployed alone."""
    here = Path(__file__).resolve()
    for path in (here.parents[1] / "config" / "deployments" / "base-mainnet.json",
                 here.parent / "base-mainnet.json"):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise SystemExit("demand_watch: base-mainnet.json not found; without it the escrow's own "
                     "settlements would count as a stranger's demand")


def _escrows(registry: dict[str, Any]) -> set[str]:
    """Every AIMarketEscrow the registry has named, live and superseded: a literal here kept
    naming the one the 2026-09-04 redeploy replaced, and missed V1 and V2 after it."""
    found = {registry["contracts"]["AIMarketEscrow"]}
    for record in registry.values():
        old = record.get("superseded") if isinstance(record, dict) else None
        if isinstance(old, dict) and old.get("AIMarketEscrow"):
            found.add(old["AIMarketEscrow"])
    return found


ESCROWS = _escrows(_registry())

OWN_WALLETS = {a.lower() for a in (
    TREASURY,
    *ESCROWS,                                          # AIMarketEscrow, every deployment
    "0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1",   # HORKOS hot signer (escrow settle proceeds)
    "0x663E0C31925EAd877fD9414C2e1862fa50b2650b",   # apex hub gas sponsor
    "0x564bE09d06117A106ECC006a19b67768cBd91666",   # WARDEN's ERC-8004 feedback wallet
    "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",   # buyer / former hestia payout
    "0x40409bE3bAf99f22aA86b2FBaAa99EF2188D5674",   # x402 settlement burner
    "0x9d24d267cf8d9a8b9ed104b4856cde8830c266ef",   # Independent's subcontract executor
    "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec",   # Attested's payment wallet
    "0x097e3F339D0b023605e12A6B81E2d6Cb7571475a",   # Pay-on-Verified demo buyer (our own /start top-up test)
)}


# Our own credit accounts on the apex hub: their calls are not demand. Sign-up there was closed
# until 2026-10-06 (hub 3.15.17 opened it), so every account minted since is a stranger's unless
# listed here.
OWN_ACCOUNTS = ("acct_06d8129188a4cda7", "acct_2d8afaad6ea5ef0c", "acct_b0f15ab854247c1f",
                "acct_656dc27abb1d3160", "acct_69fc140e62323d25", "acct_ca72364a8c93f22e",
                "acct_6fa6efffd3ebc27b", "acct_70f04e72ec07b3e5", "acct_a6ed5e16e3d2627f",
                "acct_b7b8a6a0babe6077",  # the /start top-up test, 2026-10-06
                "acct_2c8f7330a9b3e2e6")  # lesson 04 signup-credit test, 2026-10-07


def who(consumer: str) -> str:
    """The exporter's caller hash (scripts/mcp_demand_export.py)."""
    import hashlib

    return hashlib.sha256(consumer.encode()).hexdigest()[:10]


def own_callers() -> set[str]:
    extra = os.environ.get("AICOM_DEMAND_OWN_CALLERS", "")
    return {who(f"account:{a}") for a in OWN_ACCOUNTS} | {c.strip() for c in extra.split(",") if c.strip()}


def own_wallets() -> set[str]:
    extra = os.environ.get("AICOM_DEMAND_OWN_WALLETS", "")
    return OWN_WALLETS | {a.strip().lower() for a in extra.split(",") if a.strip()}


def _iso(ts: str) -> float:
    return float(calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")))


def rpc_urls() -> list[str]:
    extra = [u.strip() for u in os.environ.get("AICOM_DEMAND_RPCS", "").split(",") if u.strip()]
    return extra + [u for u in CHAIN_RPCS if u not in extra]


def _rpc(urls: list[str], method: str, params: list[Any], post=_post,
         timeout: float = 20.0) -> tuple[Any, str]:
    """The first gateway's result, or (None, why each one failed). Errors name the host only:
    a keyed gateway carries its key in the URL."""
    errors = []
    for url in urls:
        status, body, err = post(url, {"jsonrpc": "2.0", "id": 1, "method": method,
                                       "params": params}, timeout)
        if status == 200 and isinstance(body, dict) and body.get("result") is not None:
            return body["result"], ""
        detail = body.get("error") if isinstance(body, dict) else None
        why = detail.get("message") if isinstance(detail, dict) else (err or status)
        errors.append(f"{urllib.parse.urlsplit(url).hostname}: {str(why)[:80]}")
    return None, "; ".join(errors)


def _stamp(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def chain_inflows(chain: dict[str, Any], *, now: float, post=_post, urls: list[str] | None = None,
                  budget: float = SCAN_BUDGET, clock=time.monotonic,
                  sleep=time.sleep) -> tuple[list[dict[str, Any]], str]:
    """USDC transfers into the treasury in the blocks this run reads, oldest first, and "" or
    what stopped the read.

    `chain` is the state's cursor: the last block read ("cursor") and the time the chain is
    read up to ("read_at"). A run that fails or runs out of budget leaves the rest to the
    next one, so a dead gateway delays a payment and never loses it. The first run starts
    at START's block (estimated from the 2 s blocks, with a margin the timestamps trim).
    The free gateways rate-limit: reads are paced, and a refused chunk is waited out (1, 2, 4,
    8 s) while the budget lasts."""
    urls = urls or rpc_urls()
    head_hex, err = _rpc(urls, "eth_blockNumber", [], post)
    if not isinstance(head_hex, str):
        return [], f"eth_blockNumber: {err or head_hex}"
    head = int(head_hex, 16) - CONFIRMATIONS
    if "cursor" not in chain:
        chain["cursor"] = head - int((now - _iso(START)) // BLOCK_SECONDS) - 600
    to_topic = "0x" + "0" * 24 + TREASURY[2:].lower()
    out: list[dict[str, Any]] = []
    began, wait = clock(), 1.0
    while chain["cursor"] < head and clock() - began <= budget:
        lo = chain["cursor"] + 1
        hi = min(lo + CHUNK - 1, head)
        logs, err = _rpc(urls, "eth_getLogs", [{"address": USDC_BASE, "fromBlock": hex(lo),
                                                 "toBlock": hex(hi),
                                                 "topics": [TRANSFER_TOPIC, None, to_topic]}], post)
        if not isinstance(logs, list):
            if wait > 8 or clock() - began + wait > budget:
                return out, f"eth_getLogs {lo}-{hi}: {err or logs}"
            sleep(wait)
            wait *= 2
            continue
        wait = 1.0
        for log in logs:
            block = int(log["blockNumber"], 16)
            stamp = log.get("blockTimestamp")
            if not stamp:
                got, _ = _rpc(urls, "eth_getBlockByNumber", [hex(block), False], post)
                stamp = got.get("timestamp") if isinstance(got, dict) else None
            at = int(stamp, 16) if stamp else now - (head - block) * BLOCK_SECONDS
            if at < _iso(START):
                continue
            out.append({"tx": str(log["transactionHash"]).lower(), "log_index": int(log["logIndex"], 16),
                        "from": "0x" + str(log["topics"][1])[-40:], "units": int(log.get("data") or "0x0", 16),
                        "at": _stamp(at)})
        chain["cursor"] = hi
        chain["read_at"] = now - (head - hi + CONFIRMATIONS) * BLOCK_SECONDS
        sleep(PACE)
    return out, ""


def chain_health(chain: dict[str, Any], *, now: float, error: str) -> list[str]:
    """One message when the chain read is LAG_ALERT behind and failed two runs running (a
    backlog being read is not an alarm, nor is one refused run), one when it has caught up."""
    chain["last_error"] = error
    chain["failing_runs"] = chain.get("failing_runs", 0) + 1 if error else 0
    lag = now - float(chain.get("read_at") or _iso(START))
    if lag > LAG_ALERT and chain["failing_runs"] >= 2 and not chain.get("alerted"):
        chain["alerted"] = True
        return [f"\u26A0\uFE0F Тест спроса: оплаты в блокчейне не читаются уже {lag / 3600:.0f} ч — "
                f"внешние платежи сейчас не видны. Ошибка: {error or 'нет, не хватило времени'}"]
    if lag <= LAG_ALERT and chain.get("alerted"):
        chain["alerted"] = False
        return [f"\u2705 Тест спроса: оплаты в блокчейне снова читаются, прочитано до "
                f"{_stamp(float(chain['read_at']))}"]
    return []


def crawler_like(address: str, get=_get, timeout: float = 10.0) -> tuple[bool | None, int]:
    """(crawler-like, distinct payees) from the payer's own latest USDC transfers out; None
    when Blockscout does not answer (Cloudflare often refuses it) — unknown, not "no"."""
    url = (f"{BLOCKSCOUT}/addresses/{address}/token-transfers?"
           + urllib.parse.urlencode({"type": "ERC-20", "filter": "from", "token": USDC_BASE}))
    status, body, _ = get(url, timeout)
    if status != 200 or not isinstance(body, dict):
        return None, 0
    payees = {str((i.get("to") or {}).get("hash") or "").lower() for i in body.get("items") or []}
    payees.discard("")
    return len(payees) >= CRAWLER_PAYEES, len(payees)


def hub_calls(doc: Any) -> list[dict[str, str]] | None:
    """The agents' calls through the hub, from mcp-demand.json, or None if absent."""
    rows = doc.get("invocations") if isinstance(doc, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else None


def mcp_calls(doc: Any, tool: str = "x402_check") -> dict[str, float]:
    """tools/call counts of `tool` per MCP client, from mcp-demand.json."""
    per_tool = (doc or {}).get("tools_call", {}) if isinstance(doc, dict) else {}
    calls = per_tool.get(tool, {}) if isinstance(per_tool, dict) else {}
    return {str(c): float(n) for c, n in calls.items() if isinstance(n, (int, float))}


def own_client(name: str) -> bool:
    return name.lower().startswith("aicom")


def step(state: dict[str, Any], *, now: float, transfers: list[dict[str, Any]],
         mcp: dict[str, float] | None, crawler=crawler_like,
         calls: list[dict[str, str]] | None = None) -> list[str]:
    """Fold one observation into `state`; return the messages it deserves."""
    messages: list[str] = []
    seen = set(state.setdefault("seen", []))
    own = own_wallets()
    asks = {"left": CRAWLER_ASKS}
    answers: dict[str, tuple[bool | None, int]] = {}
    ask_crawler = crawler

    def crawler(address: str) -> tuple[bool | None, int]:
        # Once per payer, and bounded, so a backlog cannot outlast the unit's timeout (the
        # state would not be saved and the next run would read the same blocks again); the
        # rest are asked on later runs.
        key = address.lower()
        if key not in answers:
            if asks["left"] <= 0:
                return None, 0
            asks["left"] -= 1
            answers[key] = ask_crawler(address)
        return answers[key]

    # A payer Blockscout would not describe last time is asked again, a few per run.
    for record in [r for r in state.get("external", []) if r.get("crawler_like") is None][:3]:
        record["crawler_like"], record["payees"] = crawler(record["from"])
    paid: list[str] = []
    for t in sorted(transfers, key=lambda t: t["at"]):
        key = f"{t['tx']}:{t['log_index']}"
        if key in seen:
            continue
        seen.add(key)
        if t["from"].lower() in own:
            state["own_payments"] = state.get("own_payments", 0) + 1
            continue
        is_bot, payees = crawler(t["from"])
        record = {**t, "usd": t["units"] / 1e6, "test_price": t["units"] == TEST_PRICE_UNITS,
                  "crawler_like": is_bot, "payees": payees}
        state.setdefault("external", []).append(record)
        what = ("x402-check или mcp-diff" if record["test_price"] else f"${record['usd']:g}")
        who = (f"похоже на бота-обходчика ({payees} разных получателей)" if is_bot
               else "не похоже на бота" if is_bot is False
               else "на бота проверить не удалось, проверю позже")
        paid.append(f"{what} от {t['from']} ({who}), {t['at']}\nhttps://basescan.org/tx/{t['tx']}")
    if len(paid) > 3:
        # A backlog (a source that was down, then caught up) is one message, not a burst.
        messages.append(f"\U0001F7E2 Тест спроса: внешних платежей сразу {len(paid)}:\n" + "\n".join(paid))
    else:
        messages += [f"\U0001F7E2 Тест спроса: внешний платёж {line}" for line in paid]
    state["seen"] = sorted(seen)[-2000:]
    if calls is not None:
        known = set(state.setdefault("seen_calls", []))
        if "baseline_callers" not in state:
            # Whoever called before this first look is us (the test's own checks).
            state["baseline_callers"] = sorted({c.get("who", "") for c in calls})
            known |= {f"{c.get('at')}|{c.get('capability')}|{c.get('who')}" for c in calls}
        ours = own_callers() | set(state["baseline_callers"])
        for c in calls:
            key = f"{c.get('at')}|{c.get('capability')}|{c.get('who')}"
            if key in known:
                continue
            known.add(key)
            if c.get("who") in ours:
                state["own_calls"] = state.get("own_calls", 0) + 1
                continue
            state.setdefault("external_calls", []).append(dict(c))
            if c.get("capability") not in TEST_CAPABILITIES:
                continue      # the other direct tools: in the summary, not a message each
            via = "MCP (пробная попытка)" if c.get("caller") == "sandbox" else c.get("caller", "?")
            messages.append(f"\U0001F7E2 Тест спроса: внешний вызов {c.get('capability')} через хаб — "
                            f"{via}, исход {c.get('outcome')}, вызывающий {c.get('who')}, {c.get('at')}")
        state["seen_calls"] = sorted(known)[-2000:]
    if mcp is not None and "mcp_last" not in state:
        # The first look is the baseline: the hub's counters already hold whatever happened
        # since its last restart, our own checks included (its client families put an
        # "aicom-probe" under "other"), and none of that is the test's.
        state["mcp_last"] = dict(mcp)
    elif mcp is not None:
        last = state.setdefault("mcp_last", {})
        for client, value in mcp.items():
            before = float(last.get(client, 0.0))
            delta = value - before if value >= before else value   # a hub restart resets counters
            last[client] = value
            if delta <= 0 or own_client(client):
                continue
            totals = state.setdefault("mcp_external", {})
            # Context only: these counters include scanners' empty probes, refused before the
            # agent; the calls above are the count.
            totals[client] = totals.get(client, 0.0) + delta
    return messages


def _funnel_lines(funnel: dict[str, Any] | None) -> list[str]:
    """The x402 and MCP funnel from demand.json: outsiders only, since the test began."""
    if not isinstance(funnel, dict):
        return ["Воронка: источник недоступен"]
    lines = []
    routes = (funnel.get("x402") or {}).get("routes") or {}
    if routes:
        q = sum(r.get("quoted", 0) for r in routes.values())
        paid = sum(r.get("paid", 0) for r in routes.values())
        callers = sum(r.get("callers", 0) for r in routes.values())
        lines.append(f"x402, посторонние: запросили цену {q}, оплатили {paid} (вызывающих по маршрутам: {callers})")
        busy = sorted(routes.items(), key=lambda kv: -(kv[1].get("quoted", 0) + kv[1].get("paid", 0)))
        lines.append("  " + ", ".join(f"{r} {v.get('quoted', 0)}/{v.get('paid', 0)}" for r, v in busy[:8])
                     + " (цена/оплата)")
    else:
        lines.append("x402, посторонние: ни одного запроса к платным маршрутам")
    disc = (funnel.get("x402") or {}).get("discovery") or {}
    if disc:
        lines.append("Каталоги читали описание x402: " + ", ".join(f"{k} {v}" for k, v in sorted(disc.items(), key=lambda kv: -kv[1])))
    mcp = funnel.get("mcp") or {}
    init = sum((mcp.get("initialize") or {}).values())
    listed = sum((mcp.get("tools/list") or {}).values())
    called = {k.split(":", 1)[1]: sum(v.values()) for k, v in mcp.items() if k.startswith("tools/call:")}
    fams = sorted((mcp.get("initialize") or {}).items(), key=lambda kv: -kv[1])
    lines.append(f"MCP: подключений {init}" + (f" ({', '.join(f'{k} {v}' for k, v in fams[:5])})" if fams else "")
                 + f", списков инструментов {listed}, вызовов {sum(called.values())}"
                 + (f" ({', '.join(f'{k} {v}' for k, v in sorted(called.items(), key=lambda kv: -kv[1])[:6])})" if called else ""))
    return lines


def summary(state: dict[str, Any], *, now: float, funnel: dict[str, Any] | None = None) -> str:
    start, end = _iso(START), _iso(END)
    day = max(1, int((now - start) // 86400) + 1)
    total_days = int((end - start) // 86400) + 1
    ext = state.get("external", [])
    test_paid = [e for e in ext if e.get("test_price")]
    humans = [e for e in test_paid if e.get("crawler_like") is False]
    unknown = [e for e in test_paid if e.get("crawler_like") is None]
    mcp = state.get("mcp_external", {})
    calls = state.get("external_calls", [])
    test_calls = [c for c in calls if c.get("capability") in TEST_CAPABILITIES]
    callers = {c.get("who") for c in test_calls}
    ok_calls = [c for c in test_calls if c.get("outcome") == "ok"]
    other_calls = [c for c in calls if c.get("capability") not in TEST_CAPABILITIES]
    head = ("Итог теста спроса" if now >= end else f"Тест спроса, день {min(day, total_days)} из {total_days}")
    lines = [f"\U0001F4CA {head} (x402-check, mcp-diff, MCP x402_check)",
             f"Внешних оплат по $0.003: {len(test_paid)} (не похожих на бота: {len(humans)}"
             + (f", не проверено: {len(unknown)}" if unknown else "")
             + f"), ${sum(e['usd'] for e in test_paid):g}",
             f"Прочих внешних поступлений: {len(ext) - len(test_paid)}",
             f"Вызовов агентов теста через хаб от посторонних: {len(test_calls)} (успешных {len(ok_calls)}, "
             f"вызывающих {len(callers)}); других прямых инструментов: {len(other_calls)}"]
    lines += _funnel_lines(funnel)
    lines.append(f"Справочно, MCP tools/call x402_check с пустыми пробами сканеров: {int(sum(mcp.values()))}"
                 + (f" ({', '.join(sorted(mcp))})" if mcp else ""))
    lines.append(f"Наших платежей за то же время: {state.get('own_payments', 0)}")
    chain = state.get("chain") or {}
    if chain.get("read_at"):
        lag = now - float(chain["read_at"])
        lines.append(f"Оплаты в блокчейне прочитаны до {_stamp(float(chain['read_at']))}"
                     + (f" — \u26A0\uFE0F отстаёт на {lag / 3600:.0f} ч: {chain.get('last_error') or 'не хватило времени'}"
                        if lag > 2 * 3600 else ""))
    else:
        lines.append("\u26A0\uFE0F Оплаты в блокчейне ещё не прочитаны"
                     + (f": {chain['last_error']}" if chain.get("last_error") else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--state", default=os.environ.get("AICOM_DEMAND_STATE",
                                                          "/var/lib/aicom-alert/demand.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-hour", type=int, default=6, help="UTC hour of the daily summary")
    args = parser.parse_args(argv)
    now = time.time()
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {}
    chain = state.setdefault("chain", {})
    transfers, chain_err = chain_inflows(chain, now=now)
    if chain_err:
        print(f"inflows: {chain_err}", file=sys.stderr)
    alerts = chain_health(chain, now=now, error=chain_err)
    status, doc, err = _get(os.environ.get("AICOM_DEMAND_MCP_URL", MCP_DEMAND), 25.0)
    mcp = mcp_calls(doc) if status == 200 and isinstance(doc, dict) else None
    calls = hub_calls(doc) if status == 200 else None
    if mcp is None:
        print(f"mcp-demand: {err or status}", file=sys.stderr)
    messages = alerts + step(state, now=now, transfers=transfers, mcp=mcp, calls=calls)
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    if state.get("summary_date") != today and time.gmtime(now).tm_hour >= args.summary_hour \
            and now >= _iso(START) and (now <= _iso(END) + 86400):
        messages.append(summary(state, now=now, funnel=doc if status == 200 and isinstance(doc, dict) else None))
        state["summary_date"] = today
    if args.dry_run:
        print("\n---\n".join(messages) if messages else "(nothing to send)")
        return 0
    channels = channels_from_env(
        (os.environ.get("AICOM_ALERT_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip(),
        (os.environ.get("AICOM_ALERT_TELEGRAM_CHAT") or os.environ.get("TELEGRAM_CHAT_ID") or "").strip())
    for text in messages:
        for name, send in channels:
            ok, info = send(text)
            print(f"{name}: {'ok' if ok else 'FAILED ' + str(info)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
