"""The payment canary must fail on the regressions it exists to catch.

A monitor that passes when the thing it watches is broken is worse than no monitor: it
converts an outage into a documented all-clear. Payment enforcement on modelmarket.dev
has regressed twice already, both times silently, so each case below is a shape the hub
has actually been in — or one step away from.

Enforcement is decided per provider, not once: `AIMARKET_SELLS_FOR` gates each federated
peer and the local branch has a gate of its own. Probing a single capability once let a
$0.03 atlas capability be served free while the oracle family was correctly answering 402,
so the canary probes one capability per provider and each gets its own verdict.
"""
from __future__ import annotations

import json
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import payment_canary as canary  # noqa: E402


HEALTHY_MANIFEST = {
    "name": "modelmarket.dev",
    "payment_configured": True,
    "payment_testnet": False,
    "mcp_servers": [
        {"name": "aimarket-hub", "transport": "streamable-http",
         "url": "https://modelmarket.dev/mcp", "tools": ["market_search", "market_invoke"]},
        {"name": "aimarket-oracle-gateway", "transport": "stdio"},
    ],
}
HEALTHY_PROBES = [
    {"status": 402, "body": {"error": "payment_required", "needed": 0.001},
     "capability_id": "ablation.verify@v1", "source_hub": "https://oracles.modelmarket.dev/family",
     "price_usd": 0.001},
    {"status": 402, "body": {"error": "payment_required", "needed": 0.03},
     "capability_id": "atlas.nearest.read@v1", "source_hub": "https://atlas.modelmarket.dev",
     "price_usd": 0.03},
]
HEALTHY_MCP = {"service": "aimarket-hub-mcp", "tools": ["market_search", "market_invoke"],
               "trial": "per-caller", "transport": "streamable-http"}


def _by_name(checks):
    return {c.name: c for c in checks}


def _failed(checks):
    return {c.name for c in checks if not c.ok and c.critical}


def _gated(checks):
    return [c for c in checks if c.name.startswith("priced_capability_gated")]


def test_a_healthy_hub_passes_everything():
    checks = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP)
    assert not _failed(checks)
    assert all(c.ok for c in checks)


def test_paid_work_served_for_free_is_a_failure():
    """The 2026-07-31 shape: the hub kept answering, it just stopped charging."""
    probes = [dict(HEALTHY_PROBES[0], status=200, body={"success": True, "output": {}})]
    checks = canary.evaluate(HEALTHY_MANIFEST, probes, HEALTHY_MCP)
    assert _failed(checks)
    assert "SERVED FOR FREE" in _gated(checks)[0].detail


def test_one_free_provider_among_gated_ones_still_fails():
    """The live atlas case: oracles correctly 402, atlas served $0.03 work for nothing.

    A single averaged verdict would have called this healthy, which is exactly what a
    per-capability probe did before.
    """
    probes = [HEALTHY_PROBES[0], dict(HEALTHY_PROBES[1], status=200, body={"ok": True})]
    checks = canary.evaluate(HEALTHY_MANIFEST, probes, HEALTHY_MCP)
    failed = _failed(checks)
    assert len(failed) == 1
    assert "atlas.modelmarket.dev" in next(iter(failed))
    assert any(c.ok for c in _gated(checks)), "the gated provider must still read as passing"


def test_the_self_reported_flag_alone_cannot_pass_the_canary():
    """payment_configured=true while a priced capability is free — the 2026-08-04 shape."""
    probes = [dict(HEALTHY_PROBES[0], status=200, body={"success": True})]
    checks = canary.evaluate(HEALTHY_MANIFEST, probes, HEALTHY_MCP)
    assert _by_name(checks)["payment_configured"].ok is True
    assert _failed(checks), "the manifest's own claim must not be able to carry the verdict"


def test_payment_switched_off_is_a_failure():
    manifest = dict(HEALTHY_MANIFEST, payment_configured=False)
    assert "payment_configured" in _failed(canary.evaluate(manifest, HEALTHY_PROBES, HEALTHY_MCP))


def test_testnet_money_is_a_failure():
    manifest = dict(HEALTHY_MANIFEST, payment_testnet=True)
    assert "mainnet" in _failed(canary.evaluate(manifest, HEALTHY_PROBES, HEALTHY_MCP))


def test_an_inconclusive_probe_is_not_a_pass():
    """A 500, a 429 or a timeout proves nothing; treating it as green is how outages hide."""
    for status in (0, 404, 500, 429):
        probes = [dict(HEALTHY_PROBES[0], status=status, body={})]
        checks = canary.evaluate(HEALTHY_MANIFEST, probes, HEALTHY_MCP)
        assert _failed(checks), f"HTTP {status} passed"


def test_no_priced_capability_to_probe_is_not_a_pass():
    for empty in (None, []):
        checks = canary.evaluate(HEALTHY_MANIFEST, empty, HEALTHY_MCP)
        assert "priced_capability_gated" in _failed(checks)


def test_a_single_probe_dict_is_still_accepted():
    checks = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES[0], HEALTHY_MCP)
    assert not _failed(checks)


def test_an_unreachable_hub_reports_one_clear_failure():
    checks = canary.evaluate(None, None, None)
    assert [c.name for c in checks] == ["manifest_served"]
    assert not checks[0].ok


def test_a_dead_mcp_endpoint_is_a_failure():
    """The registry listings hand strangers this URL; silence there is an outage."""
    assert "mcp_endpoint_live" in _failed(canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, None))


def test_a_disabled_trial_is_a_failure():
    """A redeploy that drops AIMARKET_SANDBOX_ENABLED makes every newcomer meet the wall."""
    mcp = dict(HEALTHY_MCP, trial="disabled")
    assert "mcp_trial_per_caller" in _failed(canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, mcp))


def test_losing_the_hosted_listing_warns_without_failing():
    """Worth knowing, but it does not mean the endpoint is down."""
    manifest = dict(HEALTHY_MANIFEST, mcp_servers=[{"name": "x", "transport": "stdio"}])
    checks = canary.evaluate(manifest, HEALTHY_PROBES, HEALTHY_MCP)
    assert _by_name(checks)["mcp_advertised"].ok is False
    assert "mcp_advertised" not in _failed(checks)


# --- peer liveness -----------------------------------------------------------------------
#
# The payment probes are structurally blind to a dead satellite: the hub answers 402 before
# it ever contacts the provider, so a priced capability reads as perfectly gated while the
# thing behind it is in the ground. That is not hypothetical — on 2026-08-16 GAIA served its
# manifest with a clean 200 while its invoke endpoint hung, every gaia capability answered
# 502 through the hub, and this canary reported all-green for the whole outage.

ALIVE = {"url": "https://iot.modelmarket.dev", "sells": True, "manifest_ok": True,
         "alive": True, "status": 200, "error": None, "endpoint_routable": True}
GAIA_SHAPE = {"url": "https://iot.modelmarket.dev", "sells": True, "manifest_ok": True,
              "alive": False, "status": None, "error": "no response within 12s",
              "endpoint_routable": True}
GONE = {"url": "https://hunt.modelmarket.dev", "sells": False, "manifest_ok": False,
        "alive": False, "status": None, "error": "no response within 12s",
        "endpoint_routable": True}


def test_a_live_peer_passes_on_any_http_answer():
    """A 404 for a capability that cannot exist still proves the service is serving."""
    for status in (200, 400, 404, 422, 500):
        checks = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP,
                                 [dict(ALIVE, status=status)])
        assert not _failed(checks), f"HTTP {status} was treated as dead"


def test_a_served_manifest_does_not_make_a_peer_alive():
    """The exact 2026-08-16 GAIA shape — and the reason this check probes the invoke path."""
    checks = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP, [GAIA_SHAPE])
    failed = _failed(checks)
    assert "peer_alive[https://iot.modelmarket.dev]" in failed
    detail = _by_name(checks)["peer_alive[https://iot.modelmarket.dev]"].detail
    assert "manifest is served" in detail and "502" in detail


def test_payment_checks_stay_green_while_a_peer_is_dead():
    """Pins the blindness this check exists to cover: gated and alive are independent."""
    checks = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP, [GAIA_SHAPE])
    assert all(c.ok for c in _gated(checks)), "the 402 probes cannot see a dead provider"
    assert _failed(checks), "and yet the run must fail"


def test_a_dead_peer_that_sells_is_critical_and_a_free_one_is_not():
    selling = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP, [GAIA_SHAPE])
    free = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP, [GONE])
    assert _failed(selling), "a satellite whose capabilities are sold must page someone"
    assert not _failed(free), "a free peer going quiet is worth knowing, not worth waking"
    assert not _by_name(free)["peer_alive[https://hunt.modelmarket.dev]"].ok


def test_no_peers_means_no_peer_checks():
    before = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP)
    assert not any(c.name.startswith("peer_alive") for c in before)


def test_an_unroutable_advertised_endpoint_warns():
    """magic-ai-factory.com publishes http://localhost:9080/... to the whole internet."""
    peer = dict(ALIVE, endpoint_routable=False,
                advertised_endpoint="http://localhost:9080/ai-market/mcp")
    checks = canary.evaluate(HEALTHY_MANIFEST, HEALTHY_PROBES, HEALTHY_MCP, [peer])
    name = "peer_endpoint_routable[https://iot.modelmarket.dev]"
    assert _by_name(checks)[name].ok is False
    assert name not in _failed(checks), "a bad advertisement is not an outage"


@pytest.mark.parametrize("endpoint,unroutable", [
    ("http://localhost:9080/ai-market/mcp", True),
    ("http://127.0.0.1:9083/x", True),
    ("http://10.1.2.3:9083/x", True),
    ("http://192.168.0.5/x", True),
    ("https://iot.modelmarket.dev/ai-market/v2/invoke", False),
    ("https://203.0.113.80:9083/x", False),
    ("", False),
])
def test_unroutable_detection(endpoint, unroutable):
    assert canary._is_unroutable(endpoint) is unroutable


def test_the_probe_asks_the_standard_invoke_path_not_the_advertised_one(monkeypatch):
    """Trusting mcp_endpoint reported three healthy peers as dead, because one of them
    advertises localhost — the probe dialled the machine running the canary."""
    posted: list = []
    monkeypatch.setattr(canary, "_get", lambda url, timeout: (
        200, {"mcp_endpoint": "http://localhost:9080/ai-market/mcp"}))
    monkeypatch.setattr(canary, "_post",
                        lambda url, payload, timeout: (posted.append(url), (404, {}))[1])
    out = canary.probe_peer({"url": "https://factory.test", "sells": False})
    assert posted == ["https://factory.test/ai-market/v2/invoke"]
    assert out["alive"] is True and out["status"] == 404
    assert out["endpoint_routable"] is False


def test_a_single_blink_does_not_report_an_outage(monkeypatch):
    """A satellite that misses one packet should not page anyone at 06:17."""
    calls = {"n": 0}

    def flaky(url, payload, timeout):
        calls["n"] += 1
        return (0, None) if calls["n"] == 1 else (404, {})

    monkeypatch.setattr(canary, "_get", lambda url, timeout: (200, {}))
    monkeypatch.setattr(canary, "_post", flaky)
    assert canary.probe_peer({"url": "https://x.test"})["alive"] is True
    assert calls["n"] == 2, "the probe must retry before declaring a peer dead"


def test_a_sustained_outage_survives_the_retry(monkeypatch):
    monkeypatch.setattr(canary, "_get", lambda url, timeout: (200, {"mcp_endpoint": ""}))
    monkeypatch.setattr(canary, "_post", lambda url, payload, timeout: (0, None))
    out = canary.probe_peer({"url": "https://dead.test", "sells": True})
    assert out["alive"] is False and out["manifest_ok"] is True
    assert "no response" in out["error"]


def test_peers_reach_the_published_report(monkeypatch, tmp_path):
    """A conductor needs the machine-readable half: one dead peer names one host."""
    monkeypatch.setattr(canary, "observe", lambda *a, **k: {
        "manifest": HEALTHY_MANIFEST, "probes": HEALTHY_PROBES, "mcp_info": HEALTHY_MCP,
        "peers": [GAIA_SHAPE],
    })
    out = tmp_path / "status.json"
    canary.main(["--publish", str(out), "--timestamp", "2026-08-16T00:00:00Z"])
    published = json.loads(out.read_text())
    assert published["ok"] is False
    assert published["peers"][0]["url"] == "https://iot.modelmarket.dev"
    assert published["peers"][0]["alive"] is False


# --- capability selection ----------------------------------------------------------------

PRICES = {"prices": [
    {"capability_id": "cheap.oracle@v1", "product_id": "p1", "price_usd": 0.001,
     "source_hub": "https://oracles.modelmarket.dev/family"},
    {"capability_id": "dear.oracle@v1", "product_id": "p1", "price_usd": 0.5,
     "source_hub": "https://oracles.modelmarket.dev/family"},
    {"capability_id": "atlas.nearest@v1", "product_id": "p2", "price_usd": 0.03,
     "source_hub": "https://atlas.modelmarket.dev"},
    {"capability_id": "local.thing@v1", "product_id": "p3", "price_usd": 0.4,
     "source_hub": "local"},
    {"capability_id": "free.thing@v1", "product_id": "p4", "price_usd": 0,
     "source_hub": "local"},
]}


def test_one_probe_per_provider_cheapest_first():
    picked = canary.pick_priced_capabilities(PRICES)
    assert [p["capability_id"] for p in picked] == [
        "cheap.oracle@v1", "atlas.nearest@v1", "local.thing@v1"]


def test_every_provider_is_represented():
    """The atlas gap existed because only one provider was ever probed."""
    hubs = {p["source_hub"] for p in canary.pick_priced_capabilities(PRICES)}
    assert hubs == {"https://oracles.modelmarket.dev/family", "https://atlas.modelmarket.dev",
                    "local"}


def test_free_capabilities_are_never_probed():
    """A free capability answers 200 legitimately and would report a false regression."""
    picked = canary.pick_priced_capabilities(PRICES)
    assert "free.thing@v1" not in {p["capability_id"] for p in picked}


def test_the_probe_list_is_bounded():
    many = {"prices": [{"capability_id": f"c{i}@v1", "product_id": "p", "price_usd": 0.01 * (i + 1),
                        "source_hub": f"hub{i}"} for i in range(20)]}
    assert len(canary.pick_priced_capabilities(many)) == canary.MAX_PROBES


def test_malformed_price_rows_do_not_crash_the_canary():
    for bad in (None, {}, {"prices": None}, {"prices": [{"price_usd": "abc"}]},
                {"prices": [{"price_usd": 1.0}]}):        # priced but no ids
        assert canary.pick_priced_capabilities(bad) == []


def test_search_fallback_still_works_when_prices_is_unavailable():
    search = {"matches": [
        {"capability_id": "a@v1", "product_id": "p", "price_per_call_usd": 0.5},
        {"capability_id": "b@v1", "product_id": "p", "price_per_call_usd": 0.001},
    ]}
    assert canary.pick_priced_capability(search)["capability_id"] == "b@v1"
    assert canary.pick_priced_capability({"matches": []}) is None


# --- reporting ---------------------------------------------------------------------------

def _observing(probes, mcp=HEALTHY_MCP, manifest=HEALTHY_MANIFEST):
    return lambda *a, **k: {"manifest": manifest, "probes": probes, "mcp_info": mcp}


def test_exit_code_is_non_zero_when_a_critical_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(canary, "observe",
                        _observing([dict(HEALTHY_PROBES[0], status=200, body={})]))
    assert canary.main(["--timestamp", "2026-08-16T00:00:00Z"]) == 1
    assert "VERDICT: 1 critical check(s) failed" in capsys.readouterr().out


def test_exit_code_is_zero_when_healthy(monkeypatch, capsys):
    monkeypatch.setattr(canary, "observe", _observing(HEALTHY_PROBES))
    assert canary.main(["--timestamp", "2026-08-16T00:00:00Z"]) == 0
    assert "VERDICT: ok" in capsys.readouterr().out


def test_published_status_is_written_atomically(monkeypatch, tmp_path):
    monkeypatch.setattr(canary, "observe", _observing(HEALTHY_PROBES))
    out = tmp_path / "status.json"
    canary.main(["--publish", str(out), "--timestamp", "2026-08-16T00:00:00Z"])
    published = json.loads(out.read_text())
    assert published["ok"] is True
    assert published["checked_at"] == "2026-08-16T00:00:00Z"
    assert any(c["name"].startswith("priced_capability_gated") for c in published["checks"])
    assert not list(tmp_path.glob("*.tmp")), "the temp file must not be left behind"


def test_a_publish_failure_is_not_reported_as_a_payment_regression(monkeypatch, capsys):
    """Cron sees only the exit code; 1 must keep meaning 'the hub stopped charging'."""
    monkeypatch.setattr(canary, "observe", _observing(HEALTHY_PROBES))
    code = canary.main(["--publish", "/nonexistent-dir-for-test/status.json",
                        "--timestamp", "2026-08-16T00:00:00Z"])
    assert code == 2
    assert "could not publish" in capsys.readouterr().err


def test_the_probe_never_sends_a_trial_header(monkeypatch):
    """Sending one would get a legitimate 200 and hide a real regression."""
    sent: list = []

    def fake_get(url, timeout):
        if "prices" in url:
            return 200, PRICES
        return 200, {"name": "hub"}

    def fake_post(url, payload, timeout):
        sent.append(payload)
        return 402, {"error": "payment_required"}

    monkeypatch.setattr(canary, "_get", fake_get)
    monkeypatch.setattr(canary, "_post", fake_post)
    seen = canary.observe("https://hub.test", 5.0)
    assert len(seen["probes"]) == 3, "one probe per provider"
    assert all(p["status"] == 402 for p in seen["probes"])
    # _post takes a payload only; a trial identity would have to be a header, and the
    # canary's _post sets exactly two: Content-Type and User-Agent.
    assert sent and all("input" in payload for payload in sent)


def test_local_capabilities_are_probed_without_a_source_hub(monkeypatch):
    posted: list = []
    monkeypatch.setattr(canary, "_get", lambda url, timeout: (200, PRICES if "prices" in url else {"name": "h"}))
    monkeypatch.setattr(canary, "_post", lambda url, payload, timeout: (posted.append(payload), (402, {}))[1])
    canary.observe("https://hub.test", 5.0)
    local = [p for p in posted if p["capability_id"] == "local.thing@v1"]
    assert local and "source_hub" not in local[0]
