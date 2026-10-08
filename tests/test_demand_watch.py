"""The demand test's counter (scripts/demand_watch.py): only outsiders count, bots are named."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import demand_watch as dw

STRANGER = "0x" + "ab" * 20
BOT = "0xc9c7b38C0942914fC8EA12063BC92dcd3b581670"
OURS = "0x40409bE3bAf99f22aA86b2FBaAa99EF2188D5674"


def transfer(sender, units=3000, at="2026-10-06T10:00:00Z", tx="0x01", log_index=1):
    return {"tx": tx, "log_index": log_index, "from": sender, "units": units, "at": at}


def no_bots(address):
    return False, 1


def test_blockscout_pages_stop_at_the_start():
    pages = {
        None: {"items": [
            {"timestamp": "2026-10-07T10:00:00.000000Z", "transaction_hash": "0xa", "log_index": 3,
             "from": {"hash": STRANGER}, "total": {"value": "3000"}},
            {"timestamp": "2026-10-06T10:00:00.000000Z", "transaction_hash": "0xb", "log_index": 4,
             "from": {"hash": OURS}, "total": {"value": "1000"}}],
            "next_page_params": {"block_number": 5, "index": 1}},
        "5": {"items": [
            {"timestamp": "2026-10-04T10:00:00.000000Z", "transaction_hash": "0xc", "log_index": 1,
             "from": {"hash": BOT}, "total": {"value": "1000"}}],
            "next_page_params": {"block_number": 2, "index": 1}},
    }
    asked = []

    def get(url, timeout):
        asked.append(url)
        page = "5" if "block_number=5" in url else None
        return 200, pages[page], ""

    got = dw.inflows(dw._iso("2026-10-05T14:00:00Z"), get=get)
    assert [t["tx"] for t in got] == ["0xa", "0xb"]          # 10-04 is before the test
    assert got[0] == {"tx": "0xa", "log_index": 3, "from": STRANGER, "units": 3000,
                      "at": "2026-10-07T10:00:00Z"}
    assert len(asked) == 2 and "filter=to" in asked[0] and dw.USDC_BASE in asked[0]


def test_a_crawler_is_one_that_pays_many_sellers():
    def get(url, timeout):
        items = [{"to": {"hash": "0x" + f"{i:040x}"}} for i in range(12)]
        return 200, {"items": items}, ""

    assert dw.crawler_like(BOT, get=get) == (True, 12)
    assert dw.crawler_like(STRANGER, get=lambda u, t: (200, {"items": [{"to": {"hash": "0x1"}}]}, "")) == (False, 1)


def test_only_outsiders_count_and_each_payment_once():
    state: dict = {}
    msgs = dw.step(state, now=0, transfers=[transfer(OURS, tx="0x0"), transfer(STRANGER)],
                   mcp=None, crawler=no_bots)
    assert len(msgs) == 1 and STRANGER in msgs[0] and "x402-check или mcp-diff" in msgs[0]
    assert state["own_payments"] == 1 and len(state["external"]) == 1
    assert dw.step(state, now=0, transfers=[transfer(STRANGER)], mcp=None, crawler=no_bots) == []


def test_a_bot_is_reported_as_one():
    state: dict = {}
    msgs = dw.step(state, now=0, transfers=[transfer(BOT, units=1000)], mcp=None,
                   crawler=lambda a: (True, 40))
    assert "похоже на бота" in msgs[0] and "$0.001" in msgs[0]
    assert state["external"][0]["crawler_like"] is True


def test_mcp_counts_outside_clients_and_survives_a_hub_restart():
    doc = {"tools_call": {"x402_check": {"claude-ai": 3, "aicom-probe": 5},
                          "weather_now": {"cursor": 2}}}
    calls = dw.mcp_calls(doc)
    assert calls == {"claude-ai": 3.0, "aicom-probe": 5.0}
    assert dw.mcp_calls({}) == {} and dw.mcp_calls(None) == {}
    state: dict = {}
    assert dw.step(state, now=0, transfers=[], mcp=calls, crawler=no_bots) == []   # baseline
    later = dw.step(state, now=0, transfers=[], mcp={"claude-ai": 5.0, "aicom-probe": 5.0},
                    crawler=no_bots)
    assert later == [], "raw counters include scanners' empty probes: context, not news"
    assert state["mcp_external"] == {"claude-ai": 2.0}
    dw.step(state, now=0, transfers=[], mcp={"claude-ai": 1.0}, crawler=no_bots)   # restarted
    assert state["mcp_external"] == {"claude-ai": 3.0}


def call(who, at="2026-10-06T10:00:00Z", capability="x402.authorization.check@v1",
         outcome="ok", caller="sandbox"):
    return {"at": at, "capability": capability, "outcome": outcome, "caller": caller, "who": who}


def test_calls_that_reached_the_agent_are_the_count():
    mine = call("aaaaaaaaaa", at="2026-10-05T14:29:14Z")
    state: dict = {}
    assert dw.step(state, now=0, transfers=[], mcp=None, crawler=no_bots, calls=[mine]) == []
    stranger = call("bbbbbbbbbb", outcome="fail")
    ours = call(dw.who("account:acct_70f04e72ec07b3e5"), caller="account", at="2026-10-06T11:00:00Z")
    again = call("aaaaaaaaaa", at="2026-10-07T09:00:00Z")      # our own visitor, later
    msgs = dw.step(state, now=0, transfers=[], mcp=None, crawler=no_bots,
                   calls=[mine, stranger, ours, again])
    assert len(msgs) == 1 and "bbbbbbbbbb" in msgs[0] and "MCP" in msgs[0] and "fail" in msgs[0]
    assert state["own_calls"] == 2 and len(state["external_calls"]) == 1
    assert dw.step(state, now=0, transfers=[], mcp=None, crawler=no_bots,
                   calls=[mine, stranger, ours, again]) == []


def test_the_summary_says_what_was_seen():
    state = {"external": [{"usd": 0.003, "test_price": True, "crawler_like": True},
                          {"usd": 0.003, "test_price": True, "crawler_like": False},
                          {"usd": 0.001, "test_price": False, "crawler_like": False}],
             "mcp_external": {"claude-ai": 2.0}, "own_payments": 4,
             "external_calls": [call("bbbbbbbbbb"), call("bbbbbbbbbb", outcome="fail"), call("cccccccccc")]}
    funnel = {"x402": {"routes": {"x402-check": {"quoted": 5, "paid": 1, "callers": 3},
                                  "weather-now": {"quoted": 2, "paid": 0, "callers": 1}},
                       "discovery": {"x402scan": 4}},
              "mcp": {"initialize": {"claude": 6, "other": 2}, "tools/list": {"claude": 5},
                      "tools/call:x402_check": {"other": 1}}}
    text = dw.summary(state, now=dw._iso("2026-10-08T07:00:00Z"), funnel=funnel)
    assert "день 3 из 22" in text
    assert "Внешних оплат по $0.003: 2 (не похожих на бота: 1), $0.006" in text
    assert "Прочих внешних поступлений: 1" in text
    assert "Вызовов агентов теста через хаб от посторонних: 3 (успешных 2, вызывающих 2)" in text
    assert "x402, посторонние: запросили цену 7, оплатили 1 (вызывающих по маршрутам: 4)" in text
    assert "x402-check 5/1" in text and "Каталоги читали описание x402: x402scan 4" in text
    assert "MCP: подключений 8 (claude 6, other 2), списков инструментов 5, вызовов 1 (x402_check 1)" in text
    assert "Справочно, MCP tools/call x402_check с пустыми пробами сканеров: 2 (claude-ai)" in text
    assert "Воронка: источник недоступен" in dw.summary(state, now=dw._iso("2026-10-08T07:00:00Z"))
    assert dw.summary(state, now=dw._iso("2026-10-27T07:00:00Z")).startswith("\U0001F4CA Итог теста спроса")


def test_other_direct_tools_are_counted_but_not_announced():
    state: dict = {}
    dw.step(state, now=0, transfers=[], mcp=None, crawler=no_bots, calls=[])
    weather = call("dddddddddd", capability="gaia.weather.read@v1")
    assert dw.step(state, now=0, transfers=[], mcp=None, crawler=no_bots, calls=[weather]) == []
    assert state["external_calls"] == [weather]
    assert "других прямых инструментов: 1" in dw.summary(state, now=dw._iso("2026-10-06T07:00:00Z"))


def test_the_live_escrow_is_our_own_wallet():
    """The literal named the escrow the 2026-09-04 redeploy replaced."""
    import json
    from pathlib import Path

    reg = json.loads((Path(__file__).resolve().parents[1] / "config" / "deployments"
                      / "base-mainnet.json").read_text(encoding="utf-8"))
    assert reg["contracts"]["AIMarketEscrow"].lower() in dw.OWN_WALLETS
