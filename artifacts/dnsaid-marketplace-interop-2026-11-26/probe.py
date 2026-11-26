"""Reproduce DNS-AID catalogue lookup against a private .test DNS zone."""

import asyncio
import hashlib
import importlib.metadata
import json
import socketserver
import ssl
import struct
import threading
from contextlib import contextmanager
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen

import certifi
import dns.asyncresolver
import dns.dnssec
import dns.flags
import dns.message
import dns.name
import dns.query
import dns.rcode
import dns.rdata
import dns.rrset
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dns_aid.core.catalog_pointer import resolve_catalog_pointer_detail


ZONE = dns.name.from_text("modelmarket.test.")
TARGET = dns.name.from_text("modelmarket.dev.")
DRAFT_DOMAIN = "draft.modelmarket.test"
SDK_DOMAIN = "sdk.modelmarket.test"
CONTROL_DOMAIN = "control.modelmarket.test"
SUFFIX = b"agent-marketplace"
WELL_KNOWN_KEY = 65409  # Private-use value chosen by dns-aid 0.28.1.


def index_owner(domain):
    return dns.name.from_text(f"_index._agents.{domain}.")


def make_record(domain, value):
    alpn = struct.pack("!HH", 1, 3) + b"\x02h2"
    well_known = struct.pack("!HH", WELL_KNOWN_KEY, len(value)) + value
    rdata = struct.pack("!H", 1) + TARGET.to_wire() + alpn + well_known
    item = dns.rdata.from_wire("IN", "SVCB", rdata, 0, len(rdata))
    return dns.rrset.from_rdata(index_owner(domain), 60, item)


@contextmanager
def test_zone():
    signer = Ed25519PrivateKey.generate()
    dnskey = dns.dnssec.make_dnskey(signer.public_key(), "ED25519")
    trust_anchor = {ZONE: dns.rrset.from_rdata(ZONE, 60, dnskey)}
    records = (
        make_record(DRAFT_DOMAIN, struct.pack("!H", len(SUFFIX)) + SUFFIX),
        make_record(SDK_DOMAIN, SUFFIX),
    )
    answers = {}
    for record in records:
        signature = dns.dnssec.sign(record, signer, ZONE, dnskey, lifetime=600)
        answers[record.name] = (record, dns.rrset.from_rdata(record.name, 60, signature))

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            wire, listener = self.request
            query = dns.message.from_wire(wire)
            question = query.question[0]
            reply = dns.message.make_response(query)
            reply.flags |= dns.flags.AA
            print(f"DNS {question.name} {dns.rdatatype.to_text(question.rdtype)}", flush=True)
            if question.name in answers and question.rdtype == dns.rdatatype.SVCB:
                record, signature = answers[question.name]
                reply.answer.append(record)
                if query.ednsflags & dns.flags.DO:
                    reply.answer.append(signature)
            else:
                reply.set_rcode(dns.rcode.NXDOMAIN)
            listener.sendto(reply.to_wire(), self.client_address)

    with socketserver.UDPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address, trust_anchor
        finally:
            server.shutdown()
            thread.join()


def validated_record(domain, address, trust_anchor):
    query = dns.message.make_query(index_owner(domain), "SVCB", want_dnssec=True)
    reply = dns.query.udp(query, address[0], port=address[1], timeout=3)
    record, signature = reply.answer
    dns.dnssec.validate(record, signature, trust_anchor)
    print(f"Local DNSSEC validated: {record}")
    return record[0]


def draft_url(record):
    value = record.params[WELL_KNOWN_KEY].value
    length = struct.unpack_from("!H", value)[0]
    suffix = value[2:].decode("ascii")
    assert length == len(suffix) > 0  # This test advertises exactly one suffix.
    return f"https://{record.target.to_text(omit_final_dot=True)}/.well-known/{suffix}"


def get_json(url):
    parsed = urlsplit(url)
    assert parsed.scheme == "https" and parsed.hostname == TARGET.to_text(omit_final_dot=True)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(url, context=context, timeout=15) as response:
            data = response.read(2_000_000)
            assert response.geturl() == url
            payload = json.loads(data)
            print(f"HTTPS {response.status} {url} SHA256={hashlib.sha256(data).hexdigest()}")
            return payload
    except HTTPError as exc:
        print(f"HTTPS {exc.code} {url}")
        return {}


def fetch_marketplace(url):
    document = get_json(url)
    assert document["signature_profile"] == "ed25519-pipe-2"
    catalogue = get_json(document["catalogue_url"])
    assert catalogue["signature"]["public_key"] == document["signer_public_key"]
    assert catalogue["tools"]
    print(f"Marketplace manifest generated_at={catalogue['generated_at']}")


async def main():
    for name in ("dns-aid", "dnspython", "cryptography"):
        print(f"{name} {importlib.metadata.version(name)}")
    with test_zone() as (address, trust_anchor):
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = [address[0]]
        resolver.port = address[1]
        # Configure only the DNS resolver; leave SDK decoding and URL checks intact.
        with patch.object(dns.asyncresolver, "Resolver", return_value=resolver):
            control = await resolve_catalog_pointer_detail(CONTROL_DOMAIN)
            draft = await resolve_catalog_pointer_detail(DRAFT_DOMAIN)
            sdk = await resolve_catalog_pointer_detail(SDK_DOMAIN)
        assert control is None
        print("Control without SVCB: no pointer")
        assert draft and sdk
        assert draft.pointer_fqdn == index_owner(DRAFT_DOMAIN).to_text(omit_final_dot=True)
        assert sdk.pointer_fqdn == index_owner(SDK_DOMAIN).to_text(omit_final_dot=True)
        decoded_url = draft_url(validated_record(DRAFT_DOMAIN, address, trust_anchor))
        validated_record(SDK_DOMAIN, address, trust_anchor)

    print(f"SDK with draft encoding: {draft.url}")
    print(f"SDK with its own encoding: {sdk.url}")
    print(f"Draft-format diagnostic decoder: {decoded_url}")
    assert draft.url.endswith("/.well-known/ai-catalog.json")
    assert sdk.url == decoded_url
    fallback = get_json(draft.url)
    print(f"SDK default resource JSON fields: {', '.join(sorted(fallback))}")
    assert "catalogue_url" not in fallback
    fetch_marketplace(sdk.url)
    print("PASS: SDK-specific encoding and draft diagnostic reached the marketplace catalogue")


if __name__ == "__main__":
    asyncio.run(main())
