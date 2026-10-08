#!/usr/bin/env python3
"""The demand test (2026-10-05 .. 2026-10-26): does anyone outside the ecosystem use
x402.authorization.check or mcp.tools.diff?

The two HESTIA agents were put where their audience already looks — the x402 Bazaar,
x402scan and Agentic.Market (POST https://modelmarket.dev/x402/x402-check and /mcp-diff,
$0.003, paid to the treasury) and the hub's MCP endpoint (direct tool x402_check). This
counts what happens, from two public sources, so it needs no access to any server:

  - Blockscout: USDC transfers into the treasury since the start. The payer of an x402
    `exact` payment is the `from` of its transfer. $0.003 is what both agents cost.
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
from ecosystem_alert import _get, channels_from_env

TREASURY = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BLOCKSCOUT = "https://base.blockscout.com/api/v2"
MCP_DEMAND = "https://verify.modelmarket.dev/demand.json"
TEST_CAPABILITIES = ("x402.authorization.check@v1", "mcp.tools.diff@v1")
START = "2026-10-05T14:00:00Z"
END = "2026-10-26T23:59:59Z"
TEST_PRICE_UNITS = 3000          # $0.003 in USDC's 6 decimals: x402-check and mcp-diff
CRAWLER_PAYEES = 8               # distinct payees in a payer's latest transfers
# The escrow that settles channels, read from the deployment registry: a literal here kept
# naming the escrow the 2026-09-04 redeploy replaced, so the live one's transfers would have
# counted as a stranger's demand.
_REGISTRY = Path(__file__).resolve().parents[1] / "config" / "deployments" / "base-mainnet.json"
LIVE_ESCROW = json.loads(_REGISTRY.read_text(encoding="utf-8"))["contracts"]["AIMarketEscrow"]

OWN_WALLETS = {a.lower() for a in (
    TREASURY,
    LIVE_ESCROW,                                       # AIMarketEscrow (settles channels)
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


def inflows(since: float, get=_get, timeout: float = 25.0, pages: int = 20) -> list[dict[str, Any]]:
    """USDC transfers into the treasury at or after `since`, newest first."""
    out: list[dict[str, Any]] = []
    params: dict[str, Any] = {"type": "ERC-20", "filter": "to", "token": USDC_BASE}
    for _ in range(pages):
        url = f"{BLOCKSCOUT}/addresses/{TREASURY}/token-transfers?" + urllib.parse.urlencode(params)
        status, body, err = get(url, timeout)
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"blockscout: {err or status}")
        items = body.get("items") or []
        for item in items:
            stamp = str(item.get("timestamp") or "")
            if not stamp or _iso(stamp) < since:
                return out
            out.append({
                "tx": str(item.get("transaction_hash") or ""),
                "log_index": item.get("log_index"),
                "from": str((item.get("from") or {}).get("hash") or ""),
                "units": int((item.get("total") or {}).get("value") or 0),
                "at": stamp[:19] + "Z",
            })
        params = body.get("next_page_params")
        if not params or not items:
            return out
    return out


def crawler_like(address: str, get=_get, timeout: float = 25.0) -> tuple[bool, int]:
    """(crawler-like, distinct payees) from the payer's own latest USDC transfers out."""
    url = (f"{BLOCKSCOUT}/addresses/{address}/token-transfers?"
           + urllib.parse.urlencode({"type": "ERC-20", "filter": "from", "token": USDC_BASE}))
    status, body, _ = get(url, timeout)
    if status != 200 or not isinstance(body, dict):
        return False, 0
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
               else "не похоже на бота")
        messages.append(f"\U0001F7E2 Тест спроса: внешний платёж {what} от {t['from']} "
                        f"({who}), {t['at']}\nhttps://basescan.org/tx/{t['tx']}")
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
    humans = [e for e in test_paid if not e.get("crawler_like")]
    mcp = state.get("mcp_external", {})
    calls = state.get("external_calls", [])
    test_calls = [c for c in calls if c.get("capability") in TEST_CAPABILITIES]
    callers = {c.get("who") for c in test_calls}
    ok_calls = [c for c in test_calls if c.get("outcome") == "ok"]
    other_calls = [c for c in calls if c.get("capability") not in TEST_CAPABILITIES]
    head = ("Итог теста спроса" if now >= end else f"Тест спроса, день {min(day, total_days)} из {total_days}")
    lines = [f"\U0001F4CA {head} (x402-check, mcp-diff, MCP x402_check)",
             f"Внешних оплат по $0.003: {len(test_paid)} (не похожих на бота: {len(humans)}), "
             f"${sum(e['usd'] for e in test_paid):g}",
             f"Прочих внешних поступлений: {len(ext) - len(test_paid)}",
             f"Вызовов агентов теста через хаб от посторонних: {len(test_calls)} (успешных {len(ok_calls)}, "
             f"вызывающих {len(callers)}); других прямых инструментов: {len(other_calls)}"]
    lines += _funnel_lines(funnel)
    lines.append(f"Справочно, MCP tools/call x402_check с пустыми пробами сканеров: {int(sum(mcp.values()))}"
                 + (f" ({', '.join(sorted(mcp))})" if mcp else ""))
    lines.append(f"Наших платежей за то же время: {state.get('own_payments', 0)}")
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
    try:
        transfers = inflows(_iso(START))
    except RuntimeError as exc:
        print(f"inflows: {exc}", file=sys.stderr)
        transfers = []
    status, doc, err = _get(os.environ.get("AICOM_DEMAND_MCP_URL", MCP_DEMAND), 25.0)
    mcp = mcp_calls(doc) if status == 200 and isinstance(doc, dict) else None
    calls = hub_calls(doc) if status == 200 else None
    if mcp is None:
        print(f"mcp-demand: {err or status}", file=sys.stderr)
    messages = step(state, now=now, transfers=transfers, mcp=mcp, calls=calls)
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
