"""Retest dns-aid's catalogue pointer with the well-known SvcParam (key65409) in both wire formats.

dns-aid/dns-aid-core#317 (reported by Ingmar Van Glabbeek from the IETF 127 DAWN lab finding of 2026-11-26) and
the fix in #318. A loopback DNS server answers `_index._agents.<case>.modelmarket.test` SVCB queries; every case
points at modelmarket.dev, whose discovery document is at the non-default path /.well-known/agent-marketplace.
dns-aid's own resolver is only redirected to that server; its decoding, validation and URL checks run unmodified.

    python -I -B retest.py        # prints one line per case and PASS/FAIL against the behaviour #318 describes
"""

import asyncio
import importlib.metadata
import json
import socketserver
import ssl
import struct
import sys
import threading
from contextlib import contextmanager
from unittest.mock import patch
from urllib.request import urlopen

import certifi
import dns.asyncresolver
import dns.flags
import dns.message
import dns.name
import dns.rcode
import dns.rdata
import dns.rdatatype
import dns.rrset
from structlog.testing import capture_logs

from dns_aid.core.catalog_pointer import resolve_catalog_pointer_detail

TARGET = dns.name.from_text("modelmarket.dev.")
KEY = 65409  # dns-aid's private-use well-known key
MARKET = b"agent-marketplace"


def wk01(*suffixes: bytes) -> bytes:
    """draft-mk-dnsop-svcb-well-known-01 section 2.1: each entry a 2-octet length, then the suffix."""
    return b"".join(struct.pack("!H", len(s)) + s for s in suffixes)


def rdata(priority: int, value: bytes):
    alpn = struct.pack("!HH", 1, 3) + b"\x02h2"
    well_known = struct.pack("!HH", KEY, len(value)) + value
    wire = struct.pack("!H", priority) + TARGET.to_wire() + alpn + well_known
    return dns.rdata.from_wire("IN", "SVCB", wire, 0, len(wire))


# case: (records as (priority, value), expected URL suffix after #318 or None for "no pointer", expect a warning)
CASES = {
    "control": ([], None, False),
    "wk01": ([(1, wk01(MARKET))], "agent-marketplace", False),
    "plain": ([(1, MARKET)], "agent-marketplace", False),
    "wk01-two": ([(1, wk01(b"../escape", MARKET))], "agent-marketplace", False),
    "malformed": ([(1, b"\x00\x40" + MARKET)], None, True),          # prefix says 64 octets, 17 follow
    # A good record beside a malformed one is still used. The warning shows only when the malformed record is
    # examined first, which depends on the order of the answer (see the priority check below).
    "malformed-and-good": ([(1, b"\x00\x40" + MARKET), (2, wk01(MARKET))], "agent-marketplace", None),
}

# RFC 9460: a client prefers the record with the lower SvcPriority. Two valid records, different paths.
PRIORITY_CASE = "priority"
PRIORITY_RECORDS = [(1, wk01(MARKET)), (2, wk01(b"ai-catalog.json"))]


def owner(case: str) -> dns.name.Name:
    return dns.name.from_text(f"_index._agents.{case}.modelmarket.test.")


@contextmanager
def zone():
    answers = {}
    for case, (records, _, _) in [*CASES.items(), (PRIORITY_CASE, (PRIORITY_RECORDS, None, None))]:
        if records:
            answers[owner(case)] = dns.rrset.from_rdata_list(owner(case), 60, [rdata(p, v) for p, v in records])

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            wire, sock = self.request
            query = dns.message.from_wire(wire)
            q = query.question[0]
            reply = dns.message.make_response(query)
            reply.flags |= dns.flags.AA
            if q.name in answers and q.rdtype == dns.rdatatype.SVCB:
                reply.answer.append(answers[q.name])
            else:
                reply.set_rcode(dns.rcode.NXDOMAIN)
            sock.sendto(reply.to_wire(), self.client_address)

    with socketserver.UDPServer(("127.0.0.1", 0), Handler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield server.server_address
        finally:
            server.shutdown()


def discovery_ok(url: str) -> str:
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urlopen(url, context=ctx, timeout=20) as resp:
        doc = json.loads(resp.read(2_000_000))
    with urlopen(doc["catalogue_url"], context=ctx, timeout=60) as resp:
        catalogue = json.loads(resp.read(5_000_000))
    ok = doc.get("signature_profile") == "ed25519-pipe-2" and catalogue["signature"]["public_key"] == doc["signer_public_key"]
    return f"discovery document + catalogue ({len(catalogue['tools'])} tools, same signer)" if ok else "UNEXPECTED DOCUMENT"


async def main() -> int:
    print("dns-aid", importlib.metadata.version("dns-aid"), "| dnspython", importlib.metadata.version("dnspython"))
    failures = 0
    with zone() as (host, port):
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers, resolver.port = [host], port
        with patch.object(dns.asyncresolver, "Resolver", return_value=resolver):
            for case, (_, expected, expect_warning) in CASES.items():
                with capture_logs() as logs:
                    res = await resolve_catalog_pointer_detail(f"{case}.modelmarket.test")
                url = res.url if res else None
                warned = [e for e in logs if e.get("event") == "catalog_pointer.well_known_malformed"]
                want = f"https://modelmarket.dev/.well-known/{expected}" if expected else None
                ok = url == want and (expect_warning is None or bool(warned) == expect_warning)
                failures += not ok
                print(f"{'PASS' if ok else 'FAIL'} {case:19} url={url} warning={'yes' if warned else 'no'}"
                      + ("" if ok else f"   (expected url={want}, warning={'yes' if expect_warning else 'no'})"))
            picks = []
            with capture_logs():  # keep the twenty "resolved" lines out of the output
                for _ in range(20):
                    res = await resolve_catalog_pointer_detail(f"{PRIORITY_CASE}.modelmarket.test")
                    picks.append(res.url.rsplit("/", 1)[1] if res else None)
            lower = picks.count("agent-marketplace")
            print(f"INFO priority: 20 lookups of priority 1 ({MARKET.decode()}) and priority 2 (ai-catalog.json): "
                  f"priority 1 used {lower} times, priority 2 {picks.count('ai-catalog.json')} times")
    print("fetch:", discovery_ok("https://modelmarket.dev/.well-known/agent-marketplace"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
