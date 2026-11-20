"""aid.record.read@v1: the specification's examples, its refusals, and real resolver answers.

The DNS answers below are what cloudflare-dns.com and dns.google returned on 2026-11-19 for
_agent.modelmarket.dev, a name that does not exist, and a name with no TXT (bodies trimmed of
RRSIG and NSEC rows where a test does not need them). The last test runs the handler through
the hearth's own guest code, round by round, the way the WebAssembly runner does.
"""
# ruff: noqa: E501 — recorded headers and DNS answers are kept on one line

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from hestia_agents.manifests import AGENTS, handler_source

RECORD = ("v=aid2;u=https://modelmarket.dev/mcp;p=mcp;a=none;s=AIMarket hub: search and call agent tools;"
          "k=H_pv7n0l5b3o5SgCFPaAhm-K1flFG-Dim16mHmclqaM")
CLOUDFLARE = {"Status": 0, "TC": False, "RD": True, "RA": True, "AD": False, "CD": False,
              "Question": [{"name": "_agent.modelmarket.dev", "type": 16}],
              "Answer": [{"name": "_agent.modelmarket.dev", "type": 16, "TTL": 600, "data": '"' + RECORD + '"'},
                         {"name": "_agent.modelmarket.dev", "type": 46, "TTL": 600,
                          "data": "TXT 13 3 600 1796256000 1794441600 31010 modelmarket.dev. g9PAzbpb"}]}
GOOGLE = {"Status": 0, "TC": False, "RD": True, "RA": True, "AD": False, "CD": False,
          "Question": [{"name": "_agent.modelmarket.dev.", "type": 16}],
          "Answer": [{"name": "_agent.modelmarket.dev.", "type": 46, "TTL": 600,
                      "data": "txt 13 3 600 1796256000 1794441600 31010 modelmarket.dev. YKBFoVez"},
                     {"name": "_agent.modelmarket.dev.", "type": 16, "TTL": 600, "data": RECORD}],
          "Comment": "Response from 85.193.93.93."}
NXDOMAIN = {"Status": 3, "AD": False, "Question": [{"name": "_agent.nope.modelmarket.dev", "type": 16}],
            "Authority": [{"name": "modelmarket.dev", "type": 6, "TTL": 300, "data": "ns1.timeweb.ru. ..."}]}
NODATA = {"Status": 0, "AD": True, "Question": [{"name": "_agent.agentcommunity.org", "type": 16}],
          "Authority": [{"name": "agentcommunity.org", "type": 6, "TTL": 1800, "data": "suzanne.ns.cloudflare.com. ..."}]}
DATE = "Thu, 19 Nov 2026 20:32:39 GMT"


class Reply:
    def __init__(self, body=None, status=200, error=None, date=DATE):
        self.status, self.error = status, error
        self.text = json.dumps(body) if body is not None else ""
        self.headers = {"date": date} if date else {}

    @property
    def ok(self):
        return 200 <= self.status < 300


def load(replies=None):
    """The handler with a fetch() that answers from `replies`, keyed by resolver host."""
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002 — the guest's signature
        asked.append((url, dict(headers or {})))
        reply = replies[url.split("/")[2]]
        if isinstance(reply, Exception):
            raise reply
        return reply

    namespace: dict = {"fetch": fetch}
    exec(compile(handler_source("aid-record"), "aid-record", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked, namespace


def validate(*txt, at=None):
    handle, _, _ = load()
    return handle({"txt": list(txt), "at": at} if at else {"txt": list(txt)})


# ------------------------------------------------------------- the specification's records


@pytest.mark.parametrize(("txt", "proto"), [
    ("v=aid2;u=https://api.example.com/mcp;p=mcp;a=pat;s=Example AI Tools", "mcp"),
    ("v=aid2;p=mcp;u=https://api.example.com/mcp;k=JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs;"
     "a=oauth2_code;s=Secure AI Gateway", "mcp"),
    ("v=aid2;p=websocket;u=wss://agent.example.com/session;a=oauth2_code;s=Streaming Agent", "websocket"),
    ("v=aid2;u=docker:grafana/mcp:latest;p=local;a=pat;s=Run Grafana agent locally", "local"),
    (" V = aid2 ; U = https://api.example.com/mcp ; P = mcp ;; ", "mcp"),
])
def test_the_examples_of_section_2_2_are_valid(txt, proto) -> None:
    out = validate(txt)
    assert out["valid"] is True and out["code"] == 0 and out["record"]["proto"] == proto
    assert out["record"]["v"] == "aid2" and out["mode"] == "validate"


def test_a_record_with_k_names_the_keyid_a_proof_must_carry() -> None:
    out = validate(RECORD)
    assert out["pka"]["k"] == "H_pv7n0l5b3o5SgCFPaAhm-K1flFG-Dim16mHmclqaM"
    assert out["pka"]["keyid"] == "GPgQ1hgsCNYND5UeXKXx970ljHR9Tlg4dR1oMK-p9aA"  # what the live hub signs with
    assert out["record"] == {"v": "aid2", "uri": "https://modelmarket.dev/mcp", "proto": "mcp", "auth": "none",
                             "desc": "AIMarket hub: search and call agent tools",
                             "pka": "H_pv7n0l5b3o5SgCFPaAhm-K1flFG-Dim16mHmclqaM"}
    assert out["warnings"] == []


@pytest.mark.parametrize(("txt", "code", "why"), [
    ("u=https://a.example/mcp;p=mcp", 1001, "no v"),
    ("v=aid3;u=https://a.example/mcp;p=mcp", 1001, "aid3"),
    ("v=aid2;p=mcp", 1001, "no u"),
    ("v=aid2;u=https://a.example/mcp", 1001, "no p"),
    ("v=aid2;u=https://a.example/mcp;uri=https://b.example/mcp;p=mcp", 1001, "alias"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;p=a2a", 1001, "twice"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;broken", 1001, "key=value"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;a=", 1001, "empty"),
    ("v=aid2;u=https://a.example/mcp;p=telnet", 1002, "registry"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;a=magic", 1001, "auth"),
    ("v=aid2;u=http://a.example/mcp;p=mcp", 1001, "https://"),
    ("v=aid2;u=https://;p=mcp", 1001, "https://"),
    ("v=aid2;u=https://a.example/ws;p=websocket", 1001, "wss://"),
    ("v=aid2;u=bash:rm;p=local", 1001, "docker"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;s=" + "é" * 31, 1001, "62 UTF-8 bytes"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;d=http://docs.example", 1001, "docs"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;e=2027-01-01", 1001, "ISO 8601"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;k=JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs;i=g1", 1001, "kid"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;k=z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK", 1001, "32 bytes"),
    ("v=aid2;u=https://a.example/mcp;p=mcp;k=JrQLj5P/89iXES9+vFgrIy29clF9CC_oPPsw3c5D0bs", 1001, "base64url"),
    ("v=aid1;u=https://a.example/mcp;p=mcp;k=zABC", 1001, "kid"),
])
def test_what_the_specification_refuses(txt, code, why) -> None:
    out = validate(txt)
    assert out["valid"] is False and out["code"] == code, out
    assert out["error"] == {1001: "ERR_INVALID_TXT", 1002: "ERR_UNSUPPORTED_PROTO"}[code]
    assert why in out["other_records"][0]["problem"]


def test_selection_follows_section_2_3() -> None:
    aid2 = "v=aid2;u=https://a.example/mcp;p=mcp;a=none"
    aid1 = "v=aid1;u=https://old.example/mcp;p=mcp;a=none"
    out = validate(aid1, aid2)  # aid2 wins whatever the answer order
    assert out["record"]["uri"] == "https://a.example/mcp" and out["other_records"][0]["version"] == "aid1"
    out = validate("google-site-verification=abc", aid2, "v=aid2;broken")  # junk does not matter
    assert out["valid"] is True and len(out["other_records"]) == 2
    out = validate(aid2, "v=aid2;u=https://b.example/mcp;p=a2a")  # two valid: never by order
    assert out["valid"] is False and out["code"] == 1001 and "ambiguous" in out["detail"]
    out = validate(aid1)  # legacy only
    assert out["valid"] is True and "pka" not in out and any("legacy" in w for w in out["warnings"])


def test_warnings_tell_a_publisher_what_to_fix() -> None:
    out = validate("version=aid2;uri=https://a.example/mcp;proto=mcp;desc=" + "x" * 60 + ";docs=https://docs.example/"
                   + "y" * 200)
    text = " ".join(out["warnings"])
    assert out["valid"] is True
    assert "bytes" in text and "long key version, uri, proto, desc, docs" in text and "no a (auth)" in text
    assert "no k" in text
    spare = validate("v=aid2;u=https://a.example/mcp;p=mcp;a=none;k=JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bt")
    assert spare["valid"] is True and any("spare bits" in w for w in spare["warnings"])


def test_deprecation_is_judged_only_against_a_given_time() -> None:
    txt = "v=aid2;u=https://a.example/mcp;p=mcp;a=none;e=2027-01-01T00:00:00Z"
    assert "deprecated" not in validate(txt)
    assert validate(txt, at="2027-01-01T00:00:00Z")["deprecated"] is True
    later = validate(txt, at="2026-11-19T20:00:00Z")
    assert "deprecated" not in later and any("will be deprecated" in w for w in later["warnings"])


# ------------------------------------------------------------- lookups


def test_a_lookup_asks_both_resolvers_for_the_exact_name() -> None:
    handle, asked, _ = load({"cloudflare-dns.com": Reply(CLOUDFLARE), "dns.google": Reply(GOOGLE)})
    out = handle({"domain": "ModelMarket.dev."})
    assert [url for url, _ in asked] == [
        "https://cloudflare-dns.com/dns-query?name=_agent.modelmarket.dev&type=TXT&do=1",
        "https://dns.google/resolve?name=_agent.modelmarket.dev&type=TXT&do=1"]
    assert all(headers == {"accept": "application/dns-json"} for _, headers in asked)
    assert out["valid"] is True and out["txt"] == RECORD and out["query"] == "_agent.modelmarket.dev"
    assert out["observed_at"] == "2026-11-19T20:32:39Z" and out["mode"] == "lookup"
    assert out["dns"]["resolvers_agree"] is True and out["dns"]["dnssec_validated"] is False
    assert [r["txt"] for r in out["dns"]["resolvers"]] == [[RECORD], [RECORD]]  # quoted and unquoted forms
    assert out["dns"]["resolvers"][0]["ttl"] == 600
    assert any("DNSSEC" in w for w in out["warnings"])


def test_no_record_and_no_such_name_are_error_1000() -> None:
    for body in (NXDOMAIN, NODATA):
        handle, _, _ = load({"cloudflare-dns.com": Reply(body), "dns.google": Reply(body)})
        out = handle({"domain": "agentcommunity.org"})
        assert out["found"] is False and out["code"] == 1000 and out["error"] == "ERR_NO_RECORD"
        assert ".well-known" in out["detail"]


def test_one_resolver_down_still_answers_and_both_down_is_1004() -> None:
    down = Reply(status=0, error="ConnectTimeout: could not reach cloudflare-dns.com")
    handle, _, _ = load({"cloudflare-dns.com": down, "dns.google": Reply(GOOGLE)})
    out = handle({"domain": "modelmarket.dev"})
    assert out["valid"] is True and "resolvers_agree" not in out["dns"]
    assert out["dns"]["resolvers"][0] == {"resolver": "cloudflare", "ok": False, "problem": down.error}
    servfail = Reply({"Status": 2})
    handle, _, _ = load({"cloudflare-dns.com": RuntimeError("egress refused: budget is spent"),
                         "dns.google": servfail})
    out = handle({"domain": "modelmarket.dev"})
    assert out["code"] == 1004 and out["error"] == "ERR_DNS_LOOKUP_FAILED" and out["valid"] is False
    assert "SERVFAIL" in out["dns"]["resolvers"][1]["problem"]


def test_resolvers_that_disagree_are_reported() -> None:
    stale = json.loads(json.dumps(GOOGLE))
    stale["Answer"][1]["data"] = RECORD.split(";k=")[0]  # the record as it was before k was added
    handle, _, _ = load({"cloudflare-dns.com": Reply(CLOUDFLARE), "dns.google": Reply(stale)})
    out = handle({"domain": "modelmarket.dev"})
    assert out["dns"]["resolvers_agree"] is False and out["valid"] is True and "pka" in out
    assert any("different records" in w for w in out["warnings"])


def test_split_strings_escapes_cname_and_dnssec() -> None:
    half = len(RECORD) // 2
    body = {"Status": 0, "AD": True, "Answer": [
        {"name": "_agent.app.example.com", "type": 5, "TTL": 300, "data": "_agent.shared.example.com."},
        {"name": "_agent.shared.example.com", "type": 16, "TTL": 120,
         "data": '"' + RECORD[:half] + '" "' + RECORD[half:] + '"'}]}
    handle, _, namespace = load({"cloudflare-dns.com": Reply(body), "dns.google": Reply(body)})
    out = handle({"domain": "app.example.com"})
    assert out["valid"] is True and out["txt"] == RECORD  # joined in order
    assert out["dns"]["dnssec_validated"] is True and not any("DNSSEC" in w for w in out["warnings"])
    assert out["dns"]["resolvers"][0]["cname"] == ["_agent.shared.example.com"]
    strings = namespace["character_strings"]
    assert strings('"a\\"b\\\\c" "\\195\\169"') == 'a"b\\cé'
    assert strings("plain; text") == "plain; text"


@pytest.mark.parametrize("domain", ["https://example.com", "example.com/mcp", "example.com:443", "localhost",
                                    "пример.рф", "a..example.com", "-a.example.com", ""])
def test_a_domain_must_be_a_bare_host(domain) -> None:
    handle, asked, _ = load({})
    with pytest.raises(ValueError):
        handle({"domain": domain})
    assert asked == []


def test_bad_input_is_refused() -> None:
    handle, _, _ = load({})
    for payload in ({}, {"txt": []}, {"txt": [1]}, {"txt": "v=aid2", "at": "yesterday"}, []):
        with pytest.raises(ValueError):
            handle(payload)


# ------------------------------------------------------------- through the hearth's guest


def test_the_lookup_runs_round_by_round_in_the_real_guest() -> None:
    """The handler under the hearth's guest (hestia.sandbox.GUEST) in a subprocess: each fetch
    ends a run, the test plays the hearth and answers it, as hestia.runtime.wasm does."""
    sandbox = pytest.importorskip("hestia.sandbox")
    egress = pytest.importorskip("hestia.egress")
    allowed = AGENTS["aid-record"]["egress_hosts"]
    bodies = {"cloudflare-dns.com": CLOUDFLARE, "dns.google": GOOGLE}
    fetched, rounds = {}, 0
    while True:
        request = {"source": handler_source("aid-record"), "payload": {"domain": "modelmarket.dev"},
                   "fetched": fetched}
        run = subprocess.run([sys.executable, "-I", "-c", sandbox.GUEST], input=json.dumps(request),
                             capture_output=True, text=True, timeout=30, check=True)
        answer = json.loads(run.stdout.split("\x1e", 1)[1])
        if answer.get("kind") != "fetch":
            break
        rounds += 1
        assert rounds <= egress.MAX_ROUNDS
        checked = egress.EgressRequest.parse(answer["request"], allowed)  # the hearth's own gate
        assert checked.headers == {"accept": "application/dns-json"}
        fetched[egress.request_key(answer["request"])] = {
            "status": 200, "headers": {"date": DATE, "content-type": "application/dns-json"},
            "text": json.dumps(bodies[checked.host])}
    assert rounds == 2 and answer["ok"] is True
    result = answer["result"]
    assert result["valid"] is True and result["pka"]["keyid"] == "GPgQ1hgsCNYND5UeXKXx970ljHR9Tlg4dR1oMK-p9aA"
    assert result["dns"]["resolvers_agree"] is True
