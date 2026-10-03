#!/usr/bin/env python3
"""Refuse a UNI hub that came up without the fixes its publication needed.

On 2026-09-16 a stale copy of the deploy script was re-run on the host and the bubble hub
came back healthy — and wrong in six ways, for eight days: it advertised 127.0.0.1, its
admin token was the constant printed in docs/uni-realm.md, auto-crawl was off, the seed
list and the seed pins were gone, and AIMARKET_SELLS_FOR was empty. A 200 from /health says
none of that. This does, and it runs after every start: `deploy/uni-hub.sh` calls it, and a
hand recreate should too.

    python3 deploy/uni-hub-verify.py                     # container modelmarket-hub-uni
    python3 deploy/uni-hub-verify.py --container NAME --hub-url https://uni.modelmarket.dev

Reads the container's environment through `docker inspect` and prints only which rule
passed — never a value. Exit 1 if any rule fails. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

# Same list as scripts/ecosystem_alert.py PUBLISHED_ADMIN_TOKENS: tokens printed in this
# repository, which therefore open nothing.
PUBLISHED_ADMIN_TOKENS = (
    "uni-admin-token-not-a-secret-in-a-bubble",
    "platon-ecosystem-admin",
    "ci-compose-admin-token-not-a-secret",
    "replace-with-at-least-32-random-bytes",
    "replace-with-a-random-64-hex-secret",
)


def container_env(name: str) -> dict[str, str]:
    out = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, check=True)
    env = json.loads(out.stdout)[0]["Config"]["Env"]
    return dict(e.split("=", 1) for e in env if "=" in e)


def rules(env: dict[str, str], hub_url: str) -> list[tuple[str, bool]]:
    """(rule, holds) — pure, so the tests can feed it an environment."""
    base = hub_url.rstrip("/")
    seeds = [s.strip() for s in env.get("AIMARKET_SEED_LIST", "").split(",") if s.strip()]
    sells = [s.strip() for s in env.get("AIMARKET_SELLS_FOR", "").split(",") if s.strip()]
    try:
        pins = json.loads(env.get("AIMARKET_SEED_PUBKEYS") or "{}")
    except ValueError:
        pins = {}
    token = env.get("AIMARKET_ADMIN_TOKEN", "")
    return [
        ("advertises its public name (AIMARKET_HUB_URL)",
         env.get("AIMARKET_HUB_URL", "").rstrip("/") == base and base.startswith("https://")),
        ("admin token is set, long, and not one printed in the repository",
         len(token) >= 32 and token not in PUBLISHED_ADMIN_TOKENS),
        ("auto-crawl is on", env.get("AIMARKET_AUTO_CRAWL", "1").strip().lower()
         not in ("0", "false", "no")),
        ("seed list names the bubble's own satellites, and only them",
         bool(seeds) and all(s.startswith(f"{base}/sat/") for s in seeds)),
        ("every seed carries a pinned key",
         isinstance(pins, dict) and bool(seeds) and all(pins.get(s) for s in seeds)),
        ("sells on behalf of its satellites (AIMARKET_SELLS_FOR)",
         bool(sells) and all(s.startswith(f"{base}/sat/") for s in sells)),
        ("realm is sealed as uni", env.get("AIMARKET_CHAIN_REALM") == "uni"),
    ]


def _rpc_code(rpc: str, address: str, timeout: float = 5.0) -> str:
    """Bytecode at `address` on `rpc` ("0x" when none). Raises when the chain does not answer."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode",
                       "params": [address, "latest"]}).encode()
    req = urllib.request.Request(rpc, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return str(json.load(r).get("result") or "0x")


def chain_rules(env: dict[str, str], get_code=_rpc_code) -> list[tuple[str, bool]]:
    """The money side, checked against the chains themselves.

    On 2026-10-01 the bubble moved hosts without its Anvil: the hub was pointed at the
    alien-monitor demo chain (8545) and at a token and escrow deployed there, which the
    monitor's next chain reset erased. Every rule above still held, the hub answered 200, and
    every deposit failed for two days. `get_code` is injectable for the tests.
    """
    settle = env.get("AIMARKET_RPC_BASE", "").rstrip("/")
    demo = env.get("ALIEN_EVM_RPC", "").rstrip("/")

    def has_code(rpc: str, address: str) -> bool:
        if not rpc or not address:
            return False
        try:
            return len(get_code(rpc, address)) > 2
        except Exception:
            return False

    token = env.get("AIMARKET_ADDR_BASE_USDC", "")
    escrows = {env.get(k, "").lower() for k in (
        "AIMARKET_ADDR_BASE_AIMARKETESCROW", "AIMARKET_ESCROW_CONTRACT", "AIMARKET_ESCROW_EVM_ADDRESS")}
    paid_to = {env.get(k, "").lower() for k in (
        "AIMARKET_PAYMENT_RECIPIENT", "AIMARKET_X402_PAY_TO", "AIMARKET_ESCROW_HUB_ADDRESS")}
    out = [
        ("settles on the bubble's own chain, not the alien-monitor demo chain",
         bool(settle) and settle != demo),
        ("one token for deposits and x402 (AIMARKET_ADDR_BASE_USDC = AIMARKET_X402_ASSET)",
         bool(token) and token.lower() == env.get("AIMARKET_X402_ASSET", "").lower()),
        ("the settlement token exists on the settlement chain", has_code(settle, token)),
        ("one escrow address everywhere, and it exists on the settlement chain",
         len(escrows) == 1 and has_code(settle, next(iter(escrows)))),
        ("paid at the hub's own wallet everywhere (recipient = x402 payTo = escrow hub)",
         len(paid_to) == 1 and "" not in paid_to),
    ]
    lottery = env.get("AIMARKET_CHARITY_LOTTERY_ADDRESS", "")
    if lottery:
        out.append(("the charity lottery exists on the demo chain (it moves when that chain resets)",
                    has_code(demo, lottery)))
    return out


def live_rules(hub_url: str, timeout: float = 10.0) -> list[tuple[str, bool]]:
    """What the world sees through the vhost — the environment can be right and the proxy
    wrong."""
    base = hub_url.rstrip("/")
    out: list[tuple[str, bool]] = []
    try:
        with urllib.request.urlopen(f"{base}/.well-known/ai-market.json", timeout=timeout) as r:
            doc = json.load(r)
        out.append(("public well-known points at the public name",
                    str(doc.get("manifest_url") or "").startswith(base)))
    except Exception:
        out.append(("public well-known points at the public name", False))
    # A credit to an account that does not exist, with an amount that is not a number: the
    # hub checks the token first (403), and an accepted token still dies on the amount.
    refused = True
    for token in PUBLISHED_ADMIN_TOKENS:
        req = urllib.request.Request(
            f"{base}/ai-market/v2/accounts/acct_0000000000000000/credit",
            data=json.dumps({"amount_usd": "probe-not-a-number"}).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        try:
            urllib.request.urlopen(req, timeout=timeout)
            refused = False
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403):
                refused = False
        except Exception:
            pass
    out.append(("operator door refuses every published token", refused))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--container", default="modelmarket-hub-uni")
    parser.add_argument("--hub-url", default="https://uni.modelmarket.dev")
    parser.add_argument("--no-live", action="store_true", help="skip the public-side checks")
    parser.add_argument("--no-chain", action="store_true",
                        help="skip the on-chain checks (they need the docker bridge, i.e. the host)")
    args = parser.parse_args(argv)
    try:
        env = container_env(args.container)
    except Exception as exc:
        print(f"FAIL cannot inspect {args.container}: {type(exc).__name__}")
        return 1
    checked = (rules(env, args.hub_url) + ([] if args.no_chain else chain_rules(env))
               + ([] if args.no_live else live_rules(args.hub_url)))
    for rule, holds in checked:
        print(f"{'ok  ' if holds else 'FAIL'} {rule}")
    failed = [r for r, holds in checked if not holds]
    if failed:
        print(f"UNI hub {args.container} is NOT as published: {len(failed)} rule(s) failed. "
              f"Recreate it from deploy/uni-hub.sh, not from a copy on the host.")
        return 1
    print(f"UNI hub {args.container}: all {len(checked)} rules hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
