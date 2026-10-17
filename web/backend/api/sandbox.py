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

import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

import os
import re

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.sandbox_proxy_headers import (
    sandbox_proxy_forward_headers,
    sandbox_proxy_slash_variant,
    sandbox_proxy_upstream_url,
)


from web.backend.services.url_safety import validate_git_remote_url

from core.logging_utils import log_suppressed
from web.backend.services.sandbox_runtime import (
    append_image_and_command,
    detect_fastapi_backend,
    ensure_frontend_dist,
    hardened_docker_run_args,
    live_preview_iframe_path,
    preview_api_enabled,
    sandbox_preview_enabled,
    register_preview_proc,
    spa_dist_index,
    start_compose_preview,
    start_fastapi_preview,
    stop_compose_for_sandbox,
    exited_preview_sandboxes,
    stop_preview_for_sandbox,
)
from web.backend.services.sandbox_spec_landing import resolve_sandbox_index_html
from web.backend.services.sandbox_static_entry import (
    ensure_storefront_preview_index,
    resolve_static_preview_relpath,
    static_preview_file,
)
from core.paths import code_dir as resolve_product_code_dir, data_root, pipeline_json_path, sandbox_registry_path, specs_dir, product_state_dir
from web.backend.services.sandbox_preview_auth import (
    append_preview_token_query,
    mint_sandbox_preview_token,
    require_sandbox_proxy_access,
    require_sandbox_view_access,
    sanitize_git_remote_line,
)
from web.backend.services.sandbox_static_rewrite import (
    SANDBOX_HTML_CSP,
    sandbox_iframe_sandbox_attr,
    SANDBOX_VIEWER_CSP,
    _inject_iframe_base_href,
    _inject_loopback_navigation_guard,
    _neutralize_iframe_breakouts,
    _rewrite_localhost_urls,
    _rewrite_root_absolute_paths,
    inject_preview_api_fetch_shim,
    inject_sandbox_in_page_nav_helpers,
    inject_sandbox_storage_shim,
    public_origin_from_request,
    rewrite_loopback_location_header,
    rewrite_upstream_proxy_body,
    sandbox_public_url,
)
from .sandbox_parts.registry import (  # noqa: F401 - re-exported
    _get_product_code_dir,
    _lookup_sandbox,
    _prune_expired_and_teardown,
    _reap_dead_previews,
    _reap_preview_resources_bg,
    _sandbox_workdir,
    _save_registry,
    _sweep_interval_s,
    _sweeper_loop,
    _teardown_sandbox_resources,
    _tree_bytes,
    remove_sandbox_workdir,
    sweep_once,
)
from .sandbox_parts.starting import (  # noqa: F401 - re-exported
    _background_full_bootstrap,
    _build_sandbox_start_response,
    _client_ip,
    _degraded_preview_badge_html,
    _enforce_storefront_start_rate_limit,
    _ensure_fastapi_preview,
    _ensure_sandbox_capacity,
    _evict_oldest_running_sandbox,
    _finalize_sandbox_proxy_response,
    _HOP_BY_HOP_PROXY_RESP,
    _run_full_sandbox_bootstrap,
    _should_try_fastapi_preview,
    _start_sandbox_for_product,
    _storefront_allows_sandbox_preview,
    _try_docker_run,
)
from .sandbox_parts.files import (  # noqa: F401 - re-exported
    _attach_sandbox_preview_cookie,
    _binary_media_type_from_magic,
    _bytes_look_like_html,
    _content_matches_declared_type,
    _MAGIC_BYTE_TYPES,
    _proxy_request_with_slash_fallback,
    _sniff_head_bytes,
)
from .sandbox_parts.git import (  # noqa: F401 - re-exported
    _git_init_blocking,
    _git_push_blocking,
    _GIT_REF_RE,
    _git_status_blocking,
    _product_has_code,
    _product_has_html_files,
    _validate_git_ref_name,
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
_registry_lock = threading.Lock()
_sandbox_orphans_reaped = False
_preview_gc_mono = 0.0
_SANDBOX_ID_RE = re.compile(r"^sandbox-[0-9a-f]{32}$")
_WORKDIR_GRACE_S = 3600.0
_sweeper_lock = threading.Lock()
_sweeper_thread: threading.Thread | None = None


def _load_registry() -> None:
    global _sandbox_orphans_reaped
    if not _SANDBOX_REGISTRY_PATH.exists():
        return
    try:
        with open(_SANDBOX_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _active_sandboxes.update(
                {str(k): v for k, v in data.items() if isinstance(v, dict)}
            )
            from web.backend.services.sandbox_guards import (
                mark_orphaned_uvicorn_previews,
                prune_expired_sandboxes,
            )

            prune_expired_sandboxes(_active_sandboxes)
            orphaned = 0
            # Only at process boot. Reaping on every start() would kill an in-flight
            # bootstrap that looks identical to a restart orphan (no port yet).
            if not _sandbox_orphans_reaped:
                orphaned = mark_orphaned_uvicorn_previews(_active_sandboxes)
                _sandbox_orphans_reaped = True
            for entry in _active_sandboxes.values():
                if isinstance(entry, dict) and not entry.get("preview_token"):
                    entry["preview_token"] = mint_sandbox_preview_token()
            logger.info(
                "sandbox registry: loaded %d entries (%d orphaned previews reaped)",
                len(_active_sandboxes),
                orphaned,
            )
            if orphaned:
                _save_registry()
    except Exception as e:
        logger.warning("sandbox registry load failed: %s", e)


_load_registry()


def _maybe_gc_preview_resources() -> None:
    """Sweep leftover DinD preview containers/volumes without blocking start()."""
    global _preview_gc_mono
    now = time.monotonic()
    if now - _preview_gc_mono < 60:
        return
    _preview_gc_mono = now
    threading.Thread(
        target=_reap_preview_resources_bg,
        name="sandbox-preview-gc",
        daemon=True,
    ).start()


def _sweep_stale_workdirs(*, grace_s: float = _WORKDIR_GRACE_S, now: float | None = None) -> tuple[int, int]:
    """Remove ``.aicom_sandbox/sandbox-<hex>`` trees that no running row owns.

    Only id-shaped names are touched (``sandbox-gatecheck`` and other fixed names belong to
    the gates, which reuse them), and anything modified within ``grace_s`` is left alone so
    a bootstrap is never raced. Returns (trees removed, bytes freed).
    """
    now = time.time() if now is None else now
    with _registry_lock:
        live = {
            sid
            for sid, e in _active_sandboxes.items()
            if isinstance(e, dict) and e.get("status") == "running"
        }
    code_root = data_root() / "code"
    if not code_root.is_dir():
        return 0, 0
    removed = freed = 0
    for tree in code_root.glob("*/.aicom_sandbox/sandbox-*"):
        try:
            if tree.is_symlink() or not tree.is_dir() or not _SANDBOX_ID_RE.match(tree.name):
                continue
            if tree.name in live or now - tree.stat().st_mtime < grace_s:
                continue
            size = _tree_bytes(tree)
            shutil.rmtree(tree, ignore_errors=True)
            removed += 1
            freed += size
        except OSError as exc:
            log_suppressed(logger, "sandbox workdir sweep", exc_info=exc)
    if removed:
        # warning, not info: nothing in this app configures the root logger, so uvicorn's
        # lastResort handler drops every INFO line — and deleting gigabytes of preview trees
        # is exactly the event an operator must be able to find afterwards.
        logger.warning("sandbox: removed %d stale preview tree(s), %.2f GB", removed, freed / 2**30)
    return removed, freed


def start_expiry_sweeper() -> bool:
    """Start the background sweeper once per process (``AIFACTORY_SANDBOX_SWEEP_INTERVAL_S=0`` disables)."""
    global _sweeper_thread
    interval = _sweep_interval_s()
    if interval <= 0:
        return False
    with _sweeper_lock:
        if _sweeper_thread is not None and _sweeper_thread.is_alive():
            return False
        _sweeper_thread = threading.Thread(
            target=_sweeper_loop, args=(interval,), name="sandbox-expiry-sweeper", daemon=True
        )
        _sweeper_thread.start()
    return True


_STOREFRONT_START_WINDOW_SEC = 3600
_STOREFRONT_START_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_SANDBOX_STOREFRONT_STARTS_PER_HOUR", "60"))
_storefront_start_attempts: dict[str, deque[float]] = defaultdict(deque)


@router.post("/start/{product_id}")
async def start_sandbox(product_id: str, _admin: dict = Depends(require_admin_with_rbac)):
    """Start a sandbox for a product (admin console)."""
    try:
        return await asyncio.to_thread(_start_sandbox_for_product, product_id, storefront=False)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("admin sandbox start failed product=%s", product_id)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "sandbox_start_failed",
                "message": "Preview could not be started. Retry in a few seconds.",
            },
        ) from exc


@router.post("/storefront/start/{product_id}")
async def start_sandbox_storefront(product_id: str, request: Request):
    """Start a sandbox preview for a product listed on the public storefront (no admin login)."""
    # Storefront preview is the core public demo experience — allowed even when
    # AIFACTORY_DEMO_READONLY=1 (rate limits + shelf checks still apply).
    _enforce_storefront_start_rate_limit(_client_ip(request))
    if not _storefront_allows_sandbox_preview(product_id):
        raise HTTPException(status_code=404, detail="Product preview not available")
    product_code_dir = _get_product_code_dir(product_id)
    if product_code_dir:
        ensure_storefront_preview_index(product_id, code_root=product_code_dir)
    try:
        return await asyncio.to_thread(_start_sandbox_for_product, product_id, storefront=True)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("storefront sandbox start failed product=%s", product_id)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "sandbox_start_failed",
                "message": "Preview could not be started.",
            },
        ) from exc


@router.get("/ready/{sandbox_id}")
async def sandbox_ready(sandbox_id: str):
    """Poll-friendly readiness for sandbox preview (used by storefront/admin loaders)."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        return {"ready": False, "progress": 0, "stage": "not_running"}

    product_id = sandbox.get("product_id", "")
    product_code_dir = _get_product_code_dir(product_id) if product_id else None
    if not product_code_dir:
        return {"ready": False, "progress": 25, "stage": "no_code"}

    sb_state = _active_sandboxes.get(sandbox_id) or sandbox
    tier = sb_state.get("preview_tier") or "full"
    phase = sb_state.get("startup_phase") or "ready"
    base_meta = {
        "preview_tier": tier,
        "startup_phase": phase,
        "degraded_badge": tier == "degraded",
        "degraded_reasons": sb_state.get("degraded_reasons"),
        "startup_warning": sb_state.get("startup_warning"),
    }
    if phase == "failed":
        return {**base_meta, "ready": False, "progress": 0, "stage": "bootstrap_failed"}
    if phase in ("starting", "bootstrapping"):
        progress = 35 if phase == "starting" else 65
        return {**base_meta, "ready": False, "progress": progress, "stage": phase}

    if sb_state.get("compose_proxy_port"):
        return {**base_meta, "ready": True, "progress": 100, "stage": "compose_ready"}
    if sb_state.get("backend_preview_port"):
        return {**base_meta, "ready": True, "progress": 100, "stage": "api_ready"}

    from web.backend.services.sandbox_static_entry import static_html_preview_usable

    rel = resolve_static_preview_relpath(product_code_dir)
    if not rel:
        return {**base_meta, "ready": False, "progress": 40, "stage": "index_missing"}

    if not static_html_preview_usable(product_code_dir, rel):
        return {**base_meta, "ready": False, "progress": 55, "stage": "index_building", "preview_path": rel}

    idx = product_code_dir / rel
    try:
        size = idx.stat().st_size
    except OSError:
        size = 0
    if size < 400:
        return {
            **base_meta,
            "ready": False,
            "progress": 60,
            "stage": "index_building",
            "preview_path": rel,
        }

    return {
        **base_meta,
        "ready": True,
        "progress": 100,
        "stage": "preview_ready",
        "preview_path": rel,
    }


@router.get("/view/{sandbox_id}")
async def view_sandbox(request: Request, sandbox_id: str):
    """View sandbox content in browser — renders HTML demo in iframe."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")
    await require_sandbox_view_access(sandbox_id, request, sandbox=sandbox)

    product_id = sandbox.get("product_id", "unknown")
    preview_token = (sandbox.get("preview_token") or "").strip()
    from web.backend.services.sandbox_remediation_badge import (
        remediation_badge_markup,
        resolve_remediation_badge_locale,
    )

    badge_locale = resolve_remediation_badge_locale(request)
    rework_badge_html = remediation_badge_markup(product_id, locale=badge_locale)
    product_code_dir = _get_product_code_dir(product_id)
    sb_state = _active_sandboxes.get(sandbox_id) or sandbox
    compose_ok = sb_state.get("compose_proxy_port") is not None
    static_ready = (
        product_code_dir is not None
        and resolve_static_preview_relpath(product_code_dir) is not None
    )
    if (
        product_code_dir
        and not static_ready
        and _should_try_fastapi_preview(product_code_dir, compose_ok)
    ):
        await asyncio.to_thread(_ensure_fastapi_preview, sandbox_id, sb_state, product_code_dir)
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
    if product_code_dir:
        try:
            from web.backend.services.visual_gate_autofix import heal_preview_presentation

            await asyncio.to_thread(heal_preview_presentation, product_code_dir)
        except Exception as _heal_exc:
            log_suppressed(logger, "preview presentation heal on view", exc_info=_heal_exc)
        files = []
        static_preview_rel = resolve_static_preview_relpath(product_code_dir)
        for f in sorted(product_code_dir.rglob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            if any(part in f.parts for part in (".aicom_sandbox", "node_modules", ".git")):
                continue
            try:
                rel = f.relative_to(product_code_dir)
                files.append(str(rel))
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
        degraded_hint = _degraded_preview_badge_html(sb_state)
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
        elif not compose_ok and product_code_dir and ((product_code_dir / "backend").is_dir() or (product_code_dir / "server").is_dir()):
            hint_extra = ""
            if preview_api_enabled():
                hint_extra = " Preview API mode is on — ensure <code>backend/main.py</code> exposes FastAPI <code>app</code>."
            backend_hint = (
                '<span style="margin-left:1rem;color:#8888aa;font-size:0.7rem">'
                "Backend folder present — static files only until uvicorn preview starts."
                + hint_extra
                + "</span>"
            )

        spa_index = spa_dist_index(product_code_dir) if product_code_dir else None
        dist_rel = spa_index.relative_to(product_code_dir).as_posix() if spa_index else None
        preview_path, preview_label = live_preview_iframe_path(
            sandbox_id,
            dist_rel=dist_rel,
            backend_preview_port=backend_preview_port,
            compose_ok=compose_ok,
            static_rel=static_preview_rel,
        )
        if preview_token:
            preview_path = append_preview_token_query(preview_path, preview_token)
        iframe_src = sandbox_public_url(request, preview_path)

        lang_sep = "&" if "?" in iframe_src else "?"
        iframe_src = f"{iframe_src}{lang_sep}lang={badge_locale}"

        if static_preview_rel or compose_ok or backend_preview_port:
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
                <span>🌐 Live Preview — <span style="color:#6366f1">{preview_label}</span></span>{degraded_hint}{compose_hint}{backend_hint}
            </div>
            <iframe name="demo-frame" src="{iframe_src}" title="Demo Preview"
                sandbox="{sandbox_iframe_sandbox_attr()}" referrerpolicy="no-referrer"></iframe>
        </div>
    </div>
    {rework_badge_html}
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
    {rework_badge_html}
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

    return _attach_sandbox_preview_cookie(
        HTMLResponse(
            content=html,
            headers={
                "Content-Security-Policy": SANDBOX_VIEWER_CSP,
                "X-Content-Type-Options": "nosniff",
            },
        ),
        sandbox_id,
        sandbox,
    )


@router.get("/file/{sandbox_id}/{file_path:path}")
async def get_sandbox_file(request: Request, sandbox_id: str, file_path: str):
    """Serve individual files from a sandbox (for iframe preview)."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")

    product_id = sandbox.get("product_id", "unknown")
    product_code_dir = _get_product_code_dir(product_id)
    if not product_code_dir:
        raise HTTPException(status_code=404, detail="Code directory not found")

    base_dir = product_code_dir.resolve()
    candidate = base_dir / file_path
    # Security: keep the request inside the product code dir WITHOUT following any
    # symlink out of it. Generated/untrusted code can plant a symlink (e.g. to
    # /etc/passwd); resolving it would otherwise read host files via this API (S5).
    # Reject the file itself or any path component that is a symlink, then confirm
    # the fully-resolved path is still contained in base_dir.
    try:
        if candidate.is_symlink():
            raise HTTPException(status_code=403, detail="Access denied")
        # Walk every component between base_dir and the target; reject symlinked dirs.
        rel_parts = candidate.relative_to(base_dir).parts if candidate.is_relative_to(base_dir) else None
        if rel_parts is None:
            raise HTTPException(status_code=403, detail="Access denied")
        probe = base_dir
        for part in rel_parts:
            probe = probe / part
            if probe.is_symlink():
                raise HTTPException(status_code=403, detail="Access denied")
        resolved = candidate.resolve()
        resolved.relative_to(base_dir)
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError, OSError):
        raise HTTPException(status_code=403, detail="Access denied")
    full_path = resolved
    norm_path = file_path.replace("\\", "/").lstrip("/")

    if full_path.is_dir():
        # A directory URL (``…/frontend/dist/``) is what a ``#/route`` link resolves to
        # under the injected <base href>, and what a reload then requests: serve its
        # index.html like any static server. ``norm_path`` must name the file, so the
        # base href keeps the directory even when the URL had no trailing slash.
        dir_index = full_path / "index.html"
        if not dir_index.is_symlink() and dir_index.is_file():
            full_path = dir_index
            norm_path = dir_index.relative_to(base_dir).as_posix()

    if not full_path.exists() or not full_path.is_file():
        # Vite SPA builds emit ``/assets/…`` from ``frontend/dist/index.html``. When
        # <base href> was (or still is) the sandbox root, browsers request
        # ``/api/sandbox/file/{id}/assets/…`` — map that onto the dist folder.
        alt_path = None
        if norm_path.startswith("assets/"):
            spa = spa_dist_index(product_code_dir)
            if spa is not None:
                alt_candidate = spa.parent / norm_path
                try:
                    if (
                        not alt_candidate.is_symlink()
                        and alt_candidate.is_file()
                        and alt_candidate.resolve().is_relative_to(base_dir)
                    ):
                        alt_path = alt_candidate.resolve()
                except (OSError, ValueError):
                    alt_path = None
        if alt_path is None:
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        full_path = alt_path

    from web.backend.services.sandbox_file_policy import sandbox_file_path_allowed

    if not sandbox_file_path_allowed(norm_path):
        raise HTTPException(status_code=403, detail="File type not available for sandbox preview")

    try:
        content = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary file. Decide the type from magic bytes (not the extension) so a
        # mislabeled binary cannot be served as an executable/renderable type, and
        # always send nosniff (A8).
        raw = full_path.read_bytes()
        bin_type = _binary_media_type_from_magic(raw)
        return Response(
            content=raw,
            media_type=bin_type,
            headers={"X-Content-Type-Options": "nosniff"},
        )
    if isinstance(content, str) and norm_path.lower().endswith((".html", ".htm")):
        if norm_path in ("index.html", "index.htm") or norm_path.endswith("/index.html") or norm_path.endswith("/index.htm"):
            from web.backend.services.sandbox_remediation_badge import resolve_remediation_badge_locale

            badge_locale = resolve_remediation_badge_locale(request)
            content = resolve_sandbox_index_html(product_id, content, locale=badge_locale)

    # Determine content type. The extension is attacker-controlled (generated
    # code names its own files), so it MUST NOT be the sole basis for a security
    # decision (A8). We sniff the actual bytes: anything that looks like markup is
    # forced down the HTML path (neutralized + strict CSP) no matter its extension,
    # and an extension that *claims* a binary image/font must match its magic bytes
    # or it is demoted to text/plain. nosniff is always set so browsers can't
    # second-guess us into executing a mislabeled file.
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

    # Content sniffing on the raw bytes (decode-independent for binaries).
    head_bytes = _sniff_head_bytes(content)
    sniffed_html = _bytes_look_like_html(head_bytes)
    if sniffed_html and media_type not in ("text/html", "image/svg+xml"):
        # A non-HTML extension carrying HTML markup (e.g. evil.png / evil.txt):
        # treat it as HTML so it goes through neutralization + CSP, never raw.
        media_type = "text/html"
    elif media_type in _MAGIC_BYTE_TYPES and not _content_matches_declared_type(
        media_type, head_bytes
    ):
        # Declared a binary type whose magic bytes do not match — do not serve it
        # under that content-type. Demote to inert text/plain (nosniff below).
        logger.warning(
            "sandbox %s: file %r declared %s but bytes do not match; serving as text/plain",
            sandbox_id[:16],
            norm_path,
            media_type,
        )
        media_type = "text/plain"

    if isinstance(content, str):
        content = _rewrite_localhost_urls(content)
        content = _rewrite_root_absolute_paths(content)
        if media_type == "text/html":
            content = _neutralize_iframe_breakouts(content)
            content = _inject_iframe_base_href(
                content, sandbox_id, request, file_path=norm_path
            )
            content = inject_sandbox_storage_shim(content)
            sbrec = _active_sandboxes.get(sandbox_id) or {}
            if sbrec.get("backend_preview_port"):
                content = inject_preview_api_fetch_shim(
                    content,
                    sandbox_id,
                    preview_token=sbrec.get("preview_token"),
                )
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

    # nosniff on every non-HTML response so a browser can't MIME-sniff a
    # mislabeled file (e.g. text/plain that is really markup) into execution (A8).
    return Response(
        content=content,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.api_route(
    "/backend/{sandbox_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def sandbox_backend_proxy(sandbox_id: str, path: str, request: Request):
    """Reverse-proxy to uvicorn preview bound on loopback (see ``AIFACTORY_SANDBOX_PREVIEW_API``)."""
    sandbox = _lookup_sandbox(sandbox_id)
    if not sandbox or sandbox.get("status") != "running":
        raise HTTPException(status_code=404, detail="Sandbox not found or not running")
    await require_sandbox_proxy_access(sandbox_id, request, sandbox=sandbox)
    port = sandbox.get("backend_preview_port")
    if not port:
        raise HTTPException(
            status_code=503,
            detail="Preview API not active — set AIFACTORY_SANDBOX_PREVIEW_API=1 and ensure FastAPI backend exists.",
        )
    url = sandbox_proxy_upstream_url("127.0.0.1", int(port), path, request.url.query)

    body = await request.body()
    fwd_headers = sandbox_proxy_forward_headers(request)

    try:
        upstream = await _proxy_request_with_slash_fallback(
            request.method, url, fwd_headers, body
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail="Upstream error") from e

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
    await require_sandbox_proxy_access(sandbox_id, request, sandbox=sandbox)
    port = sandbox.get("compose_proxy_port")
    if not port:
        raise HTTPException(
            status_code=503,
            detail="Compose preview inactive — add docker-compose.yml with env-driven ports "
            "(API_HOST_PORT, WEB_HOST_PORT) or disable compose preview.",
        )
    from web.backend.services.sandbox_docker import docker_daemon_host

    url = sandbox_proxy_upstream_url(docker_daemon_host(), int(port), path, request.url.query)

    body = await request.body()
    fwd_headers = sandbox_proxy_forward_headers(request)

    try:
        upstream = await _proxy_request_with_slash_fallback(
            request.method, url, fwd_headers, body
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail="Upstream error") from e

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

    entry = dict(_active_sandboxes.get(sandbox_id) or {})
    await asyncio.to_thread(_teardown_sandbox_resources, sandbox_id, entry)

    with _registry_lock:
        row = _active_sandboxes.get(sandbox_id)
        if row is not None:
            row["status"] = "stopped"
            row["stopped_at"] = time.time()
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

    product_code_dir = resolve_product_code_dir(product_id)
    if not product_code_dir.exists():
        raise HTTPException(status_code=404, detail="No code directory found for this product")

    repo_dir = product_code_dir / ".git"
    if repo_dir.exists():
        return {"status": "already_initialized", "product_id": product_id}

    return await asyncio.to_thread(_git_init_blocking, product_code_dir, product_id, safe_remote)


@router.post("/git/push/{product_id}")
async def git_push(
    product_id: str,
    remote: str = "origin",
    branch: str = "main",
    _admin: dict = Depends(require_admin_with_rbac),
):
    """Commit any pending changes and push to the configured remote."""
    remote = _validate_git_ref_name(remote, "remote")
    branch = _validate_git_ref_name(branch, "branch")
    product_code_dir = resolve_product_code_dir(product_id)
    repo_dir = product_code_dir / ".git"
    if not repo_dir.exists():
        raise HTTPException(status_code=400, detail="Git repository not initialized. Call git/init first.")

    return await asyncio.to_thread(_git_push_blocking, product_code_dir, product_id, remote, branch)


@router.get("/git/status/{product_id}")
async def git_status(product_id: str, _admin: dict = Depends(require_admin_with_rbac)):
    """Get git status for a product's codebase (admin only; remotes sanitized)."""
    product_code_dir = resolve_product_code_dir(product_id)
    repo_dir = product_code_dir / ".git"
    if not repo_dir.exists():
        return {"status": "not_initialized", "product_id": product_id}

    return await asyncio.to_thread(_git_status_blocking, product_code_dir, product_id)


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
