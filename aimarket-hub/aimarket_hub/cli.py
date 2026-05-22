#!/usr/bin/env python3
"""AIMarket Hub CLI — crawl, search, invoke, serve.

Usage:
  aimarket serve                     Start the hub API server
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
import sys

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import Crawler
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.trust import TrustScorer

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RESET = "\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(description="AIMarket Hub CLI")
    sub = parser.add_subparsers(dest="command")

    # serve
    sub.add_parser("serve", help="Start the hub API server")

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

    args = parser.parse_args()

    if args.command == "serve":
        return _cmd_serve()
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


def _cmd_serve() -> int:
    import uvicorn

    config = HubConfig()
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db)
    print(f"{GREEN}Hub API starting on http://0.0.0.0:9080{RESET}")
    uvicorn.run(app, host="0.0.0.0", port=9080, log_level="info")
    return 0


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
