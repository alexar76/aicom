"""
ai.market API Client
====================

HTTP client for the ai.market Agent API.
Handles authentication, error handling, and response parsing.
"""

import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from .config import config


class APIError(Exception):
    """API error with status code and message."""
    def __init__(self, status_code: int, message: str, details: Optional[dict] = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"API Error {status_code}: {message}")


class AIMarketClient:
    """HTTP client for ai.market Agent API."""
    
    def __init__(self):
        self.base_url = config.base_url
        self.timeout = config.request_timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=config.get_headers(),
                timeout=self.timeout,
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None
    ) -> dict:
        """Make an API request."""
        client = await self._get_client()
        
        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                json=json,
            )
            
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    message = error_data.get("detail", str(error_data))
                    if isinstance(message, dict):
                        message = message.get("message", str(message))
                except:
                    message = response.text
                
                raise APIError(
                    status_code=response.status_code,
                    message=message,
                    details=error_data if 'error_data' in dir() else {}
                )
            
            return response.json()
            
        except httpx.TimeoutException:
            raise APIError(408, "Request timed out")
        except httpx.RequestError as e:
            raise APIError(0, f"Network error: {str(e)}")
    
    # =========================================================================
    # DISCOVERY
    # =========================================================================
    
    async def search_datasets(
        self,
        query: str,
        category: Optional[str] = None,
        min_rows: Optional[int] = None,
        max_price_cents: Optional[int] = None,
        limit: int = 10
    ) -> dict:
        """Search for datasets."""
        params = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        if min_rows:
            params["min_rows"] = min_rows
        if max_price_cents:
            params["max_price_cents"] = max_price_cents
        
        return await self._request("GET", "/agent/search", params=params)
    
    async def get_dataset(self, dataset_id: str) -> dict:
        """Get dataset details."""
        return await self._request("GET", f"/agent/datasets/{dataset_id}")
    
    async def evaluate_dataset(self, dataset_id: str) -> dict:
        """Get dataset evaluation (schema, statistics, compliance)."""
        return await self._request("GET", f"/agent/datasets/{dataset_id}/eval")
    
    async def preview_dataset(self, dataset_id: str, rows: int = 5) -> dict:
        """Get dataset preview (sample rows)."""
        return await self._request(
            "GET",
            f"/agent/datasets/{dataset_id}/preview",
            params={"rows": rows}
        )
    
    # =========================================================================
    # WALLET
    # =========================================================================
    
    async def get_wallet_balance(self) -> dict:
        """Get wallet balance."""
        return await self._request("GET", "/agent/wallet/balance")
    
    # =========================================================================
    # ORDERS
    # =========================================================================
    
    async def purchase_dataset(
        self,
        dataset_id: str,
        idempotency_key: Optional[str] = None,
        note: Optional[str] = None
    ) -> dict:
        """Purchase a dataset."""
        payload = {"dataset_id": dataset_id}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        if note:
            payload["note"] = note
        
        return await self._request("POST", "/agent/purchase", json=payload)
    
    async def list_orders(
        self,
        status: Optional[str] = None,
        limit: int = 20
    ) -> dict:
        """List orders."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        
        return await self._request("GET", "/agent/orders", params=params)
    
    async def get_order_data(self, order_id: str, format: str = "csv") -> dict:
        """Get download URL for order data."""
        return await self._request(
            "GET",
            f"/agent/orders/{order_id}/data",
            params={"format": format}
        )
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    async def verify_connection(self) -> dict:
        """Verify API connection and credentials."""
        try:
            # Try wallet endpoint to verify auth
            result = await self.get_wallet_balance()
            return {
                "status": "connected",
                "sandbox_mode": config.sandbox_mode,
                "balance_cents": result.get("balance_cents", 0),
            }
        except APIError as e:
            if e.status_code == 401:
                return {
                    "status": "authentication_failed",
                    "message": "Invalid or missing API key"
                }
            return {
                "status": "error",
                "message": str(e)
            }


# Global client instance
client = AIMarketClient()
