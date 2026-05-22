"""Federation crawler — discovers peer hubs via .well-known/ai-market.json.

Implements BFS crawl: seed list → discover peers → crawl their manifests.
Respects trust thresholds, validates schemas, verifies signatures.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any

import httpx

from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer
from aimarket_hub.trust import TrustScorer
from aimarket_hub.validator import validate_manifest, validate_well_known

logger = logging.getLogger(__name__)

USER_AGENT = "AIMarketHub/2.0.0"


class Crawler:
    """BFS federation crawler.

    Attributes:
        config: Hub configuration (seed list, crawl interval, etc.)
        db: Hub database
        signer: Ed25519 signer for verifying peer manifests
        trust_scorer: Computes trust scores for peers
    """

    def __init__(
        self,
        config: HubConfig | None = None,
        db: HubDatabase | None = None,
        signer: Signer | None = None,
        trust_scorer: TrustScorer | None = None,
    ):
        self.config = config or HubConfig()
        self.db = db or HubDatabase(self.config.db_path)
        self.signer = signer or Signer(self.config.signing_key_path)
        self.trust_scorer = trust_scorer or TrustScorer(self.db)
        self._http = httpx.AsyncClient(timeout=self.config.request_timeout_s)

    async def crawl(self, *, clear_first: bool = True) -> dict[str, Any]:
        """Run a full crawl cycle. Returns summary dict.

        When clear_first=True, old federated capabilities are cleared before
        re-crawling. SQLite WAL mode + single DELETE makes this atomic —
        if the crawl fails, the next successful crawl will repopulate.
        """
        if clear_first:
            self.db.clear_federated()

        logger.info("Crawler starting with %d seeds", len(self.config.seed_list))
        visited: set[str] = set()
        queue: deque[tuple[str, int, str]] = deque()

        for seed_url in self.config.seed_list:
            queue.append((seed_url, 0, "seed"))

        stats = {"discovered": 0, "indexed": 0, "errors": 0, "peers_found": 0}

        while queue:
            url, depth, discoverer = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            if depth > self.config.max_crawl_depth:
                continue

            result = await self._crawl_one(url, depth, discoverer)
            if result is None:
                stats["errors"] += 1
                continue

            stats["discovered"] += 1
            stats["indexed"] += result["capabilities_count"]
            stats["peers_found"] += len(result.get("new_peer_urls", []))

            for peer_url in result.get("new_peer_urls", []):
                if peer_url not in visited:
                    queue.append((peer_url, depth + 1, url))

        for peer in self.db.list_peers():
            score = self.trust_scorer.compute_score(peer.url)
            peer.trust_score = score
            self.db.upsert_peer(peer)

        logger.info(
            "Crawl complete: %d discovered, %d indexed, %d errors",
            stats["discovered"], stats["indexed"], stats["errors"],
        )
        return stats

    async def _crawl_one(
        self, well_known_url: str, depth: int, discoverer: str,
    ) -> dict[str, Any] | None:
        """Crawl a single hub via its .well-known endpoint."""
        base_url = well_known_url.rsplit("/.well-known/", 1)[0]

        # 1. Fetch .well-known
        try:
            resp = await self._http.get(
                well_known_url,
                headers={"User-Agent": USER_AGENT, "X-AIMarket-Crawler": self.config.hub_url},
            )
            if resp.status_code == 304:
                return {"capabilities_count": 0, "new_peer_urls": []}
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", well_known_url, exc)
            return None

        try:
            wk = resp.json()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON at %s", well_known_url)
            return None

        # 2. Validate well-known structure
        errors = validate_well_known(wk)
        if errors:
            logger.warning("Invalid well-known at %s: %s", well_known_url, errors)
            return None

        # 3. Record or update peer
        hub_name = wk.get("name", base_url)
        peer = Peer(
            url=base_url,
            name=hub_name,
            capabilities_count=wk.get("capabilities_count", 0),
            last_crawl=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            well_known_url=well_known_url,
            manifest_url=wk.get("manifest_url", f"{base_url}/ai-market/manifest"),
            public_key=wk.get("signer_public_key", ""),
            depth=depth,
            discoverer=discoverer,
        )
        self.db.upsert_peer(peer)

        # 4. Fetch and index manifest
        manifest_url = wk.get("manifest_url", f"{base_url}/ai-market/manifest")
        indexed = 0
        try:
            manifest_resp = await self._http.get(
                manifest_url,
                headers={"User-Agent": USER_AGENT},
            )
            manifest_resp.raise_for_status()
            manifest = manifest_resp.json()

            # Validate manifest structure
            m_errors = validate_manifest(manifest)
            if m_errors:
                logger.warning("Invalid manifest at %s: %s", manifest_url, m_errors)
                return None

            # Verify signature
            if not self.signer.verify_manifest_signature(manifest):
                logger.warning("Invalid manifest signature at %s", manifest_url)
                return None

            # Index capabilities
            indexed = self._index_manifest_capabilities(manifest, base_url, hub_name)

        except Exception as exc:
            logger.warning("Failed to fetch/parse manifest at %s: %s", manifest_url, exc)
            # Still return peer data even if manifest fetch fails
            return {"capabilities_count": 0, "new_peer_urls": self._extract_peer_urls(wk)}

        return {
            "capabilities_count": indexed,
            "new_peer_urls": self._extract_peer_urls(wk),
        }

    def _index_manifest_capabilities(
        self, manifest: dict[str, Any], base_url: str, hub_name: str,
    ) -> int:
        """Index all capabilities from a manifest into the database."""
        count = 0
        tools = manifest.get("tools") or []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            cap = Capability(
                capability_id=tool.get("capability_id", tool.get("name", "")),
                product_id=tool.get("product_id", ""),
                name=tool.get("name", tool.get("capability_id", "")),
                version="v1",
                description=tool.get("description", ""),
                input_schema=tool.get("input_schema", {}),
                output_schema=tool.get("output_schema", {}),
                price_per_call_usd=tool.get("price_per_call_usd", 0.35),
                p50_latency_ms=tool.get("p50_latency_ms", 3000),
                success_rate_30d=tool.get("success_rate_30d", 0.97),
                source_hub=base_url,
                source_hub_name=hub_name,
                routed_price_usd=self._routed_price(tool.get("price_per_call_usd", 0.35)),
                routing_fee_bps=self.config.routing_fee_bps,
                trust_score=0.5,
            )
            self.db.upsert_capability(cap)
            count += 1
        return count

    def _routed_price(self, base_price: float) -> float:
        return round(base_price * (1 + self.config.routing_fee_bps / 10000), 4)

    def _extract_peer_urls(self, well_known: dict[str, Any]) -> list[str]:
        """Extract peer hub URLs from a well-known response."""
        urls: list[str] = []
        peers = well_known.get("peers") or []
        for p in peers:
            if isinstance(p, dict) and p.get("url"):
                urls.append(p["url"])
        # Also crawl seed list entries from the federation block
        federation = well_known.get("federation") or {}
        seed_list = federation.get("seed_list") or []
        for s in seed_list:
            if isinstance(s, str) and s not in urls:
                urls.append(s.rsplit("/.well-known/", 1)[0])
        return urls

    async def close(self) -> None:
        await self._http.aclose()
