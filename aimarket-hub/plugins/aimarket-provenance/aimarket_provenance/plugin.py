"""ProvenancePlugin — cryptographic receipts for AI outputs.

Hooks into the hub invoke pipeline to auto-generate provenance receipts.
Registers /attest, /receipt/{id}, /verify/{id} API endpoints.
Exposes provenance capabilities in the .well-known manifest.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from aimarket_hub.database import HubDatabase
from aimarket_hub.plugin import HubPlugin
from aimarket_hub.signing import Signer

from .api import create_provenance_router
from .receipt import ProvenanceReceipt
from .storage import ProvenanceStorage

logger = logging.getLogger(__name__)

DEFAULT_SIGNING_KEY_PATH = "data/provenance_signing_key"
DEFAULT_API_TOKEN_ENV = "AIMARKET_PROVENANCE_API_TOKEN"


def _load_or_create_signer() -> tuple[Signer, str]:
    """Load persistent signing key or create one on first run.

    Returns (signer, public_key_fingerprint).
    Logs the fingerprint for audit — operators must back up this key.
    """
    key_path = os.environ.get(
        "AIMARKET_PROVENANCE_KEY_PATH", DEFAULT_SIGNING_KEY_PATH
    )
    signer = Signer(key_path=key_path)
    fingerprint = signer.public_key_b64
    logger.info(
        "Provenance signing key loaded (fingerprint: %s, path: %s)",
        fingerprint,
        key_path,
    )
    return signer, fingerprint


class ProvenancePlugin(HubPlugin):
    name = "provenance"
    version = "1.1.0"
    description = (
        "Cryptographic receipts for AI outputs with verifiable origin "
        "(Ed25519 + W3C VC + TEE attestation)"
    )
    homepage = "https://verify.aimarket.org"
    category = "compliance"

    def __init__(self) -> None:
        self._storage: ProvenanceStorage | None = None
        self._signer: Signer | None = None
        self._hub_name = "AIMarket Hub"
        self._hub_version = "3.0.0"
        self._auto_receipt = True
        self._api_token = os.environ.get(DEFAULT_API_TOKEN_ENV, "")
        self._verify_domain = os.environ.get(
            "AIMARKET_VERIFY_DOMAIN", "https://verify.aimarket.org"
        )

    def on_startup(self, db: Any) -> None:
        database_url = os.environ.get("DATABASE_URL", "")
        if hasattr(db, "db_path"):
            base_path = db.db_path.parent
            key_path = os.environ.get(
                "AIMARKET_PROVENANCE_KEY_PATH",
                str(base_path / "provenance_signing_key"),
            )
            self._storage = ProvenanceStorage(
                str(base_path / "provenance.db"),
                database_url=database_url,
            )
        else:
            self._storage = ProvenanceStorage(database_url=database_url)
        logger.info("Provenance storage initialized at %s", self._storage.db_path)

    def register_routes(self, router: Any) -> None:
        # Load persistent signing key — same key survives restarts
        signer, fingerprint = _load_or_create_signer()
        self._signer = signer

        # Configure auth
        api_token = os.environ.get(DEFAULT_API_TOKEN_ENV, "")
        if not api_token:
            logger.warning(
                "No AIMARKET_PROVENANCE_API_TOKEN set — /attest endpoint is open. "
                "Set this env var to require Bearer token authentication."
            )

        provenance_router = create_provenance_router(
            storage=self._storage or ProvenanceStorage(),
            signer=signer,
            hub_name=self._hub_name,
            hub_version=self._hub_version,
            api_token=api_token,
            verify_domain=self._verify_domain,
        )
        router.include_router(provenance_router)

    def on_invoke_post_check(
        self, output: dict, context: dict
    ) -> dict | None:
        """Auto-generate provenance receipt for every invoke.

        Attaches _provenance_receipt to the output dict so the API
        response can include a receipt reference.
        """
        if not self._auto_receipt or not self._storage:
            return None

        try:
            product_id = context.get("product_id", "")
            capability_id = context.get("capability_id", "")
            model_id = (
                f"{capability_id}@{product_id}" if product_id
                else capability_id
            )
            input_payload = context.get("input", {})
            signer = self._signer or Signer()

            receipt = ProvenanceReceipt.create(
                model_id=model_id,
                provider_hub=context.get("provider_hub", "local"),
                input_payload=input_payload,
                output_payload=output,
                signer=signer,
                hub_name=self._hub_name,
                hub_version=self._hub_version,
                latency_ms=context.get("latency_ms", 0),
                price_usd=context.get("price_usd", 0.0),
            )
            self._storage.store(receipt)

            short_id = (
                receipt.receipt_id.split(":")[-1]
                if ":" in receipt.receipt_id
                else receipt.receipt_id
            )
            output["_provenance_receipt"] = {
                "receipt_id": receipt.receipt_id,
                "verify_url": f"{self._verify_domain}/r/{short_id}",
            }
        except Exception as exc:
            logger.error("Failed to generate provenance receipt: %s", exc)

        return None  # Never blocks — side-effect only

    def get_manifest_extension(self) -> dict:
        return {
            "provenance": {
                "version": self.version,
                "receipt_format": "W3C Verifiable Credential",
                "signing_algorithm": "Ed25519",
                "endpoints": {
                    "attest": "/ai-market/v2/p/provenance/attest",
                    "receipt": "/ai-market/v2/p/provenance/receipt/{id}",
                    "verify": "/ai-market/v2/p/provenance/verify/{id}",
                },
                "features": {
                    "auto_receipt": self._auto_receipt,
                    "tee_attestation": True,
                    "zk_proofs": True,
                    "provenance_chains": True,
                },
            }
        }
