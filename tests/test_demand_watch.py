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


HEAD = 52_400_000
NOW = dw._iso("2026-10-09T08:00:00Z")


def nap(seconds):
    pass


def topic(address):
    return "0x" + "0" * 24 + address[2:].lower()


def chain(logs, *, down=(), head=HEAD):
    """A fake Base behind gateways: `logs` are (block, payer, units, log_index); a gateway whose
    host is in `down` answers 403, as Blockscout's Cloudflare did."""
    asked = []

    def post(url, payload, timeout):
        asked.append((url, payload["method"], payload["params"]))
        if any(d in url for d in down):
            return 403, None, "HTTP 403"
        if payload["method"] == "eth_blockNumber":
            return 200, {"result": hex(head)}, ""
        q = payload["params"][0]
        lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
        assert hi - lo + 1 <= dw.CHUNK and q["address"] == dw.USDC_BASE
        assert q["topics"] == [dw.TRANSFER_TOPIC, None, topic(dw.TREASURY)]
        found = [{"blockNumber": hex(b), "transactionHash": f"0x{b:064X}", "logIndex": hex(i),
                  "topics": [dw.TRANSFER_TOPIC, topic(who), topic(dw.TREASURY)], "data": hex(units),
                  "blockTimestamp": hex(int(NOW) - (head - b) * 2)}
                 for b, who, units, i in logs if lo <= b <= hi]
        return 200, {"result": found}, ""
    return post, asked


def test_the_chain_is_read_from_the_start_in_chunks_and_resumes_where_it_stopped():
    start_block = HEAD - int((NOW - dw._iso(dw.START)) // 2)
    logs = [(start_block - 400, STRANGER, 3000, 1),        # before the test: not counted
            (start_block + 10, STRANGER, 3000, 7), (HEAD - 1000, BOT, 1000, 2)]
    post, asked = chain(logs)
    state: dict = {}
    got, err = dw.chain_inflows(state, now=NOW, post=post, urls=["https://a.example"], sleep=nap)
    assert err == "" and [t["units"] for t in got] == [3000, 1000]
    assert got[0] == {"tx": f"0x{start_block + 10:064x}", "log_index": 7, "from": STRANGER,
                      "units": 3000, "at": dw._stamp(NOW - (HEAD - start_block - 10) * 2)}
    assert state["cursor"] == HEAD - dw.CONFIRMATIONS and NOW - state["read_at"] <= 2 * dw.CONFIRMATIONS
    reads = [p[0] for _, method, p in asked if method == "eth_getLogs"]
    assert int(reads[0]["fromBlock"], 16) < start_block - 400 and len(reads) > 1   # START's block, margin, chunks
    again, err = dw.chain_inflows(state, now=NOW, post=post, urls=["https://a.example"], sleep=nap)
    assert again == [] and err == ""                      # nothing read twice


def test_a_dead_gateway_falls_through_and_a_dead_chain_delays_but_loses_nothing():
    late = HEAD - 200
    post, asked = chain([(late, STRANGER, 3000, 1)], down=("a.example",))
    state = {"cursor": HEAD - 5000}
    got, err = dw.chain_inflows(state, now=NOW, post=post, urls=["https://a.example", "https://b.example"], sleep=nap)
    assert err == "" and len(got) == 1                    # the second gateway answered
    dead, _ = chain([(late, STRANGER, 3000, 1)], down=("a.example", "b.example"))
    state = {"cursor": HEAD - 5000, "read_at": NOW - 9000}
    got, err = dw.chain_inflows(state, now=NOW, post=dead, urls=["https://a.example", "https://b.example"], sleep=nap)
    assert got == [] and "a.example: HTTP 403" in err and "b.example: HTTP 403" in err
    assert state["cursor"] == HEAD - 5000                 # the gap is left for the next run
    got, err = dw.chain_inflows(state, now=NOW, post=post, urls=["https://a.example", "https://b.example"], sleep=nap)
    assert len(got) == 1 and err == ""


def test_a_keyed_gateway_never_shows_its_key():
    post, _ = chain([], down=("secret",))
    _, err = dw._rpc(["https://base.example/v2/secretKEY123"], "eth_blockNumber", [], post)
    assert "secretKEY123" not in err and "base.example" in err


def test_a_run_out_of_time_stops_without_an_error():
    post, _ = chain([])
    ticks = iter(range(0, 10_000, 60))
    state = {"cursor": HEAD - 50_000}
    _, err = dw.chain_inflows(state, now=NOW, post=post, urls=["https://a.example"], budget=100,
                              clock=lambda: next(ticks), sleep=nap)
    assert err == "" and HEAD - 50_000 < state["cursor"] < HEAD - dw.CONFIRMATIONS


def test_a_rate_limit_is_waited_out_within_the_budget():
    post, _ = chain([(HEAD - 100, STRANGER, 3000, 1)])
    hits = {"n": 0}

    def flaky(url, payload, timeout):
        if payload["method"] == "eth_getLogs" and hits["n"] < 2:
            hits["n"] += 1
            return 200, {"error": {"code": -32005, "message": "rate limit exceeded"}}, ""
        return post(url, payload, timeout)

    slept = []
    state = {"cursor": HEAD - 1000}
    got, err = dw.chain_inflows(state, now=NOW, post=flaky, urls=["https://a.example"], sleep=slept.append)
    assert err == "" and len(got) == 1 and slept.count(1.0) == 1 and 2.0 in slept


def test_catching_up_is_not_an_alarm_but_a_stuck_chain_is():
    state = {"read_at": NOW - 80 * 3600}
    assert dw.chain_health(state, now=NOW, error="") == []          # a backlog read within budget
    assert dw.chain_health(state, now=NOW, error="eth_getLogs 1-500: a.example: HTTP 403") == []
    state["read_at"] = NOW - 7 * 3600
    first = dw.chain_health(state, now=NOW, error="eth_getLogs 1-500: a.example: HTTP 403")
    assert len(first) == 1 and "7 ч" in first[0] and "HTTP 403" in first[0]
    assert dw.chain_health(state, now=NOW + 3600, error="same") == []
    state["read_at"] = NOW + 3500
    back = dw.chain_health(state, now=NOW + 3600, error="")
    assert len(back) == 1 and "снова читаются" in back[0]
    assert dw.chain_health(state, now=NOW + 3600, error="") == []
    lagging = dict(state, read_at=NOW - 4 * 3600, last_error="eth_blockNumber: x")
    text = dw.summary({"chain": lagging}, now=NOW)
    assert "отстаёт на 4 ч: eth_blockNumber: x" in text
    assert "ещё не прочитаны" in dw.summary({}, now=NOW)


def test_every_escrow_ever_deployed_is_ours():
    """The live one and each one a redeploy replaced (the registry names three by 2026-10-08)."""
    reg = dw._registry()
    old = [r["superseded"]["AIMarketEscrow"] for r in reg.values()
           if isinstance(r, dict) and "AIMarketEscrow" in (r.get("superseded") or {})]
    assert len(old) >= 2
    assert {a.lower() for a in [reg["contracts"]["AIMarketEscrow"], *old]} <= dw.OWN_WALLETS


def test_a_crawler_is_one_that_pays_many_sellers():
    def get(url, timeout):
        items = [{"to": {"hash": "0x" + f"{i:040x}"}} for i in range(12)]
        return 200, {"items": items}, ""

    assert dw.crawler_like(BOT, get=get) == (True, 12)
    assert dw.crawler_like(STRANGER, get=lambda u, t: (200, {"items": [{"to": {"hash": "0x1"}}]}, "")) == (False, 1)
    assert dw.crawler_like(BOT, get=lambda u, t: (403, None, "HTTP 403")) == (None, 0)


def test_an_unknown_payer_is_said_to_be_unknown_and_asked_again():
    state: dict = {}
    msgs = dw.step(state, now=0, transfers=[transfer(STRANGER)], mcp=None, crawler=lambda a: (None, 0))
    assert "проверить не удалось" in msgs[0] and state["external"][0]["crawler_like"] is None
    assert "не проверено: 1" in dw.summary(state, now=NOW)
    dw.step(state, now=0, transfers=[], mcp=None, crawler=lambda a: (True, 30))
    assert state["external"][0]["crawler_like"] is True and state["external"][0]["payees"] == 30


def test_a_backlog_of_payments_is_one_message():
    state: dict = {}
    many = [transfer(STRANGER, tx=f"0x{i}", log_index=i) for i in range(5)]
    msgs = dw.step(state, now=0, transfers=many, mcp=None, crawler=no_bots)
    assert len(msgs) == 1 and "сразу 5" in msgs[0] and msgs[0].count("basescan.org/tx/") == 5


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


def test_a_crowd_of_new_payers_is_looked_up_a_few_at_a_time():
    asked = []

    def crawler(address):
        asked.append(address)
        return False, 1

    payers = ["0x" + f"{i:040x}" for i in range(1, 10)]
    state: dict = {}
    dw.step(state, now=0, transfers=[transfer(a, tx=a, log_index=0) for a in payers], mcp=None,
            crawler=crawler)
    assert len(asked) == dw.CRAWLER_ASKS
    assert [r["crawler_like"] for r in state["external"]].count(None) == len(payers) - dw.CRAWLER_ASKS
    asked.clear()
    dw.step({}, now=0, transfers=[transfer(STRANGER, tx=f"0x{i}", log_index=i) for i in range(5)],
            mcp=None, crawler=crawler)
    assert asked == [STRANGER]                            # one payer, one lookup
