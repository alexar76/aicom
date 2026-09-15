#!/usr/bin/env python3
"""
Agent-to-agent economy demo — two AIMarket agents discover, pay, and invoke autonomously.

Demonstrates Protocol v2 end-to-end without human clicks:
  Agent A (buyer)  → search → channel → invoke capability on Hub
  Agent B (seller) → lists via Hub catalog (pre-seeded or factory-imported)

Usage:
  python scripts/demo_agent_to_agent.py --hub http://127.0.0.1:9083
  AIMARKET_SANDBOX_STUB_INVOKE=1 python scripts/demo_agent_to_agent.py  # offline hub

Exit 0 when both agents complete at least one successful invoke.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

try:
    from aimarket_agent import AIMarketAgent
except ImportError:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "aimarket-agent"))
    from aimarket_agent import AIMarketAgent


def run_agent(label: str, hub: str, budget: float, task: str) -> dict:
    agent = AIMarketAgent(base_url=hub, budget=budget, timeout=90.0)
    t0 = time.time()
    result = agent.run(task)
    result["agent_label"] = label
    result["elapsed_s"] = round(time.time() - t0, 2)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Two-agent AIMarket economy demo")
    parser.add_argument("--hub", default="http://127.0.0.1:9083", help="Hub base URL")
    parser.add_argument("--budget-a", type=float, default=2.0, help="Agent A channel deposit USD")
    parser.add_argument("--budget-b", type=float, default=2.5, help="Agent B channel deposit USD")
    args = parser.parse_args()

    hub = args.hub.rstrip("/")
    print(f"[demo] Hub: {hub}")
    print("[demo] Agent A — procurement bot (translate)")
    a = run_agent("buyer-A", hub, args.budget_a, "translate text to multiple languages")
    print(json.dumps({k: a[k] for k in ("agent_label", "ok", "error", "channel_id", "elapsed_s") if k in a}, indent=2))

    print("[demo] Agent B — research bot (summarize)")
    b = run_agent("buyer-B", hub, args.budget_b, "summarize long document executive summary")
    print(json.dumps({k: b[k] for k in ("agent_label", "ok", "error", "channel_id", "elapsed_s") if k in b}, indent=2))

    ok_a = bool(a.get("ok"))
    ok_b = bool(b.get("ok"))
    if ok_a and ok_b:
        print("[demo] SUCCESS — both agents completed paid autonomous cycles.")
        def _steps(res: dict) -> list:
            bom = res.get("bill_of_materials")
            if isinstance(bom, dict):
                return bom.get("results") or []
            return res.get("results") or []

        spent = sum(
            float(x.get("price_usd") or 0)
            for x in (_steps(a) + _steps(b))
            if isinstance(x, dict)
        )
        print(f"[demo] Combined spend (reported): ${spent:.4f}")
        return 0

    print("[demo] FAILED — one or both agents did not complete.", file=sys.stderr)
    def _fail_reason(res: dict) -> str:
        if res.get("error"):
            return str(res["error"])
        bom = res.get("bill_of_materials") or {}
        for step in bom.get("results") or []:
            if step.get("error"):
                return str(step["error"])
            if step.get("payment_required"):
                return "payment_required"
            if step.get("safety_blocked"):
                return f"safety:{step.get('category')}"
            if step.get("success") is False:
                return str(step.get("detail") or step)
        return "invoke did not succeed (check hub AIFACTORY_PUBLIC_URL or AIMARKET_SANDBOX_STUB_INVOKE)"

    if not ok_a:
        print(f"  Agent A: {_fail_reason(a)}", file=sys.stderr)
    if not ok_b:
        print(f"  Agent B: {_fail_reason(b)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
