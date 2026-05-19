"""
AI Market SDK (reference skeleton)
==================================
Minimal client for the AI Market Protocol v0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class AIMarketClient:
    base_url: str
    timeout_sec: float = 20.0
    access_token: str = ""

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def _auth_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if extra:
            headers.update(extra)
        return headers

    def list_products(self, **params: Any) -> dict[str, Any]:
        r = requests.get(self._url("/ai-market/products"), params=params, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def get_product(self, product_id: str) -> dict[str, Any]:
        r = requests.get(self._url(f"/ai-market/products/{product_id}"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def search_products(self, task_description: str, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"task_description": task_description, "constraints": constraints or {}}
        r = requests.post(self._url("/ai-market/products/search"), json=payload, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def get_pilot_config(self) -> dict[str, Any]:
        r = requests.get(self._url("/ai-market/pilot/config"), timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def confirm_settlement(
        self,
        *,
        product_id: str,
        tx_hash: str,
        chain: str,
        token: str,
        contract_address: str = "",
        customer_id: str = "",
        customer_email: str = "",
        wallet_address: str = "",
        amount: float = 0.0,
    ) -> dict[str, Any]:
        payload = {
            "product_id": product_id,
            "tx_hash": tx_hash,
            "chain": chain,
            "token": token,
            "contract_address": contract_address,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "wallet_address": wallet_address,
            "amount": amount,
        }
        r = requests.post(
            self._url("/ai-market/pilot/settlement/confirm"),
            json=payload,
            headers=self._auth_headers(),
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()

    def list_entitlements(self, customer_id: str) -> dict[str, Any]:
        # Endpoint now requires the caller to be the customer (Bearer JWT).
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
        r = requests.post(
            self._url(f"/ai-market/capabilities/{product_id}/{capability_id}/invoke"),
            json=payload,
            headers={"x-ai-market-license": license_key},
            timeout=self.timeout_sec,
        )
        r.raise_for_status()
        return r.json()
