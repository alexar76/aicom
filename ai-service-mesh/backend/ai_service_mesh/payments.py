"""Escrow holds — persisted in SQLite or PostgreSQL (on-chain / TEE via aimarket-plugins in hardened deploys)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_service_mesh.db import MeshStore


@dataclass
class EscrowHold:
    id: str
    task_id: str
    agent_id: str
    amount_usd: float
    status: str  # held | released | refunded


class EscrowLedger:
    def __init__(self, store: MeshStore) -> None:
        self._store = store

    def hold(self, task_id: str, agent_id: str, amount_usd: float) -> EscrowHold:
        return self._store.create_escrow_hold(task_id, agent_id, amount_usd)

    def release(self, hold_id: str) -> EscrowHold:
        return self._store.update_escrow_status(hold_id, "released")

    def refund(self, hold_id: str) -> EscrowHold:
        return self._store.update_escrow_status(hold_id, "refunded")
