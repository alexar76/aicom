from __future__ import annotations

import os
from urllib.parse import urlencode
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field


HUB = os.getenv("MEMORY_MARKET_URL", "http://localhost:8810").rstrip("/")
API_KEY = os.getenv("MEMORY_MARKET_API_KEY", "")
GATEWAY = os.getenv("SAAS_GATEWAY_URL", "http://localhost:9400").rstrip("/")
GATEWAY_TOKEN = os.getenv("SAAS_GATEWAY_API_KEY", "")
app = FastAPI(title="Personal Attested Memory", version="1.0.0")


class MemoryBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    visibility: str = "private"
    price_usdc: str | None = None
    source_refs: list[str] = Field(default_factory=list, max_length=50)
    parent_memory_ids: list[str] = Field(default_factory=list, max_length=50)


def _headers(request: Request) -> dict[str, str]:
    actor = request.headers.get("x-actor-id")
    public_key = request.headers.get("x-actor-public-key")
    signature = request.headers.get("x-actor-signature")
    # Relay only the caller's explicit end-to-end destination; never re-sign.
    timestamp = request.headers.get("x-actor-timestamp")
    nonce = request.headers.get("x-actor-nonce")
    if not actor or not public_key or not signature or not timestamp or not nonce or request.headers.get("x-actor-version") != "2" or not request.headers.get("x-actor-intent"):
        raise HTTPException(401, "cryptographic actor headers are required")
    saas_key = request.headers.get("x-saas-key", "")
    if not saas_key:
        raise HTTPException(401, "SaaS API key required")
    try:
        check = httpx.get(f"{GATEWAY}/v1/keys/introspect", params={"product": "personal"}, headers={"X-SaaS-Key": saas_key, "X-SaaS-Internal-Token": GATEWAY_TOKEN}, timeout=5)
    except httpx.HTTPError as error:
        raise HTTPException(503, "SaaS Gateway unavailable") from error
    if check.status_code >= 400:
        raise HTTPException(401, "SaaS API key is invalid or expired")
    return {"Authorization": f"Bearer {API_KEY}", "X-Actor-ID": actor, "X-Actor-Public-Key": public_key,
            "X-Actor-Timestamp": timestamp, "X-Actor-Nonce": nonce, "X-Actor-Signature": signature,
            "X-Actor-Version": "2", "X-Actor-Intent": request.headers["x-actor-intent"], "Content-Type": "application/json"}


def _call(method: str, path: str, request: Request, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, f"{HUB}{path}", headers=_headers(request), timeout=15, **kwargs)
    except httpx.HTTPError as error:
        raise HTTPException(503, "Memory Market unavailable") from error
    if response.status_code >= 400:
        raise HTTPException(response.status_code, response.json().get("detail", "Memory Market request failed"))
    return response.json()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "personal-attested-memory", "hub": HUB}


@app.get("/api/search")
def search(request: Request, q: str = Query(default="", max_length=200), limit: int = Query(default=30, ge=1, le=100)) -> Any:
    return _call("GET", "/v1/catalog?" + urlencode({"q": q, "limit": limit}), request)


@app.post("/api/memories", status_code=201)
def write(body: MemoryBody, request: Request) -> Any:
    return _call("POST", "/v1/memories", request, content=request._body)


@app.get("/api/memories/{memory_id}")
def read(memory_id: str, request: Request) -> Any:
    return _call("GET", f"/v1/memories/{memory_id}", request)
