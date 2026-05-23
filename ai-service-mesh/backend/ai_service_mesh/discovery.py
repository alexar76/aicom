"""Agent discovery — local registry + optional AIMarket hub federation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from ai_service_mesh.db import MeshStore
from ai_service_mesh.models import AgentOut, AgentStatus


@dataclass
class DiscoveryMatch:
    agent: AgentOut
    score: float
    price_usd: float
    source: str


class DiscoveryService:
    def __init__(
        self,
        store: MeshStore,
        hub_url: str = "",
        *,
        skip_demo_capabilities: bool = True,
    ) -> None:
        self._store = store
        self._hub_url = hub_url.rstrip("/")
        self._skip_demo = skip_demo_capabilities

    async def discover(
        self,
        intent: str,
        budget_usd: float,
        preferred: list[str],
    ) -> list[DiscoveryMatch]:
        matches: list[DiscoveryMatch] = []
        intent_lower = intent.lower()

        for agent in self._store.list_agents(verified_only=True):
            cap_hit = self._capability_score(agent.capabilities, intent_lower, preferred)
            if cap_hit <= 0:
                continue
            price = self._estimate_price(agent, budget_usd)
            if price > budget_usd:
                continue
            score = cap_hit * agent.trust_score
            matches.append(
                DiscoveryMatch(
                    agent=agent,
                    score=score,
                    price_usd=price,
                    source="local",
                )
            )

        if self._hub_url:
            hub_matches = await self._discover_from_hub(intent, budget_usd)
            matches.extend(hub_matches)

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:12]

    @staticmethod
    def _capability_score(caps: list[str], intent: str, preferred: list[str]) -> float:
        if preferred:
            for p in preferred:
                if any(p.lower() in c.lower() for c in caps):
                    return 1.0
            return 0.0
        for cap in caps:
            tokens = [t for t in cap.lower().replace("_", " ").split() if len(t) > 2]
            if any(t in intent for t in tokens):
                return 0.85
        return 0.0

    @staticmethod
    def _estimate_price(agent: AgentOut, budget: float) -> float:
        base = 0.25 + (1.0 - agent.trust_score) * 0.5
        return min(budget, round(base, 4))

    async def _discover_from_hub(self, intent: str, budget_usd: float) -> list[DiscoveryMatch]:
        url = f"{self._hub_url}/ai-market/v2/search"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    url,
                    params={"intent": intent, "budget": str(budget_usd), "limit": "6"},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except httpx.HTTPError:
            return []

        out: list[DiscoveryMatch] = []
        for m in data.get("matches") or []:
            product_id = str(m.get("product_id") or "")
            capability_id = str(m.get("capability_id") or "")
            if not product_id or not capability_id:
                continue
            description = str(m.get("description") or "")
            if self._skip_demo and "[DEMO]" in description:
                continue
            price = float(m.get("routed_price_usd") or m.get("price_per_call_usd") or 0)
            if price <= 0 or price > budget_usd:
                continue
            trust = float(m.get("trust_score") or 0.5)
            source_hub = str(m.get("source_hub") or "local")
            pseudo = AgentOut(
                id=f"hub_{product_id}_{capability_id}"[:48],
                name=str(m.get("name") or capability_id),
                endpoint_url=self._hub_url,
                status=AgentStatus.VERIFIED,
                trust_score=trust,
                capabilities=[capability_id, product_id],
                product_id=product_id,
                capability_id=capability_id,
                source_hub=source_hub,
                created_at="",
            )
            score = float(m.get("score") or trust)
            out.append(
                DiscoveryMatch(
                    agent=pseudo,
                    score=score,
                    price_usd=price,
                    source="hub",
                )
            )
        return out
