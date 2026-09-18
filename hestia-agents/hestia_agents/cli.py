"""Build the deploy manifests, or deploy them onto a hearth.

    python -m hestia_agents.cli build
    python -m hestia_agents.cli deploy --hearth http://127.0.0.1:9480
    python -m hestia_agents.cli verify --hearth http://127.0.0.1:9480

The deploy token comes from HESTIA_DEPLOY_TOKEN and is never printed, not even
in an error. `announce` stays off unless it is asked for on the command line:
putting a row in the Hub catalogue is an outward-facing act, not a side effect
of deploying.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from hestia_agents.manifests import AGENTS, deploy_body, write_manifests

DEFAULT_HEARTH = "http://127.0.0.1:9480"


def _client():
    try:
        import httpx
    except ImportError:  # pragma: no cover - dev extra not installed
        raise SystemExit("deploy needs httpx: uv sync --extra dev --project .") from None
    return httpx


def _token() -> str:
    token = (os.environ.get("HESTIA_DEPLOY_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "HESTIA_DEPLOY_TOKEN is empty. The hearth refuses every write without it — "
            "that is the intended default, not a fault."
        )
    return token


def cmd_build(_args: argparse.Namespace) -> int:
    for path in write_manifests():
        print("wrote", path.relative_to(path.parent.parent.parent))
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    httpx = _client()
    token = _token()
    slugs = args.only or list(AGENTS)
    failures = 0
    for slug in slugs:
        body = deploy_body(slug, announce=args.announce)
        response = httpx.post(
            f"{args.hearth.rstrip('/')}/v1/tenants",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        if response.status_code != 200:
            # Never echo the request: it carries the token header.
            print(f"  {slug}: FAILED {response.status_code} {response.text[:300]}")
            failures += 1
            continue
        out = response.json()
        print(f"  {slug}: {out['status']} -> {out['invoke_url']}")
    return 1 if failures else 0


PROBES: dict[str, dict[str, Any]] = {
    "rules-decide": {
        "policy": {
            "id": "probe@v1",
            "rules": [
                {
                    "id": "R1",
                    "when": [{"fact": "amount", "op": "<=", "value": 100}],
                    "then": {"decision": "approve", "reason": "under the limit"},
                }
            ],
            "default": {"decision": "deny", "reason": "over the limit"},
        },
        "facts": {"amount": 42},
    },
    "json-canonical": {"document": {"b": 1, "a": [1, 2]}},
    "commit-referee": {
        "commitment": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "value": "",
        "layout": "value",
    },
}


def cmd_verify(args: argparse.Namespace) -> int:
    """Invoke each deployed agent twice and prove the answer is reproducible."""
    httpx = _client()
    failures = 0
    for slug in args.only or list(AGENTS):
        url = f"{args.hearth.rstrip('/')}/t/{slug}/invoke"
        seen = []
        for _ in range(2):
            response = httpx.post(url, json=PROBES[slug], timeout=30.0)
            if response.status_code != 200:
                print(f"  {slug}: FAILED {response.status_code} {response.text[:200]}")
                failures += 1
                break
            seen.append(response.json())
        if len(seen) != 2:
            continue
        same_result = seen[0]["result"] == seen[1]["result"]
        same_signature = seen[0]["signature"] == seen[1]["signature"]
        mark = "ok" if same_result and same_signature else "NOT DETERMINISTIC"
        print(f"  {slug}: {mark} (signature repeats: {same_signature})")
        if not (same_result and same_signature):
            failures += 1
    return 1 if failures else 0


def cmd_quote(args: argparse.Namespace) -> int:
    """Ask a priced agent what it costs. Prints the exact transaction to send.

    Nothing here signs anything: the buyer pays the tenant owner from their own
    wallet, and the hearth only reads the chain afterwards.
    """
    httpx = _client()
    for slug in args.only or list(AGENTS):
        cap = AGENTS[slug]["capability_id"]
        res = httpx.post(
            f"{args.hearth.rstrip('/')}/t/{slug}/invoke",
            json=PROBES[slug], timeout=30.0,
        )
        if res.status_code != 402:
            print(f"  {slug}: free right now (HTTP {res.status_code})")
            continue
        q = res.json()
        print(f"  {slug}  [{cap}]")
        print(f"    send      : {q['amount_usd']} {q['token']}  ({q['amount_units']} base units)")
        print(f"    to        : {q['pay_to']}")
        print(f"    on        : {q['chain']}   token {q['token_contract']}")
        if q.get("binding") == "eip3009":
            print(f"    nonce     : {q['nonce']}   (expires {int(q.get('expires_at', 0))})")
            print("    pay with  : transferWithAuthorization signed over that nonce")
            print(f"    build it  : hestia-agents pay {slug} --from 0xYOURADDRESS")
            print("    then      : call --tx <tx hash> --nonce <nonce>")
        else:
            print("    then      : retry with header  X-Payment: <tx hash>")
    return 0


def cmd_pay(args: argparse.Namespace) -> int:
    """Build the payment a bound hearth will accept. Signs nothing.

    Step 1 prints EIP-712 typed data — sign it with the wallet that holds your
    key. Step 2 (`--signature`) prints the calldata to send to the token
    contract. The key never comes near this process.
    """
    import json as _json
    import time as _time

    from hestia_agents.x402 import QuoteError, calldata, typed_data

    httpx = _client()
    slug = args.slug
    res = httpx.post(
        f"{args.hearth.rstrip('/')}/t/{slug}/invoke",
        json=PROBES[slug], timeout=30.0,
    )
    if res.status_code != 200 and res.status_code != 402:
        print(f"  HTTP {res.status_code}: {res.text[:300]}")
        return 1
    if res.status_code == 200:
        print(f"  {slug} is free right now — no payment needed")
        return 0
    quote = res.json()
    valid_before = args.valid_before or int(_time.time()) + 3600
    try:
        typed = typed_data(quote, sender=args.sender, valid_before=valid_before)
    except QuoteError as exc:
        print(f"  cannot build a payment: {exc}")
        return 1
    if not args.signature:
        print("  Sign this with the wallet that holds your key (eth_signTypedData_v4):")
        print(_json.dumps(typed, indent=2))
        print()
        print("  Then re-run with --signature 0x<65-byte signature> to get the calldata.")
        print(f"  Nonce for the call header: {typed['message']['nonce']}")
        return 0
    try:
        data = calldata(typed, args.signature)
    except QuoteError as exc:
        print(f"  bad signature: {exc}")
        return 1
    print("  Send this transaction from the address you signed with:")
    print(f"    to       : {typed['domain']['verifyingContract']}   (the token contract)")
    print("    value    : 0")
    print(f"    data     : {data}")
    print()
    print("  Then present it to the hearth:")
    print(
        f"    hestia-agents call {slug} --tx <tx hash> "
        f"--nonce {typed['message']['nonce']}"
    )
    return 0


def cmd_call(args: argparse.Namespace) -> int:
    """Invoke an agent, presenting a payment transaction hash if one is given."""
    httpx = _client()
    slug = args.slug
    headers = {}
    if args.tx:
        headers["X-Payment"] = args.tx
    if getattr(args, "nonce", ""):
        # A bound hearth needs to know WHICH quote this payment settles.
        headers["X-Payment-Nonce"] = args.nonce
    res = httpx.post(
        f"{args.hearth.rstrip('/')}/t/{slug}/invoke",
        json=PROBES[slug], headers=headers, timeout=30.0,
    )
    if res.status_code == 402:
        q = res.json()
        print(f"  402 {q.get('detail')}")
        print(f"  pay {q['amount_usd']} {q['token']} to {q['pay_to']} on {q['chain']}")
        if q.get("binding") == "eip3009":
            print(
                "  this hearth binds payments: build one with  "
                f"hestia-agents pay {slug} --from 0xYOU"
            )
        return 2
    if res.status_code != 200:
        print(f"  HTTP {res.status_code}: {res.text[:300]}")
        return 1
    body = res.json()
    print("  result   :", body["result"])
    print("  receipt  :", body["signature"][:44], "...")
    print("  provider :", body["provider_pubkey"][:44], "...")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hestia-agents")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="regenerate agents/*/deploy.json").set_defaults(func=cmd_build)

    call = sub.add_parser("call", help="invoke one agent, optionally presenting a payment")
    call.add_argument("slug", choices=sorted(AGENTS))
    call.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
    call.add_argument("--tx", default="", help="payment transaction hash")
    call.add_argument(
        "--nonce", default="", help="payment nonce from the 402 (bound hearths)"
    )
    call.set_defaults(func=cmd_call)

    pay = sub.add_parser(
        "pay", help="build the EIP-3009 payment a bound hearth accepts (signs nothing)"
    )
    pay.add_argument("slug", choices=sorted(AGENTS))
    pay.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
    pay.add_argument("--from", dest="sender", required=True, help="your paying address")
    pay.add_argument("--signature", default="", help="the signed typed data, to get calldata")
    pay.add_argument("--valid-before", type=int, default=0, help="unix deadline (default +1h)")
    pay.set_defaults(func=cmd_pay)

    for name, func, helptext in (
        ("deploy", cmd_deploy, "deploy every agent onto a hearth"),
        ("verify", cmd_verify, "invoke each agent twice and compare the receipts"),
        ("quote", cmd_quote, "ask what each agent costs and how to pay it"),
    ):
        node = sub.add_parser(name, help=helptext)
        node.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
        node.add_argument("--only", action="append", choices=sorted(AGENTS))
        if name == "deploy":
            node.add_argument(
                "--announce",
                action="store_true",
                help="also announce to the Hub catalogue (off by default)",
            )
        node.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
