"""
Sandbox API
===========
Static preview: ``/api/sandbox/file/{sandbox_id}/…`` (HTML/CSS/JS/SVG) with localhost/root-path rewrites.

**Live API preview** (recommended for “real app” demos): set ``AIFACTORY_SANDBOX_PREVIEW_API=1`` to spawn **FastAPI (uvicorn)** on
``127.0.0.1`` for detected ``backend/main.py`` (or sibling layouts), then proxy via
``/api/sandbox/backend/{sandbox_id}/…``. Injected fetch shim maps ``fetch('/api/…')`` to that prefix inside the iframe — **cookies/sessions work** through the factory origin like a normal reverse proxy.

The optional **Docker DinD** ``python -m http.server`` container serves **static files only**; it does not replace uvicorn preview.

**Compose preview:** when the product repo has ``docker-compose.yml``, ``start`` runs ``docker compose up -d --build`` (see ``AIFACTORY_SANDBOX_COMPOSE_PREVIEW``) and reverse-proxies the published web/api port at ``/api/sandbox/compose/{sandbox_id}/…``. For QA parity see ``AIFACTORY_BROWSER_E2E_SERVE_MODE`` in ``browser_preview_e2e``.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.sandbox_proxy_headers import sandbox_proxy_forward_headers
from web.backend.services.url_safety import validate_git_remote_url

from core.logging_utils import log_suppressed
from web.backend.services.sandbox_preview_api import (
    detect_fastapi_backend,
    preview_api_enabled,
    register_preview_proc,
    start_fastapi_preview,
    stop_preview_for_sandbox,
)
from web.backend.services.sandbox_compose_preview import (
    start_compose_preview,
    stop_compose_for_sandbox,
)
from core.paths import code_dir, pipeline_json_path, sandbox_registry_path, specs_dir, product_state_dir
from security.docker_sandbox import append_image_and_command, hardened_docker_run_args
from web.backend.services.sandbox_static_rewrite import (
    SANDBOX_HTML_CSP,
    SANDBOX_IFRAME_SANDBOX_ATTR,
    SANDBOX_VIEWER_CSP,
    _inject_iframe_base_href,
    _inject_loopback_navigation_guard,
    _neutralize_iframe_breakouts,
    _rewrite_localhost_urls,
    _rewrite_root_absolute_paths,
    inject_preview_api_fetch_shim,
    inject_sandbox_in_page_nav_helpers,
    public_origin_from_request,
    rewrite_loopback_location_header,
    rewrite_upstream_proxy_body,
    sandbox_public_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

# Sandbox registry — persisted so iframe / file URLs survive backend restarts
# (uvicorn worker recycle, container recreate). Static viewers rely only on
# product_id + sandbox_id; uvicorn / compose backends are best-effort: ports
# that survived the restart (e.g. an external compose stack) keep working, the
# rest fail at proxy time with 502/503 rather than hiding the sandbox entirely.
_SANDBOX_REGISTRY_PATH = sandbox_registry_path()
_active_sandboxes: dict[str, dict] = {}


def _save_registry() -> None:
    try:
        _SANDBOX_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SANDBOX_REGISTRY_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_active_sandboxes, f)
        tmp.replace(_SANDBOX_REGISTRY_PATH)
    except Exception as e:
        logger.warning("sandbox registry save failed: %s", e)


def _load_registry() -> None:
    if not _SANDBOX_REGISTRY_PATH.exists():
        return
    try:
        with open(_SANDBOX_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _active_sandboxes.update(
                {str(k): v for k, v in data.items() if isinstance(v, dict)}
            )
            logger.info("sandbox registry: loaded %d entries", len(_active_sandboxes))
    except Exception as e:
        logger.warning("sandbox registry load failed: %s", e)


_load_registry()


def _lookup_sandbox(sandbox_id: str) -> Optional[dict]:
    """Return sandbox dict, reloading from disk on cache miss (multi-worker safety)."""
    sb = _active_sandboxes.get(sandbox_id)
    if sb is not None:
        return sb
    _load_registry()
    return _active_sandboxes.get(sandbox_id)


def _get_product_code_dir(product_id: str) -> Optional[Path]:
    """Get the code directory for a product, if it exists."""
    root = code_dir(product_id)
    return root if root.exists() else None


def _should_try_fastapi_preview(code_dir: Path, compose_ok: bool) -> bool:
    """Use uvicorn preview for FastAPI repos when compose is unavailable or failed."""
    if compose_ok:
        return False
    if not detect_fastapi_backend(code_dir):
        return False
    if preview_api_enabled():
        return True
    # Compose/Docker preview failed or is off — still serve SSR FastAPI apps without index.html.
    return True


def _ensure_fastapi_preview(sandbox_id: str, entry: dict, code_dir: Path) -> bool:
    """Start loopback uvicorn if missing; mutates registry entry. Returns True when listening."""
    if entry.get("backend_preview_port"):
        return True
    bp, uv_proc, pst = start_fastapi_preview(sandbox_id=sandbox_id, code_dir=code_dir)
    entry["backend_preview_port"] = bp
    entry["preview_api_status"] = pst
    if uv_proc:
        register_preview_proc(sandbox_id, uv_proc)
    if bp:
        _active_sandboxes[sandbox_id] = entry
        _save_registry()
    return bp is not None


_HOP_BY_HOP_PROXY_RESP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
        "transfer-encoding",
    }
)


def _finalize_sandbox_proxy_response(
    sandbox_id: str,
    upstream: httpx.Response,
    *,
    loopback_port: int,
    path_prefix: str,
    proxy_kind: str,
    inject_backend_fetch_shim: bool,
    request: Request | None = None,
) -> Response:
    """
    Rewrite Location / HTML / CSS / JS from loopback upstream so remote storefront viewers
    stay on the factory origin (fixes broken ``localhost`` links in Docker Compose / uvicorn previews).
    """
    out_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP_PROXY_RESP
    }
    loc = out_headers.get("location")
    if loc:
        new_loc = rewrite_loopback_location_header(loc, loopback_port, path_prefix)
        if new_loc != loc:
            out_headers["location"] = new_loc

    ct = upstream.headers.get("content-type")
    body = upstream.content
    new_body, is_html = rewrite_upstream_proxy_body(
        body,
        ct,
        sandbox_id=sandbox_id,
        proxy_kind=proxy_kind,
        inject_backend_fetch_shim=inject_backend_fetch_shim,
        public_origin=public_origin_from_request(request),
    )
    if new_body != body:
        for hk in list(out_headers.keys()):
            if hk.lower() in ("content-length", "content-encoding"):
                del out_headers[hk]

    headers_final = dict(out_headers)
    if is_html:
        headers_final["Content-Security-Policy"] = SANDBOX_HTML_CSP

    return Response(
        content=new_body,
        status_code=upstream.status_code,
        headers=headers_final,
        media_type=upstream.headers.get("content-type"),
    )


def _try_docker_run(sandbox_id: str, product_id: str, port: int) -> bool:
    """Try to start a real Docker container for the sandbox."""
    code_dir = _get_product_code_dir(product_id)
    if not code_dir:
        return False
    
    try:
        # Use python:3.12-slim as base for sandbox, mount code
        base = hardened_docker_run_args(
            name=sandbox_id,
            network="none",
            memory="256m",
            cpus="0.5",
            workdir="/app/product",
            volume_mount=f"{code_dir}:/app/product:ro",
            publish_port=port,
            read_only_root=True,
            pids_limit=64,
        )
        cmd = append_image_and_command(
            base,
            "python:3.12-slim",
            [
                "python3",
                "-m",
                "http.server",
                str(port),
                "--bind",
                "0.0.0.0",
                "--directory",
                "/app/product",
            ],
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(f"Docker sandbox {sandbox_id} started on port {port}")
            return True
        else:
            logger.warning(f"Docker sandbox start failed: {result.stderr}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Docker not available for sandbox: {e}")
        return False


@router.post("/start/{product_id}")
async def start_sandbox(product_id: str, _admin: dict = Depends(require_admin_with_rbac)):
    """Start a sandbox for a product."""
    sandbox_id = f"sandbox-{uuid.uuid4().hex[:12]}"
    port = 9000 + len(_active_sandboxes) % 1000  # allocate unique port

    code_dir = _get_product_code_dir(product_id)
    host_port = None

    compose_proxy_port: Optional[int] = None
    compose_preview_status: Optional[str] = None
    if code_dir:
        cpp, cst, _cproj = start_compose_preview(code_dir, sandbox_id)
        compose_proxy_port = cpp
        compose_preview_status = cst

    compose_ok = compose_preview_status == "ok" and compose_proxy_port is not None

    # Static file DinD (skipped when compose stack is running — same Docker daemon)
    docker_success = False
    if not compose_ok:
        docker_success = _try_docker_run(sandbox_id, product_id, port)
    if docker_success:
        host_port = port
        logger.info(f"Sandbox {sandbox_id} running as Docker container on port {port}")
    else:
        logger.info(f"Sandbox {sandbox_id} running in mock mode (no Docker available)")

    entry: dict = {
        "id": sandbox_id,
        "product_id": product_id,
        "status": "running",
        "started_at": time.time(),
        "url": f"/sandbox/{sandbox_id}",
        "port": host_port,
        "docker_mode": docker_success,
        "has_code": code_dir is not None,
        "backend_preview_port": None,
        "preview_api_status": None,
        "compose_proxy_port": compose_proxy_port,
        "compose_preview_status": compose_preview_status,
    }
    _active_sandboxes[sandbox_id] = entry
    _save_registry()

    preview_payload: dict = {"enabled": False, "proxy_prefix": None, "status": None}
    if code_dir and _should_try_fastapi_preview(code_dir, compose_ok):
        if _ensure_fastapi_preview(sandbox_id, entry, code_dir):
            preview_payload = {
                "enabled": True,
                "proxy_prefix": f"/api/sandbox/backend/{sandbox_id}/",
                "status": entry.get("preview_api_status"),
            }
        else:
            preview_payload = {"enabled": False, "proxy_prefix": None, "status": pst}
    elif compose_ok:
        preview_payload = {
            "enabled": False,
            "proxy_prefix": None,
            "status": "skipped_compose_stack",
        }

    compose_preview_payload = {
        "enabled": compose_ok,
        "proxy_prefix": (f"/api/sandbox/compose/{sandbox_id}/" if compose_ok else None),
        "status": compose_preview_status,
    }

    return {
        "sandbox_id": sandbox_id,
        "status": "running",
        "url": f"/api/sandbox/view/{sandbox_id}",
        "expires_at": time.time() + 3600,
        "port": host_port,
        "docker_mode": docker_success,
        "preview_api": preview_payload,
        "compose_preview": compose_preview_payload,
    }


@router.get("/view/{sandbox_id}")
async def view_sandbox(request: Request, sandbox_id: str):
    """View sandbox content in browser — renders HTML demo in iframe."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")

    product_id = sandbox.get("product_id", "unknown")
    code_dir = _get_product_code_dir(product_id)
    sb_state = _active_sandboxes.get(sandbox_id) or sandbox
    compose_ok = sb_state.get("compose_proxy_port") is not None
    if code_dir and _should_try_fastapi_preview(code_dir, compose_ok):
        _ensure_fastapi_preview(sandbox_id, sb_state, code_dir)
        if sandbox_id in _active_sandboxes:
            _active_sandboxes[sandbox_id].update(
                {
                    k: sb_state[k]
                    for k in ("backend_preview_port", "preview_api_status")
                    if k in sb_state
                }
            )

    # Inner DinD container listens on an unpublished port — browsers cannot reach it.
    # Always serve files through this API (iframe + /file/...) so marketplace links work.
    if sandbox.get("docker_mode") and sandbox.get("port"):
        logger.info(
            "sandbox %s: ignoring DinD localhost redirect; serving via API viewer",
            sandbox_id[:16],
        )

    # Serve generated HTML via iframe demo (same path as mock mode)
    if code_dir:
        files = []
        has_index_html = False
        for f in sorted(code_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                try:
                    rel = f.relative_to(code_dir)
                    files.append(str(rel))
                    if f.name == "index.html":
                        has_index_html = True
                except ValueError as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (web/backend/api/sandbox.py)", exc_info=_suppressed_exc)

        file_list_html = "\n".join(
            (
                f'<li><a href="{sandbox_public_url(request, "/api/sandbox/file/" + sandbox_id + "/" + rel_path)}" '
                f'target="demo-frame" style="color:#6366f1;text-decoration:none">{rel_path}</a></li>'
            )
            for rel_path in files[:100]
        )

        sb_state = _active_sandboxes.get(sandbox_id) or sandbox
        compose_proxy_port = sb_state.get("compose_proxy_port")
        compose_ok = compose_proxy_port is not None
        backend_preview_port = sb_state.get("backend_preview_port")
        compose_hint = ""
        if compose_ok:
            compose_hint = (
                '<span style="margin-left:1rem;color:#22c55e;font-size:0.7rem">'
                f"Docker Compose — proxied: <code>/api/sandbox/compose/{sandbox_id}/…</code>"
                "</span>"
            )

        backend_hint = ""
        if sb_state.get("backend_preview_port"):
            backend_hint = (
                '<span style="margin-left:1rem;color:#22c55e;font-size:0.7rem">'
                f"Live API (proxied): <code>/api/sandbox/backend/{sandbox_id}/…</code> · "
                "<span style=\"color:#8888aa\">fetch('/api/…') is rewritten in-page.</span>"
                "</span>"
            )
        elif not compose_ok and code_dir and ((code_dir / "backend").is_dir() or (code_dir / "server").is_dir()):
            hint_extra = ""
            if preview_api_enabled():
                hint_extra = " Preview API mode is on — ensure <code>backend/main.py</code> exposes FastAPI <code>app</code>."
            backend_hint = (
                '<span style="margin-left:1rem;color:#8888aa;font-size:0.7rem">'
                "Backend folder present — static files only until uvicorn preview starts."
                + hint_extra
                + "</span>"
            )

        if compose_ok:
            iframe_src = sandbox_public_url(request, f"/api/sandbox/compose/{sandbox_id}/")
            preview_label = "docker compose stack"
        elif backend_preview_port:
            iframe_src = sandbox_public_url(request, f"/api/sandbox/backend/{sandbox_id}/")
            preview_label = "FastAPI live app"
        else:
            iframe_src = sandbox_public_url(request, f"/api/sandbox/file/{sandbox_id}/index.html")
            preview_label = "index.html"

        if has_index_html or compose_ok or backend_preview_port:
            # Show the demo in an iframe with a file browser panel
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>🔬 Sandbox Demo: {product_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', system-ui, sans-serif; background: #0a0a1a; color: #e0e0ff; }}
        .header {{
            background: rgba(255,255,255,0.05); backdrop-filter: blur(16px);
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding: 0.75rem 1.5rem; display: flex; align-items: center; gap: 1rem;
        }}
        .header h1 {{ font-size: 1rem; font-weight: 600; color: #6366f1; }}
        .header .status {{
            font-size: 0.75rem; padding: 0.25rem 0.75rem;
            border-radius: 20px; background: rgba(99,102,241,0.15);
            color: #6366f1; border: 1px solid rgba(99,102,241,0.3);
        }}
        .layout {{ display: flex; height: calc(100vh - 56px); }}
        .sidebar {{
            width: 250px; background: rgba(255,255,255,0.02);
            border-right: 1px solid rgba(255,255,255,0.08);
            padding: 1rem; overflow-y: auto;
        }}
        .sidebar h2 {{ font-size: 0.75rem; text-transform: uppercase; color: #666688; margin-bottom: 0.75rem; letter-spacing: 0.05em; }}
        .sidebar ul {{ list-style: none; }}
        .sidebar li {{ margin-bottom: 0.25rem; }}
        .sidebar a {{
            display: block; padding: 0.4rem 0.6rem; border-radius: 6px;
            font-size: 0.8125rem; color: #8888aa; text-decoration: none;
            transition: all 0.15s ease; font-family: 'JetBrains Mono', monospace;
        }}
        .sidebar a:hover {{ background: rgba(99,102,241,0.1); color: #e0e0ff; }}
        .main {{ flex: 1; display: flex; flex-direction: column; }}
        .toolbar {{
            padding: 0.5rem 1rem; background: rgba(255,255,255,0.02);
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.75rem; color: #666688;
        }}
        iframe {{
            flex: 1; width: 100%; border: none; background: white;
        }}
        .placeholder {{
            display: flex; align-items: center; justify-content: center;
            flex: 1; color: #666688; font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔬 Sandbox Demo</h1>
        <span class="status">{product_id}</span>
        <span style="font-size:0.75rem;color:#666688;margin-left:auto">Sandbox: {sandbox_id[:12]}…</span>
    </div>
    <div class="layout">
        <div class="sidebar">
            <h2>📁 Code Files</h2>
            <ul>{file_list_html}</ul>
        </div>
        <div class="main">
            <div class="toolbar">
                <span>🌐 Live Preview — <span style="color:#6366f1">{preview_label}</span></span>{compose_hint}{backend_hint}
            </div>
            <iframe name="demo-frame" src="{iframe_src}" title="Demo Preview"
                sandbox="{SANDBOX_IFRAME_SANDBOX_ATTR}" referrerpolicy="no-referrer"></iframe>
        </div>
    </div>
</body>
</html>"""
        else:
            # No index.html — show file listing with preview option
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>🔬 Sandbox: {product_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', system-ui, sans-serif; background: #0a0a1a; color: #e0e0ff; padding: 2rem; }}
        h1 {{ font-size: 1.5rem; color: #6366f1; margin-bottom: 0.5rem; }}
        .note {{ color: #666688; font-size: 0.875rem; margin-bottom: 1.5rem; }}
        ul {{ list-style: none; }}
        li {{ padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        a {{ color: #6366f1; text-decoration: none; font-family: 'JetBrains Mono', monospace; font-size: 0.875rem; }}
        a:hover {{ color: #818cf8; }}
    </style>
</head>
<body>
    <h1>🔬 Sandbox: {product_id}</h1>
    <p class="note">No index.html found. Select a file to preview:</p>
    <ul>{file_list_html}</ul>
</body>
</html>"""
    else:
        html = f"""<!DOCTYPE html>
<html><head><title>Sandbox: {product_id}</title>
<style>body{{font-family:monospace;background:#111;color:#eee;padding:2em;text-align:center}}
h1{{color:#6366f1}} .note{{color:#666;margin-top:2em}}
</style></head>
<body>
<h1>🔬 Sandbox: {product_id}</h1>
<p class="note">No code directory found for this product.</p>
<p class="note">Run the pipeline first to generate code, then start a sandbox.</p>
</body></html>"""

    return HTMLResponse(
        content=html,
        headers={
            "Content-Security-Policy": SANDBOX_VIEWER_CSP,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/file/{sandbox_id}/{file_path:path}")
async def get_sandbox_file(request: Request, sandbox_id: str, file_path: str):
    """Serve individual files from a sandbox (for iframe preview)."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")

    product_id = sandbox.get("product_id", "unknown")
    code_dir = _get_product_code_dir(product_id)
    if not code_dir:
        raise HTTPException(status_code=404, detail="Code directory not found")

    full_path = code_dir / file_path
    # Security: ensure the resolved path is within the code directory
    try:
        full_path = full_path.resolve()
        full_path.relative_to(code_dir.resolve())
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    try:
        content = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary file — return as-is
        content = full_path.read_bytes()
        return Response(content=content, media_type="application/octet-stream")

    # Determine content type
    ext = full_path.suffix.lower()
    media_types = {
        ".html": "text/html",
        ".htm": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".wasm": "application/wasm",
    }
    media_type = media_types.get(ext, "text/plain")

    if isinstance(content, str):
        content = _rewrite_localhost_urls(content)
        content = _rewrite_root_absolute_paths(content)
        if media_type == "text/html":
            content = _neutralize_iframe_breakouts(content)
            content = _inject_iframe_base_href(content, sandbox_id, request)
            sbrec = _active_sandboxes.get(sandbox_id) or {}
            if sbrec.get("backend_preview_port"):
                content = inject_preview_api_fetch_shim(content, sandbox_id)
            content = _inject_loopback_navigation_guard(content)
            content = inject_sandbox_in_page_nav_helpers(content)
            return Response(
                content=content,
                media_type=media_type,
                headers={
                    "Content-Security-Policy": SANDBOX_HTML_CSP,
                    "X-Content-Type-Options": "nosniff",
                },
            )
        elif media_type == "image/svg+xml":
            content = _neutralize_iframe_breakouts(content)

    return Response(content=content, media_type=media_type)


@router.api_route(
    "/backend/{sandbox_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def sandbox_backend_proxy(sandbox_id: str, path: str, request: Request):
    """Reverse-proxy to uvicorn preview bound on loopback (see ``AIFACTORY_SANDBOX_PREVIEW_API``)."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")
    port = sandbox.get("backend_preview_port")
    if not port:
        raise HTTPException(
            status_code=503,
            detail="Preview API not active — set AIFACTORY_SANDBOX_PREVIEW_API=1 and ensure FastAPI backend exists.",
        )
    query = request.url.query
    url = f"http://127.0.0.1:{int(port)}/{path}"
    if query:
        url = f"{url}?{query}"

    body = await request.body()
    fwd_headers = sandbox_proxy_forward_headers(request)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            upstream = await client.request(
                request.method,
                url,
                headers=fwd_headers,
                content=body if body else None,
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}") from e

    return _finalize_sandbox_proxy_response(
        sandbox_id,
        upstream,
        loopback_port=int(port),
        path_prefix=f"/api/sandbox/backend/{sandbox_id}/",
        proxy_kind="backend",
        inject_backend_fetch_shim=True,
        request=request,
    )


@router.api_route(
    "/compose/{sandbox_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def sandbox_compose_proxy(sandbox_id: str, path: str, request: Request):
    """Reverse-proxy to ``docker compose`` published port (generated stack + DB containers)."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")
    port = sandbox.get("compose_proxy_port")
    if not port:
        raise HTTPException(
            status_code=503,
            detail="Compose preview inactive — add docker-compose.yml with env-driven ports "
            "(API_HOST_PORT, WEB_HOST_PORT) or disable compose preview.",
        )
    query = request.url.query
    url = f"http://127.0.0.1:{int(port)}/{path}"
    if query:
        url = f"{url}?{query}"

    body = await request.body()
    fwd_headers = sandbox_proxy_forward_headers(request)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            upstream = await client.request(
                request.method,
                url,
                headers=fwd_headers,
                content=body if body else None,
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}") from e

    return _finalize_sandbox_proxy_response(
        sandbox_id,
        upstream,
        loopback_port=int(port),
        path_prefix=f"/api/sandbox/compose/{sandbox_id}/",
        proxy_kind="compose",
        inject_backend_fetch_shim=False,
        request=request,
    )


@router.post("/stop/{sandbox_id}")
async def stop_sandbox(sandbox_id: str, _admin: dict = Depends(require_admin_with_rbac)):
    """Stop a running sandbox."""
    if _lookup_sandbox(sandbox_id) is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    stop_preview_for_sandbox(sandbox_id)
    stop_compose_for_sandbox(sandbox_id)

    # Stop Docker container if running
    if _active_sandboxes[sandbox_id].get("docker_mode"):
        try:
            subprocess.run(
                ["docker", "stop", sandbox_id],
                capture_output=True, text=True, timeout=15
            )
            subprocess.run(
                ["docker", "rm", sandbox_id],
                capture_output=True, text=True, timeout=15
            )
            logger.info(f"Docker container {sandbox_id} stopped and removed")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to stop Docker container {sandbox_id}: {e}")

    _active_sandboxes[sandbox_id]["status"] = "stopped"
    _active_sandboxes[sandbox_id]["stopped_at"] = time.time()
    _save_registry()

    logger.info(f"Stopped sandbox {sandbox_id}")
    return {"status": "stopped"}


@router.get("/status/{sandbox_id}")
async def sandbox_status(sandbox_id: str):
    """Get sandbox status."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    return sandbox


@router.get("/active")
async def list_active_sandboxes(_admin: dict = Depends(require_admin_with_rbac)):
    """List all active sandboxes."""
    _load_registry()
    active = {
        sid: sb for sid, sb in _active_sandboxes.items()
        if sb.get("status") == "running"
    }
    return {"active_sandboxes": len(active), "sandboxes": list(active.values())}


# ── Git Integration ──────────────────────────────────────────────────────


@router.post("/git/init/{product_id}")
async def git_init(
    product_id: str,
    remote_url: str = "",
    _admin: dict = Depends(require_admin_with_rbac),
):
    """Initialize a git repository for the product's generated code."""
    safe_remote = ""
    if remote_url.strip():
        try:
            safe_remote = validate_git_remote_url(remote_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    product_code_dir = code_dir(product_id)
    if not product_code_dir.exists():
        raise HTTPException(status_code=404, detail="No code directory found for this product")

    repo_dir = product_code_dir / ".git"
    if repo_dir.exists():
        return {"status": "already_initialized", "product_id": product_id}

    try:
        import subprocess
        result = subprocess.run(
            ["git", "init"],
            cwd=str(product_code_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git init failed: {result.stderr}")

        # Configure basic git user
        subprocess.run(
            ["git", "config", "user.email", "ai-factory@aicom.local"],
            cwd=str(product_code_dir), capture_output=True, timeout=5
        )
        subprocess.run(
            ["git", "config", "user.name", "AI-Factory"],
            cwd=str(product_code_dir), capture_output=True, timeout=5
        )

        # Initial commit of existing code
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(product_code_dir), capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit - AI-Factory generated code"],
            cwd=str(product_code_dir), capture_output=True, timeout=10
        )

        # Set remote if provided
        if safe_remote:
            subprocess.run(
                ["git", "remote", "add", "origin", safe_remote],
                cwd=str(product_code_dir), capture_output=True, timeout=5
            )

        logger.info(f"Git repository initialized for product {product_id}")
        return {
            "status": "initialized",
            "product_id": product_id,
            "code_dir": str(product_code_dir),
            "remote": safe_remote or None,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git init timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git executable not found in container")


@router.post("/git/push/{product_id}")
async def git_push(
    product_id: str,
    remote: str = "origin",
    branch: str = "main",
    _admin: dict = Depends(require_admin_with_rbac),
):
    """Commit any pending changes and push to the configured remote."""
    product_code_dir = code_dir(product_id)
    repo_dir = product_code_dir / ".git"
    if not repo_dir.exists():
        raise HTTPException(status_code=400, detail="Git repository not initialized. Call git/init first.")

    try:
        import subprocess

        # Check if remote is configured
        remote_check = subprocess.run(
            ["git", "remote", "get-url", remote],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        if remote_check.returncode != 0:
            raise HTTPException(status_code=400, detail=f"Remote '{remote}' not configured. Set a remote URL first.")
        configured_url = (remote_check.stdout or "").strip()
        try:
            validate_git_remote_url(configured_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Unsafe git remote: {exc}") from exc

        # Add all changes
        subprocess.run(["git", "add", "-A"], cwd=str(product_code_dir), capture_output=True, timeout=10)

        # Commit if there are changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=5
        )
        if status.stdout.strip():
            subprocess.run(
                ["git", "commit", "-m", f"Auto-commit: AI-Factory update"],
                cwd=str(product_code_dir), capture_output=True, timeout=10
            )

        # Push to remote
        push_result = subprocess.run(
            ["git", "push", remote, branch],
            cwd=str(product_code_dir), capture_output=True, text=True, timeout=30
        )
        if push_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git push failed: {push_result.stderr}")

        return {
            "status": "pushed",
            "product_id": product_id,
            "remote": remote,
            "branch": branch,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git operation timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git executable not found in container")


@router.get("/git/status/{product_id}")
async def git_status(product_id: str):
    """Get git status for a product's codebase."""
    code_dir = code_dir(product_id)
    repo_dir = code_dir / ".git"
    if not repo_dir.exists():
        return {"status": "not_initialized", "product_id": product_id}

    try:
        import subprocess

        # Check remote
        remote_result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(code_dir), capture_output=True, text=True, timeout=5
        )
        remotes = remote_result.stdout.strip().split("\n") if remote_result.stdout.strip() else []

        # Check branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(code_dir), capture_output=True, text=True, timeout=5
        )
        branch = branch_result.stdout.strip()

        # Check status
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(code_dir), capture_output=True, text=True, timeout=5
        )
        changes = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []

        # Check log
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(code_dir), capture_output=True, text=True, timeout=5
        )
        commits = log_result.stdout.strip().split("\n") if log_result.stdout.strip() else []

        return {
            "status": "initialized",
            "product_id": product_id,
            "branch": branch,
            "remotes": remotes,
            "uncommitted_changes": len(changes),
            "change_list": changes[:20],
            "recent_commits": commits,
        }
    except FileNotFoundError:
        return {"status": "error", "detail": "git executable not found"}


# ── Helpers to check product code readiness ─────────────────────────────────


def _product_has_code(product_id: str) -> bool:
    """Check if a product has actual generated code files on disk."""
    manifest_path = code_dir(product_id) / "code_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        files = manifest.get("files", [])
        if not files:
            return False
        code_dir = code_dir(product_id)
        for f_entry in files:
            fpath = f_entry.get("path") or f_entry.get("file_path", "")
            if fpath and (code_dir / fpath).exists():
                return True
        return False
    except Exception:
        return False


def _product_has_html_files(product_id: str) -> bool:
    """Check if a product has at least one .html file in its code directory."""
    code_dir = code_dir(product_id)
    if not code_dir.exists():
        return False
    try:
        for _ in code_dir.rglob("*.html"):
            return True
    except Exception as _suppressed_exc:
        log_suppressed(logger, "non-fatal (web/backend/api/sandbox.py)", exc_info=_suppressed_exc)
    return False


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/products")
async def list_sandboxable_products():
    """List products that have code directories available for sandbox/git.
    Includes readiness indicators so the UI can warn about incomplete sandboxes."""
    from core.paths import data_root

    code_base = data_root() / "code"
    products = []

    # Load pipeline state to get product names (from idea field or metadata)
    pipeline_state_file = pipeline_json_path()
    pipeline_products = {}
    if pipeline_state_file.exists():
        try:
            with open(pipeline_state_file) as f:
                state = json.load(f)
            for pid, pdata in state.get("products", {}).items():
                pipeline_products[pid] = pdata
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/api/sandbox.py)", exc_info=_suppressed_exc)

    if code_base.exists():
        for d in sorted(code_base.iterdir()):
            if d.is_dir():
                pid = d.name
                repo_dir = d / ".git"
                git_status = "initialized" if repo_dir.exists() else "not_initialized"

                # Check if product has actual code files
                has_code = _product_has_code(pid)
                has_html = _product_has_html_files(pid)

                # Skip products with no code files at all
                if not has_code:
                    continue

                # Try to get product name from pipeline state's idea field
                product_name = ""
                if pid in pipeline_products:
                    idea = pipeline_products[pid].get("idea", "")
                    product_name = idea[:60].strip() if idea else ""

                # Fallback: try to load from spec file
                if not product_name:
                    spec_file = specs_dir(pid) / "specification.json"
                    if spec_file.exists():
                        try:
                            with open(spec_file) as f:
                                spec = json.load(f)
                            product_name = spec.get("product_name", spec.get("name", ""))
                        except Exception as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/sandbox.py)", exc_info=_suppressed_exc)

                # Fallback: try marketing content
                if not product_name:
                    mkt_file = product_state_dir(pid) / "marketing_content.json"
                    if mkt_file.exists():
                        try:
                            with open(mkt_file) as f:
                                mkt = json.load(f)
                            product_name = mkt.get("product_name", "")
                        except Exception as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/sandbox.py)", exc_info=_suppressed_exc)

                products.append({
                    "product_id": pid,
                    "product_name": product_name or pid,
                    "code_dir": str(d),
                    "git_status": git_status,
                    "has_code": has_code,
                    "has_html": has_html,
                    "sandbox_ready": has_code and has_html,
                })
    return {"products": products, "count": len(products)}
