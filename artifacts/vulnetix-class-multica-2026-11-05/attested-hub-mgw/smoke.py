"""Inside the new image, no network: gateway rows show the hub's address, others are unchanged, file = context."""
import hashlib, os, sys
from types import SimpleNamespace
from aimarket_hub.hub_routes.catalog import published_invoke_url
HUB = "https://hub.attestedmemory.net"
VIA = HUB + "/ai-market/v2/invoke"
cap = lambda url, src="local": SimpleNamespace(invoke_url=url, source_hub=src)
cases = [
    (cap("http://memory-market:8810/capabilities/memory-write/memory.write@v1/invoke"), VIA),
    (cap("http://multica-provider:8090/capabilities/github-digest-order/github.digest.order@v1/invoke"), VIA),
    (cap("http://127.0.0.1:9000/x"), VIA),
    (cap("https://seller.example.com/invoke"), "https://seller.example.com/invoke"),
    (cap("", "https://peer.example"), VIA),
    (cap(""), None),
]
for c, want in cases:
    got = published_invoke_url(c, HUB + "/")
    assert got == want, (c, got, want)
got = hashlib.sha256(open("/app/aimarket_hub/hub_routes/catalog.py", "rb").read()).hexdigest()
assert got == sys.argv[1], (got, sys.argv[1])
print("smoke ok: 6 address cases, file = build context")
