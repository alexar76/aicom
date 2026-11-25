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

    def lineage(self, memory_id: str) -> dict | None:
        """The ledger's receipt chain for a memory, or None when the ledger is unreachable."""
        if not self.settings.provenance_url:
            return None
        try:
            response = httpx.get(
                f"{self.settings.provenance_url.rstrip('/')}/v1/lineage/{memory_id}",
                headers={"Authorization": f"Bearer {self.settings.provenance_token}"},
                timeout=4,
            )
            response.raise_for_status()
            lineage = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        return lineage if isinstance(lineage, dict) else None

    def verify_receipt(self, receipt_id: str) -> dict | None:
        """The ledger's verdict on one receipt, or None when the ledger is unreachable."""
        if not self.settings.provenance_url:
            return None
        try:
            response = httpx.post(
                f"{self.settings.provenance_url.rstrip('/')}/v1/receipts/verify",
                json={"receipt_id": receipt_id},
                headers={"Authorization": f"Bearer {self.settings.provenance_token}"},
                timeout=4,
            )
            if response.status_code == 404:
                return {"receipt_id": receipt_id, "valid": False, "checks": {"exists": False}}
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    def created_receipt(self, unit: MemoryUnit) -> dict | None:
        """The ledger's ``created`` receipt for this unit's content, if one exists: an earlier attest
        may have reached the ledger while its answer never reached us. Only a receipt in the name
        of the unit's owner counts; one with the same content hash appended by anyone else (a hub
        buyer, say) is not this unit's creation. None also when the ledger is unreachable."""
        lineage = self.lineage(unit.id)
        for receipt in (lineage or {}).get("receipts") or []:
            if (receipt.get("event_type") == "created" and receipt.get("content_hash") == unit.content_hash
                    and receipt.get("actor_id") == unit.owner_id):
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
