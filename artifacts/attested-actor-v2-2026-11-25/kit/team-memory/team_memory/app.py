from __future__ import annotations

import os
import json
from urllib.parse import urlencode
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

HUB = os.getenv("MEMORY_MARKET_URL", "http://localhost:8810").rstrip("/")
API_KEY = os.getenv("MEMORY_MARKET_API_KEY", "")
GATEWAY = os.getenv("SAAS_GATEWAY_URL", "http://localhost:9400").rstrip("/")
GATEWAY_TOKEN = os.getenv("SAAS_GATEWAY_API_KEY", "")
app = FastAPI(title="Team Memory OS", version="1.0.0")


class TeamMemory(BaseModel):
    team_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=50)


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class TeamMember(BaseModel):
    actor_id: str = Field(min_length=10, max_length=120)
    role: str = Field(default="member", pattern=r"^(member|admin)$")


def _headers(request: Request, team_id: str) -> dict[str, str]:
    values = {name: request.headers.get(name, "") for name in (
        "x-actor-id", "x-actor-public-key", "x-actor-signature", "x-actor-timestamp", "x-actor-nonce", "x-actor-version", "x-actor-intent")}
    if not all(values.values()):
        raise HTTPException(401, "cryptographic actor headers are required")
    saas_key = request.headers.get("x-saas-key", "")
    if not saas_key:
        raise HTTPException(401, "SaaS API key required")
    try:
        gateway_headers = {
            "X-SaaS-Key": saas_key,
            "X-SaaS-Internal-Token": GATEWAY_TOKEN,
            "X-Actor-ID": values["x-actor-id"],
            "X-Actor-Public-Key": values["x-actor-public-key"],
            "X-Actor-Timestamp": values["x-actor-timestamp"],
            "X-Actor-Nonce": values["x-actor-nonce"],
            "X-Actor-Signature": values["x-actor-signature"],
            "X-Actor-Version": values["x-actor-version"], "X-Actor-Intent": values["x-actor-intent"],
        }
        check = httpx.get(f"{GATEWAY}/v1/keys/introspect", params={"product": "team"}, headers={**gateway_headers}, timeout=5)
        assertion = httpx.get(f"{GATEWAY}/v1/teams/{team_id}/assertion", headers=gateway_headers, timeout=5)
    except httpx.HTTPError as error:
        raise HTTPException(503, "SaaS Gateway unavailable") from error
    if check.status_code >= 400 or assertion.status_code >= 400:
        raise HTTPException(401, "SaaS API key is invalid or expired")
    return {"Authorization": f"Bearer {API_KEY}", "X-Actor-ID": values["x-actor-id"], "X-Actor-Public-Key": values["x-actor-public-key"],
            "X-Actor-Timestamp": values["x-actor-timestamp"], "X-Actor-Nonce": values["x-actor-nonce"],
            "X-Actor-Signature": values["x-actor-signature"],
            "X-Actor-Version": values["x-actor-version"], "X-Actor-Intent": values["x-actor-intent"], "X-Team-ID": team_id, "X-Team-Assertion": assertion.json()["assertion"]}


def _call(method: str, path: str, request: Request, team_id: str | None = None, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, f"{HUB}{path}", headers={**(_headers(request, team_id) if team_id else _headers(request, "")), "Content-Type": "application/json"}, timeout=15, **kwargs)
    except httpx.HTTPError as error:
        raise HTTPException(503, "Memory Market unavailable") from error
    if response.status_code >= 400:
        raise HTTPException(response.status_code, response.json().get("detail", "Memory Market request failed"))
    return response.json()


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "team-memory-os", "hub": HUB}


@app.post("/api/team-memories", status_code=201)
def write(body: TeamMemory, request: Request) -> Any:
    tags = [f"team:{body.team_id}", *body.tags]
    result = _call("POST", "/v1/memories", request, team_id=body.team_id, content=json.dumps({"title": body.title, "content": body.content, "tags": tags, "visibility": "shared", "source_refs": body.source_refs}, ensure_ascii=False, separators=(",", ":")).encode())
    return result


@app.get("/api/team-search")
def search(request: Request, team_id: str, q: str = "", limit: int = 30) -> Any:
    return _call("GET", "/v1/catalog?" + urlencode({"q": q, "limit": max(1, min(limit, 100))}), request, team_id=team_id)


@app.get("/api/team-memories/{memory_id}")
def read(memory_id: str, request: Request, team_id: str) -> Any:
    return _call("GET", f"/v1/memories/{memory_id}", request, team_id=team_id)


def _gateway_team(request: Request, method: str, path: str, **kwargs: Any) -> Any:
    saas_key = request.headers.get("x-saas-key", "")
    actor_headers = {
        "X-Actor-ID": request.headers.get("x-actor-id", ""),
        "X-Actor-Public-Key": request.headers.get("x-actor-public-key", ""),
        "X-Actor-Timestamp": request.headers.get("x-actor-timestamp", ""),
        "X-Actor-Nonce": request.headers.get("x-actor-nonce", ""),
        "X-Actor-Signature": request.headers.get("x-actor-signature", ""),
        "X-Actor-Version": request.headers.get("x-actor-version", ""),
        "X-Actor-Intent": request.headers.get("x-actor-intent", ""),
    }
    if not saas_key or not all(actor_headers.values()):
        raise HTTPException(401, "SaaS API key and signed actor identity are required")
    headers = {"X-SaaS-Key": saas_key, "X-SaaS-Internal-Token": GATEWAY_TOKEN, **actor_headers}
    try:
        response = httpx.request(method, f"{GATEWAY}{path}", headers={**headers, "Content-Type": "application/json"}, timeout=10, **kwargs)
    except httpx.HTTPError as error:
        raise HTTPException(503, "SaaS Gateway unavailable") from error
    if response.status_code >= 400:
        raise HTTPException(response.status_code, response.json().get("detail", "team request failed"))
    return response.json()


@app.post("/api/teams", status_code=201)
def create_team(body: TeamCreate, request: Request) -> Any:
    return _gateway_team(request, "POST", "/v1/teams", content=request._body)


@app.post("/api/teams/{team_id}/members", status_code=201)
def add_member(team_id: str, body: TeamMember, request: Request) -> Any:
    return _gateway_team(request, "POST", f"/v1/teams/{team_id}/members", content=request._body)


@app.delete("/api/teams/{team_id}/members/{member_actor_id}")
def remove_member(team_id: str, member_actor_id: str, request: Request) -> Any:
    return _gateway_team(request, "DELETE", f"/v1/teams/{team_id}/members/{member_actor_id}")
