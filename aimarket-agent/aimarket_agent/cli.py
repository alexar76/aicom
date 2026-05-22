#!/usr/bin/env python3
"""AIMarket Agent CLI — pip-installable reference consumer.

Usage:
    aimarket-agent run "translate spec to 5 langs" --budget 3.00
    aimarket-agent search "legal review"
    aimarket-agent invoke prod-xxx/translate.multi@v2 --input '{"text":"hello"}'
"""

from __future__ import annotations

import argparse
import json
import sys

from aimarket_agent.agent import AIMarketAgent

_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_RESET = "\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIMarket Agent — AI-to-AI protocol consumer"
    )
    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Execute full autonomous cycle")
    run_p.add_argument("task", nargs="?", default="translate spec to 5 langs + legal review")
    run_p.add_argument("--base-url", default="http://127.0.0.1:9080")
    run_p.add_argument("--budget", type=float, default=3.0)
    run_p.add_argument("--affiliate", default="")
    run_p.add_argument("--json", action="store_true")

    # search
    search_p = sub.add_parser("search", help="Discover capabilities")
    search_p.add_argument("query", nargs="?", default="")
    search_p.add_argument("--base-url", default="http://127.0.0.1:9080")
    search_p.add_argument("--limit", type=int, default=8)
    search_p.add_argument("--json", action="store_true")

    # invoke
    invoke_p = sub.add_parser("invoke", help="Invoke a single capability")
    invoke_p.add_argument("capability_ref", help="product_id/capability_id")
    invoke_p.add_argument("--base-url", default="http://127.0.0.1:9080")
    invoke_p.add_argument("--input", default="{}", help="JSON input payload")
    invoke_p.add_argument("--budget", type=float, default=3.0)

    args = parser.parse_args()

    if args.command == "run":
        return _cmd_run(args)
    elif args.command == "search":
        return _cmd_search(args)
    elif args.command == "invoke":
        return _cmd_invoke(args)
    else:
        parser.print_help()
        return 0


def _cmd_run(args) -> int:
    agent = AIMarketAgent(
        base_url=args.base_url,
        budget=args.budget,
        affiliate_id=args.affiliate,
    )
    try:
        result = agent.run(args.task)
    except KeyboardInterrupt:
        print(f"{_YELLOW}Interrupted{_RESET}", file=sys.stderr)
        return 130
    finally:
        agent.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    if result.get("error"):
        print(f"[{_RED}error{_RESET}] {result['error']}", file=sys.stderr)
        return 1

    plan = result.get("plan") or []
    steps = " → ".join(s["capability_id"] for s in plan)
    est = result.get("estimated_total_usd", 0)
    print(f"[{_GREEN}plan{_RESET}] {steps}  (est ${est:.2f})")

    bom = result.get("bill_of_materials") or {}
    for r in bom.get("results") or []:
        if r.get("safety_blocked"):
            print(f"[{_RED}safety{_RESET}] {r['capability_id']} blocked: {r.get('category', '?')}")
            continue
        ok = r.get("success")
        mark = "✓" if ok else "✗"
        color = _GREEN if ok else _RED
        print(f"[{color}call{_RESET}] {r.get('capability_id', '?')} ${r.get('price_usd', 0):.2f} {mark}")

    settlement = bom.get("settlement") or {}
    used = settlement.get("used_usd", 0)
    refund = settlement.get("refund_usd", 0)
    print(f"[{_GREEN}settle{_RESET}] used ${used:.2f}, refund ${refund:.2f}")

    total = result.get("total_spent_usd", 0)
    print(f"[{_BOLD}total{_RESET}] ${total:.2f}")

    out_path = "bill_of_materials.json"
    with open(out_path, "w") as f:
        json.dump(bom, f, indent=2, ensure_ascii=False)
    print(f"[{_DIM}saved{_RESET}] {out_path}")

    return 0 if result.get("ok") else 1


def _cmd_search(args) -> int:
    agent = AIMarketAgent(base_url=args.base_url)
    try:
        matches = agent.discover(args.query, limit=args.limit)
    finally:
        agent.close()

    if args.json:
        print(json.dumps(matches, indent=2, ensure_ascii=False))
        return 0

    print(f"\n{_BOLD}Search: \"{args.query}\"{_RESET}\n")
    for i, m in enumerate(matches, 1):
        print(f"  {i}. {_BOLD}{m.get('capability_id', '?')}{_RESET}")
        print(f"     ${m.get('price_per_call_usd', 0):.2f} · {m.get('p50_latency_ms', '?')}ms")
        if m.get("source_hub_name"):
            print(f"     🌐 {m['source_hub_name']} (trust: {m.get('trust_score', '?')})")
        print()
    return 0


def _cmd_invoke(args) -> int:
    parts = args.capability_ref.split("/", 1)
    product_id = parts[0]
    capability_id = parts[1] if len(parts) > 1 else parts[0]
    inp = json.loads(args.input)

    agent = AIMarketAgent(base_url=args.base_url, budget=args.budget)
    try:
        result = agent.invoke_single(product_id, capability_id, inp)
    finally:
        agent.close()

    if result.get("safety_blocked"):
        print(f"[{_RED}safety{_RESET}] Blocked: {result.get('category')} — {result.get('reason')}")
        return 1

    ok = result.get("success", False)
    mark = "✓" if ok else "✗"
    color = _GREEN if ok else _RED
    print(f"[{color}invoke{_RESET}] {capability_id} ${result.get('price_usd', 0):.2f} {mark}")
    if ok:
        print(json.dumps(result.get("result", {}), indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
