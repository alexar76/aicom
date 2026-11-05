"""WARDEN's ERC-8004 feedback (deploy/erc-8004/feedback.py): reports carry the fields EIP-8004
requires of a feedback file, and a new WARDEN release re-issues every live feedback."""

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
    assert rep["tag1"] == "warden-scan" and rep["tag2"] == f"ruleset-v{fb.RULESET_VERSION}"
    assert rep["endpoint"] == "https://a42.example/mcp"
    assert rep["scanner"]["package"] == f"@aimarket/warden@{fb.WARDEN_VERSION}"


def test_calldata_tags_the_current_ruleset(fb):
    data = fb.calldata(42, 97, "https://a42.example/mcp", "https://x/r.json", b"\0" * 32)
    assert f"ruleset-v{fb.RULESET_VERSION}".encode().hex() in data
    assert b"ruleset-v8".hex() not in data


def test_a_new_release_reissues_a_live_feedback_on_unchanged_tools(fb):
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
