"""Edge vhosts send the browser security headers on every response.

nginx drops every inherited add_header in a location that declares one of its own, so
a server-level nosniff/X-Frame-Options/Referrer-Policy/HSTS silently vanished from any
path that also set Cache-Control or CORS. Each vhost below sets the headers at server
level and repeats them in every location that has add_header lines of its own; the
Metis catch-all on :80 no longer serves its key-taking API over cleartext.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ("Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy")

VHOSTS = [
    "deploy/nginx/atlas.modelmarket.dev.conf",
    "deploy/nginx/monitor.modelmarket.dev.conf",
    "deploy/nginx/monitor-uni.modelmarket.dev.conf",
    "deploy/nginx/verify.modelmarket.dev.conf",
    "deploy/nginx/edu.modelmarket.dev.conf",
    "deploy/nginx/modeldev.modelmarket.dev.conf",
    "deploy/nginx/pulse.modelmarket.dev.conf",
    "deploy/nginx/service-mesh.modelmarket.dev.conf",
    "deploy/nginx/oracles.modelmarket.dev.conf",
    "deploy/nginx/iot.modelmarket.dev.conf",
    "deploy/nginx/hunt.modelmarket.dev.conf",
    "deploy/nginx/use.modelmarket.dev.conf",
    "metis/deploy/nginx.conf",
]


def _blocks(text: str):
    """(kind, header, body-without-nested-blocks, nested) for each brace block."""
    text = re.sub(r"#[^\n]*", "", text)
    out, stack = [], []
    line_start = 0
    for i, c in enumerate(text):
        if c == "\n":
            line_start = i + 1
        elif c == "{":
            stack.append((text[line_start:i].strip(), i))
        elif c == "}":
            header, ob = stack.pop()
            out.append((header.split()[0] if header else "", header, ob, i, len(stack)))
    return text, out


def _own(text, ob, cb, inner):
    seg = text[ob + 1:cb]
    for _, _, iob, icb, _ in inner:
        if ob < iob and icb < cb:
            seg = seg.replace(text[iob:icb + 1], "{}")
    return seg


def _headers(seg: str) -> set[str]:
    return {h.lower() for h in re.findall(r"add_header\s+([A-Za-z-]+)", seg)}


@pytest.mark.parametrize("path", VHOSTS)
def test_locations_repeat_the_servers_security_headers(path):
    text, bl = _blocks((ROOT / path).read_text(encoding="utf-8"))
    servers = [b for b in bl if b[0] == "server"]
    locations = [b for b in bl if b[0] == "location"]
    checked = 0
    for _, _, ob, cb, _ in servers:
        own = _own(text, ob, cb, bl)
        if re.search(r"^\s*return\s+30[178]\b", own, re.M) and "location" not in text[ob:cb]:
            continue
        server_sec = {h.lower() for h in SECURITY} & _headers(own)
        if not server_sec:
            continue
        checked += 1
        for _, header, lob, lcb, _ in locations:
            if not (ob < lob and lcb < cb):
                continue
            loc = _headers(_own(text, lob, lcb, bl))
            if loc:
                missing = server_sec - loc
                assert not missing, f"{path}: `{header}` sets its own add_header and so drops {sorted(missing)}"
    assert checked, f"{path}: no server block sends the security headers"


@pytest.mark.parametrize("path", VHOSTS)
def test_every_content_server_sends_nosniff_and_referrer_policy(path):
    text, bl = _blocks((ROOT / path).read_text(encoding="utf-8"))
    for _, header, ob, cb, _ in [b for b in bl if b[0] == "server"]:
        body = text[ob:cb]
        own = _own(text, ob, cb, bl)
        if not re.search(r"\b(proxy_pass|root|try_files|alias)\b", body):
            continue  # redirect-only
        if re.search(r"location\s+/\s*\{\s*return\s+30[178]", body):
            continue
        got = _headers(own)
        assert {"x-content-type-options", "referrer-policy"} <= got, f"{path}: a server block lacks them: {sorted(got)}"


def test_metis_serves_no_api_over_cleartext():
    text, bl = _blocks((ROOT / "metis" / "deploy" / "nginx.conf").read_text(encoding="utf-8"))
    for _, header, ob, cb, _ in [b for b in bl if b[0] == "server"]:
        body = text[ob:cb]
        if re.search(r"listen\s+80\b", body) and not re.search(r"listen\s+[^;]*443", body):
            assert "proxy_pass" not in body, "a :80 server block proxies to an API over cleartext HTTP"
