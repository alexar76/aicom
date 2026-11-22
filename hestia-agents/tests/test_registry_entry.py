"""registry.entry.verify@v1 against seven registry entries as they stood on 2026-11-21.

`registry_entry_vectors.json` holds every reply the agent's hosts gave on 2026-11-21 (recorded with
scripts/record_fetches.py, the hearth's limits applied): the official MCP registry, npm, PyPI,
nuget.org, dns.google, and the /.well-known/mcp-registry-auth files of the domains named. The
negative cases change one recorded reply, so each test shows the one fact that turns a verdict.
The ownership rules are the registry's own (internal/validators/registries/mcpname.go, npm.go,
pypi.go, nuget.go and internal/api/handlers/v0/auth at main on 2026-11-21).
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import json
from pathlib import Path

import pytest
from replay import load, text_of, with_json

from hestia_agents.manifests import AGENTS, deploy_body

V = json.loads((Path(__file__).parent / "registry_entry_vectors.json").read_text(encoding="utf-8"))
SLUG = "registry-entry"


def run(case, tamper=None, payload=None):
    handle, asked, ns = load(SLUG, V[case]["fetched"], tamper)
    return handle(payload or V[case]["payload"]), asked, ns


def test_an_npm_package_whose_mcpname_names_the_server_verifies() -> None:
    out, asked, _ = run("warden")
    assert out["verdict"] == "verified" and out["problems"] == [] and out["warnings"] == []
    (npm,) = out["packages"]
    assert npm["identifier"] == "@aimarket/warden" and npm["version"] == "0.35.0"
    assert [(c["check"], c["ok"]) for c in npm["checks"]] == [
        ("published", True),
        ("mcpName", True),
    ]
    assert (
        npm["repository"] == "github.com/alexar76/warden"
        and npm["repository_owner_matches"] is True
    )
    # The registry's own URL form: url.PathEscape keeps @ and escapes the scope's slash.
    assert asked == [
        "https://registry.modelcontextprotocol.io/v0.1/servers/io.github.alexar76%2Fwarden/versions/0.35.0",
        "https://registry.npmjs.org/@aimarket%2Fwarden/0.35.0",
    ]
    assert out["namespace"] == {
        "kind": "github",
        "owner": "alexar76",
        "repository": "https://github.com/alexar76/warden",
        "repository_owner_matches": True,
    }


def test_a_domain_namespace_with_its_key_in_dns_verifies_and_a_redirect_is_not_followed() -> None:
    out, _, _ = run("notion")
    assert out["verdict"] == "verified"
    ns = out["namespace"]
    assert ns["publishes_registry_key"] is True
    (lookup,) = ns["dns"]
    assert lookup["domain"] == "notion.com" and lookup["dnssec_validated"] is True
    assert [k["record"] for k in lookup["keys"] if k["valid"]] == [
        "v=MCPv1; k=ed25519; p=wv6IKlrIuEu00zHS//f5iBxZtZGb+UYuqaRlrg3CEY4="
    ]
    assert ns["http"]["status"] == 302 and "does not follow" in ns["http"]["note"]
    assert all(r["on_namespace_domain"] for r in out["remotes"])


def test_npm_pypi_and_nuget_pass_oci_and_mcpb_are_named_as_not_checked() -> None:
    out, asked, _ = run("microsoft_esrp")
    assert out["verdict"] == "verified_partly" and out["problems"] == []
    by_type = {p["registry_type"]: p for p in out["packages"]}
    for kind, marker in (("npm", "mcpName"), ("pypi", "mcp-name"), ("nuget", "mcp-name")):
        assert [(c["check"], c["ok"]) for c in by_type[kind]["checks"]] == [
            ("published", True),
            (marker, True),
        ], kind
    assert by_type["oci"]["checked"] is False and "config" in by_type["oci"]["reason"]
    assert by_type["mcpb"]["checked"] is False
    assert len(out["not_checked"]) == 2
    # The subdomain's own TXT set holds a valid key, so the parent is not asked.
    assert [d["domain"] for d in out["namespace"]["dns"]] == ["esrp.microsoft.com"]
    assert len(asked) == 5


def test_a_deprecated_entry_is_a_warning_not_a_mismatch() -> None:
    out, _, _ = run("csoai_pypi")
    assert out["registry"]["status"] == "deprecated"
    assert out["verdict"] == "verified"
    assert out["warnings"] == ["the registry marks this version deprecated"]


def test_a_well_known_page_that_is_html_holds_no_key_but_dns_does() -> None:
    out, _, _ = run("mcparmory")
    ns = out["namespace"]
    assert (
        ns["http"]["status"] == 200
        and ns["http"]["keys"] == []
        and "no MCPv1" in ns["http"]["note"]
    )
    assert ns["publishes_registry_key"] is True and out["verdict"] == "verified_partly"


def test_an_unknown_name_is_not_found_after_one_request() -> None:
    out, asked, _ = run("missing")
    assert out["verdict"] == "not_found" and out["found"] is False and len(asked) == 1
    assert "404" in out["detail"]


def test_a_remote_only_domain_server_rests_on_its_dns_key() -> None:
    out, _, _ = run("stripe")
    assert out["verdict"] == "verified" and out["packages"] == []
    assert out["namespace"]["publishes_registry_key"] is True


# ------------------------------------------------------------------ one changed fact each


def test_a_package_json_naming_another_server_is_a_mismatch() -> None:
    def tamper(url, raw):
        if "registry.npmjs.org" in url:
            doc = text_of(raw)
            doc["mcpName"] = "io.github.someone-else/warden"
            return with_json(raw, doc)
        return raw

    out, _, _ = run("warden", tamper)
    assert out["verdict"] == "mismatch"
    assert out["problems"] == [
        'npm @aimarket/warden: package.json mcpName is "io.github.someone-else/warden", not io.github.alexar76/warden'
    ]


def test_a_missing_npm_version_is_a_mismatch() -> None:
    def tamper(url, raw):
        return (
            {"status": 404, "headers": {}, "text": '{"error":"not found"}'}
            if "npmjs" in url
            else raw
        )

    out, _, _ = run("warden", tamper)
    assert out["verdict"] == "mismatch" and "HTTP 404" in out["problems"][0]


def test_a_package_repository_under_another_owner_is_a_warning() -> None:
    def tamper(url, raw):
        if "registry.npmjs.org" in url:
            doc = text_of(raw)
            doc["repository"] = {
                "type": "git",
                "url": "git+https://github.com/elsewhere/warden.git",
            }
            return with_json(raw, doc)
        return raw

    out, _, _ = run("warden", tamper)
    assert out["verdict"] == "verified"
    assert out["warnings"] == [
        "npm @aimarket/warden: package.json repository is github.com/elsewhere/warden, not under the namespace owner alexar76"
    ]


def test_a_readme_token_glued_to_a_full_stop_fails_as_at_the_registry() -> None:
    name = "io.github.CSOAI-ORG/meok-stripe-acp-checkout-mcp"

    def tamper(url, raw):
        if "pypi.org" in url:
            doc = text_of(raw)
            doc["info"]["description"] = "Install it. mcp-name: " + name + ".\n"
            return with_json(raw, doc)
        return raw

    out, _, _ = run("csoai_pypi", tamper)
    assert out["verdict"] == "mismatch"
    assert 'glued to "."' in out["problems"][0]


def test_a_yanked_release_is_a_warning() -> None:
    def tamper(url, raw):
        if "pypi.org" in url:
            doc = text_of(raw)
            doc["info"].update(yanked=True, yanked_reason="broken build")
            return with_json(raw, doc)
        return raw

    out, _, _ = run("csoai_pypi", tamper)
    assert out["verdict"] == "verified"
    assert "pypi meok-stripe-acp-checkout-mcp: yanked on PyPI: broken build" in out["warnings"]


def test_no_key_in_dns_without_domain_is_unchecked_and_with_an_empty_well_known_is_a_mismatch() -> (
    None
):
    def no_key(url, raw):
        if "dns.google" in url:
            doc = text_of(raw)
            doc["Answer"] = [a for a in doc.get("Answer", []) if "MCPv1" not in a["data"]]
            return with_json(raw, doc)
        return raw

    # Stripe's subdomain-free name: one lookup, no key, HTTP not asked.
    out, _, _ = run("stripe", no_key)
    assert (
        out["verdict"] == "verified_partly" and out["namespace"]["publishes_registry_key"] is False
    )
    assert "give domain" in out["not_checked"][0]
    # Notion with its domain named: DNS empty and the well-known a redirect, so nothing authorizes it.
    out, _, _ = run("notion", no_key)
    assert out["verdict"] == "mismatch"
    assert "does not authorize registry publishing now" in out["problems"][0]


def test_a_subdomain_falls_back_to_its_parent_in_dns() -> None:
    parent = json.dumps(
        [
            "GET",
            "https://dns.google/resolve?name=microsoft.com&type=TXT",
            [["accept", "application/dns-json"]],
            None,
        ],
        separators=(",", ":"),
    )
    extra = {
        parent: {
            "status": 200,
            "headers": {},
            "text": json.dumps(
                {
                    "Status": 0,
                    "AD": False,
                    "Answer": [
                        {
                            "type": 16,
                            "data": "v=MCPv1; k=ed25519; p=wv6IKlrIuEu00zHS//f5iBxZtZGb+UYuqaRlrg3CEY4=",
                        }
                    ],
                }
            ),
        }
    }

    def no_key(url, raw):
        if "esrp.microsoft.com" in url:
            doc = text_of(raw)
            doc["Answer"] = []
            return with_json(raw, doc)
        return raw

    handle, asked, _ = load(SLUG, V["microsoft_esrp"]["fetched"], no_key, extra)
    out = handle(V["microsoft_esrp"]["payload"])
    assert [d["domain"] for d in out["namespace"]["dns"]] == ["esrp.microsoft.com", "microsoft.com"]
    assert out["namespace"]["publishes_registry_key"] is True and len(asked) == 6


def test_the_six_request_budget_leaves_the_rest_unchecked_not_failed() -> None:
    def many(url, raw):
        if "/v0.1/servers/" in url:
            doc = text_of(raw)
            doc["server"]["packages"] = [dict(doc["server"]["packages"][0]) for _ in range(7)]
            return with_json(raw, doc)
        return raw

    out, asked, _ = run("warden", many)
    assert len(asked) == 6
    assert out["verdict"] == "verified_partly" and out["problems"] == []
    assert sum(1 for p in out["packages"] if p["checked"]) == 5
    assert all("six requests" in reason for reason in out["not_checked"])


# ------------------------------------------------------------------ the registry's own rules


@pytest.mark.parametrize(
    "content, found, glued",
    [
        ("mcp-name: a.b/c", True, None),
        ("<!-- mcp-name: a.b/c -->", True, None),
        ("<!-- mcp-name: a.b/c-->", True, None),
        ("mcp-name: a.b/c<br>", True, None),
        ("mcp-name: a.b/c\n", True, None),
        ("mcp-name: a.b/c.", False, "."),
        ("mcp-name: a.b/c-extra", False, "-"),
        ("mcp-name: a.b/c-extra mcp-name: a.b/c ok", True, None),
        ("mcp-name:  a.b/c", False, None),
        ("MCP-NAME: a.b/c", False, None),
    ],
)
def test_mcp_name_token_follows_mcpname_go(content, found, glued) -> None:
    _, _, ns = load(SLUG, {})
    assert ns["mcp_name_token"](content, "a.b/c") == (found, glued)


def test_proof_keys_parse_like_parsepublickey() -> None:
    _, _, ns = load(SLUG, {})
    keys = ns["proof_keys"]
    good = keys("v=MCPv1; k=ed25519; p=wv6IKlrIuEu00zHS//f5iBxZtZGb+UYuqaRlrg3CEY4=")
    assert [k["valid"] for k in good] == [True]
    # Two records in one string both count (key rotation).
    two = keys(
        "v=MCPv1; k=ed25519; p=wv6IKlrIuEu00zHS//f5iBxZtZGb+UYuqaRlrg3CEY4=\nv=MCPv1; k=ed25519; p=AAAA"
    )
    assert [k["valid"] for k in two] == [True, False] and "32 bytes" in two[1]["problem"]
    # A real compressed P-384 key from microsoft.com's apex, and the same key with x moved off the curve.
    p384 = "Asc8WWov6gsmCCzn4CSrwRuJIh5SqvaitKz/LlTW+SD54lLC52wzcnWhlTI416p2vw=="
    assert keys("v=MCPv1; k=ecdsap384; p=" + p384)[0]["valid"] is True
    import base64

    p, b = ns["P384"], ns["P384_B"]
    raw = bytearray(base64.b64decode(p384))
    x = int.from_bytes(raw[1:], "big")
    # The next x whose x^3 - 3x + b is a non-residue mod p (Euler's criterion, computed here, not
    # by the handler): no y exists, so no point.
    while pow((x**3 - 3 * x + b) % p, (p - 1) // 2, p) != p - 1:
        x += 1
    raw[1:] = x.to_bytes(48, "big")
    off = keys("v=MCPv1; k=ecdsap384; p=" + base64.b64encode(bytes(raw)).decode())[0]
    assert off["valid"] is False and "not a point" in off["problem"]
    assert keys("v=MCPv1; k=rsa; p=AAAA")[0]["problem"] == "k must be ed25519 or ecdsap384"
    assert keys("v=MCPv2; k=ed25519; p=wv6IKlrIuEu00zHS//f5iBxZtZGb+UYuqaRlrg3CEY4=") == []


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "registry server name"),
        ({"name": "warden"}, "registry server name"),
        ({"name": "io.github/warden"}, "io.github.<owner>"),
        ({"name": "com.notion/mcp", "domain": "evil.example"}, "exact domain"),
        ({"name": "com.notion/mcp", "domain": "mcp.notion.com"}, "exact domain"),
        ({"name": "io.github.a/b", "version": "1/2"}, "version"),
        ("io.github.a/b", "send an object"),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_names_its_hosts_and_the_domain_field_and_is_free() -> None:
    meta = AGENTS[SLUG]
    assert meta["capability_id"] == "registry.entry.verify@v1" and meta["price_per_call_usd"] == 0
    body = deploy_body(SLUG)
    assert body["egress_hosts"] == [
        "registry.modelcontextprotocol.io",
        "registry.npmjs.org",
        "pypi.org",
        "api.nuget.org",
        "dns.google",
    ]
    assert body["egress_input_fields"] == ["domain"]
    assert meta["sandbox_only"] is True
