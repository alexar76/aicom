"""
Sandbox runtime facade — single import surface for preview + hardened Docker.

Implementation stays split (security hardening vs preview orchestration) to avoid
merging unlike lifecycles. Callers should import from this module instead of
reaching into five sandbox_* files directly.

See ``docs/architecture/module-boundaries.md``.
"""

from __future__ import annotations

# Hardened static DinD (security layer)
from security.docker_sandbox import append_image_and_command, hardened_docker_run_args

# Pipeline isolation (optional / tests; not used by HTTP preview today)
from security.sandbox_isolation import SandboxIsolation, SandboxStatus

# Preview infrastructure
from web.backend.services.sandbox_docker import (
    docker_available,
    ensure_ephemeral_postgres,
    pick_loopback_port,
    reap_stale_preview_resources,
    stop_ephemeral_services,
)
from web.backend.services.sandbox_compose_preview import (
    compose_preview_enabled,
    find_compose_file,
    start_compose_preview,
    stop_compose_for_sandbox,
)
from web.backend.services.sandbox_preview_api import (
    detect_fastapi_backend,
    ensure_frontend_dist,
    live_preview_iframe_path,
    preview_api_enabled,
    register_preview_proc,
    spa_dist_index,
    start_fastapi_preview,
    stop_preview_for_sandbox,
    terminate_preview_process,
    wait_port_open,
)

__all__ = [
    "SandboxIsolation",
    "SandboxStatus",
    "append_image_and_command",
    "hardened_docker_run_args",
    "compose_preview_enabled",
    "detect_fastapi_backend",
    "docker_available",
    "ensure_ephemeral_postgres",
    "ensure_frontend_dist",
    "find_compose_file",
    "live_preview_iframe_path",
    "pick_loopback_port",
    "preview_api_enabled",
    "reap_stale_preview_resources",
    "register_preview_proc",
    "spa_dist_index",
    "start_compose_preview",
    "start_fastapi_preview",
    "stop_compose_for_sandbox",
    "stop_ephemeral_services",
    "stop_preview_for_sandbox",
    "terminate_preview_process",
    "wait_port_open",
]
