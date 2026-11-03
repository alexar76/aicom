"""`aimarket rpc-check`: every chain node the payment paths ask, asked what they will be asked.

2026-10-21: the Independent hub's deposit watcher had one node, mainnet.base.org, which answered
eth_chainId and eth_blockNumber and refused every eth_getLogs with 429 — for 13 days, with nothing
but a log line a minute to show for it. A check of eth_chainId alone would have called it healthy.
"""
from __future__ import annotations

import json

import httpx
from aimarket_hub import cli, settle

WALLET = "0x" + "d7" * 20


def _node(url, method, params, timeout):
    if method == "eth_chainId":
        return hex(8453)
    if method == "eth_blockNumber":
        return hex(5000 if url != "http://stale.test" else 4000)
    if method == "eth_getLogs":
        if url == "http://limited.test":
            request = httpx.Request("POST", url)
            raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))
        f = params[0]
        assert int(f["toBlock"], 16) - int(f["fromBlock"], 16) + 1 == 500
        assert f["topics"][2] == "0x" + WALLET[2:].rjust(64, "0")
        return []
    raise AssertionError(method)


def _env(monkeypatch, urls):
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", "0x" + "a1" * 20)
    monkeypatch.setenv("AIMARKET_TOPUP_PAY_TO", WALLET)
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", urls)
    monkeypatch.setenv("AIMARKET_RPC_BASE", "http://good.test")
    monkeypatch.setattr(settle, "_rpc", _node)


def test_rpc_check_tells_the_node_that_refuses_the_scan_from_the_one_that_serves_it(monkeypatch, capsys):
    _env(monkeypatch, "http://limited.test,http://good.test,http://stale.test")
    assert cli.main(["rpc-check", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    watcher = {r["url"]: r for r in out["lists"][0]["rows"]}
    assert watcher["http://good.test"]["usable"] is True
    assert watcher["http://limited.test"]["usable"] is False and watcher["http://limited.test"]["logs"] == "refused"
    assert watcher["http://stale.test"]["usable"] is False and watcher["http://stale.test"]["lag"] == 1000
    assert [r["url"] for r in out["lists"][1]["rows"]] == ["http://good.test"]


def test_rpc_check_exits_1_when_no_node_can_serve_the_scan(monkeypatch, capsys):
    _env(monkeypatch, "http://limited.test")
    assert cli.main(["rpc-check"]) == 1
    assert "no node" in capsys.readouterr().out
