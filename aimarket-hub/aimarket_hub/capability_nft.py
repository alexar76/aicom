"""Capability NFT — transferable pre-paid entitlements.

PRODUCTION (recommended): use OnChainNFTRegistry, which wraps the deployed
AIMarketCapabilityNFT ERC-721 (see contracts/evm/AIMarketCapabilityNFT.sol).
The contract is the authoritative source of ownership and remaining calls.

DEVELOPMENT: InMemoryNFTRegistry is provided for local testing. It loses
all state on restart — never use in production.

Factory:
    registry = make_nft_registry()  # picks on-chain if AIMARKET_NFT_CONTRACT set
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from aimarket_hub.signing import Signer

logger = logging.getLogger(__name__)


# ── Common types ─────────────────────────────────────────────────


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
    owner_address: str
    original_owner: str
    minted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    transferred_at: Optional[str] = None
    transfer_count: int = 0
    metadata_uri: str = ""
    signature: str = ""
    backend: str = "in-memory"  # "in-memory" or "on-chain:<chain>"

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
            "image": "",
            "attributes": [
                {"trait_type": "Capability", "value": self.capability_id},
                {"trait_type": "Total Calls", "value": self.total_calls},
                {"trait_type": "Price Per Call", "value": f"${self.price_per_call_usd}"},
                {"trait_type": "Transfer Count", "value": self.transfer_count},
                {"trait_type": "Backend", "value": self.backend},
            ],
        }


class NFTRegistryProtocol(Protocol):
    """Common interface for in-memory and on-chain registries."""

    def mint(
        self,
        capability_id: str,
        product_id: str,
        total_calls: int,
        price_per_call_usd: float,
        owner_address: str,
    ) -> CapabilityNFT: ...

    def transfer(
        self,
        token_id: str,
        from_address: str,
        to_address: str,
        from_signature_b64: str = "",
    ) -> dict[str, Any]: ...

    def consume_call(self, token_id: str) -> dict[str, Any]: ...

    def get_nft(self, token_id: str) -> CapabilityNFT | None: ...

    def get_owned(self, address: str) -> list[CapabilityNFT]: ...

    def stats(self) -> dict[str, Any]: ...


# ── In-memory registry (DEV only) ─────────────────────────────────


class InMemoryNFTRegistry:
    """In-memory NFT registry for local development and tests.

    Loses all state on restart. NOT a real NFT — do not use in production.
    Use OnChainNFTRegistry for any deployment where users hold real value.
    """

    def __init__(self, signer: Signer | None = None):
        self.signer = signer or Signer()
        self._nfts: dict[str, CapabilityNFT] = {}
        self._ownership: dict[str, list[str]] = {}
        self._pubkeys: dict[str, str] = {}
        logger.warning(
            "InMemoryNFTRegistry initialized — DEVELOPMENT ONLY. "
            "NFTs lose state on restart. Use OnChainNFTRegistry in production."
        )

    def register_owner_pubkey(self, address: str, pubkey_b64: str) -> None:
        """Register address → pubkey for signature verification on transfer."""
        self._pubkeys[address] = pubkey_b64

    def mint(
        self,
        capability_id: str,
        product_id: str,
        total_calls: int,
        price_per_call_usd: float,
        owner_address: str,
    ) -> CapabilityNFT:
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
            backend="in-memory",
        ).sign(self.signer)
        self._nfts[token_id] = nft
        self._ownership.setdefault(owner_address, []).append(token_id)
        return nft

    def transfer(
        self,
        token_id: str,
        from_address: str,
        to_address: str,
        from_signature_b64: str = "",
    ) -> dict[str, Any]:
        nft = self._nfts.get(token_id)
        if not nft:
            return {"error": "NFT not found"}
        if nft.owner_address != from_address:
            return {"error": "not the owner"}
        if nft.is_exhausted:
            return {"error": "NFT exhausted — no calls remaining"}

        owner_pubkey = self._pubkeys.get(from_address)
        if not owner_pubkey:
            return {"error": "from_address has no registered pubkey — use register_owner_pubkey first"}
        if not from_signature_b64:
            return {"error": "from_signature_b64 required (sign 'transfer:<token>:<from>:<to>:<transfer_count>')"}
        canonical = f"transfer:{token_id}:{from_address}:{to_address}:{nft.transfer_count}"
        if not self.signer.verify(owner_pubkey, from_signature_b64, canonical):
            return {"error": "invalid transfer signature"}

        nft.owner_address = to_address
        nft.transferred_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        nft.transfer_count += 1
        nft.sign(self.signer)

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
            "backend": "in-memory",
            "total_nfts": total,
            "active_nfts": active,
            "exhausted_nfts": total - active,
            "total_remaining_value_usd": round(total_value, 2),
            "total_transfers": total_transfers,
            "avg_transfers_per_nft": round(total_transfers / max(total, 1), 2),
        }

    @staticmethod
    def compute_gift_canonical(token_id: str, from_address: str, to_address: str) -> str:
        return f"transfer:{token_id}:{from_address}:{to_address}:0"


# ── On-chain registry (PRODUCTION) ────────────────────────────────


class OnChainNFTRegistry:
    """Thin client around the deployed AIMarketCapabilityNFT ERC-721.

    The contract is authoritative — this client just submits transactions
    and reads state. All ownership and remaining-calls truth lives on chain.

    Requires:
        AIMARKET_NFT_CONTRACT  — deployed address
        AIMARKET_NFT_CHAIN_RPC — RPC URL (Base, Ethereum, etc.)
        AIMARKET_NFT_OWNER_KEY — private key of the contract owner (for mint/auth)

    Optional:
        AIMARKET_NFT_CHAIN     — chain name (default "base")

    Mint is permissioned (only contract owner). Transfer is standard ERC-721.
    consumeCall requires the calling hub address to be authorized via
    setAuthorizedHub (done by owner once per hub).
    """

    def __init__(
        self,
        contract_address: str,
        rpc_url: str,
        owner_private_key: str,
        chain: str = "base",
        signer: Signer | None = None,
    ):
        try:
            from web3 import Web3
            from eth_account import Account
        except ImportError as exc:
            raise ImportError(
                "OnChainNFTRegistry requires web3 and eth_account. "
                "Install: pip install web3 eth-account"
            ) from exc

        self._Web3 = Web3
        self._Account = Account
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.chain = chain
        self.signer = signer or Signer()

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise RuntimeError(f"Could not connect to RPC {rpc_url}")

        self._owner_account = Account.from_key(owner_private_key)
        self._owner_address = self._owner_account.address

        self.contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=_CAPABILITY_NFT_ABI,
        )
        logger.info(
            "OnChainNFTRegistry initialized — contract=%s chain=%s owner=%s",
            self.contract_address, chain, self._owner_address,
        )

    # ── Write paths (require gas) ───────────────────────────────

    def mint(
        self,
        capability_id: str,
        product_id: str,
        total_calls: int,
        price_per_call_usd: float,
        owner_address: str,
    ) -> CapabilityNFT:
        cap_bytes32 = self._to_bytes32(capability_id)
        prod_bytes32 = self._to_bytes32(product_id)
        price_usd6 = int(round(price_per_call_usd * 1_000_000))
        owner_cs = self._Web3.to_checksum_address(owner_address)

        tx = self.contract.functions.mint(
            owner_cs, cap_bytes32, prod_bytes32, total_calls, price_usd6
        ).build_transaction({
            "from": self._owner_address,
            "nonce": self.w3.eth.get_transaction_count(self._owner_address),
            "gas": 300_000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self._owner_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Parse EntitlementMinted event for tokenId
        token_id = self._parse_minted_event(receipt)
        return CapabilityNFT(
            token_id=str(token_id),
            capability_id=capability_id,
            product_id=product_id,
            total_calls=total_calls,
            remaining_calls=total_calls,
            price_per_call_usd=price_per_call_usd,
            total_paid_usd=total_calls * price_per_call_usd,
            owner_address=owner_cs,
            original_owner=owner_cs,
            backend=f"on-chain:{self.chain}",
        ).sign(self.signer)

    def consume_call(self, token_id: str) -> dict[str, Any]:
        """Submit consumeCall as the contract-authorized hub.

        Note: the calling address (self._owner_address used here) must have
        been authorized via setAuthorizedHub. In a real setup, each hub
        would use its OWN private key, not the contract owner's.
        """
        tid = int(token_id)
        try:
            tx = self.contract.functions.consumeCall(tid).build_transaction({
                "from": self._owner_address,
                "nonce": self.w3.eth.get_transaction_count(self._owner_address),
                "gas": 100_000,
                "gasPrice": self.w3.eth.gas_price,
            })
            signed = self._owner_account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
        except Exception as exc:
            return {"error": str(exc), "token_id": token_id}

        remaining = self.contract.functions.remainingCalls(tid).call()
        return {
            "token_id": token_id,
            "consumed": True,
            "remaining_calls": remaining,
            "tx_hash": tx_hash.hex(),
        }

    def transfer(
        self,
        token_id: str,
        from_address: str,
        to_address: str,
        from_signature_b64: str = "",  # unused on-chain (ERC-721 uses signed tx)
    ) -> dict[str, Any]:
        """Transfer via ERC-721. The from_address must sign their own tx.

        This method submits a transfer FROM the contract owner (delegated mode);
        in standard use, the actual owner submits transferFrom themselves.
        Returned dict mirrors the in-memory API for compatibility.
        """
        return {
            "error": (
                "On-chain transfer requires the token owner to sign their own "
                "transferFrom transaction. Call contract.transferFrom(from, to, tokenId) "
                "from the owner's wallet directly."
            )
        }

    # ── Read paths (no gas) ─────────────────────────────────────

    def get_nft(self, token_id: str) -> CapabilityNFT | None:
        try:
            tid = int(token_id)
            e = self.contract.functions.getEntitlement(tid).call()
            owner = self.contract.functions.ownerOf(tid).call()
        except Exception:
            return None

        # Entitlement struct: (capabilityId, productId, totalCalls, remainingCalls,
        #                      pricePerCallUsd6, mintedAt, transferCount)
        cap_id_bytes, prod_id_bytes, total, remaining, price_usd6, minted_at, xfer_count = e
        return CapabilityNFT(
            token_id=str(tid),
            capability_id=self._from_bytes32(cap_id_bytes),
            product_id=self._from_bytes32(prod_id_bytes),
            total_calls=total,
            remaining_calls=remaining,
            price_per_call_usd=price_usd6 / 1_000_000,
            total_paid_usd=total * (price_usd6 / 1_000_000),
            owner_address=owner,
            original_owner="",  # not tracked on-chain
            minted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(minted_at)),
            transfer_count=xfer_count,
            backend=f"on-chain:{self.chain}",
        )

    def get_owned(self, address: str) -> list[CapabilityNFT]:
        """Returns empty list — ERC-721 doesn't expose 'tokens of owner' efficiently.

        For production, use an off-chain indexer (TheGraph subgraph at
        contracts/evm/subgraph) which tracks ownership events.
        """
        logger.warning(
            "OnChainNFTRegistry.get_owned: requires indexer (subgraph). "
            "Returning empty list. Use TheGraph for ownership queries."
        )
        return []

    def stats(self) -> dict[str, Any]:
        try:
            next_id = self.contract.functions.nextTokenId().call()
            total = next_id - 1
        except Exception:
            total = 0
        return {
            "backend": f"on-chain:{self.chain}",
            "contract": self.contract_address,
            "total_minted": total,
            "note": "Use subgraph indexer for per-owner queries and stats.",
        }

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _to_bytes32(s: str) -> bytes:
        b = s.encode("utf-8")
        if len(b) > 32:
            # Hash long strings deterministically
            return hashlib.sha256(b).digest()
        return b.ljust(32, b"\x00")

    @staticmethod
    def _from_bytes32(b: bytes) -> str:
        return b.rstrip(b"\x00").decode("utf-8", errors="replace")

    def _parse_minted_event(self, receipt) -> int:
        # EntitlementMinted(uint256 indexed tokenId, address indexed to, ...)
        # tokenId is first indexed param after the event signature
        for log in receipt["logs"]:
            try:
                event = self.contract.events.EntitlementMinted().process_log(log)
                return event["args"]["tokenId"]
            except Exception:
                continue
        raise RuntimeError("EntitlementMinted event not found in tx receipt")


# ── Factory ──────────────────────────────────────────────────────


def make_nft_registry(signer: Signer | None = None) -> NFTRegistryProtocol:
    """Create the appropriate NFT registry based on env config.

    If AIMARKET_NFT_CONTRACT is set → OnChainNFTRegistry (production).
    Otherwise → InMemoryNFTRegistry (development, with loud warning).
    """
    contract = os.environ.get("AIMARKET_NFT_CONTRACT", "").strip()
    rpc = os.environ.get("AIMARKET_NFT_CHAIN_RPC", "").strip()
    key = os.environ.get("AIMARKET_NFT_OWNER_KEY", "").strip()
    chain = os.environ.get("AIMARKET_NFT_CHAIN", "base").strip()

    if contract and rpc and key:
        return OnChainNFTRegistry(
            contract_address=contract,
            rpc_url=rpc,
            owner_private_key=key,
            chain=chain,
            signer=signer,
        )
    if contract or rpc or key:
        logger.warning(
            "Partial on-chain NFT config detected. Need all of: "
            "AIMARKET_NFT_CONTRACT, AIMARKET_NFT_CHAIN_RPC, AIMARKET_NFT_OWNER_KEY. "
            "Falling back to in-memory registry."
        )
    return InMemoryNFTRegistry(signer=signer)


# Backward-compat alias — existing code uses NFTRegistry
NFTRegistry = InMemoryNFTRegistry


# ── ABI (minimal — only methods we call) ──────────────────────────


_CAPABILITY_NFT_ABI = [
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "capabilityId", "type": "bytes32"},
            {"name": "productId", "type": "bytes32"},
            {"name": "totalCalls", "type": "uint64"},
            {"name": "pricePerCallUsd6", "type": "uint64"},
        ],
        "name": "mint",
        "outputs": [{"name": "tokenId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "consumeCall",
        "outputs": [{"name": "remaining", "type": "uint64"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "getEntitlement",
        "outputs": [{
            "components": [
                {"name": "capabilityId", "type": "bytes32"},
                {"name": "productId", "type": "bytes32"},
                {"name": "totalCalls", "type": "uint64"},
                {"name": "remainingCalls", "type": "uint64"},
                {"name": "pricePerCallUsd6", "type": "uint64"},
                {"name": "mintedAt", "type": "uint32"},
                {"name": "transferCount", "type": "uint32"},
            ],
            "name": "",
            "type": "tuple",
        }],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "remainingCalls",
        "outputs": [{"name": "", "type": "uint64"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "nextTokenId",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "tokenId", "type": "uint256"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "capabilityId", "type": "bytes32"},
            {"indexed": False, "name": "productId", "type": "bytes32"},
            {"indexed": False, "name": "totalCalls", "type": "uint64"},
            {"indexed": False, "name": "pricePerCallUsd6", "type": "uint64"},
        ],
        "name": "EntitlementMinted",
        "type": "event",
    },
]
