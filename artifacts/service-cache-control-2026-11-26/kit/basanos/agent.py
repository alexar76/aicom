from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from basanos import CAPABILITY_ID, PRODUCT_ID, __version__
from basanos.federation import load_capability, manifest, well_known
from basanos.intel.ingest import ingest_into
from basanos.intel.sources import intel_enabled
from basanos.intel.store import KnowledgeStore
from basanos.memos import MemoStore
from basanos.models import InvokeEnvelope
from basanos.scanner import scan
from basanos.signing import ProviderSigner

MAX_INVOKE_BYTES = 65_536
#: A scan walks up to 200 files through every detector plus the whole-tree graph pass, so
#: /invoke is real CPU. Unbounded it is a free denial-of-service once this node is in a
#: public catalogue — which is exactly what federating it does.
INVOKE_RATE_MAX = int(os.getenv("BASANOS_INVOKE_RATE_MAX", "12"))
INVOKE_RATE_WINDOW_S = float(os.getenv("BASANOS_INVOKE_RATE_WINDOW_S", "60"))
PUBLIC_URL = os.getenv("BASANOS_PUBLIC_URL", "http://127.0.0.1:9470").rstrip("/")
ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "frontend"
DATA_DIR = Path(os.getenv("BASANOS_DATA_DIR", str(ROOT / "data")))

SIGNER = ProviderSigner()
CAPABILITY = load_capability()
_invoke_hits: dict[str, list[float]] = {}


def _from_local_proxy(peer: str) -> bool:
    """Could the TCP peer be our own reverse proxy (this host or its docker network)? Only
    then are X-Real-IP / X-Forwarded-For the caller's: anyone reaching the port another way
    writes them itself and gets a fresh rate-limit bucket per request."""
    try:
        addr = ipaddress.ip_address((peer or "").split("%")[0])
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def _client_key(request: Request) -> str:
    """Behind the documented nginx edge, X-Real-Ip is the real caller; the raw peer is the
    proxy, i.e. one shared bucket for the whole internet. Taken only from that proxy."""
    peer = (request.client.host if request.client else "") or ""
    real = (request.headers.get("x-real-ip") or "").strip() if _from_local_proxy(peer) else ""
    if real:
        return real
    return peer or "unknown"


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = now - INVOKE_RATE_WINDOW_S
    hits = [t for t in _invoke_hits.get(key, []) if t > window]
    if len(hits) >= INVOKE_RATE_MAX:
        _invoke_hits[key] = hits
        return True
    hits.append(now)
    _invoke_hits[key] = hits
    if len(_invoke_hits) > 4096:
        for stale in [k for k, v in _invoke_hits.items() if not v or max(v) <= window][:2048]:
            _invoke_hits.pop(stale, None)
    return False
STORE = KnowledgeStore(str(DATA_DIR / "intel"))
MEMOS = MemoStore(str(DATA_DIR / "memos"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="BASANOS",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


# Validity of the two public discovery documents, stated in HTTP (RFC 9111 Cache-Control, RFC 5861
# stale-if-error, weak ETag per RFC 9110): a hub reads these to decide how long it may keep serving
# this node's catalogue when a re-read fails. Every other response stays no-store (middleware below).
# Both documents are re-signed on every request, so the ETag leaves out the signature and the
# generation time; it changes when what the document says changes.
_STALE_IF_ERROR_S = 172800


def _with_validity(request: Request, document: dict, max_age_s: int) -> Response:
    content = {k: v for k, v in document.items() if k not in ("generated_at", "signature")}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                       default=str).encode("utf-8")).hexdigest()
    etag = f'W/"{digest}"'
    headers = {"ETag": etag,
               "Cache-Control": f"public, max-age={max_age_s}, stale-if-error={_STALE_IF_ERROR_S}"}
    names = {part.strip().removeprefix("W/") for part in request.headers.get("if-none-match", "").split(",")}
    if "*" in names or f'"{digest}"' in names:
        return Response(status_code=304, headers=headers)
    return JSONResponse(document, headers=headers)


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    response = None
    if request.method == "POST" and request.url.path in {"/invoke", "/intel"}:
        raw_length = request.headers.get("content-length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            length = -1
        if length < 0 or length > MAX_INVOKE_BYTES:
            response = JSONResponse(
                {"detail": f"request body must be 0-{MAX_INVOKE_BYTES} bytes"},
                status_code=413,
            )
    if response is None:
        response = await call_next(request)
    if "cache-control" not in response.headers:  # the discovery documents set their own
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/", response_model=None)
def root():
    for candidate in (UI_DIR / "landing.html", ROOT / "docs" / "landing" / "index.html"):
        if candidate.is_file():
            return FileResponse(candidate, media_type="text/html; charset=utf-8")
    return RedirectResponse(url="/ui/", status_code=307)


@app.get("/stone.js", response_model=None)
def stone_module():
    for candidate in (UI_DIR / "stone.js", ROOT / "docs" / "landing" / "stone.js"):
        if candidate.is_file():
            return FileResponse(candidate, media_type="text/javascript; charset=utf-8")
    return JSONResponse({"detail": "missing"}, status_code=404)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "agent": PRODUCT_ID,
        "kind": "tool",
        "version": __version__,
        "capability_id": CAPABILITY_ID,
        "provider_pubkey": SIGNER.public_key_b64,
        "intel_enabled": intel_enabled(),
        "role": "contract-assurance",
        "not": ["AgentAuditPool", "MOMUS", "THEMIS", "HEPHAESTUS"],
    }


@app.get("/.well-known/ai-market.json")
async def ai_market_well_known(request: Request) -> Response:
    """Federation entry point. Without this the hub crawler cannot discover this node, and
    a node outside the federated catalogue is invisible to signal-hunt (which derives its
    sources from it) and to the LOGOS assistant (which answers from the same live list)."""
    return _with_validity(
        request,
        well_known(
            public_url=PUBLIC_URL,
            version=__version__,
            seed=SIGNER.seed,
            capability=CAPABILITY,
            key_path=DATA_DIR / "manifest_key_unused",
        ),
        60,
    )


@app.get("/ai-market/v2/manifest")
async def ai_market_manifest(request: Request) -> Response:
    """Signed catalogue row. The signature is over the HUB's canonical form, imported from
    aimarket-oracle-core rather than reimplemented — see basanos.federation."""
    return _with_validity(
        request,
        manifest(
            public_url=PUBLIC_URL,
            version=__version__,
            seed=SIGNER.seed,
            capability=CAPABILITY,
            key_path=DATA_DIR / "manifest_key_unused",
        ),
        300,
    )


# Two paths, one handler. `/invoke` is this node's own contract; `/ai-market/v2/invoke` is
# the one the federation uses — `oracle_core.Protocol.well_known()` derives it as
# f"{base}/ai-market/v2/invoke" and cannot be told otherwise, so every hub-routed call lands
# there. Serving only `/invoke` meant a listed, priced capability answered 404 to the Hub.
@app.post("/invoke")
@app.post("/ai-market/v2/invoke")
async def invoke(raw_request: Request, request: InvokeEnvelope) -> JSONResponse:
    if _rate_limited(_client_key(raw_request)):
        return JSONResponse(
            {"detail": f"rate limited: {INVOKE_RATE_MAX} scans per "
                       f"{int(INVOKE_RATE_WINDOW_S)}s per caller"},
            status_code=429,
        )
    if not hmac.compare_digest(request.product_id, PRODUCT_ID):
        return JSONResponse({"detail": "product_id does not match this provider"}, status_code=400)
    if not hmac.compare_digest(request.capability_id, CAPABILITY_ID):
        return JSONResponse({"detail": "capability_id does not match this provider"}, status_code=400)

    try:
        raw_envelope = json.loads(await raw_request.body(), object_pairs_hook=_unique_object)
        input_payload = raw_envelope["input"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"detail": "request must contain unambiguous JSON"}, status_code=400)

    payload = request.input
    if payload.ingest_intel:
        await ingest_into(STORE)
    try:
        pack = scan(root_names=payload.roots, store=STORE, memos=MEMOS)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return JSONResponse(
        {"success": True, "result": pack},
        headers={
            "X-Provider-Signature": SIGNER.sign_result(
                pack,
                capability_id=CAPABILITY_ID,
                product_id=PRODUCT_ID,
                input_payload=input_payload,
            )
        },
    )


@app.get("/intel")
def intel_summary() -> dict:
    return {"intel_enabled": intel_enabled(), **STORE.summary()}


@app.get("/memos")
def memos_summary() -> dict:
    return MEMOS.summary()


@app.post("/intel")
async def intel_ingest(raw_request: Request) -> JSONResponse:
    try:
        json.loads(await raw_request.body() or b"{}", object_pairs_hook=_unique_object)
    except (ValueError, json.JSONDecodeError):
        return JSONResponse({"detail": "request must contain unambiguous JSON"}, status_code=400)
    result = await ingest_into(STORE)
    return JSONResponse(result)


if UI_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

# The landing is served from "/" while the rest of the UI lives under "/ui", so the landing's
# `fonts/fonts.css` resolves to /fonts/ and would miss the mount above. Both pages point at the
# same bundle; the console just reaches it through /ui.
#
# The MIME registration is not cosmetic here: `mimetypes` reads /etc/mime.types, which the slim
# base image does not carry, so the stylesheet went out as text/plain — and this app sends
# X-Content-Type-Options: nosniff on every response, which makes a browser refuse a stylesheet
# that is not text/css. Self-hosting the fonts without this line would have left the landing
# unstyled rather than merely un-fonted.
for _ext, _type in ((".woff2", "font/woff2"), (".css", "text/css")):
    mimetypes.add_type(_type, _ext)

for _fonts in (UI_DIR / "fonts", ROOT / "docs" / "landing" / "fonts"):
    if _fonts.is_dir():
        app.mount("/fonts", StaticFiles(directory=str(_fonts)), name="fonts")
        break


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "9470")))
