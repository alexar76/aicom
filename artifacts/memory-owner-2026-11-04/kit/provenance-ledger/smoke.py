"""Provenance-ledger smoke inside the new image: the attestation actor is the hub's buyer ref or aimarket:anonymous."""
from fastapi import Request
from provenance_ledger.app import _aimarket_actor


def req(h):
    return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in h.items()]})


ref = "bref-" + "c" * 32
assert _aimarket_actor(req({"X-AIMarket-Buyer-Ref": ref})) == "aimarket:" + ref
assert _aimarket_actor(req({"X-Payment-Channel": ""})) == "aimarket:anonymous"
print("provenance-ledger smoke ok")
