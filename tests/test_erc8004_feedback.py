"""WARDEN's ERC-8004 feedback (deploy/erc-8004/feedback.py): reports carry the fields EIP-8004
requires of a feedback file, and a live feedback is re-issued only when its statement changes."""

import hashlib
import importlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ERC = os.path.join(HERE, "..", "deploy", "erc-8004")


@pytest.fixture()
def fb(tmp_path, monkeypatch):
    pytest.importorskip("eth_account")
    pytest.importorskip("eth_abi")
    monkeypatch.setenv("WARDEN_FB_STATE", str(tmp_path))
    monkeypatch.setenv("WARDEN_FB_REPORTS", str(tmp_path / "reports"))
    monkeypatch.syspath_prepend(ERC)
    sys.modules.pop("feedback", None)
    mod = importlib.import_module("feedback")
    mod.CLIENT = mod.FEEDBACK_WALLET
    os.makedirs(mod.OUT, exist_ok=True)
    return mod


TOOLS = [{"name": "get_price", "description": "Price of a token.", "inputSchema": {"type": "object"}}]


def row(agent_id, **extra):
    return {"agent_id": agent_id, "title": f"agent {agent_id}", "url": f"https://a{agent_id}.example/mcp",
            "status": "ok", "tools": 1, "score": 97, "wouldBlock": False, "advisory": 0, **extra}


def scan(fb, rows):
    return {"warden": fb.WARDEN_VERSION, "ruleset": {"version": fb.RULESET_VERSION, "ref": {"digest": "x"}},
            "rows": rows}


def live(fb, agent_id, report):
    name = f"warden-{agent_id}.json"
    with open(os.path.join(fb.OUT, name), "w") as f:
        json.dump(report, f)
    with open(fb.LOG, "a") as f:
        f.write(json.dumps({"agentId": agent_id, "kind": "give", "client": fb.FEEDBACK_WALLET, "status": "ok",
                            "uri": f"{fb.BASE_URL}/{name}"}) + "\n")


def old_v1(fb, tools):
    digest = hashlib.sha256(fb.canonical(tools)).hexdigest()
    return {"type": "aimarket.warden-scan/v1", "scanner": {"package": "@aimarket/warden@0.8.2"},
            "result": {"toolsSha256": digest}}


def test_report_has_the_fields_eip_8004_requires(fb):
    rep = fb.report_for(row(42), TOOLS, scan(fb, []), "2026-11-05T10:00:00Z")
    assert rep["agentRegistry"] == f"eip155:8453:{fb.IDENTITY}"
    assert rep["agentId"] == 42
    assert rep["clientAddress"] == f"eip155:8453:{fb.FEEDBACK_WALLET}"
    assert rep["createdAt"] == "2026-11-05T10:00:00Z"
    assert rep["value"] == 97 and rep["valueDecimals"] == 0
    assert rep["tag1"] == "compliance" and rep["tag2"] == "warden-scan"
    assert rep["scanner"]["ruleset"]["version"] == fb.RULESET_VERSION      # the ruleset stays in the file
    assert rep["endpoint"] == "https://a42.example/mcp"
    assert rep["scanner"]["package"] == f"@aimarket/warden@{fb.WARDEN_VERSION}"


def test_calldata_carries_a_score_tag_and_names_the_scanner(fb):
    """tag1 is one an indexer averages as a 0-100 rating; tag2 says whose rating it is."""
    from eth_abi import decode
    data = bytes.fromhex(fb.calldata(42, 97, "https://a42.example/mcp", "https://x/r.json", b"\0" * 32)[2:])
    assert data[:4] == fb.SELECTOR
    agent, value, decimals, tag1, tag2, endpoint, uri, digest = decode(
        ["uint256", "int128", "uint8", "string", "string", "string", "string", "bytes32"], data[4:])
    assert (agent, value, decimals) == (42, 97, 0)
    assert (tag1, tag2) == ("compliance", "warden-scan")
    assert endpoint == "https://a42.example/mcp" and uri == "https://x/r.json"
    assert b"ruleset-v" not in data


def test_a_live_feedback_under_the_old_tags_is_reissued_once(fb):
    """Same tools, same scanner, but given as warden-scan / ruleset-vN: revoke + give; then nothing."""
    old = fb.report_for(row(300), TOOLS, scan(fb, []), "2026-11-20T10:00:00Z")
    old["tag1"], old["tag2"] = "warden-scan", f"ruleset-v{fb.RULESET_VERSION}"
    live(fb, 300, old)
    actions, held, _ = fb.decide(scan(fb, [row(300)]), {"300": TOOLS}, "2026-11-26T18:00:00Z", set())
    assert [a[0] for a in actions] == ["revoke", "give"]
    assert actions[0][2] == "moved to the tags compliance / warden-scan"
    new = json.load(open(actions[1][2]))
    assert (new["tag1"], new["tag2"]) == ("compliance", "warden-scan")

    # The report served under the old tags is not rewritten: its bytes are what the old hash commits to.
    assert json.load(open(os.path.join(fb.OUT, "warden-300.json")))["tag1"] == "warden-scan"

    live(fb, 301, fb.report_for(row(301), TOOLS, scan(fb, []), "2026-11-26T18:00:00Z"))
    actions, _, _ = fb.decide(scan(fb, [row(301)]), {"301": TOOLS}, "2026-11-27T18:00:00Z", set())
    assert actions == []


def test_a_report_in_the_old_format_is_reissued_on_unchanged_tools(fb):
    live(fb, 100, old_v1(fb, TOOLS))
    actions, held, _ = fb.decide(scan(fb, [row(100)]), {"100": TOOLS}, "2026-11-05T10:00:00Z", set())
    assert [a[0] for a in actions] == ["revoke", "give"]
    assert "rescanned with @aimarket/warden" in actions[0][2]
    assert os.path.basename(actions[1][2]) == "warden-100-20261105.json"
    assert held == []


def test_same_release_and_same_tools_leave_the_feedback_alone(fb):
    first, _, _ = fb.decide(scan(fb, [row(100)]), {"100": TOOLS}, "2026-11-05T10:00:00Z", set())
    with open(fb.LOG, "a") as f:
        f.write(json.dumps({"agentId": 100, "kind": "give", "client": fb.FEEDBACK_WALLET, "status": "ok",
                            "uri": f"{fb.BASE_URL}/{os.path.basename(first[0][2])}"}) + "\n")
    again, _, _ = fb.decide(scan(fb, [row(100)]), {"100": TOOLS}, "2026-11-12T10:00:00Z", set())
    assert again == []


def test_a_blocking_finding_on_rescan_revokes_and_holds(fb):
    live(fb, 300, old_v1(fb, TOOLS))
    actions, held, _ = fb.decide(scan(fb, [row(300, wouldBlock=True)]), {"300": TOOLS},
                                 "2026-11-05T10:00:00Z", set())
    assert [(a[0], a[2]) for a in actions] == [("revoke", "a blocking finding appeared")]
    assert [r["agent_id"] for r in held] == [300]


def _give(aid):
    return ("give", row(aid), f"/tmp/warden-{aid}.json")


def _revoke_give(aid):
    return [("revoke", row(aid), "changed"), _give(aid)]


def test_take_tx_budget_keeps_pairs_and_defers_the_rest(fb):
    # 12 revoke+give pairs = 24 txs; cap 20 must keep 10 pairs (20) and defer 4.
    actions = []
    for aid in range(12):
        actions.extend(_revoke_give(aid))
    kept, deferred = fb.take_tx_budget(actions, 20)
    assert deferred == 4
    assert len(kept) == 20
    assert [a[0] for a in kept[18:20]] == ["revoke", "give"]
    assert kept[18][1]["agent_id"] == kept[19][1]["agent_id"] == 9


def test_take_tx_budget_does_not_split_a_trailing_pair(fb):
    # Cap 2 with a give then a revoke+give: keep the lone give; pair needs 2 and would exceed.
    actions = [_give(1), ("revoke", row(2), "x"), _give(2)]
    kept, deferred = fb.take_tx_budget(actions, 2)
    assert [a[0] for a in kept] == ["give"]
    assert deferred == 2


def test_take_tx_budget_under_cap_unchanged(fb):
    actions = [_give(1), _give(2)]
    kept, deferred = fb.take_tx_budget(actions, 20)
    assert kept == actions and deferred == 0



def test_a_second_report_on_the_same_day_gets_its_own_file(fb):
    """Given in the morning under the old tags, re-issued the same day: the morning file stays as served."""
    old = fb.report_for(row(400), TOOLS, scan(fb, []), "2026-11-26T10:00:00Z")
    old["tag1"], old["tag2"] = "warden-scan", f"ruleset-v{fb.RULESET_VERSION}"
    first = os.path.join(fb.OUT, "warden-400.json")
    morning = os.path.join(fb.OUT, "warden-400-20261126.json")
    for path in (first, morning):
        with open(path, "w") as f:
            json.dump(old, f)
    with open(fb.LOG, "a") as f:
        f.write(json.dumps({"agentId": 400, "kind": "give", "client": fb.FEEDBACK_WALLET, "status": "ok",
                            "uri": f"{fb.BASE_URL}/warden-400-20261126.json"}) + "\n")
    before = open(morning, "rb").read()
    actions, _, _ = fb.decide(scan(fb, [row(400)]), {"400": TOOLS}, "2026-11-26T18:00:00Z", set())
    assert [a[0] for a in actions] == ["revoke", "give"]
    assert os.path.basename(actions[1][2]) == "warden-400-20261126-2.json"
    assert open(morning, "rb").read() == before
    assert json.load(open(actions[1][2]))["tag1"] == "compliance"
    # A retry of the same run finds its own report and reuses it.
    again, _, _ = fb.decide(scan(fb, [row(400)]), {"400": TOOLS}, "2026-11-26T18:30:00Z", set())
    assert os.path.basename(again[1][2]) == "warden-400-20261126-2.json"


def test_a_new_release_alone_leaves_a_live_feedback_in_place(fb):
    """Same definitions, same score, given by an older release: nothing is sent, the re-check is recorded."""
    old = fb.report_for(row(500), TOOLS, scan(fb, []), "2026-11-20T10:00:00Z")
    old["scanner"]["package"] = "@aimarket/warden@0.20.0"
    live(fb, 500, old)
    s = scan(fb, [row(500)])
    actions, held, unreachable = fb.decide(s, {"500": TOOLS}, "2026-11-27T10:00:00Z", set())
    assert actions == [] and held == [] and unreachable == []
    assert fb.CONFIRMED == [{"agentId": 500, "report": f"{fb.BASE_URL}/warden-500.json", "value": 97,
                             "toolsSha256": old["result"]["toolsSha256"]}]
    doc = json.load(open(fb.write_confirmed(s, "2026-11-27T10:00:00Z")))
    assert doc["type"] == "aimarket.warden-scan-confirmations/v1" and doc["checkedAt"] == "2026-11-27T10:00:00Z"
    assert doc["scanner"]["package"] == f"@aimarket/warden@{fb.WARDEN_VERSION}"
    assert [e["agentId"] for e in doc["confirmed"]] == [500]


def test_a_new_release_that_changes_the_score_reissues(fb):
    old = fb.report_for(row(501), TOOLS, scan(fb, []), "2026-11-20T10:00:00Z")
    old["scanner"]["package"] = "@aimarket/warden@0.20.0"
    live(fb, 501, old)
    actions, _, _ = fb.decide(scan(fb, [row(501, score=90)]), {"501": TOOLS}, "2026-11-27T10:00:00Z", set())
    assert [a[0] for a in actions] == ["revoke", "give"]
    assert actions[0][2].startswith("score changed from 97 to 90 under @aimarket/warden")
    assert json.load(open(actions[1][2]))["value"] == 90
    assert fb.CONFIRMED == []


def test_the_installer_pins_the_release_the_script_names(fb):
    """install_refresh.sh installs the scanner; feedback.py refuses a scan made by any other release."""
    import re
    text = open(os.path.join(ERC, "install_refresh.sh")).read()
    assert re.search(r"^WARDEN_VERSION=(\S+)", text, re.M).group(1) == fb.WARDEN_VERSION
    assert fb.WARDEN_INTEGRITY.startswith("sha512-") and fb.RULESET_VERSION.isdigit()
