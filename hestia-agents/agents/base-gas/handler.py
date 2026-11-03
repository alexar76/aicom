"""Base gas price, read live from the chain's public RPC through the hearth (hestia.egress).

The sandbox has no sockets: fetch() asks the hearth, which talks only to mainnet.base.org,
the one host this agent's deploy names. Two reads, two fetch rounds.
"""


def _rpc(method, params=None):
    r = fetch("https://mainnet.base.org", method="POST",  # noqa: F821 — the sandbox provides fetch()
              json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []})
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
        "source": "https://mainnet.base.org (eth_gasPrice, eth_blockNumber)",
    }
