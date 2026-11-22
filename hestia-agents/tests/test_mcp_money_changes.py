"""mcp.money_tools.changes@v1: questions answered from HISTOR's money-tool feed.

`mcp_money_changes_vectors.json` holds the feed histor/money_changes.py built on 2026-11-22 from HISTOR's
public change feed (changes up to id 177 765): 26 changes, 20 medium and 6 low, served as the reply to
https://histor.modelmarket.dev/datasets/feeds/money-tool-changes.json. The high-severity case adds one
made-up item to it.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from replay import load

from hestia_agents.manifests import deploy_body

V = json.loads(
    (Path(__file__).parent / "mcp_money_changes_vectors.json").read_text(encoding="utf-8")
)
SLUG = "mcp-money-changes"
CASE = V["feed_2026_11_22"]
RAW = next(iter(CASE["fetched"].values()))
FEED = json.loads(RAW["text"])


def run(payload, change=None):
    fetched = copy.deepcopy(CASE["fetched"])
    if change is not None:
        raw = next(iter(fetched.values()))
        doc = json.loads(raw["text"])
        change(doc)
        raw["text"] = json.dumps(doc)
    handle, asked, _ = load(SLUG, fetched)
    return handle(payload), asked


def test_everything_in_the_feed_newest_first_in_one_request() -> None:
    out, asked = run({"limit": 100})
    assert asked == ["https://histor.modelmarket.dev/datasets/feeds/money-tool-changes.json"]
    assert out["matched"] == 26 and out["counts"] == {"high": 0, "medium": 20, "low": 6}
    ids = [i["change_id"] for i in out["items"]]
    assert ids == sorted(ids, reverse=True) and not out["truncated"]
    assert out["cursor"] == FEED["cursor"] == 177765
    assert out["feed"]["sha256"] == hashlib.sha256(RAW["text"].encode()).hexdigest()
    assert out["feed"]["rules"] == "money-tools/v1" and out["feed"]["window_days"] == 7


def test_a_server_filter_finds_its_changes() -> None:
    out, _ = run({"server": "swaptitan"})
    assert out["matched"] == 2
    assert {t["tool"] for i in out["items"] for t in i["tools"]} == {"create_wallet"}
    out, _ = run({"server": ["onv.codes"]})
    assert out["matched"] == 2
    assert {tuple(i["flags"]) for i in out["items"]} == {
        ("added_moves_value",),
        ("removed_moves_value",),
    }


def test_severity_flags_and_limit() -> None:
    medium, _ = run({"min_severity": "medium", "limit": 3})
    assert medium["matched"] == 20 and len(medium["items"]) == 3 and medium["truncated"]
    keys, _ = run({"flags": "mentions_keys"})
    assert keys["matched"] == 3 and all(
        "added_text" in t for i in keys["items"] for t in i["tools"]
    )
    high, _ = run({"min_severity": "high"})
    assert high["matched"] == 0 and high["items"] == []


def test_since_a_change_id_or_a_time() -> None:
    newest = max(i["change_id"] for i in FEED["items"])
    assert run({"since": newest})[0]["matched"] == 0
    assert run({"since": str(newest - 1)})[0]["matched"] == 1
    late = sorted(i["observed_at"] for i in FEED["items"])[-3]
    assert run({"since": late})[0]["matched"] == 2
    assert run({"since": "2026-11-21"})[0]["matched"] == 26


def test_an_address_swap_is_high() -> None:
    def add(doc):
        doc["items"].insert(
            0,
            {
                "change_id": 999999,
                "observed_at": "2026-11-22T16:00:00Z",
                "target_id": "x",
                "name": "io.example/pay",
                "page": "https://histor.modelmarket.dev/s/x",
                "flags": ["address_replaced"],
                "severity": "high",
                "tools": [
                    {
                        "tool": "pay_merchant",
                        "change": "modified",
                        "kind": "moves_value",
                        "new_addresses": ["0x" + "2" * 40],
                        "removed_addresses": ["0x" + "1" * 40],
                    }
                ],
            },
        )

    out, _ = run({"min_severity": "high"}, change=add)
    assert out["matched"] == 1 and out["items"][0]["tools"][0]["new_addresses"] == ["0x" + "2" * 40]


def test_a_feed_of_another_schema_is_refused() -> None:
    def other(doc):
        doc["schema"] = "something/else"

    with pytest.raises(RuntimeError, match="histor.money-tool-changes/v1"):
        run({}, change=other)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "send an object"),
        ({"since": "yesterday"}, "since is an ISO time"),
        ({"since": True}, "since is an ISO time"),
        ({"min_severity": "urgent"}, "min_severity is low, medium or high"),
        ({"limit": 0}, "limit must be a whole number from 1 to 100"),
        ({"limit": 101}, "limit must be"),
        ({"server": 5}, "server must be a string"),
        ({"flags": [""]}, "flags must be a string"),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_reaches_histor_only_and_is_priced() -> None:
    body = deploy_body(SLUG)
    assert body["egress_hosts"] == ["histor.modelmarket.dev"]
    assert body["capability"]["price_per_call_usd"] == 0.002
    assert body["capability"]["capability_id"] == "mcp.money_tools.changes@v1"
