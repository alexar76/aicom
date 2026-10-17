"""Starting a sandbox: the FastAPI or Docker preview, storefront rate limits, capacity and
eviction, the full bootstrap in the background, and the start response.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response

from web.backend.services.sandbox_preview_auth import (
    append_preview_token_query,
    mint_sandbox_preview_token,
)
from web.backend.services.sandbox_runtime import (
    append_image_and_command,
    detect_fastapi_backend,
    ensure_frontend_dist,
    hardened_docker_run_args,
    register_preview_proc,
    sandbox_preview_enabled,
    spa_dist_index,
    start_compose_preview,
    start_fastapi_preview,
)
from web.backend.services.sandbox_static_entry import resolve_static_preview_relpath
from web.backend.services.sandbox_static_rewrite import (
    public_origin_from_request,
    rewrite_loopback_location_header,
    rewrite_upstream_proxy_body,
    SANDBOX_HTML_CSP,
)

# Logged under the sandbox module's own name, whatever package path it was imported by.
logger = logging.getLogger(__name__.rsplit(".", 2)[0] + ".sandbox")


def _should_try_fastapi_preview(product_code_dir: Path, compose_ok: bool) -> bool:
    """Use uvicorn preview for FastAPI repos when compose is unavailable or failed.

    When a built SPA exists, FastAPI can serve UI + API on one origin — prefer that
    over a compose ``web`` container that cannot proxy ``/api/v1``.
    """
    # Operator kill-switch first: this decides whether UNTRUSTED generated code gets
    # pip-installed and imported in this container at all (docs/sandbox-trust-model.md).
    if not sandbox_preview_enabled():
        return False
    if spa_dist_index(product_code_dir) and detect_fastapi_backend(product_code_dir):
        return True
    if compose_ok:
        return False
    if not detect_fastapi_backend(product_code_dir):
        return False
    # NOT gated on AIFACTORY_SANDBOX_PREVIEW_API: that flag gates the /api/sandbox/backend
    # PROXY route (line ~1362), not whether uvicorn starts. The dead `if
    # preview_api_enabled(): return True` that used to sit here read as a gate and was
    # not one -- both branches returned True. Use AIFACTORY_SANDBOX_PREVIEW_ENABLED=0
    # above to actually turn previews off.
    return True


def _ensure_fastapi_preview(sandbox_id: str, entry: dict, product_code_dir: Path) -> bool:
    """Start loopback uvicorn if missing; mutates registry entry. Returns True when listening."""
    if entry.get("backend_preview_port"):
        return True
    bp, uv_proc, pst = start_fastapi_preview(sandbox_id=sandbox_id, code_dir=product_code_dir)
    entry["backend_preview_port"] = bp
    entry["preview_api_status"] = pst
    if uv_proc:
        register_preview_proc(sandbox_id, uv_proc)
    if bp:
        sandbox_api._active_sandboxes[sandbox_id] = entry
        sandbox_api._save_registry()
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
        k: v for k, v in upstream.headers.items() if k.lower() not in sandbox_api._HOP_BY_HOP_PROXY_RESP
    }
    loc = out_headers.get("location")
    if loc:
        new_loc = rewrite_loopback_location_header(loc, loopback_port, path_prefix)
        if new_loc != loc:
            out_headers["location"] = new_loc

    ct = upstream.headers.get("content-type")
    body = upstream.content
    sb = sandbox_api._lookup_sandbox(sandbox_id) or {}
    new_body, is_html = rewrite_upstream_proxy_body(
        body,
        ct,
        sandbox_id=sandbox_id,
        proxy_kind=proxy_kind,
        inject_backend_fetch_shim=inject_backend_fetch_shim,
        public_origin=public_origin_from_request(request),
        preview_token=sb.get("preview_token"),
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
    product_code_dir = sandbox_api._get_product_code_dir(product_id)
    if not product_code_dir:
        return False
    
    try:
        from web.backend.services.sandbox_docker import docker_cli_env

        # Use python:3.12-slim as base for sandbox, mount code
        base = hardened_docker_run_args(
            name=sandbox_id,
            network="none",
            memory="256m",
            cpus="0.5",
            workdir="/app/product",
            volume_mount=f"{product_code_dir}:/app/product:ro",
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
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=docker_cli_env(),
        )
        if result.returncode == 0:
            logger.info(f"Docker sandbox {sandbox_id} started on port {port}")
            return True
        else:
            logger.warning(f"Docker sandbox start failed: {result.stderr}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Docker not available for sandbox: {e}")
        return False


def _client_ip(request: Request) -> str:
    # Canonical resolver: the RIGHTMOST non-trusted X-Forwarded-For entry.
    # The inline parser this replaces trusted the LEFTMOST value, which the client
    # controls -- nginx `proxy_add_x_forwarded_for` APPENDS what it saw, so a caller
    # that sends its own X-Forwarded-For lands leftmost and can rotate a spoofed IP
    # past this per-IP limit. See web/backend/http/client_ip.py.
    from web.backend.http.client_ip import client_ip as _resolve

    return _resolve(request)


def _enforce_storefront_start_rate_limit(ip: str) -> None:
    now = time.time()
    window = sandbox_api._storefront_start_attempts[ip]
    while window and now - window[0] > sandbox_api._STOREFRONT_START_WINDOW_SEC:
        window.popleft()
    if len(window) >= sandbox_api._STOREFRONT_START_MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many sandbox previews. Try again later.")
    window.append(now)


def _storefront_allows_sandbox_preview(product_id: str) -> bool:
    from web.backend.api.products import _get_products_map, _public_storefront_grid_accepts

    product = _get_products_map().get(product_id)
    if not product:
        return False
    if not _public_storefront_grid_accepts(product_id, product):
        return False
    return sandbox_api._product_has_code(product_id)


def _degraded_preview_badge_html(sb_state: dict[str, Any]) -> str:
    if sb_state.get("preview_tier") != "degraded":
        return ""
    from web.backend.services.sandbox_guards import degraded_badge_message

    msg = degraded_badge_message(sb_state.get("degraded_reasons"))
    return (
        '<span style="margin-left:0.75rem;font-size:0.7rem;padding:0.2rem 0.55rem;'
        'border-radius:6px;background:rgba(234,179,8,0.15);color:#facc15;'
        'border:1px solid rgba(234,179,8,0.35)" title="'
        + msg.replace('"', "&quot;")
        + '">⚠ '
        + msg
        + "</span>"
    )


def _build_sandbox_start_response(
    sandbox_id: str,
    entry: dict[str, Any],
    *,
    preview_payload: dict[str, Any],
    compose_preview_payload: dict[str, Any],
    plan: Any | None = None,
) -> dict[str, Any]:
    preview_token = entry.get("preview_token") or ""
    view_url = f"/api/sandbox/view/{sandbox_id}"
    if preview_token:
        view_url = append_preview_token_query(view_url, preview_token)
    out: dict[str, Any] = {
        "sandbox_id": sandbox_id,
        "status": entry.get("status", "running"),
        "url": view_url,
        "expires_at": entry.get("expires_at", time.time() + 3600),
        "port": entry.get("port"),
        "docker_mode": entry.get("docker_mode", False),
        "preview_tier": entry.get("preview_tier", "full"),
        "startup_phase": entry.get("startup_phase", "ready"),
        "preview_api": preview_payload,
        "compose_preview": compose_preview_payload,
    }
    if entry.get("degraded_reasons"):
        out["degraded_reasons"] = entry["degraded_reasons"]
    warning = (plan.startup_warning if plan else None) or entry.get("startup_warning")
    if warning:
        out["startup_warning"] = warning
    if entry.get("preview_tier") == "degraded":
        out["degraded_badge"] = True
    return out


def _run_full_sandbox_bootstrap(
    sandbox_id: str,
    product_id: str,
    product_code_dir: Path,
    port: int,
    *,
    storefront: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compose + optional DinD + uvicorn preview (full product demo)."""
    compose_proxy_port: Optional[int] = None
    compose_preview_status: Optional[str] = None
    ensure_frontend_dist(product_code_dir)
    prefer_spa = bool(spa_dist_index(product_code_dir) and detect_fastapi_backend(product_code_dir))
    if prefer_spa:
        cpp, cst, _cproj = None, "skipped_fastapi_spa", None
    else:
        cpp, cst, _cproj = start_compose_preview(
            product_code_dir,
            sandbox_id,
            storefront=storefront,
        )
    compose_proxy_port = cpp
    compose_preview_status = cst
    compose_ok = compose_preview_status == "ok" and compose_proxy_port is not None

    docker_success = False
    host_port = None
    if not compose_ok and not prefer_spa:
        docker_success = sandbox_api._try_docker_run(sandbox_id, product_id, port)
        if docker_success:
            host_port = port

    with sandbox_api._registry_lock:
        entry = sandbox_api._active_sandboxes.get(sandbox_id) or {}
        entry.update(
            {
                "port": host_port,
                "docker_mode": docker_success,
                "compose_proxy_port": compose_proxy_port,
                "compose_preview_status": compose_preview_status,
                "startup_phase": "bootstrapping",
            }
        )
        sandbox_api._active_sandboxes[sandbox_id] = entry
        sandbox_api._save_registry()

    preview_payload: dict[str, Any] = {"enabled": False, "proxy_prefix": None, "status": None}
    if sandbox_api._should_try_fastapi_preview(product_code_dir, compose_ok):
        if sandbox_api._ensure_fastapi_preview(sandbox_id, entry, product_code_dir):
            preview_payload = {
                "enabled": True,
                "proxy_prefix": f"/api/sandbox/backend/{sandbox_id}/",
                "status": entry.get("preview_api_status"),
            }
        else:
            preview_payload = {
                "enabled": False,
                "proxy_prefix": None,
                "status": entry.get("preview_api_status"),
            }
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

    with sandbox_api._registry_lock:
        entry = sandbox_api._active_sandboxes.get(sandbox_id) or {}
        entry["startup_phase"] = "ready"
        sandbox_api._active_sandboxes[sandbox_id] = entry
        sandbox_api._save_registry()

    return preview_payload, compose_preview_payload


def _background_full_bootstrap(
    sandbox_id: str,
    product_id: str,
    port: int,
    *,
    storefront: bool,
) -> None:
    try:
        product_code_dir = sandbox_api._get_product_code_dir(product_id)
        if not product_code_dir:
            return
        sandbox_api._run_full_sandbox_bootstrap(
            sandbox_id,
            product_id,
            product_code_dir,
            port,
            storefront=storefront,
        )
    except Exception:
        logger.exception("background sandbox bootstrap failed sandbox=%s", sandbox_id[:16])
        with sandbox_api._registry_lock:
            entry = sandbox_api._active_sandboxes.get(sandbox_id)
            if entry:
                entry["startup_phase"] = "failed"
                sandbox_api._save_registry()


def _evict_oldest_running_sandbox() -> str | None:
    """Stop the oldest live sandbox to free a concurrency slot."""
    sandbox_api._prune_expired_and_teardown()
    now = time.time()
    candidates: list[tuple[str, dict[str, Any]]] = []
    for sid, sb in sandbox_api._active_sandboxes.items():
        if sb.get("status") != "running":
            continue
        expires = sb.get("expires_at")
        if isinstance(expires, (int, float)) and expires < now:
            continue
        candidates.append((sid, sb))
    if not candidates:
        return None

    candidates.sort(key=lambda item: float(item[1].get("started_at") or 0))
    sandbox_id = candidates[0][0]

    sandbox_api._teardown_sandbox_resources(sandbox_id, sandbox_api._active_sandboxes.get(sandbox_id))

    sandbox_api._active_sandboxes[sandbox_id]["status"] = "stopped"
    sandbox_api._active_sandboxes[sandbox_id]["stopped_at"] = time.time()
    sandbox_api._save_registry()
    logger.info("Evicted oldest sandbox %s to free a preview slot", sandbox_id)
    return sandbox_id


def _ensure_sandbox_capacity(*, storefront: bool) -> None:
    """Prune stale rows and evict oldest previews when storefront is at the cap."""
    from web.backend.services.sandbox_guards import (
        count_running_sandboxes,
        enforce_concurrency_limit,
        sandbox_max_concurrent,
        storefront_max_concurrent,
    )

    sandbox_api._load_registry()
    sandbox_api._prune_expired_and_teardown()
    sandbox_api._maybe_gc_preview_resources()
    cap = storefront_max_concurrent() if storefront else sandbox_max_concurrent()
    # Storefront already evicted; admin Files tab did not — so two leftover
    # rows (stuck bootstrap + another product's static preview) made Retry
    # return HTTP 500 / sandbox_busy while the operator was looking at Sentinel.
    while count_running_sandboxes(sandbox_api._active_sandboxes) >= cap:
        if not sandbox_api._evict_oldest_running_sandbox():
            break
    with sandbox_api._registry_lock:
        enforce_concurrency_limit(sandbox_api._active_sandboxes, storefront=storefront)


def _start_sandbox_for_product(
    product_id: str,
    *,
    storefront: bool = False,
    wait_for_bootstrap: bool = False,
) -> dict:
    """Core sandbox start: full stack by default; degraded static only when disk/RAM is low.

    ``wait_for_bootstrap`` blocks until the full-stack bootstrap finishes, so the returned
    ``preview_api`` / ``compose_preview`` describe a stack that is already live. It defaults to
    False because that is the only safe default for an HTTP caller: the bootstrap creates a
    venv, installs dependencies and builds the SPA, which the response's own
    ``startup_warning`` itself describes as "several minutes". Only a background job may ask to
    wait — ``working_app_publish`` does, because it decides whether the app is publishable from
    exactly those two fields.
    """
    from web.backend.services.sandbox_guards import evaluate_sandbox_resource_plan

    sandbox_api._ensure_sandbox_capacity(storefront=storefront)

    sandbox_id = f"sandbox-{uuid.uuid4().hex}"
    preview_token = mint_sandbox_preview_token()
    port = 9000 + (len(sandbox_api._active_sandboxes) % 1000)

    product_code_dir = sandbox_api._get_product_code_dir(product_id)
    if product_code_dir:
        from web.backend.services.sandbox_spec_landing import materialize_spec_landing_on_disk

        materialize_spec_landing_on_disk(product_id, code_root=product_code_dir)
        sandbox_api.ensure_storefront_preview_index(product_id, code_root=product_code_dir)

    static_rel = (
        resolve_static_preview_relpath(product_code_dir) if product_code_dir else None
    )
    plan = evaluate_sandbox_resource_plan(
        product_code_dir,
        has_static_preview=static_rel is not None,
    )

    entry: dict[str, Any] = {
        "id": sandbox_id,
        "product_id": product_id,
        "preview_token": preview_token,
        "status": "running",
        "started_at": time.time(),
        "expires_at": time.time() + 3600,
        "url": f"/sandbox/{sandbox_id}",
        "port": None,
        "docker_mode": False,
        "has_code": product_code_dir is not None,
        "preview_tier": plan.tier,
        "startup_phase": "starting",
        "backend_preview_port": None,
        "preview_api_status": None,
        "compose_proxy_port": None,
        "compose_preview_status": None,
    }
    if plan.tier == "degraded":
        entry["degraded_reasons"] = list(plan.reasons)
        entry["startup_phase"] = "ready"
        entry["startup_warning"] = None
    elif plan.startup_warning:
        entry["startup_warning"] = plan.startup_warning

    with sandbox_api._registry_lock:
        sandbox_api._active_sandboxes[sandbox_id] = entry
        sandbox_api._save_registry()

    preview_payload: dict[str, Any] = {"enabled": False, "proxy_prefix": None, "status": None}
    compose_preview_payload: dict[str, Any] = {
        "enabled": False,
        "proxy_prefix": None,
        "status": None,
    }

    if plan.tier == "degraded":
        return sandbox_api._build_sandbox_start_response(
            sandbox_id,
            entry,
            preview_payload=preview_payload,
            compose_preview_payload=compose_preview_payload,
            plan=plan,
        )

    # Unless a caller explicitly asks to wait, the full-stack bootstrap runs in the BACKGROUND.
    # Holding one HTTP request open for a multi-minute venv build is how the admin preview
    # broke: any interruption (a VPN reconnect, an idle proxy, a closed laptop) aborts the POST
    # after the server has already created the sandbox, so the browser reports a bare
    # "NetworkError" and the operator is shown a dead end while a perfectly good sandbox
    # finishes booting behind it. nginx logs those as 499 — the client gave up, not the server.
    #
    # Returning as soon as the sandbox is registered is also the contract the client was already
    # written for: it polls GET /ready/{id} for `startup_phase` and drives a progress bar from
    # it, which only ever advanced on the storefront path. Failures still surface, through
    # `startup_phase: "failed"` set by _background_full_bootstrap.
    if product_code_dir and not wait_for_bootstrap:
        threading.Thread(
            target=sandbox_api._background_full_bootstrap,
            args=(sandbox_id, product_id, port),
            kwargs={"storefront": storefront},
            daemon=True,
            name=f"sandbox-bootstrap-{sandbox_id[:12]}",
        ).start()
    elif product_code_dir:
        preview_payload, compose_preview_payload = sandbox_api._run_full_sandbox_bootstrap(
            sandbox_id,
            product_id,
            product_code_dir,
            port,
            storefront=storefront,
        )
        entry = sandbox_api._active_sandboxes.get(sandbox_id) or entry

    return sandbox_api._build_sandbox_start_response(
        sandbox_id,
        entry,
        preview_payload=preview_payload,
        compose_preview_payload=compose_preview_payload,
        plan=plan,
    )


# Imported last on purpose: this code reads sandbox's state, settings and helpers at
# call time (where tests patch them), and either module may load first.
from .. import sandbox as sandbox_api  # noqa: E402
