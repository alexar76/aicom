"""site.agent_policy@v1: RFC 9309 as HISTOR's crawler applies it, plus Content-Signal and llms.txt.

`site_policy_vectors.json` holds what six sites served on 2026-11-21 (scripts/record_fetches.py; the
llms.txt bodies cut to their first 4 KiB, all the agent reads): modelmarket.dev, nytimes.com (its
robots.txt redirects to www), www.nytimes.com, www.cloudflare.com (a Content-Signal line that sits
in the Cohere-ai group), developers.cloudflare.com (the line in the * group) and github.com. The rules
themselves are tested on small files, several from RFC 9309's own text.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import json
from pathlib import Path

import pytest
from replay import load

from hestia_agents.manifests import AGENTS, deploy_body

V = json.loads((Path(__file__).parent / "site_policy_vectors.json").read_text(encoding="utf-8"))
SLUG = "site-policy"


def key(url):
    return json.dumps(["GET", url, [["accept", "text/plain"]], None], separators=(",", ":"))


def site(robots, status=200, llms=(404, ""), host="example.com", extra=None):
    fetched = {
        key("https://" + host + "/robots.txt"): {
            "status": status,
            "headers": {"date": "Sat, 21 Nov 2026 21:00:00 GMT"},
            "text": robots,
        },
        key("https://" + host + "/llms.txt"): {"status": llms[0], "headers": {}, "text": llms[1]},
    }
    fetched.update(extra or {})
    return fetched


def run(payload, fetched):
    handle, asked, ns = load(SLUG, fetched)
    return handle(payload), asked, ns


def verdicts(out):
    return {row["agent"]: row["allowed"] for row in out["agents"]}


def test_recorded_sites() -> None:
    out, asked, _ = run({"url": "www.nytimes.com"}, V["www.nytimes.com"]["fetched"])
    assert (
        out["verdict"] == "ok"
        and "GPTBot" in out["disallowed"]
        and "ClaudeBot" in out["disallowed"]
    )
    assert len(asked) == 2
    out, _, _ = run({"url": "nytimes.com"}, V["nytimes.com"]["fetched"])
    assert out["verdict"] == "redirected_elsewhere" and out["next"] == {"url": "www.nytimes.com"}
    assert all(row["allowed"] is None for row in out["agents"])
    out, _, _ = run({"url": "www.cloudflare.com"}, V["www.cloudflare.com"]["fetched"])
    assert out["signal_lines"] == [
        {"line": "Content-Signal: ai-train=yes, search=yes, ai-input=yes", "group": ["Cohere-ai"]}
    ]
    assert not any(
        row.get("content_signal") for row in out["agents"]
    )  # no default agent is Cohere-ai
    out, _, _ = run({"url": "developers.cloudflare.com"}, V["developers.cloudflare.com"]["fetched"])
    star = next(r for r in out["agents"] if r["agent"] == "*")
    assert star["content_signal"] == {"ai-train": True, "search": True, "ai-input": True}
    out, _, _ = run({"url": "modelmarket.dev"}, V["modelmarket.dev"]["fetched"])
    assert out["disallowed"] == [] and out["llms_txt"]["present"] is True
    out, _, _ = run({"url": "github.com"}, V["github.com"]["fetched"])
    assert out["disallowed"] == ["Bytespider"]


def test_the_longest_match_decides_and_allow_wins_a_tie() -> None:
    robots = "User-agent: *\nAllow: /example/page/\nDisallow: /example/page/disallowed.gif\nAllow: /x\nDisallow: /x\n"
    for path, allowed in (
        ("/example/page/", True),
        ("/example/page/disallowed.gif", False),
        ("/x", True),
        ("/robots.txt", True),
    ):
        out, _, _ = run({"url": "example.com", "path": path, "agents": ["*"]}, site(robots))
        assert verdicts(out)["*"] is allowed, path


@pytest.mark.parametrize(
    "rule, path, allowed",
    [
        ("Disallow: /*.php$", "/index.php", False),
        ("Disallow: /*.php$", "/index.php?x=1", True),
        ("Disallow: /fish*", "/fishheads/yummy.html", False),
        ("Disallow: /fish", "/Fish.asp", True),  # paths are case-sensitive
        (
            "Disallow: /foo/bar%3Cbaz",
            "/foo/bar<baz",
            False,
        ),  # percent-encoding normalised on both sides
        ("Disallow: /ümlaut", "/%C3%BCmlaut", False),
    ],
)
def test_rfc_9309_patterns(rule, path, allowed) -> None:
    out, _, _ = run(
        {"url": "example.com", "path": path, "agents": ["*"]}, site("User-agent: *\n" + rule + "\n")
    )
    assert verdicts(out)["*"] is allowed


def test_group_selection_is_by_product_token() -> None:
    robots = (
        "User-agent: *\nDisallow: /\n\nUser-agent: gptbot\nUser-agent: ClaudeBot\nAllow: /\n\n"
        "User-agent: GPTBot\nDisallow: /private\n"
    )
    out, _, _ = run(
        {"url": "example.com", "path": "/private/x", "agents": ["GPTBot", "ClaudeBot", "CCBot"]},
        site(robots),
    )
    assert verdicts(out) == {"GPTBot": False, "ClaudeBot": True, "CCBot": False}
    rows = {r["agent"]: r for r in out["agents"]}
    assert rows["GPTBot"]["group"] == "GPTBot" and rows["CCBot"]["group"] == "*"
    out, _, _ = run(
        {"url": "example.com", "agents": ["GPTBot"]}, site("User-agent: GPTBot/1.1\nDisallow: /\n")
    )
    assert verdicts(out) == {"GPTBot": False}


def test_unavailable_allows_everything_and_unreachable_disallows_everything() -> None:
    out, _, _ = run({"url": "example.com", "agents": ["*"]}, site("", status=404))
    assert out["verdict"] == "unavailable" and verdicts(out) == {"*": True}
    out, _, _ = run({"url": "example.com", "agents": ["*"]}, site("", status=503))
    assert out["verdict"] == "unreachable" and verdicts(out) == {"*": False}


def test_a_same_host_redirect_is_followed() -> None:
    fetched = site("User-agent: *\nDisallow: /\n", extra={})
    fetched[key("https://example.com/robots.txt")] = {
        "status": 301,
        "headers": {"location": "/robots-new.txt"},
        "text": "",
    }
    fetched[key("https://example.com/robots-new.txt")] = {
        "status": 200,
        "headers": {},
        "text": "User-agent: *\nDisallow: /\n",
    }
    out, asked, _ = run({"url": "example.com", "agents": ["*"]}, fetched)
    assert out["redirects"] == ["https://example.com/robots-new.txt"] and verdicts(out) == {
        "*": False
    }
    assert asked[:2] == ["https://example.com/robots.txt", "https://example.com/robots-new.txt"]


def test_an_html_page_at_llms_txt_is_not_an_llms_txt() -> None:
    out, _, _ = run(
        {"url": "example.com", "agents": ["*"]}, site("", llms=(200, "<!doctype html><html>..."))
    )
    assert out["llms_txt"] == {"status": 200, "present": False}
    out, _, _ = run(
        {"url": "example.com", "agents": ["*"]},
        site("", llms=(200, "# Example\n\n> An example site\n")),
    )
    assert out["llms_txt"]["title"] == "Example"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "domain"),
        ({"url": "http://example.com"}, "https"),
        ({"url": "https://example.com:8443/"}, "port 443"),
        ({"url": "example.com", "path": "x"}, "start with /"),
        ({"url": "example.com", "agents": ["bad agent"]}, "product tokens"),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_reaches_only_the_named_host() -> None:
    body = deploy_body(SLUG)
    assert "egress_hosts" not in body and body["egress_input_fields"] == ["url"]
    assert AGENTS[SLUG]["capability_id"] == "site.agent_policy@v1"
