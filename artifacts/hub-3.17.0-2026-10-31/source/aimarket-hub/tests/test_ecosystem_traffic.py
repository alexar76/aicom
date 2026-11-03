"""SELF vs EXT: the hub's ecosystem registry (aimarket_hub/ecosystem.py).

The owner's rule (2026-10-02): SELF is the hub itself and the components bound to it that are
part of its ecosystem; EXT is everybody else — including outside services on a billed rail
(PingBlip's credit account read SELF for a day because it had been listed as "ours") and
anybody running this code for themselves. Default: only the hub itself; the operator lists the
rest in ecosystem.json. Addresses here are documentation ranges (RFC 5737 / 3849).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from itertools import product

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import ecosystem
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.ecosystem import (
    CALLER_ADDRESS, CALLER_EXTERNAL, CALLER_FORWARDED, CALLER_WALLET,
    TRAFFIC_EXTERNAL, TRAFFIC_SELF, parse_policy,
)
from aimarket_hub.mcp_gateway import MCP_CALLER_HEADER
from aimarket_hub.models import Capability, InvocationStat
from aimarket_hub.signing import Signer

OURS = "198.51.100.7"          # an ecosystem server
OURS_V6 = "2001:db8:7::/64"
STRANGER = "203.0.113.5"
OUTSIDE_SERVICE = "203.0.113.80"  # e.g. a game we host but that is a customer, not ecosystem
OUR_WALLET = "0x" + "11" * 20
THEIR_WALLET = "0x" + "22" * 20
FREE = {"product_id": "demo-echo", "capability_id": "demo.free@v1",
        "input": {"text": "hi"}, "source_hub": "local"}


def _policy(**sections):
    data = {"version": 1, **sections}
    return parse_policy(data, proxies=[])


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.delenv("AIMARKET_OPERATOR_ACCOUNTS", raising=False)
    monkeypatch.delenv("AIMARKET_TRUSTED_PROXIES", raising=False)
    ecosystem._clear_cache()
    yield
    ecosystem._clear_cache()


# ── the file ──────────────────────────────────────────────────────────────────

def test_entries_are_strings_or_value_note_objects():
    p = _policy(self={
        "accounts": ["acct_desk", {"value": "acct_canary", "note": "subcontract canary"}],
        "networks": [OURS, {"value": OURS_V6, "note": "desk host v6"}],
        "wallets": [{"value": OUR_WALLET.upper().replace("0X", "0x"), "note": "test buyer"}],
    })
    assert p.status == "ok"
    assert p.self_accounts == {"acct_desk", "acct_canary"}
    assert len(p.self_networks) == 2
    assert p.self_wallets == {OUR_WALLET}


@pytest.mark.parametrize("data", [
    {"version": 1, "selff": {}},                               # typo at the top
    {"version": 1, "self": {"netwroks": [OURS]}},             # typo in a section
    {"version": 2, "self": {}},                                # unknown schema
    {"self": {}},                                              # no version
    {"version": 1, "self": {"networks": OURS}},               # not a list
    [],                                                        # not an object
])
def test_structural_mistakes_reject_the_whole_file(data):
    with pytest.raises(ValueError):
        parse_policy(data, proxies=[])


@pytest.mark.parametrize("network", [
    "127.0.0.1", "::1", "10.1.2.3", "172.18.0.1", "192.168.1.10", "100.64.0.1", "169.254.1.1",
    "fd00::1", "fe80::1", "0.0.0.0/0", "198.51.0.0/8", "198.51.0.0/16", "2001:db8::/16",
    "2001:db8::/48", "64:ff9b::c633:6407", "2002:c633:6407::1", "not-an-ip", "",
])
def test_addresses_the_hub_plumbing_or_a_typo_produce_are_refused(network):
    p = _policy(self={"networks": [network, OURS]})
    assert p.status == "partial"
    assert len(p.self_networks) == 1  # the good one still applies
    assert p.problems


def test_documentation_ranges_are_accepted_and_mapped_v6_is_normalised():
    p = _policy(self={"networks": ["::ffff:198.51.100.7", "203.0.113.0/24", "2001:db8:7::/56"]})
    assert p.status == "ok"
    for ip in (OURS, "::ffff:203.0.113.9", "2001:db8:7::42"):
        assert p.caller_class(label="anonymous", client_ip=ip).startswith(CALLER_ADDRESS + ":")


def test_a_network_that_holds_a_trusted_proxy_is_refused():
    proxy = ecosystem.parse_ip("198.51.100.9")
    p = parse_policy({"version": 1, "self": {"networks": ["198.51.100.0/24"]}}, proxies=[proxy])
    assert p.self_networks == ()
    assert any("trusted proxy" in x for x in p.problems)


def test_external_wins_when_an_entry_is_in_both_lists():
    p = _policy(self={"accounts": ["acct_x"], "wallets": [OUR_WALLET], "networks": ["203.0.113.0/24"]},
                external={"accounts": ["acct_x"], "wallets": [OUR_WALLET], "networks": [OUTSIDE_SERVICE]})
    assert p.status == "partial"
    assert "acct_x" not in p.self_accounts
    assert p.classify("account:acct_x") == (TRAFFIC_EXTERNAL, "override")
    assert p.caller_class(label="x402", payer_wallet=OUR_WALLET) == CALLER_EXTERNAL
    assert p.caller_class(label="anonymous", client_ip=OUTSIDE_SERVICE) == CALLER_EXTERNAL
    assert p.caller_class(label="anonymous", client_ip="203.0.113.1").startswith(CALLER_ADDRESS)


def test_the_older_env_list_still_counts_and_is_merged(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_OPERATOR_ACCOUNTS", "acct_env1, acct_env2")
    env_only = ecosystem.current(tmp_path / "absent.json")
    assert env_only.source == "env" and env_only.status == "absent"
    assert env_only.self_accounts == {"acct_env1", "acct_env2"}
    f = tmp_path / "ecosystem.json"
    f.write_text(json.dumps({"version": 1, "self": {"accounts": ["acct_file"]}}))
    both = ecosystem.current(f)
    assert both.source == "file+env"
    assert both.self_accounts == {"acct_env1", "acct_env2", "acct_file"}


def test_without_a_file_only_the_hub_itself_is_self(tmp_path):
    p = ecosystem.current(tmp_path / "ecosystem.json")
    assert (p.source, p.status) == ("default", "absent")
    assert p.classify("operator_self") == (TRAFFIC_SELF, "operator")
    assert p.classify("https://hub.example/", hub_url="https://hub.example") == (TRAFFIC_SELF, "operator")
    for label in ("account:acct_any", "x402", "channel:ch_1", "sandbox:v", "mcp:m", "anonymous"):
        assert p.classify(label)[0] == TRAFFIC_EXTERNAL
    assert p.caller_class(label="anonymous", client_ip=OURS) == ""


# ── write time ────────────────────────────────────────────────────────────────

POLICY = _policy(
    self={"accounts": ["acct_ours"], "networks": [OURS], "wallets": [OUR_WALLET]},
    external={"accounts": ["acct_customer_game"], "networks": [OUTSIDE_SERVICE], "wallets": [THEIR_WALLET]},
)


A = "address:" + ecosystem.entry_ref(ecosystem.parse_policy(
    {"version": 1, "self": {"networks": [OURS]}}, proxies=[]).self_networks[0])
W = "wallet:" + ecosystem.entry_ref(OUR_WALLET)


@pytest.mark.parametrize("label,ip,wallet,forwarded,expected", [
    # a forward is judged by the hub that saw the buyer — never SELF here...
    ("account:acct_ours", OURS, "", True, CALLER_FORWARDED),
    ("sandbox:hub-fed-abc", OURS, "", True, CALLER_FORWARDED),
    ("anonymous", OURS, "", True, CALLER_FORWARDED),
    # ...except for a payer verified on chain, which is evidence wherever it arrives
    ("x402", OURS, OUR_WALLET, True, W),
    ("x402", OURS, THEIR_WALLET, True, CALLER_EXTERNAL),
    # explicit external entries beat everything else
    ("anonymous", OUTSIDE_SERVICE, "", False, CALLER_EXTERNAL),
    ("x402", OURS, THEIR_WALLET, False, CALLER_EXTERNAL),
    # billed rails: who paid, never where from
    ("x402", STRANGER, OUR_WALLET, False, W),
    ("x402", OURS, "0x" + "33" * 20, False, ""),
    ("channel:ch_1", STRANGER, OUR_WALLET, False, ""),  # a header-named channel vouches for nothing
    ("channel:ch_1", OURS, "", False, ""),
    ("account:acct_stranger", OURS, "", False, ""),     # a stranger's allowance from our host
    ("operator_self", STRANGER, "", False, ""),
    # trials name a visitor: from a server they are a relay, never SELF by address
    ("sandbox:assay-1", OURS, "", False, ""),
    ("sandbox:mcpx-1", OURS, "", False, ""),
    # no payer, no visitor: the direct caller's address
    ("anonymous", OURS, "", False, A),
    ("mcp:mcpx-1", OURS, "", False, A),
    ("anonymous", "::ffff:" + OURS, "", False, A),
    ("anonymous", STRANGER, "", False, ""),
    ("anonymous", "127.0.0.1", "", False, ""),
    ("anonymous", "testclient", "", False, ""),
    ("anonymous", "", "", False, ""),
])
def test_write_time_precedence(label, ip, wallet, forwarded, expected):
    assert POLICY.caller_class(label=label, client_ip=ip, payer_wallet=wallet,
                               forwarded=forwarded) == expected


def test_taking_an_entry_out_revokes_the_rows_it_produced():
    """The evidence is not stored, but WHICH entry vouched is: a mistaken entry is reversible."""
    later = _policy(self={"accounts": ["acct_ours"]})
    assert POLICY.classify("anonymous", A) == (TRAFFIC_SELF, "address")
    assert later.classify("anonymous", A) == (TRAFFIC_EXTERNAL, None)
    assert POLICY.classify("x402", W) == (TRAFFIC_SELF, "wallet")
    assert later.classify("x402", W) == (TRAFFIC_EXTERNAL, None)


# ── read time, and the SQL twin ───────────────────────────────────────────────

@pytest.mark.parametrize("label,cc,expected", [
    ("operator_self", CALLER_FORWARDED, (TRAFFIC_SELF, "operator")),
    ("local", "", (TRAFFIC_SELF, "operator")),
    ("account:acct_ours", "", (TRAFFIC_SELF, "account")),
    ("account:acct_ours", CALLER_FORWARDED, (TRAFFIC_EXTERNAL, "forwarded")),
    ("account:acct_ours", CALLER_EXTERNAL, (TRAFFIC_EXTERNAL, "override")),
    ("account:acct_customer_game", "", (TRAFFIC_EXTERNAL, "override")),
    ("account:acct_stranger", "", (TRAFFIC_EXTERNAL, None)),
    ("anonymous", A, (TRAFFIC_SELF, "address")),
    ("x402", W, (TRAFFIC_SELF, "wallet")),
    ("anonymous", "address:0000000000", (TRAFFIC_EXTERNAL, None)),
    ("x402", "", (TRAFFIC_EXTERNAL, None)),
])
def test_read_time_classification(label, cc, expected):
    assert POLICY.classify(label, cc, "https://hub.example") == expected


def test_lifetime_totals_agree_with_the_feed_row_for_row(tmp_path):
    """The SQL condition is the twin of classify(): every combination, counted once."""
    db = HubDatabase(tmp_path / "hub.db")
    labels = ["operator_self", "local", "https://hub.example", "https://hub.example/",
              "account:acct_ours", "account:acct_customer_game", "account:acct_stranger",
              "x402", "channel:ch_1", "sandbox:v1", "mcp:m1", "anonymous", "",
              # legacy shapes the write sites no longer produce
              " operator_self", "local//", "https://hub.example//", " account:acct_ours"]
    classes = list(ecosystem.CALLER_CLASSES) + [A, W, "address:0000000000"]
    expected_self = 0
    for i, (label, cc) in enumerate(product(labels, classes)):
        db.record_invocation(InvocationStat(
            capability_id=f"c{i}@v1", product_id="p", source_hub="local", price_usd=0.0,
            latency_ms=1, success=True, timestamp="2026-10-02T00:00:00Z",
            consumer_hub=label, caller_class=cc,
        ))
        if POLICY.classify(label, cc, "https://hub.example")[0] == TRAFFIC_SELF:
            expected_self += 1
    split = db.consumer_traffic_totals(policy=POLICY, hub_url="https://hub.example")
    assert split["operator_self"] == expected_self
    assert split["operator_self"] + split["external"] == len(labels) * len(classes)
    # and with an empty registry only the hub itself is self
    bare = ecosystem.EcosystemPolicy()
    assert db.consumer_traffic_totals(policy=bare, hub_url="https://hub.example")["operator_self"] == \
        sum(1 for lab, cc in product(labels, classes)
            if bare.classify(lab, cc, "https://hub.example")[0] == TRAFFIC_SELF)


def test_an_unknown_caller_class_is_not_stored(tmp_path):
    db = HubDatabase(tmp_path / "hub.db")
    db.record_invocation(InvocationStat(capability_id="c@v1", product_id="p", source_hub="local",
                                        price_usd=0.0, latency_ms=1, success=True,
                                        timestamp="2026-10-02T00:00:00Z", consumer_hub="anonymous",
                                        caller_class="address; DROP"))
    assert db.recent_stats(limit=1)[0]["caller_class"] == ""


# ── reload ────────────────────────────────────────────────────────────────────

def test_an_edit_applies_without_a_restart_and_a_broken_edit_keeps_the_last_good(tmp_path):
    f = tmp_path / "ecosystem.json"
    f.write_text(json.dumps({"version": 1, "self": {"accounts": ["acct_a"]}}))
    assert ecosystem.current(f).self_accounts == {"acct_a"}
    f.write_text(json.dumps({"version": 1, "self": {"accounts": ["acct_a", "acct_b"]}}) + " ")
    assert ecosystem.current(f).self_accounts == {"acct_a", "acct_b"}
    f.write_text('{"version": 1, "self": {"accounts": ["acct_c"],}')  # a trailing comma
    broken = ecosystem.current(f)
    assert broken.status == "invalid"
    assert broken.self_accounts == {"acct_a", "acct_b"}
    f.write_text('{"version": 1, "selff": {}}' + "  ")  # a second broken edit in a row
    assert ecosystem.current(f).self_accounts == {"acct_a", "acct_b"}
    f.unlink()  # deleting the file is a deliberate reset to the default rule
    gone = ecosystem.current(f)
    assert (gone.status, gone.self_accounts) == ("absent", frozenset())


def test_the_check_command_reports_what_the_hub_would_do(tmp_path, capsys):
    f = tmp_path / "ecosystem.json"
    f.write_text(json.dumps({"version": 1, "self": {"networks": [OURS, "10.0.0.1"]}}))
    assert ecosystem._main(["check", str(f)]) == 2
    out = capsys.readouterr().out
    assert "partial" in out and "1 networks" in out and "10.0.0.1" in out
    f.write_text("{")
    assert ecosystem._main(["check", str(f)]) == 1


def test_the_published_summary_holds_counts_only():
    s = POLICY.public_summary()
    flat = json.dumps(s)
    assert s["self"] == {"accounts": 1, "networks": 1, "wallets": 1}
    for secret in (OURS, OUR_WALLET, "acct_ours", "acct_customer_game"):
        assert secret not in flat


# ── through the hub ───────────────────────────────────────────────────────────

@contextmanager
def _hub(monkeypatch, tmp_path, policy: dict | None, *, trusted: str = "testclient"):
    """A hub behind a declared proxy, so X-Forwarded-For names the caller like nginx does."""
    monkeypatch.setenv("AIMARKET_TRUSTED_PROXIES", trusted)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0.05")
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    if policy is not None:
        (root / "ecosystem.json").write_text(json.dumps(policy))
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    db.upsert_capability(Capability(
        capability_id="demo.free@v1", product_id="demo-echo", name="Free",
        description="Costs nothing", price_per_call_usd=0.0,
        source_hub="local", invoke_url="", prompt_template='{"ok": true}',
    ))
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client, db, root


def _invoke(client, ip, **headers):
    r = client.post("/ai-market/v2/invoke", json=FREE, headers={"X-Forwarded-For": ip, **headers})
    assert r.status_code == 200, r.text
    return r


def test_a_call_from_an_ecosystem_server_is_self_and_says_why(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, {"version": 1, "self": {"networks": [OURS]}}) as (client, db, _):
        _invoke(client, OURS)
        _invoke(client, STRANGER)
        _invoke(client, OURS, **{"X-AIMarket-Routing-Hub": "https://peer.example"})  # a forward
        _invoke(client, OURS, **{MCP_CALLER_HEADER: "mcpx-1"})
        stored = [r["caller_class"] for r in db.recent_stats(limit=10)]
        assert sorted(stored) == sorted([A, "", CALLER_FORWARDED, A])

        data = client.get("/ai-market/v2/stats/live").json()
        got = sorted((e["traffic_class"], e["traffic_basis"] or "") for e in data["events"])
        assert got == sorted([(TRAFFIC_SELF, "address"), (TRAFFIC_SELF, "address"),
                              (TRAFFIC_EXTERNAL, ""), (TRAFFIC_EXTERNAL, "forwarded")])
        for e in data["events"]:
            assert "caller_class" not in e
        s = data["summary"]
        assert (s["operator_self_invocations"], s["external_invocations"]) == (2, 2)
        assert (s["operator_self_events_in_page"], s["external_events_in_page"]) == (2, 2)
        assert s["traffic_policy"]["self"]["networks"] == 1
        assert s["traffic_policy"]["status"] == "ok"
        assert OURS not in json.dumps(data)


def test_a_paying_account_is_judged_by_the_registry_not_by_the_address(monkeypatch, tmp_path):
    """A stranger's allowance spent from our provider host stays EXT; listing the account later
    re-classifies its history (read time), taking it out turns it back."""
    with _hub(monkeypatch, tmp_path, {"version": 1, "self": {"networks": [OURS]}}) as (client, db, root):
        signup = client.post("/ai-market/v2/accounts", json={"label": "desk"}).json()
        _invoke(client, OURS, **{"X-API-Key": signup["api_key"]})
        assert db.recent_stats(limit=1)[0]["caller_class"] == ""
        ev = client.get("/ai-market/v2/stats/live").json()["events"][0]
        assert (ev["traffic_class"], ev["traffic_basis"]) == (TRAFFIC_EXTERNAL, None)

        f = root / "ecosystem.json"
        f.write_text(json.dumps({"version": 1, "self": {"networks": [OURS],
                                                         "accounts": [signup["account_id"]]}}))
        ev = client.get("/ai-market/v2/stats/live").json()["events"][0]
        assert (ev["traffic_class"], ev["traffic_basis"]) == (TRAFFIC_SELF, "account")

        f.write_text(json.dumps({"version": 1, "self": {"networks": [OURS]},
                                 "external": {"accounts": [signup["account_id"]]}}))
        ev = client.get("/ai-market/v2/stats/live").json()["events"][0]
        assert (ev["traffic_class"], ev["traffic_basis"]) == (TRAFFIC_EXTERNAL, "override")


def test_an_outside_service_on_our_hardware_is_external(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, {"version": 1, "self": {"networks": ["203.0.113.0/24"]},
                                      "external": {"networks": [OUTSIDE_SERVICE]}}) as (client, db, _):
        _invoke(client, OUTSIDE_SERVICE)
        _invoke(client, "203.0.113.81")
        got = sorted(e["traffic_class"] for e in client.get("/ai-market/v2/stats/live").json()["events"])
        assert got == [TRAFFIC_EXTERNAL, TRAFFIC_SELF]


def test_the_home_page_classifies_like_the_feed(monkeypatch, tmp_path):
    from aimarket_hub.terminal_ssr import snapshot
    with _hub(monkeypatch, tmp_path, {"version": 1, "self": {"networks": [OURS]}}) as (client, db, root):
        _invoke(client, OURS)
        _invoke(client, STRANGER)
        feed = client.get("/ai-market/v2/stats/live").json()
        policy = ecosystem.current(root / "ecosystem.json")
        summary, events = snapshot(db, hub_url="", event_limit=12, policy=policy)
        assert [e["traffic_class"] for e in events] == [e["traffic_class"] for e in feed["events"]]
        assert summary["operator_self_invocations"] == feed["summary"]["operator_self_invocations"] == 1
        assert all("caller_class" not in e for e in events)
        page = client.get("/").text
        assert OURS not in page


def test_the_shipped_example_is_valid_and_holds_no_real_addresses():
    import ipaddress
    from pathlib import Path
    example = Path(__file__).parents[1] / "examples" / "ecosystem.example.json"
    p = ecosystem.load_policy(example)
    assert p.status == "ok", p.problems
    documentation = [ipaddress.ip_network(n) for n in (
        "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]
    for net in p.self_networks + p.external_networks:
        assert any(net.version == d.version and net.subnet_of(d) for d in documentation), net


def test_forwards_and_relays_from_our_own_servers_stay_external(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, {"version": 1, "self": {"networks": [OURS]}}) as (client, db, _):
        _invoke(client, OURS, **{"X-AIMarket-Sandbox-Visitor": "hub-fed-0123456789abcdef0123"})
        _invoke(client, OURS, **{"X-AIMarket-Sandbox-Visitor": "visitor-abc"})  # a relayed trial
        assert {r["caller_class"] for r in db.recent_stats(limit=10)} == {CALLER_FORWARDED, ""}
    # a peer that is not our proxy but forwards for someone else is a relay
    with _hub(monkeypatch, tmp_path, {"version": 1, "self": {"networks": [OURS]}},
              trusted="203.0.113.250") as (client, db, _):
        client.post("/ai-market/v2/invoke", json=FREE, headers={"X-Forwarded-For": "198.51.100.200"})
        assert [r["caller_class"] for r in db.recent_stats(limit=1)] == [CALLER_FORWARDED]
        # nginx's own X-Real-IP is no relay signal
        client.post("/ai-market/v2/invoke", json=FREE, headers={"X-Real-IP": "198.51.100.200"})
        assert [r["caller_class"] for r in db.recent_stats(limit=1)] == [""]


def test_a_call_uvicorn_already_resolved_is_not_a_relay(monkeypatch, tmp_path):
    """Behind nginx with AIMARKET_TRUSTED_PROXIES set, uvicorn rewrites the peer to the real
    client before the app runs, and X-Forwarded-For is still there. 3.15.0 read that as a relay
    and stored every proxied call as forwarded."""
    policy = {"version": 1, "self": {"networks": [OURS]}}
    root = tmp_path / "uv"
    root.mkdir()
    (root / "ecosystem.json").write_text(json.dumps(policy))
    monkeypatch.setenv("AIMARKET_TRUSTED_PROXIES", "127.0.0.1,172.18.0.1")
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    db.upsert_capability(Capability(
        capability_id="demo.free@v1", product_id="demo-echo", name="Free", description="Costs nothing",
        price_per_call_usd=0.0, source_hub="local", invoke_url="", prompt_template='{"ok": true}'))
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    for ip, want in ((OURS, A), (STRANGER, "")):
        with TestClient(app, client=(ip, 40000)) as client:  # what uvicorn leaves the app
            r = client.post("/ai-market/v2/invoke", json=FREE,
                            headers={"X-Forwarded-For": f"{ip}, 172.18.0.1", "X-Real-IP": "172.18.0.1"})
            assert r.status_code == 200, r.text
        assert db.recent_stats(limit=1)[0]["caller_class"] == want, ip
