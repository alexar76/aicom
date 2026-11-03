#!/usr/bin/env python3
"""AIMarket Hub CLI — crawl, search, invoke, publish, serve.

Usage:
  aimarket quickstart                Make a fresh hub sellable in one command
  aimarket add <capability_id>       List your own API on this hub (operator, local)
  aimarket doctor [--url URL]        Run the federation admission check against this hub
  aimarket node init|serve|knock     Make a service you already run a node (no hub needed)
  aimarket serve                     Start the hub API server
  aimarket publish capability.json   Publish a capability to the hub catalog
  aimarket crawl                     Run a federation crawl cycle
  aimarket search <query>            Search the federated catalog
  aimarket invoke <capability_id>    Invoke a capability
  aimarket peers                     List known peer hubs
  aimarket stats                     Show hub statistics
  aimarket trust <hub_url>           Show trust score for a hub
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from aimarket_hub import envfile
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import Crawler
from aimarket_hub.database import HubDatabase
from aimarket_hub.trust import TrustScorer

# Env flags that must never be on in production. The standalone hub image (independent/,
# and every hub wheel installed from PyPI) ships WITHOUT the repo's `security` package, so
# `security.prod_startup_guard` is unreachable there and this list is the only gate that
# runs. Anything added to one must be added to the other; tests/test_prod_startup_guard.py
# asserts that parity by BEHAVIOUR (setting each flag and checking both gates refuse),
# not by reading this source, so a rename here cannot quietly detach the check.
#
#   PAYMENT_VERIFY_STUB          every tx hash accepted with no on-chain check
#   PAYMENT_TESTNET              demo tx hashes settle against a testnet RPC
#   ZK_SIMULATED                 "privacy-preserving" proofs are simulated
#   TEE_SOFTWARE_OK              attestation with no hardware behind it
#   SUPPLY_SECURITY_RELAXED      no publisher collateral — anyone may list on a hub that
#                                advertises itself as stake-gated
#   CHANNEL_ALLOW_UNPROVEN_PAYER deposits credited with no proof of control over the paying
#                                wallet, so the channel_secret goes to whoever calls open()
#                                first (channels._allow_unproven_payer)
#   SANDBOX_STUB_INVOKE          trials answer with canned output and nothing executes
PROD_FORBIDDEN_FLAGS: tuple[str, ...] = (
    "AIFACTORY_PAYMENT_VERIFY_STUB",
    "AIFACTORY_PAYMENT_TESTNET",
    "AIMARKET_ZK_SIMULATED",
    "AIMARKET_TEE_SOFTWARE_OK",
    "AIMARKET_SUPPLY_SECURITY_RELAXED",
    "AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER",
    "AIMARKET_SANDBOX_STUB_INVOKE",
)


def prod_forbidden_flags_active() -> list[str]:
    """Which of PROD_FORBIDDEN_FLAGS the environment currently has switched on.

    Truthy, not ``== "1"``. ``RELAXED=true`` does not actually relax anything — the
    runtime that reads it tests ``== "1"`` — but the operator plainly meant it to, and
    refusing to boot is the right answer to that intent either way.
    """
    return [
        name
        for name in PROD_FORBIDDEN_FLAGS
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
    ]


BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    # Before anything builds a HubConfig: the settings quickstart saved (envfile.py).
    envfile.load()
    parser = argparse.ArgumentParser(description="AIMarket Hub CLI")
    sub = parser.add_subparsers(dest="command")

    # quickstart
    qs = sub.add_parser(
        "quickstart",
        help="Make a fresh hub sellable: a free ping, a priced capability, a buyer key, saved settings",
    )
    qs.add_argument("--name", default=None,
                    help="This hub's public name (do not call it AIMarket — see the naming note)")
    qs.add_argument("--url", default=None,
                    help="This hub's public https URL, if it already has one")
    qs.add_argument("--price", type=float, default=0.004,
                    help="Price per call of the sample capability (default 0.004)")
    qs.add_argument("--grant", type=float, default=0.05,
                    help="Starting balance for the buyer key (default 0.05)")
    qs.add_argument("--no-sample", action="store_true",
                    help="Skip the sample capabilities; only save settings and mint the buyer key")
    qs.add_argument("--no-buyer", action="store_true",
                    help="Do not mint a buyer key (nothing secret is printed)")

    # add
    add_p = sub.add_parser(
        "add", help="List your own API on this hub — operator only, writes the local database",
    )
    add_p.add_argument("capability_id", help="Versioned id, e.g. weather.now@v1")
    add_p.add_argument("--url", required=True, help="Your endpoint; the hub POSTs the invoke to it")
    add_p.add_argument("--price", type=float, default=0.0, help="USD per call (0 = free)")
    add_p.add_argument("--pay-to", default="",
                       help="Your wallet (0x…): buyers pay it USDC directly, the hub never holds it")
    add_p.add_argument("--name", default="", help="Display name")
    add_p.add_argument("--description", default="", help="What it does, in one sentence")
    add_p.add_argument("--product", default="", help="product_id (default: the id's first segment)")
    add_p.add_argument("--input-schema", default="", help="JSON schema, inline or @file.json")
    add_p.add_argument("--provider-pubkey", default="",
                       help="Ed25519 key your endpoint signs responses with (required in production)")

    # node
    node_p = sub.add_parser(
        "node", help="Make a service you already run a node of the federation (no hub needed)",
    )
    node_sub = node_p.add_subparsers(dest="node_command")
    ni = node_sub.add_parser("init", help="Write a node.toml template")
    ni.add_argument("--out", default="node.toml")
    ns = node_sub.add_parser("serve", help="Serve the node beside your API")
    ns.add_argument("--config", default="node.toml")
    ns.add_argument("--host", default="0.0.0.0")
    ns.add_argument("--port", type=int, default=9090)
    nk = node_sub.add_parser("knock", help="Announce the node to a hub")
    nk.add_argument("--config", default="node.toml")
    nk.add_argument("--hub", default="https://modelmarket.dev")

    # doctor
    doc_p = sub.add_parser(
        "doctor", help="Run the same admission check other hubs run on this one",
    )
    doc_p.add_argument("--url", default=None,
                       help="Public URL to check (default: AIMARKET_HUB_URL)")
    doc_p.add_argument("--json", action="store_true", help="Print the raw dossier")

    # rpc-check
    rpc_p = sub.add_parser(
        "rpc-check", help="Ask every chain RPC node this hub's payment paths use, from this machine",
    )
    rpc_p.add_argument("--window", type=int, default=None,
                       help="eth_getLogs block window to try (default: the deposit watcher's chunk)")
    rpc_p.add_argument("--json", action="store_true", help="Print the rows as JSON")

    # serve
    serve_p = sub.add_parser("serve", help="Start the hub API server")
    serve_p.add_argument(
        "--init", action="store_true",
        help="First start with no settings file: set the hub up as quickstart does (no buyer key)",
    )

    # publish
    publish_p = sub.add_parser("publish", help="Publish a capability manifest")
    publish_p.add_argument(
        "manifest",
        nargs="?",
        default="capability.json",
        help="Path to capability manifest JSON",
    )
    publish_p.add_argument("--hub", default=None, help="Hub base URL (default: HubConfig.hub_url)")
    publish_p.add_argument("--token", default=None, help="AIMARKET_PUBLISH_TOKEN (or env)")

    # crawl
    sub.add_parser("crawl", help="Run federation crawl")

    # search
    search_p = sub.add_parser("search", help="Search capabilities")
    search_p.add_argument("query", nargs="?", default="", help="Search query")
    search_p.add_argument("--hub", default="any", help="Filter by source hub")
    search_p.add_argument("--limit", type=int, default=10)
    search_p.add_argument("--json", action="store_true")

    # invoke
    invoke_p = sub.add_parser("invoke", help="Invoke a capability")
    invoke_p.add_argument("capability_ref", help="product_id/capability_id")
    invoke_p.add_argument("--input", default="{}", help="JSON input payload")
    invoke_p.add_argument("--hub", default="local", help="Source hub")

    # peers
    sub.add_parser("peers", help="List known peers")

    # stats
    sub.add_parser("stats", help="Show hub statistics")

    # trust
    trust_p = sub.add_parser("trust", help="Show trust score")
    trust_p.add_argument("hub_url", help="Hub URL")

    mcp_p = sub.add_parser("mcp", help="Run the local hub's MCP tools over stdio (no HTTP listener)")
    mcp_p.add_argument("--init", action="store_true", help="Initialize a fresh dev hub, as serve --init does")

    args = parser.parse_args(argv)

    if args.command == "mcp":
        from contextlib import redirect_stdout

        # Preserve the protocol stream before redirecting startup/plugin prints.
        output = sys.stdout
        with redirect_stdout(sys.stderr):
            if args.init:
                _init_if_new()
            return _cmd_serve(stdio_output=output)
    if args.command == "quickstart":
        return _cmd_quickstart(args)
    if args.command == "add":
        return _cmd_add(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "rpc-check":
        return _cmd_rpc_check(args)
    if args.command == "node":
        return _cmd_node(args, node_p)
    if args.command == "serve":
        if getattr(args, "init", False):
            _init_if_new()
        _release_notice()
        return _cmd_serve()
    elif args.command == "publish":
        return _cmd_publish(args)
    elif args.command == "crawl":
        return _cmd_crawl()
    elif args.command == "search":
        return _cmd_search(args)
    elif args.command == "invoke":
        return _cmd_invoke(args)
    elif args.command == "peers":
        return _cmd_peers()
    elif args.command == "stats":
        return _cmd_stats()
    elif args.command == "trust":
        return _cmd_trust(args)
    else:
        parser.print_help()
        return 0


def uvicorn_proxy_kwargs(raw: str, *, production: bool) -> dict[str, object]:
    """uvicorn keyword args that make the PROXIED client address trustworthy — and only
    from the proxy.

    ``uvicorn.run(app)`` was called with no proxy configuration at all, so uvicorn's
    default (``forwarded_allow_ips="127.0.0.1"``, or whatever ``FORWARDED_ALLOW_IPS``
    happened to say) decided the question implicitly. Behind
    ``deploy/nginx/modelmarket.dev.conf`` the hub's peer is the proxy on every request,
    so the per-IP channel cap and the invoke rate limiter saw ONE address for the whole
    internet — a single shared bucket, and nothing bounding the LRU eviction those
    limiters lean on. From a container the peer is the bridge gateway, which is not in
    uvicorn's default list either, so the forwarded header was ignored outright.

    Contract (same env var the app-side ``_client_address`` reads, so both layers agree):
      * ``AIMARKET_TRUSTED_PROXIES`` unset/empty → proxy headers are NOT processed at all.
        A directly exposed hub must never believe a caller's own ``X-Forwarded-For``.
      * set to the proxy address(es) → uvicorn trusts the header from exactly those peers.
      * ``*`` is refused: blanket trust lets every caller forge its own client address and
        mint a fresh rate-limit bucket per request. In production that is a hard startup
        failure (silently serving with forgeable rate-limit keys is worse than not
        starting); elsewhere it degrades to "no proxy trusted", loudly.
    """
    entries = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if "*" in entries:
        message = (
            "AIMARKET_TRUSTED_PROXIES=* is refused: blanket-trusting X-Forwarded-For "
            "lets every caller forge its own client address and defeat the per-IP rate "
            "limits. List the proxy address(es) explicitly (e.g. 127.0.0.1)."
        )
        if production:
            print(f"{RED}Production startup refused: {message}{RESET}", file=sys.stderr)
            raise SystemExit(1)
        print(f"{YELLOW}[proxy]{RESET} {message} Ignoring the header.")
        entries = []
    trusted = [e for e in entries if e != "*"]
    if not trusted:
        if production:
            print(
                f"{YELLOW}[proxy]{RESET} AIMARKET_TRUSTED_PROXIES not set — per-IP rate "
                "limits key on the immediate peer. Behind a reverse proxy that is the "
                "PROXY's address, so every caller shares one bucket."
            )
        return {"proxy_headers": False}
    print(f"{GREEN}[proxy]{RESET} trusting X-Forwarded-For from {', '.join(trusted)}")
    return {"proxy_headers": True, "forwarded_allow_ips": ",".join(trusted)}


def _release_notice() -> None:
    """Say once if PyPI has a newer aimarket-hub (release_check.py); silent when offline."""
    from aimarket_hub import release_check

    if not release_check.enabled():
        return
    line = release_check.notice(newest=release_check.latest())
    if line:
        print(f"  {YELLOW}!{RESET} {line}")


def _init_if_new() -> None:
    """`serve --init`: a first start with no settings file sets the hub up by itself.

    On a platform (Railway, Render, Fly) there is no shell before the first start in which to
    run `quickstart`, so the image starts with `serve --init`. It does what quickstart does —
    settings saved to the data volume, an admin token, the free `hub.ping@v1` and the priced
    sample — except mint a buyer key, because a key printed to platform logs is a key leaked.
    Once the settings file exists this does nothing, so it is safe on every restart.
    """
    path = envfile.default_path(HubConfig().db_path)
    if path.exists():
        return
    print(f"{BOLD}First start: no {path} yet — setting this hub up as `aimarket quickstart` "
          f"does (no buyer key).{RESET}")
    _cmd_quickstart(SimpleNamespace(
        name=None, url=None, price=0.004, grant=0.0, no_sample=False, no_buyer=True,
    ))


def _cmd_serve(*, stdio_output=None) -> int:
    import os

    import uvicorn

    config = HubConfig()
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db)

    # Warn about active stub/dev flags at startup
    stub_flags = []
    if os.environ.get("AIMARKET_ZK_SIMULATED", "").strip() == "1":
        stub_flags.append("AIMARKET_ZK_SIMULATED=1 (ZK proofs are simulated — no cryptographic privacy)")
    if os.environ.get("AIFACTORY_PAYMENT_VERIFY_STUB", "").strip() == "1":
        stub_flags.append("AIFACTORY_PAYMENT_VERIFY_STUB=1 (all tx hashes accepted without on-chain check)")
    if os.environ.get("AIFACTORY_PAYMENT_TESTNET", "").strip() == "1":
        stub_flags.append("AIFACTORY_PAYMENT_TESTNET=1 (testnet mode — demo tx hashes accepted)")
    if os.environ.get("AIMARKET_TEE_SOFTWARE_OK", "").strip() == "1":
        stub_flags.append("AIMARKET_TEE_SOFTWARE_OK=1 (software TEE attestation — no hardware guarantee)")
    if os.environ.get("AIMARKET_SUPPLY_SECURITY_RELAXED", "").strip() == "1":
        stub_flags.append("AIMARKET_SUPPLY_SECURITY_RELAXED=1 (no publisher collateral — anyone may list)")
    if os.environ.get("AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER", "").strip() == "1":
        stub_flags.append("AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER=1 (deposits credited without payer proof)")
    if os.environ.get("AIMARKET_SANDBOX_STUB_INVOKE", "").strip() == "1":
        stub_flags.append("AIMARKET_SANDBOX_STUB_INVOKE=1 (sandbox trials return canned demo output)")
    prod = os.environ.get("AIFACTORY_PROD", "").strip() == "1"
    if prod:
        stub_flags.append("AIFACTORY_PROD=1 (production mode — stub flags will HARD-BLOCK startup)")
    for flag in stub_flags:
        print(f"{YELLOW}[stub]{RESET} {flag}")

    # Enforce what the banner promises. Previously startup only WARNED and then
    # ran uvicorn regardless, so a standalone hub with AIFACTORY_PROD=1 and
    # AIFACTORY_PAYMENT_VERIFY_STUB=1 would start and credit payment channels for
    # free (no on-chain verification). Prefer the full production guard when the
    # security module is importable; otherwise enforce the payment/ZK stub gate
    # inline so the standalone package still fails closed.
    if prod:
        try:
            from security.prod_startup_guard import assert_production_startup_safe

            assert_production_startup_safe(exit_on_failure=True)
        except ImportError:
            # The standalone image has no `security` package — PROD_FORBIDDEN_FLAGS is
            # the whole gate here. See its comment for what each flag does.
            active = prod_forbidden_flags_active()
            if active:
                print(
                    f"{RED}Production startup refused: AIFACTORY_PROD=1 with unsafe stub "
                    f"flag(s) active: {', '.join(active)}. Set them to 0 before running "
                    f"in production.{RESET}",
                    file=__import__("sys").stderr,
                )
                raise SystemExit(1)

            # Stub flags were the only thing this fallback checked, so a production hub
            # could boot with an Anvil recipient and route real deposits to a wallet whose
            # private key is public. The addresses live in aimarket_hub.config precisely
            # because the `security` package is absent from the standalone image.
            from aimarket_hub import realm
            from aimarket_hub.config import is_dev_chain_address

            # Two gates check this, and they must agree: `payment_readiness` (which reports)
            # and this one (which refuses to boot). The realm exemption belongs in both — a
            # sealed bubble runs ENTIRELY on Anvil addresses, so the boot gate alone would
            # keep UNI out of production mode and force it into a demo shape that behaves
            # differently from LIVE. Missing the second copy of a guard is how this codebase
            # has broken before, so it is spelled out rather than assumed.
            in_bubble = realm.is_uni()
            for var in ("AIMARKET_PAYMENT_RECIPIENT", "AIMARKET_ESCROW_EVM_ADDRESS"):
                value = os.environ.get(var, "").strip()
                if value and is_dev_chain_address(value) and not in_bubble:
                    print(
                        f"{RED}Production startup refused: {var}={value} is an Anvil/Hardhat "
                        f"dev-chain address. Its private key is public — real funds sent there "
                        f"are sweepable by anyone. Set a wallet you control.{RESET}",
                        file=__import__("sys").stderr,
                    )
                    raise SystemExit(1)

    proxy_kwargs = uvicorn_proxy_kwargs(
        os.environ.get("AIMARKET_TRUSTED_PROXIES", ""), production=prod
    )

    if stdio_output is not None:
        from aimarket_hub.mcp_stdio import run

        try:
            asyncio.run(run(app, output=stdio_output))
        finally:
            db.close()
        return 0

    bind_host = os.environ.get("AIMARKET_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0"
    print(f"{GREEN}Hub API starting on http://{bind_host}:9083{RESET}")
    uvicorn.run(app, host=bind_host, port=9083, log_level="info", **proxy_kwargs)
    return 0



JOIN_GUIDE = "https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.md"
OPERATOR_GUIDE = "https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md"
_CAPABILITY_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}@v[0-9]+$"


def _public_host(url: str | None) -> str:
    """The host of a URL other hubs could reach, or "" for a local/private one."""
    from urllib.parse import urlparse

    host = (urlparse(url or "").hostname or "").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return ""
    try:
        import ipaddress

        if not ipaddress.ip_address(host).is_global:
            return ""
    except ValueError:
        pass  # a name, not an address
    return host


def _cmd_quickstart(args) -> int:
    """Turn a fresh deployment into one that can actually take money — and be admitted.

    What a stranger got before this existed: a hub whose catalogue is six crawled peers
    owned by somebody else, zero capabilities of its own (the twelve seeded demo rows have
    no execution path, so `fulfillment` strips them from search, the manifest and /mcp),
    and no way to charge for anything short of deploying an escrow contract on Base. Three
    facts, each of which on its own makes the node unpayable.

    Following this command's own instructions from a clean machine (2026-10-12) found three
    more. The settings it asked for were five `export` lines, so the first `serve` from a new
    shell ran without them. There was no admin token, so the operator could neither approve
    a peer nor top up a buyer. And the only sample was priced, so the federation's sandbox
    had nothing of the newcomer's to run and judged it by whatever else its manifest held.

    So it now saves the settings next to the database (`envfile`, read by every command),
    generates the admin token, and lists two capabilities the operator really owns and the
    hub can execute with no provider, model or network: a FREE `hub.ping@v1` that answers
    with a signed receipt (what another hub's sandbox runs) and a priced `hub.hello@v1`
    (what a buyer pays for). Then it mints a buyer key and prints the sale. Idempotent:
    a second run keeps the token and the name unless told otherwise.
    """
    import secrets

    from aimarket_hub import credits, signing
    from aimarket_hub.models import Capability

    env_path = envfile.default_path(HubConfig().db_path)
    saved = envfile.read(env_path)

    # Explicit choices replace what was saved; everything else is only filled in.
    explicit: dict[str, str] = {}
    if args.name:
        explicit["AIMARKET_HUB_NAME"] = args.name.strip()
    if args.url:
        explicit["AIMARKET_HUB_URL"] = args.url.strip().rstrip("/")
    defaults: dict[str, str] = {
        "AIMARKET_CREDITS_ENABLED": "1",
        # Publisher trust scored by THIS hub, not by another operator's oracle.
        "AIMARKET_ORACLE_FAMILY_URL": "off",
    }
    url_now = explicit.get("AIMARKET_HUB_URL") or os.environ.get("AIMARKET_HUB_URL", "")
    defaults["AIMARKET_HUB_NAME"] = _public_host(url_now) or "Unnamed hub"
    key_path = Path(HubConfig().signing_key_path)
    # Hybrid from the first start, but never flip an existing Ed25519-only identity.
    if signing.pqc_available() and (not key_path.exists() or Path(f"{key_path}_mldsa").exists()):
        defaults["AIMARKET_PQC"] = "1"
    missing = {
        k: os.environ.get(k, v) for k, v in defaults.items()
        if k not in saved and k not in explicit
    }
    if "AIMARKET_ADMIN_TOKEN" not in saved and not os.environ.get("AIMARKET_ADMIN_TOKEN"):
        missing["AIMARKET_ADMIN_TOKEN"] = secrets.token_urlsafe(32)
    if explicit:
        envfile.update(env_path, explicit)
        os.environ.update(explicit)
    added = envfile.merge(env_path, missing)
    for key, value in added.items():
        os.environ.setdefault(key, value)

    config = HubConfig()
    db = HubDatabase(config.db_path)
    credits.configure(db._conn)

    print(f"{BOLD}AIMarket Hub — quickstart{RESET}")
    print(f"  name      {config.hub_name}")
    print(f"  hub url   {config.hub_url}")
    print(f"  database  {config.db_path}")
    print(f"  settings  {env_path}  {DIM}(read by every `aimarket` command; 0600 — it holds "
          f"the admin token){RESET}")
    if added or explicit:
        print(f"            {DIM}saved: {', '.join(sorted({*added, *explicit}))}{RESET}")

    if not credits.enabled():
        print()
        print(f"{YELLOW}The credits rail is off in this environment, so every priced capability "
              f"is served FREE.{RESET}")
        print(f"  Something set {BOLD}AIMARKET_CREDITS_ENABLED=0{RESET} explicitly; unset it to "
              f"use the saved value.")

    base = config.hub_url.rstrip("/")
    if not args.no_sample:
        # A JSON object in prompt_template IS the hub's zero-dependency execution path
        # (fulfillment.has_execution_path): the invoke handler returns it verbatim, signed.
        # No URL inside either pack: it would go stale when the hub moves, and on a local
        # trial the sandbox's safety gate refuses an answer naming a private address.
        ping = {
            "pong": True,
            "note": "Free liveness check. Other hubs' admission sandbox runs this one.",
        }
        db.upsert_capability(Capability(
            capability_id="hub.ping@v1",
            product_id="hub-hello",
            name="Hub ping",
            description=(
                "Free: answers with a signed receipt, so anyone (and another hub's admission "
                "sandbox) can check this hub executes and signs. Created by `aimarket quickstart`."
            ),
            output_schema={"type": "object", "properties": {
                "pong": {"type": "boolean"}, "note": {"type": "string"},
            }},
            price_per_call_usd=0.0,
            source_hub="local",
            source_hub_name=config.hub_name,
            invoke_url="",
            prompt_template=json.dumps(ping),
            trust_score=0.5,
        ))
        pack = {
            "answer": "This hub is live and this capability is really executable.",
            "replace_me": "List your own API with `aimarket add`, or edit this pack.",
        }
        db.upsert_capability(Capability(
            capability_id="hub.hello@v1",
            product_id="hub-hello",
            name="Hub hello",
            description=(
                "Sample capability created by `aimarket quickstart` — replace it with "
                "something of your own."
            ),
            price_per_call_usd=float(args.price),
            source_hub="local",
            source_hub_name=config.hub_name,
            invoke_url="",
            prompt_template=json.dumps(pack),
            trust_score=0.5,
        ))
        print()
        print(f"  {GREEN}✓{RESET} listed {BOLD}hub-hello/hub.ping@v1{RESET} free "
              f"{DIM}(signed receipt — what other hubs' sandbox runs){RESET}")
        print(f"  {GREEN}✓{RESET} listed {BOLD}hub-hello/hub.hello@v1{RESET} at ${args.price}/call "
              f"{DIM}(local, executable, yours){RESET}")

    if getattr(args, "no_buyer", False):
        _signing_report(config.signing_key_path)
        return 0
    ledger = credits.ledger()
    account = ledger.create_account(label="quickstart buyer", grant_usd=float(args.grant))
    print(f"  {GREEN}✓{RESET} buyer key {BOLD}{account['api_key']}{RESET} "
          f"{DIM}(${account['balance_usd']} balance — shown once){RESET}")

    print()
    print(f"{BOLD}Sell it:{RESET}")
    print(f"  {DIM}# 1. the buyer finds it{RESET}")
    print(f"  curl -s '{base}/ai-market/v2/search?intent=hello'")
    print(f"  {DIM}# 2. the buyer pays for it{RESET}")
    print(f"  curl -s -X POST '{base}/ai-market/v2/invoke' \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -H 'X-API-Key: {account['api_key']}' \\")
    print("    -d '{\"product_id\":\"hub-hello\",\"capability_id\":\"hub.hello@v1\","
          "\"input\":{},\"source_hub\":\"local\"}'")
    print(f"  {DIM}# 3. the operator watches the money{RESET}")
    print(f"  curl -s '{base}/ai-market/v2/stats/live' | jq .summary.credits")
    print()
    print(f"{BOLD}Next:{RESET}")
    print(f"  aimarket serve                 {DIM}# start it — the saved settings come with it{RESET}")
    print(f"  aimarket add my.api@v1 --url https://api.example.com/run --price 0.01 --pay-to 0x…")
    print(f"                                 {DIM}# your own API; buyers pay your wallet directly{RESET}")
    print(f"  aimarket doctor --url https://your-hub.example")
    print(f"                                 {DIM}# the admission check other hubs will run on you{RESET}")
    print(f"  {DIM}Top up a buyer:  POST {base}/ai-market/v2/accounts/<id>/credit — admin bearer = "
          f"AIMARKET_ADMIN_TOKEN in {env_path}{RESET}")
    print(f"  {DIM}Go public and join the federation: {JOIN_GUIDE}{RESET}")
    _signing_report(config.signing_key_path)
    return 0


def _signing_report(key_path: str | Path) -> None:
    """How this hub will sign, said before `serve`, and which key files are its identity.

    Two things a fresh hub otherwise learns too late. Without dilithium-py it cannot check a
    post-quantum signature, and verification fails closed, so it silently never indexes a peer
    that signs hybrid. Hybrid signing itself is opt-in (`AIMARKET_PQC`), and once it is on, peers
    pin the ML-DSA key on first sight and reject a different one later: that key file is as much
    the hub's identity as the classical key, and a restore that forgets it drops the hub from the
    federation until every peer re-pins.
    """
    from aimarket_hub import signing

    key = Path(key_path)
    pq_key = Path(f"{key}_mldsa")
    library = signing.pqc_available()
    print()
    if not library:
        print(f"{YELLOW}dilithium-py is missing, so this hub cannot check post-quantum signatures "
              f"and will not index peers that sign hybrid (the AIMarket hubs do).{RESET}")
        print(f"    {BOLD}pip install 'aimarket-hub[pqc]'{RESET}")
    hybrid = signing.hub_signs_hybrid(key)
    if not hybrid:
        print(f"{YELLOW}Signing is Ed25519 only: post-quantum signing is off.{RESET}")
        if signing.pqc_signing_setting() is None and key.exists():
            print("  This hub already has an Ed25519-only identity, so it keeps it.")
        print("  To sign hybrid (Ed25519 + ML-DSA-65), as every AIMarket hub does:")
        print(f"    {BOLD}export AIMARKET_PQC=1{RESET}")
        print(f"  {DIM}Then back up {pq_key} together with {key}.{RESET}")
        return
    if not library:
        print(f"  {RED}✗{RESET} hybrid signing needs it: `serve` refuses to start until it is installed.")
        return
    signing.Signer(key, pqc=True)  # loads or creates both keys, exactly as `serve` will
    print(f"  {GREEN}✓{RESET} signing hybrid {DIM}(Ed25519 + ML-DSA-65){RESET}")
    print(f"    classical key     {key}")
    print(f"    post-quantum key  {pq_key}")
    print(f"  {DIM}Back up both and keep them on one volume. Peers pin the post-quantum key: "
          f"lose it and they reject this hub until each one re-pins it.{RESET}")


def _cmd_add(args) -> int:
    """List the operator's own API on this hub, straight into the local database.

    The HTTP door (`aimarket publish` → `/supply/register`) is the door for OTHER people's
    supply, and it gates them accordingly: a publisher id, a credential, and collateral. An
    operator listing their own endpoint on their own hub walked into all of it — a $10 stake
    paid to themselves, waived only by `AIMARKET_SUPPLY_OPERATOR_PUBLISHERS` plus an admin
    token plus a restart, none of it documented (2026-10-12). The operator already owns the
    database this writes; there is no one to protect them from. The row is operator-owned
    (no separate publisher), exactly like the quickstart samples.

    Money: `--pay-to` is the wallet buyers pay USDC to, seller-direct; the hub never holds it.
    Without it a priced listing is paid to `AIMARKET_X402_PAY_TO` if set, else only by credit
    accounts on THIS hub — which a buyer routed from another hub does not have.
    """
    import re

    from aimarket_hub import settle
    from aimarket_hub.models import Capability
    from aimarket_hub.signing import decode_b64
    from aimarket_hub.supply_security import SupplySecurityPolicy

    def fail(message: str) -> int:
        print(f"{RED}✗{RESET} {message}")
        return 1

    cap_id = (args.capability_id or "").strip()
    if not re.match(_CAPABILITY_ID, cap_id):
        return fail(f"capability id {cap_id!r} must look like name.verb@v1")
    url = (args.url or "").strip()
    if not url.startswith(("http://", "https://")) or any(c in url for c in "\r\n\t "):
        return fail(f"--url must be an http(s) URL, got {url!r}")
    price = float(args.price or 0.0)
    if not (price >= 0.0) or price != price or price == float("inf"):
        return fail("--price must be a finite number ≥ 0")
    pay_to = (args.pay_to or "").strip()
    if pay_to and not settle.is_address(pay_to):
        return fail(f"--pay-to must be a 0x wallet address, got {pay_to!r}")
    pubkey = (args.provider_pubkey or "").strip()
    if pubkey:
        try:
            if len(decode_b64(pubkey)) != 32:
                raise ValueError
        except Exception:
            return fail("--provider-pubkey must be a base64 Ed25519 public key (32 bytes)")
    schema: dict = {}
    raw_schema = (args.input_schema or "").strip()
    if raw_schema:
        try:
            text = Path(raw_schema[1:]).read_text(encoding="utf-8") if raw_schema.startswith("@") else raw_schema
            schema = json.loads(text)
        except (OSError, ValueError) as exc:
            return fail(f"--input-schema: {exc}")
        if not isinstance(schema, dict):
            return fail("--input-schema must be a JSON object")

    config = HubConfig()
    policy = SupplySecurityPolicy.from_config(config)
    if policy.require_response_signature and not pubkey:
        return fail(
            "this hub runs in production mode, where every provider response must be signed "
            "(X-Provider-Signature). Pass --provider-pubkey with the Ed25519 key your endpoint "
            "signs with — examples/hello-capability/server.py shows the signature."
        )

    product = (args.product or "").strip() or cap_id.split("@", 1)[0].split(".", 1)[0]
    db = HubDatabase(config.db_path)
    existed = db.get_capability(product, cap_id, source_hub="local") is not None
    db.upsert_capability(Capability(
        capability_id=cap_id,
        product_id=product,
        name=(args.name or "").strip() or cap_id.split("@", 1)[0],
        description=(args.description or "").strip(),
        input_schema=schema,
        price_per_call_usd=price,
        source_hub="local",
        source_hub_name=config.hub_name,
        invoke_url=url,
        payout_address=pay_to,
        provider_pubkey=pubkey,
        trust_score=0.5,
    ))

    from aimarket_hub import credits, x402

    payee = settle.seller_pay_to(SimpleNamespace(payout_address=pay_to, publisher_id=""),
                                 operator_pay_to=x402.recipient())
    base = config.hub_url.rstrip("/")
    print(f"  {GREEN}✓{RESET} {'updated' if existed else 'listed'} {BOLD}{product}/{cap_id}{RESET} "
          f"{'free' if price == 0 else f'at ${price}/call'} → {url}")
    if price > 0 and payee:
        print(f"    {DIM}buyers pay USDC to {payee} directly (x402); the hub never holds it{RESET}")
    elif price > 0 and credits.enabled():
        print(f"{YELLOW}    No wallet: only credit accounts on THIS hub can pay. A buyer routed from "
              f"another hub cannot — add --pay-to 0x… (or set AIMARKET_X402_PAY_TO).{RESET}")
    elif price > 0:
        print(f"{YELLOW}    No wallet and the credits rail is off: this price is not collected "
              f"and the call is served free. Add --pay-to 0x….{RESET}")
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        print(f"{YELLOW}    {url} is loopback: the hub refuses it unless AIMARKET_ALLOW_LOCAL_PUBLISH=1 "
              f"(dev) or that host is in AIMARKET_INVOKE_HOST_GATEWAY (Docker).{RESET}")
    print(f"    {DIM}Your endpoint receives POST {{\"input\": …, \"product_id\": …, \"capability_id\": …}} "
          f"and answers 200 with a JSON object (or {{\"result\": …}}).{RESET}")
    print(f"    {DIM}Try it: curl -s -X POST '{base}/ai-market/v2/invoke' -H 'Content-Type: application/json' "
          f"-d '{{\"product_id\":\"{product}\",\"capability_id\":\"{cap_id}\",\"input\":{{}},"
          f"\"source_hub\":\"local\"}}'{RESET}")
    return 0


def _cmd_node(args, parser) -> int:
    """`aimarket node`: see aimarket_hub/node.py."""
    from aimarket_hub import node

    cmd = getattr(args, "node_command", None)
    if cmd == "init":
        out = Path(args.out)
        if out.exists():
            print(f"{RED}✗{RESET} {out} exists; not overwriting it")
            return 1
        out.write_text(node.TEMPLATE, encoding="utf-8")
        print(f"  {GREEN}✓{RESET} wrote {out} — name your routes in it, then `aimarket node serve`")
        return 0
    if cmd not in ("serve", "knock"):
        parser.print_help()
        return 0
    try:
        cfg = node.load(args.config)
    except (OSError, ValueError) as exc:
        print(f"{RED}✗{RESET} {args.config}: {exc}")
        return 1
    if cmd == "knock":
        answer = node.knock(cfg, args.hub)
        print(json.dumps(answer, indent=2))
        if answer.get("assay_url"):
            print(f"\n  Verdict: {answer['assay_url']}")
        return 0 if answer.get("acknowledged") else 1
    import uvicorn

    from aimarket_hub import release_check

    if release_check.enabled():
        line = release_check.notice(newest=release_check.latest())
        if line:
            print(f"  {YELLOW}!{RESET} {line}")
    app = node.create_app(cfg)
    print(f"{GREEN}Node {cfg.name}{RESET}: {len(cfg.capabilities)} capabilities → {cfg.upstream}")
    print(f"  public as {cfg.url} — check it with `aimarket doctor --url {cfg.url}`, then "
          f"`aimarket node knock`")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


#: What to do about each check the federation assay can fail, in operator words.
_DOCTOR_HINTS: dict[str, str] = {
    "url_public": "Other hubs must reach it: a public https address, not localhost or a private IP. "
                  "Set AIMARKET_HUB_URL (or quickstart --url) to it.",
    "well_known_schema": "/.well-known/ai-market.json is missing or not schema-valid. Is the URL the "
                         "hub itself (behind a path prefix, include the prefix)?",
    "advertised_key": "The well-known names no signer_public_key.",
    "manifest_schema": "The manifest at manifest_url is missing, off-origin or not schema-valid. If "
                       "nginx rewrites paths, the manifest URL must stay on the same origin.",
    "manifest_signed": "The manifest signature does not verify under the advertised key. The line "
                       "above says which way: a signature that is not an object (spec §7.3.1), a "
                       "proxy rewriting the body, or a key file swapped under a running hub.",
    "manifest_fresh": "generated_at is stale: a cache in front of the hub is serving an old manifest.",
    "invoke_same_origin": "The invoke URL the well-known advertises is on another origin.",
    "sandbox_probe": "The sandbox could not run anything of yours. `aimarket quickstart` lists a free "
                     "hub.ping@v1 for exactly this.",
    "sandbox_receipt_signed": "The answer carried no receipt signed by this hub's key.",
    "sandbox_price_matches": "The 402 quotes a different price than your catalogue lists.",
    "sandbox_price_enforced": "A priced capability answered without payment: switch a rail on "
                              "(AIMARKET_CREDITS_ENABLED=1, or --pay-to on the listing).",
    "sandbox_analysis": "The free answer failed the safety gate (private address, secrets, or not "
                        "matching its output_schema).",
    "sandbox_key_mismatch": "A receipt was signed by a key that is not this hub's.",
}


def _cmd_rpc_check(args) -> int:
    """Ask each chain node the payment paths use what they will ask it, from this machine.

    Free RPC nodes cap per source IP, so only a check run where the hub runs says anything.
    Two lists, because the overrides differ: settlement and the deposit watcher read
    AIMARKET_SETTLE_RPC_URL when it is set, deposit verification AIMARKET_RPC_<CHAIN>. The
    watcher's own eth_getLogs (the token's Transfers into the top-up wallet, one chunk wide)
    is tried on the first list — the call public Base nodes refused with 429 or a range cap
    while answering eth_chainId and eth_blockNumber. Exit 1 when no node can serve the scan.
    """
    import json as _json

    from aimarket_hub import chain_net, deposit_verify, deposit_watch, settle, x402

    chain_id = x402.chain_id() or None
    profile = x402.asset_profile() or {}
    wallet = deposit_watch.dedicated_wallet() or "0x" + "0" * 36 + "dead"
    window = args.window or deposit_watch.chunk_blocks()
    logs = {"address": str(profile.get("address") or "").lower(),
            "topics": [deposit_watch.TRANSFER_TOPIC, None, "0x" + wallet[2:].rjust(64, "0")], "window": window}
    lists = [("settlement + deposit watcher", settle.rpc_urls(chain_id), logs if logs["address"] else None),
             ("deposit verification", deposit_verify.rpc_urls_for(x402.chain()), None)]
    report, scan_ok = [], 0
    for label, urls, flt in lists:
        if not urls:
            report.append({"list": label, "rows": [], "detail": "no RPC configured"})
            continue
        pool = chain_net.RpcPool(chain_net.NetworkSpec(
            id=x402.chain(), kind=chain_net.EVM, display_name=x402.chain(), chain_id=chain_id, cluster=None,
            rpc_urls=tuple(urls), native_symbol="", explorer_tx=""), transport=settle._pool_transport, timeout=15.0)
        rows = pool.check(logs_filter=flt)
        if flt is not None:
            scan_ok = sum(1 for r in rows if r["usable"])
        report.append({"list": label, "rows": rows})
    if args.json:
        print(_json.dumps({"chain": x402.chain(), "chain_id": chain_id, "window": window, "lists": report}, indent=2))
        return 0 if scan_ok else 1
    print(f"{BOLD}AIMarket Hub — rpc-check{RESET}  {x402.chain()} ({chain_id}), eth_getLogs window {window} blocks")
    for entry in report:
        print(f"\n{BOLD}{entry['list']}{RESET}")
        if not entry["rows"]:
            print(f"  {RED}✗{RESET} {entry.get('detail', '')}")
        for r in entry["rows"]:
            mark = f"{GREEN}✓{RESET}" if r["usable"] else f"{RED}✗{RESET}"
            lag = "-" if r["lag"] is None else r["lag"]
            note = f"  {DIM}{r['detail']}{RESET}" if r["detail"] else ""
            print(f"  {mark} {r['url']:<44} lag {lag!s:>3}  {r['ms']:>5} ms  logs {r['logs'] or '-'}{note}")
    verdict = f"{GREEN}{scan_ok} node(s){RESET}" if scan_ok else f"{RED}no node{RESET}"
    print(f"\n{verdict} can serve the deposit watcher's scan; calls rotate over the list and a refusing node rests.")
    return 0 if scan_ok else 1


def _cmd_doctor(args) -> int:
    """Run on this hub the same assay another hub runs before admitting it.

    Being conformant and being admitted are different questions, and only the second decides
    whether anyone indexes you. On 2026-10-12 a hub set up from the operator quickstart passed
    the protocol conformance runner 24/24 and still landed in `review` at the assay. This runs
    `federation_assay.run_assay` itself — not a re-implementation that could drift — from a
    throwaway identity and database, and never calls the LLM judge (the one check that needs a
    token, and the operator's own key would be spent on it).
    """
    import contextlib
    import logging
    import tempfile

    from aimarket_hub import federation_assay as fa
    from aimarket_hub.signing import Signer

    config = HubConfig()
    url = (args.url or config.hub_url or "").strip().rstrip("/")
    if not url:
        print(f"{RED}✗{RESET} no URL: pass --url or set AIMARKET_HUB_URL")
        return 1
    if not args.json:
        print(f"{BOLD}AIMarket Hub — doctor{RESET}  {url}")
        _release_notice()
        if not _public_host(url):
            print(f"  {YELLOW}!{RESET} {url} is not a public address — other hubs cannot reach it, "
                  f"so `url_public` fails below. Everything else is still checked.")
        if not os.environ.get("AIMARKET_ADMIN_TOKEN"):
            print(f"  {YELLOW}!{RESET} AIMARKET_ADMIN_TOKEN is not set: you cannot approve peers or "
                  f"top up buyers (`aimarket quickstart` generates one).")
        if (config.hub_name or "").strip().lower() in ("aimarket hub", ""):
            print(f"  {YELLOW}!{RESET} the hub is called {config.hub_name!r}: give it your own name "
                  f"(quickstart --name); there is no trademark licence for “AIMarket”.")

    # Nothing answering is one problem with one fix, not eleven failed checks.
    import httpx

    try:
        httpx.get(f"{url}/.well-known/ai-market.json", timeout=10, follow_redirects=False)
    except httpx.HTTPError as exc:
        print(f"  {RED}✗{RESET} nothing answers at {url} ({type(exc).__name__}).")
        if not _public_host(url):
            print(f"      Start the hub first — `aimarket serve` in another terminal — and run doctor again.")
        else:
            print(f"      Is the hub running, and does DNS/TLS for this name point at it?")
        return 1

    with tempfile.TemporaryDirectory(prefix="aimarket-doctor-") as tmp:
        acfg = HubConfig()
        acfg.db_path = str(Path(tmp) / "assayer.db")
        acfg.signing_key_path = str(Path(tmp) / "assayer_key")
        acfg.federation_judge_key = ""
        acfg.federation_auto_admit = False
        acfg.federation_assay_sandbox = True
        quiet = logging.getLogger("aimarket_hub")
        previous = quiet.level
        quiet.setLevel(logging.ERROR)
        try:
            with contextlib.redirect_stderr(open(os.devnull, "w")):
                db = HubDatabase(acfg.db_path)
                signer = Signer(acfg.signing_key_path, pqc=False)
            local = not _public_host(url)
            saved_guard = fa._crawler._url_is_safe
            get_json = post_json = None
            if local:
                # Reach a local hub anyway, so a pre-deploy run checks everything but
                # reachability. `url_public` is still scored from the real guard below.
                import httpx

                async def get_json(target: str) -> dict:
                    async with httpx.AsyncClient(timeout=20) as client:
                        return (await client.get(target)).json()

                async def post_json(target: str, body: dict, headers: dict) -> dict:
                    async with httpx.AsyncClient(timeout=20) as client:
                        resp = await client.post(target, json=body, headers=headers)
                        try:
                            parsed = resp.json()
                        except ValueError:
                            parsed = {}
                        return {"http_status": resp.status_code, "json": parsed,
                                "bytes": len(resp.content)}

                fa._crawler._url_is_safe = lambda _u, *_a, **_k: True
            try:
                dossier = asyncio.run(fa.run_assay(
                    url, config=acfg, db=db, signer=signer,
                    get_json=get_json, post_json=post_json, crawl_on_admit=False,
                ))
            except Exception as exc:
                # The assay must turn anything a peer publishes into a failed check. If it raises
                # instead, that is our bug, and a traceback hides the one useful fact: the
                # operator did nothing wrong by running this (2026-10-21, a string signature).
                from aimarket_hub import __version__

                if args.json:
                    print(json.dumps({"url": url, "verdict": None, "assay_error":
                                      f"{type(exc).__name__}: {str(exc)[:200]}",
                                      "hub_version": __version__}, indent=2))
                    return 1
                print(f"  {RED}✗{RESET} the assay itself crashed on what {url} publishes: "
                      f"{type(exc).__name__}: {str(exc)[:200]}")
                print(f"      This is a bug in aimarket-hub {__version__}, not a verdict. Please report "
                      f"it: https://github.com/alexar76/aimarket-hub/issues/new?template=admission.yml")
                return 1
            finally:
                fa._crawler._url_is_safe = saved_guard
            if local:
                dossier["verdict_once_public"] = fa.score_verdict(dossier.get("checks", []))
                for check in dossier.get("checks", []):
                    if check.get("id") == "url_public":
                        check["ok"] = False
                        check["detail"] = "not a public address (checked locally anyway)"
                dossier["verdict"] = fa.score_verdict(dossier.get("checks", []))
        finally:
            quiet.setLevel(previous)

    if args.json:
        print(json.dumps(dossier, indent=2, default=str))
        return 0 if dossier.get("verdict") == "pass" else 1

    marks = {True: f"{GREEN}✓{RESET}", False: f"{RED}✗{RESET}", None: f"{DIM}·{RESET}"}
    print()
    for check in dossier.get("checks", []):
        cid = str(check.get("id") or "")
        if cid in ("llm_verdict", "sandbox_judge"):
            continue
        ok = check.get("ok")
        # A failed check's detail is the instruction for fixing it; cut at 110 it lost the half
        # that says how (the §7.3.1 object shape). Passing and skipped rows stay short.
        detail = str(check.get("detail") or "")[:400 if ok is False else 110]
        print(f"  {marks.get(ok, marks[None])} {cid}{DIM}{'  ' + detail if detail else ''}{RESET}")
        if ok is False and cid in _DOCTOR_HINTS:
            print(f"      {YELLOW}{_DOCTOR_HINTS[cid]}{RESET}")
    sandbox = dossier.get("sandbox") or {}
    if sandbox.get("attempted"):
        print(f"  {DIM}sandbox ran {sandbox.get('capability_id')} ({sandbox.get('probe_kind')}), "
              f"HTTP {sandbox.get('http_status')}{RESET}")
    verdict = str(dossier.get("verdict") or "")
    colour = GREEN if verdict == "pass" else (YELLOW if verdict == "review" else RED)
    print()
    print(f"  verdict: {colour}{BOLD}{verdict or 'unknown'}{RESET}  "
          f"{DIM}(the LLM judge is not consulted here; a hub with a judge token may still veto){RESET}")
    once_public = str(dossier.get("verdict_once_public") or "")
    if once_public:
        print(f"  once it is public: {GREEN if once_public == 'pass' else YELLOW}{BOLD}{once_public}"
              f"{RESET}  {DIM}— everything but reachability was checked{RESET}")
    if verdict == "pass":
        print("  A hub with auto-admit on will index you after your knock:")
        print(f"    curl -X POST https://modelmarket.dev/ai-market/v2/federation/announce \\")
        print(f"      -H 'Content-Type: application/json' \\")
        print(f"      -d '{{\"hub_url\": \"{url}\", \"hub_name\": \"{config.hub_name}\"}}'")
    else:
        print(f"  Fix the ✗ lines and run doctor again. Guide: {JOIN_GUIDE}")
    return 0 if verdict == "pass" else 1


def _cmd_publish(args) -> int:
    import httpx

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"{YELLOW}Manifest not found: {manifest_path}{RESET}")
        return 1

    config = HubConfig()
    hub_url = (args.hub or config.hub_url).rstrip("/")
    token = (args.token or os.environ.get("AIMARKET_PUBLISH_TOKEN", "")).strip()
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(f"{BOLD}Publish → {hub_url}{RESET}")
    print(f"  {body.get('product_id')}/{body.get('capability_id')}")

    try:
        resp = httpx.post(
            f"{hub_url}/ai-market/v2/supply/register",
            json=body,
            headers=headers,
            timeout=30,
        )
        data = resp.json()
        if resp.status_code == 200:
            print(f"  {GREEN}✓ published{RESET}  ${data.get('price_per_call_usd', '?')}/call")
            print(f"  search: {data.get('search_hint', '')}")
            return 0
        print(f"  {YELLOW}{resp.status_code}{RESET} {data.get('detail', data)}")
        return 1
    except Exception as exc:
        print(f"  Error: {exc}")
        return 1


def _cmd_crawl() -> int:
    config = HubConfig()
    db = HubDatabase(config.db_path)
    crawler = Crawler(config=config, db=db)

    async def _run():
        try:
            return await crawler.crawl()
        finally:
            await crawler.close()

    stats = asyncio.run(_run())
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_search(args) -> int:
    config = HubConfig()
    db = HubDatabase(config.db_path)
    results = db.search_capabilities(args.query, limit=args.limit)

    if args.json:
        print(json.dumps([{
            "capability_id": r.capability_id,
            "product_id": r.product_id,
            "source_hub": r.source_hub,
            "source_hub_name": r.source_hub_name,
            "price": r.price_per_call_usd,
            "routed_price": r.routed_price_usd,
            "trust": r.trust_score,
            "description": r.description,
        } for r in results], indent=2))
        return 0

    print(f"\n{BOLD}Search: \"{args.query}\"{RESET}\n")
    for i, r in enumerate(results[:args.limit], 1):
        hub_tag = f"{GREEN}[{r.source_hub_name or 'local'}]{RESET}"
        trust = r.trust_score
        price = r.routed_price_usd or r.price_per_call_usd
        print(f"  {i}. {BOLD}{r.capability_id}{RESET} @ {r.product_id}  {hub_tag}")
        print(f"     {r.description[:100]}")
        print(f"     ${price:.2f}  trust={trust:.2f}  latency={r.p50_latency_ms}ms\n")
    return 0


def _cmd_invoke(args) -> int:
    import httpx

    config = HubConfig()
    parts = args.capability_ref.split("/", 1)
    product_id = parts[0]
    capability_id = parts[1] if len(parts) > 1 else parts[0]
    inp = json.loads(args.input)

    print(f"{BOLD}Invoke: {product_id}/{capability_id}{RESET}")
    print(f"  Target hub: {args.hub}")

    try:
        resp = httpx.post(
            f"{config.hub_url}/ai-market/v2/invoke",
            json={
                "product_id": product_id,
                "capability_id": capability_id,
                "source_hub": args.hub,
                "input": inp,
            },
            timeout=60,
        )
        if resp.status_code == 402:
            print(f"  {DIM}402 Payment Required — see X-Payment-Required{RESET}")
            print(json.dumps(resp.json(), indent=2))
            return 0
        data = resp.json()
        ok = data.get("success", False)
        mark = "✓" if ok else "✗"
        color = GREEN if ok else RESET
        print(f"  {color}{mark} ${data.get('price_usd', '?')}  {data.get('latency_ms', '?')}ms{RESET}")
        if ok:
            print(json.dumps(data.get("result", {}), indent=2))
        return 0 if ok else 1
    except Exception as exc:
        print(f"  Error: {exc}")
        return 1


def _cmd_peers() -> int:
    config = HubConfig()
    db = HubDatabase(config.db_path)
    peers = db.list_peers()

    print(f"\n{BOLD}Known Peers ({len(peers)}){RESET}\n")
    for p in peers:
        print(f"  {BOLD}{p.name}{RESET}  {DIM}{p.url}{RESET}")
        print(f"    capabilities: {p.capabilities_count}  trust: {p.trust_score:.2f}  depth: {p.depth}")
        print(f"    last crawl: {p.last_crawl}\n")
    return 0


def _cmd_stats() -> int:
    config = HubConfig()
    db = HubDatabase(config.db_path)
    s = db.stats_summary()

    print(f"\n{BOLD}Hub Statistics{RESET}\n")
    for k, v in s.items():
        label = k.replace("_", " ").title()
        print(f"  {label}: {GREEN}{v}{RESET}")
    return 0


def _cmd_trust(args) -> int:
    config = HubConfig()
    db = HubDatabase(config.db_path)
    scorer = TrustScorer(db)
    score = scorer.compute_score(args.hub_url)
    details = scorer.score_details(args.hub_url)

    print(f"\n{BOLD}Trust Score: {args.hub_url}{RESET}\n")
    print(f"  Score: {GREEN}{score:.4f}{RESET}")
    print(f"  Weights: {details.get('weights', {})}")
    return 0


def _entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
