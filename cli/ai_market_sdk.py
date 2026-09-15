"""
AI Market SDK — Python client for Protocol v0 and v1.
======================================================
Minimal, dependency-light client covering both protocol versions.

Usage::

    # AIMarketClient from package cli.ai_market_sdk
    client = AIMarketClient(base_url="http://127.0.0.1:9080")

    # v1 flow (recommended)
    wk = client.well_known()
    plan = client.discover("translate spec to 5 langs + legal review", budget_usd=3.0)
    ch = client.open_channel(deposit_usd=3.0, tx_hash="demo-...")
    r = client.invoke_capability_v1(
        product_id="prod-xxx", capability_id="translate.multi@v2",
        payload={"text": "hello"}, payment_channel=ch["channel"]["channel_id"],
    )
    client.close_channel(channel_id=ch["channel"]["channel_id"])

    # v0 flow (backward-compat, license-key based)
    products = client.list_products()
    settlement = client.confirm_settlement(product_id="...", tx_hash="0x...", ...)
    result = client.invoke_capability(product_id="...", capability_id="...",
                                      license_key="...", payload={...})
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

import requests


@dataclass
class AIMarketClient:
    """Unified client for AI Market Protocol v0 and v1."""

    base_url: str
    timeout_sec: float = 20.0
    access_token: str = ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def _auth_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if extra:
            headers.update(extra)
        return headers

    # ------------------------------------------------------------------
    # v1 — Discovery
    # ------------------------------------------------------------------

    def well_known(self) -> dict[str, Any]:
        """GET /.well-known/ai-market.json"""
        r = requests.get(self._url("/.well-known/ai-market.json"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def manifest_v1(self) -> dict[str, Any]:
        """GET /ai-market/manifest — full signed catalog."""
        r = requests.get(self._url("/ai-market/manifest"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def mcp_tools(self) -> dict[str, Any]:
        """GET /ai-market/mcp — MCP tools list."""
        r = requests.get(self._url("/ai-market/mcp"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def discover(self, query: str, budget_usd: float | None = None, limit: int = 8) -> dict[str, Any]:
        """POST /ai-market/discover — NL intent → ranked plan."""
        r = requests.post(
            self._url("/ai-market/discover"),
            json={"query": query, "budget_usd": budget_usd, "limit": limit},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # v1 — Pricing
    # ------------------------------------------------------------------

    def get_pricing(self, product_id: str, capability_id: str, input_size: int = 0) -> dict[str, Any]:
        """GET /ai-market/pricing/{pid}/{cid} — price quote."""
        r = requests.get(
            self._url(f"/ai-market/pricing/{product_id}/{capability_id}"),
            params={"input_size": input_size},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    def estimate_pricing(self, product_id: str, capability_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /ai-market/pricing/{pid}/{cid} — price quote by payload."""
        r = requests.post(
            self._url(f"/ai-market/pricing/{product_id}/{capability_id}"),
            json={"input": payload},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # v1 — Payment channels
    # ------------------------------------------------------------------

    def open_channel(self, deposit_usd: float, tx_hash: str = "", token: str = "", chain: str = "",
                     wallet: str = "") -> dict[str, Any]:
        """POST /ai-market/channel/open — open pre-funded channel."""
        r = requests.post(
            self._url("/ai-market/channel/open"),
            json={"deposit_usd": deposit_usd, "tx_hash": tx_hash, "token": token,
                  "chain": chain, "wallet": wallet},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    def close_channel(self, channel_id: str, settle_tx_hash: str = "") -> dict[str, Any]:
        """POST /ai-market/channel/close — settle and refund."""
        r = requests.post(
            self._url("/ai-market/channel/close"),
            json={"channel_id": channel_id, "settle_tx_hash": settle_tx_hash},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # v1 — Invoke
    # ------------------------------------------------------------------

    def invoke_capability_v1(
        self,
        *,
        product_id: str,
        capability_id: str,
        payload: dict[str, Any],
        payment_channel: str | None = None,
        payment_tx: dict[str, Any] | None = None,
    ) -> requests.Response:
        """POST /capabilities/{pid}/{cid}/invoke — v1 invoke with payment.

        Returns the raw ``requests.Response`` so callers can inspect
        status_code (402 = payment required) and headers.
        """
        headers: dict[str, str] = {}
        if payment_channel:
            headers["X-Payment-Channel"] = payment_channel
        if payment_tx:
            headers["X-Payment"] = json.dumps(payment_tx)
        return requests.post(
            self._url(f"/capabilities/{product_id}/{capability_id}/invoke"),
            json={"input": payload},
            headers=headers,
            timeout=self.timeout_sec,
        )

    # ------------------------------------------------------------------
    # v1 — Pipelines
    # ------------------------------------------------------------------

    def run_pipeline(self, nodes: list[dict[str, Any]], channel_id: str = "") -> dict[str, Any]:
        """POST /ai-market/pipelines — execute a DAG pipeline."""
        r = requests.post(
            self._url("/ai-market/pipelines"),
            json={"nodes": nodes, "channel_id": channel_id},
            timeout=self.timeout_sec * 4,  # pipelines can be long
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # v1 — Receipts & stats
    # ------------------------------------------------------------------

    def get_receipt(self, nonce: str) -> dict[str, Any]:
        """GET /ai-market/receipt/{nonce} — signed payment receipt."""
        r = requests.get(self._url(f"/ai-market/receipt/{nonce}"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def get_stats(self, limit: int = 50) -> dict[str, Any]:
        """GET /ai-market/stats — recent invocation feed."""
        r = requests.get(self._url("/ai-market/stats"), params={"limit": limit}, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # v0 — backward-compatible
    # ------------------------------------------------------------------

    def list_products(self) -> dict[str, Any]:
        """GET /ai-market/products — list shipped products."""
        r = requests.get(self._url("/ai-market/products"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def get_product(self, product_id: str) -> dict[str, Any]:
        """GET /ai-market/products/{id} — product detail."""
        r = requests.get(self._url(f"/ai-market/products/{product_id}"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def search_products(self, task_description: str) -> dict[str, Any]:
        """POST /ai-market/products/search — keyword search (v0)."""
        r = requests.post(
            self._url("/ai-market/products/search"),
            json={"task_description": task_description},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    def get_pilot_config(self) -> dict[str, Any]:
        """GET /ai-market/pilot/config — chain/token/contract."""
        r = requests.get(self._url("/ai-market/pilot/config"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def confirm_settlement(
        self,
        *,
        product_id: str,
        tx_hash: str,
        chain: str = "",
        token: str = "",
        contract_address: str = "",
        customer_id: str = "",
        customer_email: str = "",
        wallet_address: str = "",
    ) -> dict[str, Any]:
        """POST /ai-market/pilot/settlement/confirm — verify tx + create license."""
        payload: dict[str, Any] = {
            "product_id": product_id,
            "tx_hash": tx_hash,
        }
        if chain:
            payload["chain"] = chain
        if token:
            payload["token"] = token
        if contract_address:
            payload["contract_address"] = contract_address
        if customer_id:
            payload["customer_id"] = customer_id
        if customer_email:
            payload["customer_email"] = customer_email
        if wallet_address:
            payload["wallet_address"] = wallet_address
        r = requests.post(
            self._url("/ai-market/pilot/settlement/confirm"),
            json=payload,
            headers=self._auth_headers(),
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    def list_entitlements(self, customer_id: str) -> dict[str, Any]:
        """GET /ai-market/entitlements/{customer_id} — list licenses (JWT required)."""
        r = requests.get(
            self._url(f"/ai-market/entitlements/{customer_id}"),
            headers=self._auth_headers(),
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    def invoke_capability(
        self, *, product_id: str, capability_id: str, license_key: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /ai-market/capabilities/{pid}/{cid}/invoke — v0 invoke (license key)."""
        r = requests.post(
            self._url(f"/ai-market/capabilities/{product_id}/{capability_id}/invoke"),
            json=payload,
            headers={"x-ai-market-license": license_key},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()
