from __future__ import annotations

import httpx

from .config import Settings
from .models import MemoryUnit, VerifyMemory


class TrustClients:
    def __init__(self, settings: Settings):
        self.settings = settings

    def attest(self, unit: MemoryUnit, event_type: str, actor_id: str, metadata: dict | None = None) -> dict | None:
        if not self.settings.provenance_url:
            return None
        payload = {
            "memory_id": unit.id,
            "event_type": event_type,
            "content_hash": unit.content_hash,
            "actor_id": actor_id,
            "source_refs": unit.source_refs,
            "parent_memory_ids": unit.parent_memory_ids,
            "metadata": metadata or {},
        }
        try:
            response = httpx.post(
                f"{self.settings.provenance_url.rstrip('/')}/v1/attestations",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.settings.provenance_token}",
                    "X-AIMarket-Internal-Token": __import__("os").getenv("AIMARKET_CAPABILITY_TOKEN", ""),
                },
                timeout=4,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None

    def created_receipt(self, unit: MemoryUnit) -> dict | None:
        """The ledger's ``created`` receipt for this unit's content, if one exists: an earlier attest
        may have reached the ledger while its answer never reached us. None also when the ledger is
        unreachable."""
        if not self.settings.provenance_url:
            return None
        try:
            response = httpx.get(
                f"{self.settings.provenance_url.rstrip('/')}/v1/lineage/{unit.id}",
                headers={"Authorization": f"Bearer {self.settings.provenance_token}"},
                timeout=4,
            )
            response.raise_for_status()
            receipts = response.json().get("receipts") or []
        except (httpx.HTTPError, ValueError):
            return None
        for receipt in receipts:
            if receipt.get("event_type") == "created" and receipt.get("content_hash") == unit.content_hash:
                return receipt
        return None

    def verify(self, unit: MemoryUnit, request: VerifyMemory) -> dict | None:
        if not self.settings.truth_url:
            return None
        try:
            response = httpx.post(
                f"{self.settings.truth_url.rstrip('/')}/v1/memories/verify",
                json={"memory_id": unit.id, **request.model_dump(mode="json")},
                headers={"X-AIMarket-Internal-Token": __import__("os").getenv("AIMARKET_CAPABILITY_TOKEN", "")},
                timeout=8,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None
