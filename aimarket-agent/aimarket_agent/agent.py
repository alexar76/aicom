"""AIMarketAgent — The reference consumer for Protocol v2.

Encapsulates the full autonomous cycle:
    discovery → channel open → invoke (safety-gated) → settle → bill of materials.

Lightweight: only httpx + cryptography dependencies. No FastAPI, no database.
Designed to be pip-installed by any AI agent runtime.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import httpx


class AIMarketAgent:
    """Reference consumer for AIMarket Protocol v2.

    Usage:
        agent = AIMarketAgent(base_url="https://hub.example.com", budget=3.00)
        result = agent.run("translate spec to 5 langs + legal review")
        print(result["bill_of_materials"])
    """

    def __init__(
        self,
        base_url: str,
        budget: float = 3.0,
        timeout: float = 120.0,
        affiliate_id: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.budget = budget
        self.timeout = timeout
        self.affiliate_id = affiliate_id
        self.session = httpx.Client(timeout=timeout)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _open_channel(self) -> str:
        """Try to open a payment channel; return channel_id or "" if hub has no channels plugin."""
        try:
            ch = self.session.post(
                self._url("/ai-market/v2/channel/open"),
                json={"deposit_usd": self.budget, "tx_hash": f"agent-{int(time.time())}"},
            )
            if ch.status_code == 404:
                return ""  # channels plugin not installed on this hub
            ch.raise_for_status()
            return (ch.json().get("channel") or {}).get("channel_id", "")
        except Exception:
            return ""

    def _close_channel(self, channel_id: str) -> dict[str, Any]:
        if not channel_id:
            return {"skipped": "no channel was opened"}
        try:
            r = self.session.post(
                self._url("/ai-market/v2/channel/close"),
                json={"channel_id": channel_id, "settle_tx_hash": f"agent-settle-{channel_id}"},
            )
            r.raise_for_status()
            return r.json().get("settlement") or {}
        except Exception:
            return {"error": "settle failed"}

    def run(self, task: str) -> dict[str, Any]:
        """Execute the full autonomous cycle for *task*.

        Returns bill-of-materials dict with all receipts.
        """
        result: dict[str, Any] = {"task": task, "ok": False}

        # ── Phase 1: Discovery ──────────────────────────────────
        try:
            wk = self.session.get(self._url("/.well-known/ai-market.json"))
            wk.raise_for_status()
        except Exception as exc:
            return {**result, "error": f"discovery failed: {exc}"}

        # Hub v3 exposes capability discovery via GET /ai-market/v2/search.
        # Older drafts proposed POST /ai-market/discover with a "plan" response —
        # we fall back to v2 search and synthesise a one-step plan per match.
        plan: list[dict[str, Any]] = []
        try:
            search = self.session.get(
                self._url("/ai-market/v2/search"),
                params={
                    "intent": task,
                    "budget": str(self.budget),
                    "limit": "6",
                },
            )
            search.raise_for_status()
            matches = search.json().get("matches") or []
            for m in matches:
                plan.append({
                    "product_id": m.get("product_id", ""),
                    "capability_id": m.get("capability_id", ""),
                    "source_hub": m.get("source_hub", "local"),
                    "draft_input": {"text": task},
                    "est_price_usd": m.get("routed_price_usd") or m.get("price_per_call_usd", 0),
                })
        except Exception as exc:
            return {**result, "error": f"search failed: {exc}"}

        if not plan:
            return {**result, "plan": [], "note": "no matching capabilities"}

        # Cap plan at first match for predictable spend; multi-step DAGs are a
        # future protocol-level feature (pipelines endpoint).
        plan = plan[:1]
        result["plan"] = plan
        result["estimated_total_usd"] = sum(s["est_price_usd"] for s in plan)

        # ── Phase 2: Channel open (optional) ──────────────────
        channel_id = self._open_channel()
        result["channel_id"] = channel_id

        # ── Phase 3: Invoke each step ──────────────────────────
        results: list[dict[str, Any]] = []
        context: dict[str, Any] = {}
        total_spent = 0.0
        all_ok = True

        for step in plan:
            pid = step["product_id"]
            cid = step["capability_id"]
            source_hub = step.get("source_hub", "local")
            inp = dict(step.get("draft_input") or {})
            if context:
                inp.setdefault("context", context)

            headers: dict[str, str] = {}
            if channel_id:
                headers["X-Payment-Channel"] = channel_id
            if self.affiliate_id:
                headers["X-AIMarket-Affiliate"] = self.affiliate_id

            try:
                r = self.session.post(
                    self._url("/ai-market/v2/invoke"),
                    json={
                        "product_id": pid,
                        "capability_id": cid,
                        "source_hub": source_hub,
                        "input": inp,
                    },
                    headers=headers,
                )
            except Exception as exc:
                results.append({"error": str(exc), "capability_id": cid})
                all_ok = False
                break

            if r.status_code == 403:
                rejection = r.json()
                results.append({
                    "capability_id": cid,
                    "safety_blocked": True,
                    "category": rejection.get("category"),
                    "reason": rejection.get("reason"),
                })
                all_ok = False
                break

            if r.status_code == 402:
                results.append({
                    "capability_id": cid,
                    "payment_required": True,
                    "detail": r.json(),
                })
                all_ok = False
                break

            if not r.is_success:
                results.append({"error": f"HTTP {r.status_code}", "capability_id": cid})
                all_ok = False
                break

            body = r.json()
            price_val = body.get("price_usd", 0) or 0
            total_spent += price_val
            results.append(body)

            if body.get("success"):
                context = body.get("result") or {}
            else:
                all_ok = False
                break

        # ── Phase 4: Settle ─────────────────────────────────────
        settlement = self._close_channel(channel_id)

        # ── Phase 5: Bill of materials ──────────────────────────
        bom: dict[str, Any] = {
            "task": task,
            "plan": plan,
            "results": results,
            "settlement": settlement,
            "channel_id": channel_id,
            "total_spent_usd": round(total_spent, 4),
            "all_ok": all_ok,
            "protocol_version": "v2",
            "agent_version": "2.0.0",
        }

        result["ok"] = all_ok
        result["bill_of_materials"] = bom
        result["total_spent_usd"] = round(total_spent, 4)
        return result

    def discover(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search for capabilities without invoking."""
        try:
            r = self.session.get(
                self._url("/ai-market/v2/search"),
                params={"intent": query, "budget": str(self.budget), "limit": str(limit)},
            )
            r.raise_for_status()
            return r.json().get("matches") or []
        except Exception:
            return []

    def invoke_single(
        self,
        product_id: str,
        capability_id: str,
        input_payload: dict[str, Any],
        source_hub: str = "local",
    ) -> dict[str, Any]:
        """Invoke a single capability directly."""
        channel_id = self._open_channel()
        headers: dict[str, str] = {}
        if channel_id:
            headers["X-Payment-Channel"] = channel_id

        try:
            r = self.session.post(
                self._url("/ai-market/v2/invoke"),
                json={
                    "product_id": product_id,
                    "capability_id": capability_id,
                    "source_hub": source_hub,
                    "input": input_payload,
                },
                headers=headers,
            )
        finally:
            self._close_channel(channel_id)

        if r.status_code == 403:
            return {"safety_blocked": True, **r.json()}
        return r.json()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "AIMarketAgent":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
