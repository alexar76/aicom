"""Base gas price, read live from the chain's public RPC through the hearth (hestia.egress).

The sandbox has no sockets: fetch() asks the hearth, which answers from its pool of free Base RPCs
(base-rpc.hestia.modelmarket.dev), or, on a hearth without one, reads mainnet.base.org. Two reads,
two fetch rounds.
"""


# The hearth's pool of free Base RPCs (hestia.rpc_pool) is tried first for Base mainnet. A hearth
# without it refuses that name, and the agent then reads the public RPC for the rest of the call.
POOL = "https://base-rpc.hestia.modelmarket.dev"
_POOL_FOR = {"https://mainnet.base.org"}
_no_pool = []


def _post(url, body):
    if url in _POOL_FOR and not _no_pool:
        try:
            reply = fetch(POOL, method="POST", json=body)  # noqa: F821 — the sandbox provides fetch()
        except Exception:  # noqa: BLE001 — the hearth refused the name: no pool on this hearth
            reply = None
        if reply is not None and reply.status not in (0, 429) and reply.status < 500:
            return reply
        _no_pool.append(True)
    return fetch(url, method="POST", json=body)  # noqa: F821


def _rpc(method, params=None):
    r = _post("https://mainnet.base.org",
              {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []})
    if not r.ok:
        raise RuntimeError(f"base rpc answered {r.status}")
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"base rpc error: {str(body['error'])[:120]}")
    return body["result"]


def handle(payload):
    gas_wei = int(_rpc("eth_gasPrice"), 16)
    block = int(_rpc("eth_blockNumber"), 16)
    return {
        "chain": "eip155:8453",
        "block": block,
        "gas_price_wei": gas_wei,
        "gas_price_gwei": round(gas_wei / 1e9, 9),
        "source": ("https://mainnet.base.org" if _no_pool else POOL)
        + " (eth_gasPrice, eth_blockNumber)",
    }
