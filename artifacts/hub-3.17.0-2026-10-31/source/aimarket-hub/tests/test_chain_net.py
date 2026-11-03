"""Tests for the unified EVM+Solana network registry + health-checked RPC failover.

All offline: a fake transport records calls and is scripted to fail/succeed per URL; a fake
clock drives cooldown/return-to-default deterministically. No real network, no hanging.
"""
from __future__ import annotations

import os

import pytest

from aimarket_hub import chain_net as cn


# ── fakes ────────────────────────────────────────────────────────────────────
class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class FakeTransport:
    """Scripted transport. ``down`` URLs raise (transport error → failover); ``errors`` URLs
    return a JSON-RPC error object; everything else returns a canned result."""

    def __init__(self, down=(), result=None, errors=()):
        self.down = set(down)
        self.errors = set(errors)
        self.result = result if result is not None else {"jsonrpc": "2.0", "id": 1, "result": "0x2105"}
        self.calls: list[str] = []

    def __call__(self, url, body, timeout):
        self.calls.append(url)
        if url in self.down:
            raise ConnectionError(f"down: {url}")
        if url in self.errors:
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "boom"}}
        return self.result


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip any AIMARKET_/legacy chain env so each test is hermetic."""
    for k in list(os.environ):
        if k.startswith(("AIMARKET_", "BASE_RPC", "ETHEREUM_RPC", "ARBITRUM_RPC", "SOLANA_RPC", "AIFACTORY_PAYMENT_RPC")):
            monkeypatch.delenv(k, raising=False)


# ═══════════════════════════════════ registry / selection ═══════════════════
class TestNetworkSelection:
    def test_default_is_base_with_demo_contracts(self):
        net = cn.active_network()
        assert net.id == "base" and net.is_evm and net.chain_id == 8453
        assert net.rpc_urls[0] == "https://mainnet.base.org"  # preferred default wins
        assert "https://base.gateway.tenderly.co" in net.rpc_urls  # serves the deposit scan
        assert net.addresses["AIMarketEscrow"] == "0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb"
        assert net.addresses["USDC"].lower().startswith("0x833589")

    def test_env_selects_network(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_CHAIN", "solana")
        net = cn.active_network()
        assert net.id == "solana" and net.is_solana and net.cluster == "mainnet-beta"
        assert net.native_symbol == "SOL"

    def test_rpc_priority_explicit_then_legacy_then_presets(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_RPC_BASE", "https://my.node, https://my.backup")
        monkeypatch.setenv("BASE_RPC_URL", "https://legacy.node")  # explicit operator config
        net = cn.network("base")
        assert net.rpc_urls[0] == "https://my.node"        # new explicit list — preferred default
        assert net.rpc_urls[1] == "https://my.backup"
        assert net.rpc_urls[2] == "https://legacy.node"    # legacy config outranks public presets
        assert "https://mainnet.base.org" in net.rpc_urls[3:]  # presets are pure backups, last

    def test_rpc_urls_deduped(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_RPC_BASE", "https://mainnet.base.org")  # same as preset[0]
        net = cn.network("base")
        assert net.rpc_urls.count("https://mainnet.base.org") == 1

    def test_testnet_variant(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_TESTNET", "1")
        net = cn.network("base")
        assert net.testnet is True and net.chain_id == 84532
        assert net.rpc_urls[0] == "https://sepolia.base.org"

    def test_address_override_via_env(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ADDR_BASE_ESCROW", "0xabc")
        net = cn.network("base")
        assert net.addresses["ESCROW"] == "0xabc"

    def test_adhoc_evm_network_via_env(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_CHAIN", "optimism")
        monkeypatch.setenv("AIMARKET_CHAIN_KIND", "evm")
        monkeypatch.setenv("AIMARKET_CHAIN_ID", "10")
        monkeypatch.setenv("AIMARKET_RPC_OPTIMISM", "https://mainnet.optimism.io")
        net = cn.active_network()
        assert net.id == "optimism" and net.is_evm and net.chain_id == 10
        assert net.rpc_urls == ("https://mainnet.optimism.io",)


# ═══════════════════════════════════ failover / priority ════════════════════
class TestRpcPoolFailover:
    def _spec(self, urls):
        return cn.NetworkSpec(id="base", kind=cn.EVM, display_name="Base", chain_id=8453,
                              cluster=None, rpc_urls=tuple(urls), native_symbol="ETH", explorer_tx="")

    def test_prefers_first_healthy_default(self):
        t = FakeTransport()
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        assert pool.call("eth_chainId") == "0x2105"
        assert t.calls == ["https://a"]  # default has priority — b never touched

    def test_fails_over_to_next_on_transport_error(self):
        t = FakeTransport(down={"https://a"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        assert pool.call("eth_chainId") == "0x2105"
        assert t.calls == ["https://a", "https://a", "https://b"]  # retry a, then fail over

    def test_transient_failure_retries_same_endpoint_before_failover(self):
        class _Transient:
            def __init__(self): self.calls = []
            def __call__(self, url, body, timeout):
                self.calls.append(url)
                if len(self.calls) == 1:
                    raise ConnectionError("one-off transport failure")
                return {"result": "0x2105"}

        transport = _Transient()
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=transport)
        assert pool.call("eth_chainId") == "0x2105"
        assert transport.calls == ["https://a", "https://a"]
        assert pool._endpoints[0].healthy is True

    def test_all_down_fails_fast_not_hang(self):
        t = FakeTransport(down={"https://a", "https://b"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        with pytest.raises(cn.AllEndpointsDown):
            pool.call("eth_chainId")

    def test_returns_to_preferred_default_after_cooldown(self):
        clock = FakeClock()
        t = FakeTransport(down={"https://a"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t, cooldown=30.0, clock=clock)
        # 1st call: a down → b serves; a is demoted with a 30s cooldown.
        pool.call("eth_chainId")
        t.calls.clear()
        # within cooldown: a is skipped, straight to b.
        pool.call("eth_chainId")
        assert t.calls == ["https://b"]
        # a recovers and cooldown expires → a is re-probed and reclaimed as the default.
        t.down.clear()
        clock.advance(31.0)
        t.calls.clear()
        assert pool.call("eth_chainId") == "0x2105"
        assert t.calls == ["https://a"]  # back to the preferred default

    def test_repeated_outage_gets_exponential_cooldown(self):
        clock = FakeClock()
        t = FakeTransport(down={"https://a"})
        pool = cn.RpcPool(
            self._spec(["https://a", "https://b"]),
            transport=t,
            cooldown=10.0,
            max_cooldown=60.0,
            clock=clock,
        )
        pool.call("eth_chainId")
        first_until = pool._endpoints[0].cooldown_until
        clock.advance(11.0)
        pool.call("eth_chainId")
        second_until = pool._endpoints[0].cooldown_until
        assert first_until == 1010.0
        assert second_until == 1031.0  # second failure: 20 seconds from t=1011

    def test_node_error_propagates_without_failover(self):
        t = FakeTransport(errors={"https://a"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        with pytest.raises(cn.RpcError):
            pool.call("eth_getTransactionByHash", ["0x1"])
        assert t.calls == ["https://a"]  # reached a node, rejected on merits — b untouched

    def test_run_fails_over_on_raise_but_accepts_not_found_return(self):
        # fn raises on the first url (transport), returns a "not found" value on the second:
        # the not-found is a legitimate answer and must NOT trigger further failover.
        attempts = []

        def fn(url):
            attempts.append(url)
            if url == "https://a":
                raise ConnectionError("boom")
            return {"verified": False, "error": "not found"}

        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=FakeTransport())
        out = pool.run(fn)
        assert out == {"verified": False, "error": "not found"}
        assert attempts == ["https://a", "https://a", "https://b"]

    def test_no_urls_raises(self):
        with pytest.raises(cn.ChainNetError):
            cn.RpcPool(self._spec([]), transport=FakeTransport())


# ═══════════════════════════════════ health ═════════════════════════════════
class TestHealth:
    def _spec(self, urls, kind=cn.EVM):
        return cn.NetworkSpec(id="base" if kind == cn.EVM else "solana", kind=kind,
                              display_name="N", chain_id=8453 if kind == cn.EVM else None,
                              cluster=None if kind == cn.EVM else "mainnet-beta",
                              rpc_urls=tuple(urls), native_symbol="ETH", explorer_tx="")

    def test_healthy_url_returns_first_up(self):
        t = FakeTransport(down={"https://a"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        assert pool.healthy_url() == "https://b"

    def test_healthy_url_none_when_all_down(self):
        t = FakeTransport(down={"https://a", "https://b"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        assert pool.healthy_url() is None  # caller degrades to "offline", no hang

    def test_evm_probe_is_chainid_solana_is_gethealth(self):
        seen = {}

        def transport(url, body, timeout):
            seen[url] = body["method"]
            return {"result": "ok"}

        cn.RpcPool(self._spec(["https://e"], cn.EVM), transport=transport).healthy_url()
        cn.RpcPool(self._spec(["https://s"], cn.SOLANA), transport=transport).healthy_url()
        assert seen["https://e"] == "eth_chainId"
        assert seen["https://s"] == "getHealth"

    def test_health_report_shape(self):
        t = FakeTransport(down={"https://b"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        rep = pool.health()
        assert rep["network"] == "base" and rep["healthy"] is True
        assert [e["healthy"] for e in rep["endpoints"]] == [True, False]


# ═══════════════════════════════════ audit hardening ════════════════════════
class TestHardening:
    def _spec(self, urls):
        return cn.NetworkSpec(id="base", kind=cn.EVM, display_name="Base", chain_id=8453,
                              cluster=None, rpc_urls=tuple(urls), native_symbol="ETH", explorer_tx="")

    def test_non_dict_response_fails_over_not_returned(self):
        # A broken endpoint returning a non-JSON-object must be treated as a transport failure
        # (fail over), never returned to the caller as a "result".
        class _T:
            def __init__(self): self.calls = []
            def __call__(self, url, body, timeout):
                self.calls.append(url)
                return "not-an-object" if url == "https://a" else {"result": "0x2105"}
        t = _T()
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        assert pool.call("eth_chainId") == "0x2105"
        assert t.calls == ["https://a", "https://a", "https://b"]

    def test_health_marks_non_dict_down(self):
        class _T:
            def __call__(self, url, body, timeout):
                return "garbage" if url == "https://a" else {"result": "ok"}
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=_T())
        rep = pool.health()
        assert [e["healthy"] for e in rep["endpoints"]] == [False, True]

    def test_malformed_float_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_RPC_TIMEOUT", "not-a-number")
        pool = cn.RpcPool(self._spec(["https://a"]), transport=FakeTransport())
        assert pool._timeout == 6.0  # default, no crash

    def test_non_http_scheme_dropped(self):
        with pytest.raises(cn.ChainNetError):  # file:// is the only url → nothing usable
            cn.RpcPool(self._spec(["file:///etc/passwd"]), transport=FakeTransport())
        pool = cn.RpcPool(self._spec(["file:///x", "https://b"]), transport=FakeTransport())
        assert [e.url for e in pool._endpoints] == ["https://b"]  # file:// silently dropped

    def test_redact_url_strips_credentials_and_path(self):
        assert cn.redact_url("https://user:KEY@rpc.example.com/v2/SECRET?k=1") == "https://rpc.example.com"
        assert cn.redact_url("https://rpc.example.com:8545/path") == "https://rpc.example.com:8545"

    def test_pool_for_reuses_health_state(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_RPC_BASE", "https://a,https://b")
        cn._POOL_CACHE.clear()
        try:
            assert cn.pool_for("base", timeout=4.0) is cn.pool_for("base", timeout=4.0)
        finally:
            cn._POOL_CACHE.clear()


# ═══════════════════════════════════ rotation, refusals, list check ═════════
class _Http429(Exception):
    """urllib's HTTPError shape: a ``code`` and the reply ``headers``."""

    def __init__(self, retry_after: str = ""):
        super().__init__("HTTP Error 429: Too Many Requests")
        self.code = 429
        self.headers = {"Retry-After": retry_after} if retry_after else {}


class TestRotationAndRefusals:
    def _spec(self, urls):
        return cn.NetworkSpec(id="base", kind=cn.EVM, display_name="Base", chain_id=8453,
                              cluster=None, rpc_urls=tuple(urls), native_symbol="ETH", explorer_tx="")

    def test_a_rotating_pool_starts_each_call_at_the_next_node(self):
        t = FakeTransport()
        pool = cn.RpcPool(self._spec(["https://a", "https://b", "https://c"]), transport=t, rotate=True)
        for _ in range(4):
            pool.call("eth_blockNumber")
        assert t.calls == ["https://a", "https://b", "https://c", "https://a"]

    def test_rotation_skips_a_resting_node(self):
        clock = FakeClock()
        t = FakeTransport(down={"https://b"})
        pool = cn.RpcPool(self._spec(["https://a", "https://b", "https://c"]), transport=t, rotate=True,
                          cooldown=30.0, clock=clock)
        pool.call("eth_blockNumber")      # a
        pool.call("eth_blockNumber")      # b down (asked twice: a transport error is retried) → c
        t.calls.clear()
        for _ in range(4):
            pool.call("eth_blockNumber")
        assert "https://b" not in t.calls and set(t.calls) == {"https://a", "https://c"}

    def test_a_rate_limit_reply_fails_over_at_once_and_rests_the_node(self):
        class _Limited(FakeTransport):
            def __call__(self, url, body, timeout):
                self.calls.append(url)
                if url == "https://a":
                    return {"jsonrpc": "2.0", "id": 1,
                            "error": {"code": -32005, "message": "eth_getLogs is limited to 0 - 50 blocks range"}}
                return {"jsonrpc": "2.0", "id": 1, "result": []}

        t = _Limited()
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t)
        assert pool.call("eth_getLogs", [{}]) == []
        assert t.calls == ["https://a", "https://b"]          # not asked twice: it refused, it is not down
        assert pool._endpoints[0].healthy is False and "limited to" in pool._endpoints[0].last_error

    def test_http_429_is_not_retried_and_rests_as_long_as_retry_after_asks(self):
        clock = FakeClock()

        class _T(FakeTransport):
            def __call__(self, url, body, timeout):
                self.calls.append(url)
                if url == "https://a":
                    raise _Http429(retry_after="120")
                return {"result": "0x1"}

        t = _T()
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t, cooldown=30.0,
                          max_cooldown=300.0, clock=clock)
        assert pool.call("eth_getLogs", [{}]) == "0x1"
        assert t.calls == ["https://a", "https://b"]
        assert pool._endpoints[0].cooldown_until == clock.t + 120.0

    def test_a_bad_request_still_raises_without_failover(self):
        t = FakeTransport(errors={"https://a"})       # "boom": the request, not a limit
        pool = cn.RpcPool(self._spec(["https://a", "https://b"]), transport=t, rotate=True)
        with pytest.raises(cn.RpcError):
            pool.call("eth_call", [{}])
        assert t.calls == ["https://a"]

    def test_all_down_names_every_node_by_host_only(self):
        t = FakeTransport(down={"https://a.example/KEY", "https://b.example"})
        pool = cn.RpcPool(self._spec(["https://a.example/KEY", "https://b.example"]), transport=t)
        with pytest.raises(cn.AllEndpointsDown) as err:
            pool.call("eth_blockNumber")
        assert "https://a.example:" in str(err.value) and "https://b.example:" in str(err.value)
        assert "KEY" not in str(err.value).replace("down: https://a.example/KEY", "")

    def test_pool_for_urls_keeps_one_pool_per_list(self):
        t = FakeTransport()
        one = cn.pool_for_urls(["https://a", "https://b"], chain_id=8453, transport=t)
        assert cn.pool_for_urls(["https://a", "https://b"], chain_id=8453, transport=t) is one
        assert cn.pool_for_urls(["https://b", "https://a"], chain_id=8453, transport=t) is not one
        cn.reset_pools()
        assert cn.pool_for_urls(["https://a", "https://b"], chain_id=8453, transport=t) is not one


class TestListCheck:
    def _spec(self, urls):
        return cn.NetworkSpec(id="base", kind=cn.EVM, display_name="Base", chain_id=8453,
                              cluster=None, rpc_urls=tuple(urls), native_symbol="ETH", explorer_tx="")

    def test_check_says_which_nodes_can_serve_the_scan(self):
        heads = {"https://good": 1000, "https://limited": 1000, "https://stale": 900,
                 "https://other-chain": 1000}

        class _T:
            def __init__(self):
                self.windows = []

            def __call__(self, url, body, timeout):
                m = body["method"]
                if m == "eth_chainId":
                    return {"result": hex(1 if url == "https://other-chain" else 8453)}
                if m == "eth_blockNumber":
                    return {"result": hex(heads[url])}
                if m == "eth_getLogs":
                    if url == "https://limited":
                        raise _Http429()
                    f = body["params"][0]
                    self.windows.append(int(f["toBlock"], 16) - int(f["fromBlock"], 16) + 1)
                    return {"result": []}
                raise AssertionError(m)

        t = _T()
        pool = cn.RpcPool(self._spec(list(heads)), transport=t)
        rows = {r["url"]: r for r in pool.check(logs_filter={"address": "0xusdc", "topics": [], "window": 500})}
        assert rows["https://good"]["usable"] and rows["https://good"]["logs"] == "ok"
        assert not rows["https://limited"]["usable"] and rows["https://limited"]["logs"] == "refused"
        assert not rows["https://stale"]["usable"] and rows["https://stale"]["lag"] == 100
        assert not rows["https://other-chain"]["usable"] and "chain 1" in rows["https://other-chain"]["detail"]
        assert set(t.windows) == {500}
        assert pool._endpoints[1].healthy is False      # the check rests the refusing node too
