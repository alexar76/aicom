"""Capability NFT — Transferable Entitlements (#8)

Pre-pay for 1000 calls → NFT on your address → sell on secondary market,
transfer to sub-agent, use as gift card.

Liquidity for unused credits + viral distribution via "gift 100 Lyra calls to a friend."
Something Stripe fundamentally cannot do.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from aimarket_hub.signing import Signer


@dataclass
class CapabilityNFT:
    """Transferable pre-paid entitlement to capability invocations."""

    token_id: str
    capability_id: str
    product_id: str
    total_calls: int
    remaining_calls: int
    price_per_call_usd: float
    total_paid_usd: float
    owner_address: str  # Blockchain address
    original_owner: str
    minted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    transferred_at: Optional[str] = None
    transfer_count: int = 0
    metadata_uri: str = ""
    signature: str = ""

    @property
    def is_exhausted(self) -> bool:
        return self.remaining_calls <= 0

    @property
    def remaining_value_usd(self) -> float:
        return round(self.remaining_calls * self.price_per_call_usd, 4)

    def canonical(self) -> str:
        return (
            f"token_id:{self.token_id}"
            f"|capability_id:{self.capability_id}"
            f"|product_id:{self.product_id}"
            f"|total_calls:{self.total_calls}"
            f"|remaining_calls:{self.remaining_calls}"
            f"|owner:{self.owner_address}"
            f"|transfer_count:{self.transfer_count}"
        )

    def sign(self, signer: Signer) -> "CapabilityNFT":
        self.signature = signer.sign_canonical(self.canonical())
        return self

    def metadata(self) -> dict[str, Any]:
        """ERC-721 compatible metadata."""
        return {
            "name": f"AIMarket: {self.capability_id} × {self.total_calls} calls",
            "description": f"Pre-paid entitlement for {self.total_calls} invocations of {self.capability_id}",
            "image": "",  # Would be generated
            "attributes": [
                {"trait_type": "Capability", "value": self.capability_id},
                {"trait_type": "Total Calls", "value": self.total_calls},
                {"trait_type": "Price Per Call", "value": f"${self.price_per_call_usd}"},
                {"trait_type": "Transfer Count", "value": self.transfer_count},
            ],
        }


class NFTRegistry:
    """On-chain-capable NFT registry for capability entitlements.

    In production, this would be an ERC-721 contract on Base/Ethereum.
    Here it's an in-memory registry with the same interface.
    """

    def __init__(self, signer: Signer | None = None):
        self.signer = signer or Signer()
        self._nfts: dict[str, CapabilityNFT] = {}
        self._ownership: dict[str, list[str]] = {}  # address → [token_ids]

    def mint(
        self,
        capability_id: str,
        product_id: str,
        total_calls: int,
        price_per_call_usd: float,
        owner_address: str,
    ) -> CapabilityNFT:
        """Mint a new capability NFT."""
        token_id = f"nft_{int(time.time())}_{hashlib.sha256(f'{capability_id}:{owner_address}:{time.time()}'.encode()).hexdigest()[:8]}"

        total_paid = total_calls * price_per_call_usd
        nft = CapabilityNFT(
            token_id=token_id,
            capability_id=capability_id,
            product_id=product_id,
            total_calls=total_calls,
            remaining_calls=total_calls,
            price_per_call_usd=price_per_call_usd,
            total_paid_usd=total_paid,
            owner_address=owner_address,
            original_owner=owner_address,
        ).sign(self.signer)

        self._nfts[token_id] = nft
        self._ownership.setdefault(owner_address, []).append(token_id)
        return nft

    def transfer(self, token_id: str, from_address: str, to_address: str) -> dict[str, Any]:
        """Transfer NFT ownership."""
        nft = self._nfts.get(token_id)
        if not nft:
            return {"error": "NFT not found"}
        if nft.owner_address != from_address:
            return {"error": "not the owner"}
        if nft.is_exhausted:
            return {"error": "NFT exhausted — no calls remaining"}

        nft.owner_address = to_address
        nft.transferred_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        nft.transfer_count += 1
        nft.sign(self.signer)

        # Update ownership registry
        if from_address in self._ownership:
            self._ownership[from_address] = [t for t in self._ownership[from_address] if t != token_id]
        self._ownership.setdefault(to_address, []).append(token_id)

        return {
            "token_id": token_id,
            "transferred": True,
            "from": from_address,
            "to": to_address,
            "remaining_calls": nft.remaining_calls,
            "transfer_count": nft.transfer_count,
        }

    def consume_call(self, token_id: str) -> dict[str, Any]:
        """Consume one invocation from an NFT."""
        nft = self._nfts.get(token_id)
        if not nft:
            return {"error": "NFT not found"}
        if nft.is_exhausted:
            return {"error": "NFT exhausted", "token_id": token_id}

        nft.remaining_calls -= 1
        nft.sign(self.signer)

        return {
            "token_id": token_id,
            "consumed": True,
            "remaining_calls": nft.remaining_calls,
            "capability_id": nft.capability_id,
            "product_id": nft.product_id,
        }

    def gift(
        self,
        capability_id: str,
        product_id: str,
        call_count: int,
        price_per_call_usd: float,
        from_address: str,
        to_address: str,
    ) -> CapabilityNFT:
        """Gift calls to another address (mint + immediate transfer)."""
        nft = self.mint(capability_id, product_id, call_count, price_per_call_usd, from_address)
        self.transfer(nft.token_id, from_address, to_address)
        return self._nfts[nft.token_id]

    def get_nft(self, token_id: str) -> CapabilityNFT | None:
        return self._nfts.get(token_id)

    def get_owned(self, address: str) -> list[CapabilityNFT]:
        token_ids = self._ownership.get(address, [])
        return [self._nfts[tid] for tid in token_ids if tid in self._nfts]

    def stats(self) -> dict[str, Any]:
        total = len(self._nfts)
        active = sum(1 for n in self._nfts.values() if not n.is_exhausted)
        total_value = sum(n.remaining_value_usd for n in self._nfts.values() if not n.is_exhausted)
        total_transfers = sum(n.transfer_count for n in self._nfts.values())
        return {
            "total_nfts": total,
            "active_nfts": active,
            "exhausted_nfts": total - active,
            "total_remaining_value_usd": round(total_value, 2),
            "total_transfers": total_transfers,
            "avg_transfers_per_nft": round(total_transfers / max(total, 1), 2),
        }
