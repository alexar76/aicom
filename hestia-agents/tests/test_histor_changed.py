"""histor.changed_since@v1 against answers HISTOR really gave on 2026-11-20.

`histor_changed_vectors.json`: HISTOR's signed /check for https://modelmarket.dev/mcp and its current
set (unchanged), and for https://socialloop.ai/mcp with the set it served four changes earlier
(previously observed), with that server's change list and token cost history. The server rotates a
UUID default in one schema every half hour, which is exactly the kind of change an approval misses.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hestia_agents.manifests import deploy_body, handler_source

V = json.loads((Path(__file__).parent / "histor_changed_vectors.json").read_text(encoding="utf-8"))


class Reply:
    def __init__(self, body, status=200):
        self.status, self.error, self.headers, self.text = status, None, {}, json.dumps(body)

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.text)


def load(check, v=V):
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        asked.append((method, url))
        path = url.split("histor.modelmarket.dev", 1)[1]
        if path.startswith("/api/v1/check"):
            return Reply(check)
        if path.endswith("/cost?limit=50"):
            return Reply(v["cost"])
        if path.startswith("/api/v1/changes?watch="):
            return Reply({"changes": v["detail"].get("changes") or []})
        if path.startswith("/api/v1/servers/"):
            return Reply(v["detail"])
        return Reply({}, 404)

    namespace = {"fetch": fetch}
    exec(compile(handler_source("histor-changed"), "histor-changed", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked


def test_an_unchanged_server_says_since_when() -> None:
    handle, asked = load(V["hub_check"])
    out = handle(
        {
            "endpoint": "https://modelmarket.dev/mcp",
            "approved_digest": V["hub_check"]["query"]["toolSetDigest"],
        }
    )
    assert (
        out["verdict"] == "unchanged"
        and out["unchanged_since"] == V["hub_check"]["observed"]["unchangedSince"]
    )
    assert out["histor_check"]["signature"]["value"] and len(asked) == 1


def test_a_server_that_moved_lists_every_change_since_your_set() -> None:
    handle, asked = load(V["prev_check"])
    out = handle({"endpoint": "https://socialloop.ai/mcp", "approved_digest": V["approved"]})
    assert out["verdict"] == "changed" and out["complete"] is True, out
    assert out["changes_since"] == 4 and len(out["changes"]) == 4
    assert out["changes"][-1]["from"] == V["approved"]  # the move away from your set
    assert out["changes"][0]["to"] == out["current_digest"]
    assert out["changed_at"] == out["changes"][-1]["observed_at"]
    assert "create_event_draft" in out["tools"]["modified"]
    tokens = out["tokens"]
    assert (
        tokens["tokenizer"] == "o200k_base"
        and tokens["delta"] == tokens["now"] - tokens["approved"]
    )
    assert tokens["delta"] == sum(c["tokens_delta"] for c in out["changes"])  # each step adds up
    assert len(asked) == 3


def test_a_set_histor_never_saw_and_an_unread_server() -> None:
    never = copy.deepcopy(V["prev_check"])
    never["match"] = "different"
    handle, asked = load(never)
    out = handle({"endpoint": "https://socialloop.ai/mcp", "approved_digest": V["approved"]})
    assert out["verdict"] == "approved_set_never_observed" and len(asked) == 1
    unread = copy.deepcopy(V["prev_check"])
    unread["match"] = "not-listed"
    unread["target"] = {}
    handle, _ = load(unread)
    assert (
        handle({"endpoint": "https://x.example.org/mcp", "approved_digest": V["approved"]})[
            "verdict"
        ]
        == "not_recorded"
    )


def test_a_set_older_than_the_listed_changes_is_marked_incomplete() -> None:
    old_set = "sha256-" + "B" * 43 + "="
    check = copy.deepcopy(V["prev_check"])
    check["query"]["toolSetDigest"] = old_set  # HISTOR's answer names the set it was asked about
    handle, _ = load(check)
    out = handle({"endpoint": "https://socialloop.ai/mcp", "approved_digest": old_set})
    assert (
        out["verdict"] == "changed" and out["complete"] is False and "older than" in out["detail"]
    )
    assert out["tokens"]["approved"] is None


def test_input_is_checked() -> None:
    handle, asked = load(V["hub_check"])
    for payload in (
        {},
        {"endpoint": "https://x/mcp"},
        {"endpoint": "https://x/mcp", "approved_digest": "x"},
    ):
        with pytest.raises(ValueError):
            handle(payload)
    handle({"endpoint": "https://modelmarket.dev/mcp", "approved_tools": [{"name": "a"}]})
    assert asked[-1][0] == "POST"


def test_the_manifest_reaches_histor_only() -> None:
    assert deploy_body("histor-changed")["egress_hosts"] == ["histor.modelmarket.dev"]
