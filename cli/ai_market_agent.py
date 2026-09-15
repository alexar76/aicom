#!/usr/bin/env python3
"""
AI Market reference agent (Protocol v1)
=======================================
Hello-world client for AI-to-AI discovery, payment channels, and invoke.

Usage:
  python cli/ai_market_agent.py "translate spec to 5 langs + legal review" --budget 3.0
  python cli/ai_market_agent.py --base-url http://127.0.0.1:9080 "summarize release notes"
  python cli/ai_market_agent.py --json "translate spec" --budget 2.0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import requests

# Terminal formatting (no dependencies beyond stdlib)
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_RESET = "\033[0m"
_CHECK = "✓"
_CROSS = "✗"
_DOTS = ".."


def _fmt(label: str, value: str = "", color: str = "") -> str:
    """Format a log line label."""
    c = color or _DIM
    return f"{c}[{label}]{_RESET} {value}"


def _price(usd: float) -> str:
    return f"${usd:.2f}"


def _elapsed(seconds: float) -> str:
    return f"{seconds:.1f}s"


class AIMarketAgent:
    """Reference consumer for AI Market Protocol v1.

    Encapsulates the full autonomous cycle:
    discovery → channel open → invoke → settle → bill of materials.
    """

    def __init__(
        self,
        base_url: str,
        budget: float = 3.0,
        timeout: float = 120.0,
        json_output: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.budget = budget
        self.timeout = timeout
        self.json_output = json_output
        self.session = requests.Session()
        self._log_lines: list[str] = []

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _log(self, label: str, msg: str = "", color: str = "") -> None:
        line = _fmt(label, msg, color)
        if not self.json_output:
            print(line, file=sys.stderr)
        self._log_lines.append(line)

    def run(self, task: str) -> dict[str, Any]:
        """Execute the full autonomous cycle for *task*.

        Returns the bill-of-materials dict.
        """
        # ── Phase 1: Discovery ──────────────────────────────────────
        self._log("discover", f"indexing {self._url('/.well-known/ai-market.json')}")
        try:
            wk = self.session.get(
                self._url("/.well-known/ai-market.json"), timeout=self.timeout
            )
            wk.raise_for_status()
        except requests.RequestException as exc:
            self._log("error", f"well-known fetch failed: {exc}", _RED)
            if self.json_output:
                print(json.dumps({"error": str(exc), "phase": "discovery"}))
            return {"error": str(exc)}
        meta = wk.json()
        n_caps = meta.get("capabilities_count", "?")
        n_prods = meta.get("products_count", "?")
        self._log(
            "discover",
            f"{n_caps} capabilities across {n_prods} products",
            _GREEN,
        )

        self._log("discover", f"searching: \"{task[:80]}\"")
        try:
            disc = self.session.post(
                self._url("/ai-market/discover"),
                json={"query": task, "budget_usd": self.budget, "limit": 6},
                timeout=self.timeout,
            )
            disc.raise_for_status()
        except requests.RequestException as exc:
            self._log("error", f"discover failed: {exc}", _RED)
            if self.json_output:
                print(json.dumps({"error": str(exc), "phase": "discover"}))
            return {"error": str(exc)}
        plan_data = disc.json()
        plan = plan_data.get("plan") or []
        est = plan_data.get("estimated_total_usd", 0)
        if not plan:
            self._log("plan", "no matching capabilities found", _YELLOW)
            if self.json_output:
                print(json.dumps(plan_data))
            return plan_data
        steps = " → ".join(s["capability_id"] for s in plan)
        self._log("plan", f"{steps}  (est {_price(est)})", _GREEN)

        # ── Phase 2: Channel open ───────────────────────────────────
        try:
            ch = self.session.post(
                self._url("/ai-market/channel/open"),
                json={"deposit_usd": self.budget, "tx_hash": f"demo-{int(time.time())}"},
                timeout=self.timeout,
            )
            ch.raise_for_status()
        except requests.RequestException as exc:
            self._log("error", f"channel open failed: {exc}", _RED)
            if self.json_output:
                print(json.dumps({"error": str(exc), "phase": "channel_open"}))
            return {"error": str(exc)}
        channel = ch.json().get("channel") or {}
        ch_id = channel.get("channel_id", "?")
        self._log("channel", f"opened {ch_id} with {_price(self.budget)} deposit")

        # ── Phase 3: Invoke each step ───────────────────────────────
        results: list[dict[str, Any]] = []
        context: dict[str, Any] = {}
        all_ok = True
        for step in plan:
            pid = step["product_id"]
            cid = step["capability_id"]
            inp = dict(step.get("draft_input") or {})
            if context:
                inp.setdefault("context", context)
            t0 = time.time()
            try:
                r = self.session.post(
                    self._url(f"/capabilities/{pid}/{cid}/invoke"),
                    json={"input": inp},
                    headers={"X-Payment-Channel": ch_id},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                self._log("call", f"{cid} request failed: {exc}", _RED)
                all_ok = False
                break
            elapsed = time.time() - t0
            if r.status_code == 402:
                pay_info = r.json().get("payment_required", {})
                amt = pay_info.get("amount", "?")
                self._log(
                    "call",
                    f"{cid} payment required ({amt}), retry with on-chain tx",
                    _YELLOW,
                )
                all_ok = False
                break
            if not r.ok:
                self._log("call", f"{cid} HTTP {r.status_code}: {r.text[:200]}", _RED)
                all_ok = False
                break
            body = r.json()
            price_val = body.get("price_usd", 0)
            ok = body.get("success")
            mark = _CHECK if ok else _CROSS
            color = _GREEN if ok else _RED
            self._log(
                "call",
                f"{cid} {_DOTS * 6} {_price(price_val)} {mark} {_elapsed(elapsed)}",
                color,
            )
            results.append(body)
            if ok:
                context = body.get("result") or {}
            else:
                self._log("call", f"{cid} returned success=false", _RED)
                all_ok = False
                break

        # ── Phase 4: Settle ─────────────────────────────────────────
        try:
            settle = self.session.post(
                self._url("/ai-market/channel/close"),
                json={"channel_id": ch_id, "settle_tx_hash": f"demo-settle-{ch_id}"},
                timeout=self.timeout,
            )
            settle.raise_for_status()
        except requests.RequestException as exc:
            self._log("error", f"settle failed: {exc}", _RED)
            if self.json_output:
                print(json.dumps({"error": str(exc), "phase": "settle"}))
            return {"error": str(exc)}
        st = settle.json().get("settlement") or {}
        used = st.get("used_usd", 0)
        refund = st.get("refund_usd", 0)
        self._log(
            "settle",
            f"used {_price(used)}, refund {_price(refund)}",
            _GREEN,
        )

        # ── Phase 5: Bill of materials ──────────────────────────────
        bom: dict[str, Any] = {
            "task": task,
            "plan": plan,
            "results": results,
            "settlement": st,
            "channel_id": ch_id,
            "all_ok": all_ok,
        }
        out_path = "bill_of_materials.json"
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(bom, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            self._log("error", f"cannot write {out_path}: {exc}", _RED)
        else:
            self._log("saved", out_path)

        if self.json_output:
            print(json.dumps(bom, indent=2, ensure_ascii=False))
        return bom


def main() -> int:
    p = argparse.ArgumentParser(
        description="AI Market Protocol v1 reference agent"
    )
    p.add_argument(
        "task",
        nargs="?",
        default="translate spec to 5 langs + legal review",
        help="Natural-language task description",
    )
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:9080",
        help="Base URL of the AI-Factory instance",
    )
    p.add_argument(
        "--budget",
        type=float,
        default=3.0,
        help="Maximum budget in USD (default: 3.00)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP request timeout in seconds (default: 120)",
    )
    p.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit bill_of_materials.json to stdout instead of logging to stderr",
    )
    args = p.parse_args()
    agent = AIMarketAgent(
        base_url=args.base_url,
        budget=args.budget,
        timeout=args.timeout,
        json_output=args.json_output,
    )
    try:
        result = agent.run(args.task)
    except KeyboardInterrupt:
        if not args.json_output:
            print(_fmt("abort", "interrupted", _YELLOW), file=sys.stderr)
        return 130
    except Exception as exc:
        if not args.json_output:
            print(_fmt("error", str(exc), _RED), file=sys.stderr)
        return 1
    if result.get("error"):
        return 1
    if not result.get("all_ok", True):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
