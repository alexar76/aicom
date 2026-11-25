from __future__ import annotations

import asyncio
import hmac
import os
import re
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from .aimarket import BY_CAPABILITY, CAPABILITIES, register, signed_protocol_manifest
from .config import Settings, get_settings
from .crypto import Signer
from .models import AttestationCreate, Lineage, Receipt, VerifyRequest, VerifyResult
from .store import ChainHeadMissing, HubAppendRefused, Ledger


def production_mode() -> bool:
    """Fail CLOSED: production unless the operator says otherwise.

    Every gate here used to switch on ``AIFACTORY_PROD`` being SET, so a deployment that
    forgot the variable — or copied an ``.env.example`` carrying ``AIFACTORY_PROD=0`` —
    ran with no actor verification and no capability authentication, silently. Now an
    explicit ``AIFACTORY_PROD=1`` always wins, and only an explicit ``AIFACTORY_DEV=1``
    turns the checks off. Unset means production.
    """
    if os.getenv("AIFACTORY_PROD", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return os.getenv("AIFACTORY_DEV", "").strip().lower() not in {"1", "true", "yes"}

hub_published = 0


@lru_cache
def ledger() -> Ledger:
    settings = get_settings()
    return Ledger(settings.db_path, Signer(settings.key_file))


@asynccontextmanager
async def lifespan(_: FastAPI):
    if production_mode():
        get_settings()
        ledger()
    async def publish() -> None:
        global hub_published
        hub_published = await register(ledger().signer)

    task = asyncio.create_task(publish())
    yield
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Attested Memory Provenance Ledger", version="0.2.0", lifespan=lifespan)


def require_admin(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    expected = f"Bearer {settings.admin_token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid operator token")


def require_capability_token(request: Request) -> None:
    if not production_mode():
        return
    expected = os.getenv("AIMARKET_CAPABILITY_TOKEN", "").strip()
    supplied = request.headers.get("x-aimarket-internal-token", "")
    if len(expected) < 32 or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="internal service authentication required")


@app.get("/healthz")
def health(response: Response) -> dict:
    database_ok = True
    try:
        ledger().connection.execute("SELECT 1")
    except Exception:
        database_ok = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database_ok else "degraded", "service": "provenance-ledger", "hub_published": hub_published,
        "capabilities": len(CAPABILITIES),
        "database": {"backend": "postgresql" if ledger().connection.is_postgres else "sqlite", "healthy": database_ok},
        "pqc": "hybrid-ml-dsa-65" if ledger().signer.pq_public_key else "classical-only",
    }


@app.post("/v1/attestations", response_model=Receipt, dependencies=[Depends(require_admin)])
def create_attestation(request: AttestationCreate) -> Receipt:
    try:
        return ledger().append(request)
    except ChainHeadMissing:
        raise HTTPException(status_code=409, detail=_HEAD_MISSING) from None


@app.get("/v1/receipts/{receipt_id}", response_model=Receipt, dependencies=[Depends(require_admin)])
def get_receipt(receipt_id: str) -> Receipt:
    try:
        return ledger().get(receipt_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="receipt not found") from None


@app.get("/v1/lineage/{memory_id}", response_model=Lineage, dependencies=[Depends(require_admin)])
def get_lineage(memory_id: str) -> Lineage:
    return ledger().lineage(memory_id)


@app.post("/v1/receipts/verify", response_model=VerifyResult, dependencies=[Depends(require_admin)])
def verify_receipt(request: VerifyRequest) -> VerifyResult:
    try:
        return ledger().verify(request.receipt_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="receipt not found") from None


def _public_base(default_port: int) -> str:
    """Where this service can be REACHED from outside, for its own well-known.

    `AIMARKET_INVOKE_BASE` is where the co-located hub DIALS this service — a container
    hostname on a single-host deploy (`http://memory-market:8810`). Using it to describe
    ourselves handed that hostname to everyone who fetched our well-known: a manifest URL
    that resolves on exactly one machine in the world.

    One variable cannot answer both "where do I call you" and "where are you", so
    `AIMARKET_PUBLIC_BASE` answers the second and falls back to the first. A deployment that
    sets nothing behaves exactly as before.
    """
    public = os.getenv("AIMARKET_PUBLIC_BASE", "").strip()
    if public.startswith(("http://", "https://")):
        return public.rstrip("/")
    return os.getenv("AIMARKET_INVOKE_BASE", f"http://localhost:{default_port}").rstrip("/")


@app.get("/.well-known/ai-market.json")
def well_known() -> dict:
    signer = ledger().signer
    base = _public_base(8812)
    return {
        "name": "Provenance Ledger", "description": "Hybrid-signed lineage for portable memory.",
        "protocol_versions": ["v2"], "hub_version": "provider-0.2.0",
        "manifest_url": f"{base}/ai-market/v2/manifest",
        "products_count": len(CAPABILITIES), "capabilities_count": len(CAPABILITIES),
        "categories": sorted({item.category for item in CAPABILITIES}),
        "signer_public_key": signer.public_key, "pq_public_key": signer.pq_public_key,
    }


@app.get("/ai-market/v2/manifest")
def protocol_manifest() -> dict:
    return signed_protocol_manifest(ledger().signer)


_BUYER_REF = re.compile(r"bref-[0-9a-f]{32}")
_NEEDS_BUYER = (
    "memory.attest@v1 needs a buyer the hub can name: call it with an X-API-Key credit account "
    "(or a verified payment); trial and anonymous calls can read lineage and verify receipts only"
)


_HEAD_MISSING = "this memory has receipts but no recorded chain head; the ledger will not extend it"
def _aimarket_actor(request: Request) -> str:
    """Who an attestation made through the hub is recorded under.

    The buyer the hub vouches for (`X-AIMarket-Buyer-Ref`, sent only to the operator's own
    providers beside the internal token), else plainly `aimarket:anonymous`. It used to be a
    hash of `X-Payment-Channel`, which named one made-up actor for every buyer on credits,
    x402 or a trial, and a new one for channel buyers after each hub restart.
    """
    ref = (request.headers.get("x-aimarket-buyer-ref") or "").strip()
    return "aimarket:" + ref if _BUYER_REF.fullmatch(ref) else "aimarket:anonymous"


@app.post("/capabilities/{product_id}/{capability_id}/invoke", dependencies=[Depends(require_capability_token)])
def invoke_capability(
    product_id: str, capability_id: str, body: dict, request: Request, response: Response
) -> dict:
    capability = BY_CAPABILITY.get(capability_id)
    if capability is None or capability.product_id != product_id:
        raise HTTPException(status_code=404, detail="unknown capability")
    payload = body.get("input", body)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="input must be an object")
    try:
        if capability_id == "memory.attest@v1":
            actor = _aimarket_actor(request)
            # A receipt says who attested what; one in the name of nobody is an unaccountable write.
            # Memory Market refuses anonymous writes the same way (_NEEDS_BUYER); reads stay open.
            if actor == "aimarket:anonymous":
                raise HTTPException(status_code=403, detail=_NEEDS_BUYER)
            attestation = AttestationCreate.model_validate({**payload, "actor_id": actor})
            # A hub buyer extends only a chain they started, and starts none under a Memory Market
            # id (Ledger.append, checked under the append lock).
            result = ledger().append(attestation, hub_caller=True).model_dump(mode="json")
        elif capability_id == "lineage.get@v1":
            result = ledger().lineage(str(payload.get("memory_id") or "")).model_dump(mode="json")
        else:
            result = ledger().verify(str(payload.get("receipt_id") or "")).model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail="receipt not found") from None
    except ChainHeadMissing:
        raise HTTPException(status_code=409, detail=_HEAD_MISSING) from None
    except HubAppendRefused as refusal:
        raise HTTPException(status_code=403, detail=str(refusal)) from None
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from None

    for key, value in ledger().signer.response_headers(capability_id, product_id, payload, result).items():
        response.headers[key] = value
    return {
        "success": True, "result": result,
        "crypto": {"hybrid": ledger().signer.pq_public_key is not None},
    }
