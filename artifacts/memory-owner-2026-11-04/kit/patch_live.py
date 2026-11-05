#!/usr/bin/env python3
"""patch_live.py {hub-invoke|memory-market} IN OUT

Ports the 2026-11-04 buyer-owner fix onto a LIVE file copied out of a running container
(the live hub runs the pre-split hub_routes/invoke.py; the live memory-market is older than
main). The new text is the same as on main. Refuses unless every anchor appears exactly once.
"""
import sys

HUB = [
    (
        "from aimarket_hub import credits, invoke_funding, provider_request_auth, settle, verified_settlement, x402\n",
        "from aimarket_hub import credits, invoke_funding, provider_buyer_ref, provider_request_auth, settle, verified_settlement, x402\n",
    ),
    (
        '''        if capability_token and target_host in set(invoke_gateway_hosts()):
            provider_headers["X-AIMarket-Internal-Token"] = capability_token
''',
        '''        if capability_token and target_host in set(invoke_gateway_hosts()):
            provider_headers["X-AIMarket-Internal-Token"] = capability_token
            # Who the buyer is, as one stable pseudonym the operator's own provider can key
            # the buyer's data by (Attested Memory owners). Same gate as the token, so a
            # third-party seller never gets it; left out for anonymous and trial calls.
            buyer_ref = provider_buyer_ref.buyer_ref(d.signer, call, local)
            if buyer_ref:
                provider_headers[provider_buyer_ref.HEADER] = buyer_ref
''',
    ),
]

MEMORY_MARKET = [
    (
        '''def _aimarket_actor(request: Request) -> str:
    channel = request.headers.get("x-payment-channel", "anonymous")
    return "aimarket:" + hashlib.sha256(channel.encode()).hexdigest()[:20]
''',
        '''_BUYER_REF = re.compile(r"bref-[0-9a-f]{32}")
_NEEDS_BUYER = (
    "this capability needs a buyer the hub can name: call it with an X-API-Key credit "
    "account (or a verified payment); trial and anonymous calls can read public memories only"
)


def _aimarket_actor(request: Request) -> str | None:
    """The buyer the hub vouches for on this invoke, or None for an anonymous caller.

    The hub sends `X-AIMarket-Buyer-Ref` (aimarket_hub/provider_buyer_ref.py) only to its
    operator's own providers, next to the internal token this route already requires, and
    only when it authenticated the buyer: a credit account, a verified x402 payer or a held
    payment channel. The owner used to be a hash of `X-Payment-Channel`, which was empty for
    every buyer on credits, x402 or a trial — all of them one shared owner, reading each
    other's private memories — and keyed per hub process for channel buyers, so it changed
    on every hub restart. None now means: public memories only, no writes.
    """
    ref = (request.headers.get("x-aimarket-buyer-ref") or "").strip()
    if not _BUYER_REF.fullmatch(ref):
        return None
    return "aimarket:" + ref
''',
    ),
    (
        '''    actor = _aimarket_actor(request)
    try:
        if capability_id == "memory.write@v1":
''',
        '''    actor = _aimarket_actor(request)
    if actor is None and capability_id not in ("memory.read@v1", "memory.search@v1"):
        raise HTTPException(status_code=403, detail=_NEEDS_BUYER)
    try:
        if capability_id == "memory.write@v1":
''',
    ),
]


def main() -> None:
    kind, src, dst = sys.argv[1:4]
    pairs = {"hub-invoke": HUB, "memory-market": MEMORY_MARKET}[kind]
    text = open(src, encoding="utf-8").read()
    for old, new in pairs:
        n = text.count(old)
        if n != 1:
            sys.exit(f"{kind}: anchor found {n} times, expected 1 — stop:\n{old[:120]}")
        text = text.replace(old, new)
    if kind == "memory-market" and "\nimport re\n" not in text:
        sys.exit("memory-market: live app.py does not import re — stop")
    open(dst, "w", encoding="utf-8").write(text)
    print(f"{kind}: {len(pairs)} anchors patched -> {dst}")


if __name__ == "__main__":
    main()
