"""
Run generated ``docker-compose.yml`` stacks for marketplace sandbox previews.

The factory container must have access to the Docker socket (same trust model as DinD static sandbox).

Env **AIFACTORY_SANDBOX_COMPOSE_PREVIEW** — ``1``/``true`` (default), ``0`` to disable.
Generated repos should publish ports via ``API_HOST_PORT``, ``WEB_HOST_PORT``, etc.; we inject free host ports before ``docker compose up``.
Also passes **SANDBOX_DEMO_EMAIL** / **SANDBOX_DEMO_PASSWORD** (and Vite mirrors) for prefilled auth in the iframe unless overridden by ``AIFACTORY_SANDBOX_DEMO_*`` on the factory host.

Env **AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION** — ``1`` (default): create a Docker **internal**
bridge network per preview so stack containers cannot egress to the public internet (intra-stack traffic only).
Set ``0`` to disable if a generated stack must reach external hosts at runtime.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from core.child_env import is_sensitive, scrub_child_env
from core.logging_utils import log_suppressed
from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose
from web.backend.services.sandbox_docker import docker_available, docker_cli_env, pick_loopback_port
from web.backend.services.sandbox_preview_network import (
    prepare_isolation_for_compose,
    preview_network_isolation_enabled,
    remove_internal_network,
)

logger = logging.getLogger(__name__)

_compose_meta: dict[str, dict[str, Any]] = {}


def compose_preview_enabled() -> bool:
    v = os.environ.get("AIFACTORY_SANDBOX_COMPOSE_PREVIEW", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


COMPOSE_NAMES = ("docker-compose.yml", "compose.yaml", "compose.yml")

_MAX_COMPOSE_BYTES = 1_000_000
_INTERPOLATION_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")
_DOCKER_CLIENT_ENV = ("DOCKER_HOST", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY", "DOCKER_CONFIG")
_FORBIDDEN_SERVICE_KEYS = {
    "cap_add",
    "cgroup",
    "cgroup_parent",
    "configs",
    "container_name",
    "credential_spec",
    "develop",
    "device_cgroup_rules",
    "devices",
    "dns",
    "dns_opt",
    "dns_search",
    "extra_hosts",
    "external_links",
    "extends",
    "gpus",
    "group_add",
    "ipc",
    "isolation",
    "links",
    "network_mode",
    "pid",
    "privileged",
    "runtime",
    "secrets",
    "security_opt",
    "sysctls",
    "use_api_socket",
    "userns_mode",
    "uts",
    "volumes_from",
}


def find_compose_file(code_dir: Path) -> Optional[Path]:
    for name in COMPOSE_NAMES:
        p = code_dir / name
        if p.is_file():
            return p
    return None


def _inside_project(path: Path, code_dir: Path) -> bool:
    try:
        path.resolve().relative_to(code_dir.resolve())
        return True
    except (OSError, ValueError):
        return False


def _host_bind_source(volume: Any) -> Optional[str]:
    """Return a host bind source, or None for named/anonymous/tmpfs volumes."""
    if isinstance(volume, dict):
        mount_type = str(volume.get("type") or "volume").strip().lower()
        source = str(volume.get("source") or volume.get("src") or "").strip()
        if mount_type == "bind":
            return source or "<empty>"
        if mount_type not in ("volume", "tmpfs"):
            return source or f"<{mount_type}>"
        return None
    if not isinstance(volume, str):
        return "<invalid>"
    value = volume.strip()
    if "${" in value:
        return value
    # A single container path is an anonymous volume. In source:target syntax,
    # Compose treats path-like sources as host binds and simple names as volumes.
    if ":" not in value:
        return None
    source = value.split(":", 1)[0].strip()
    if (
        source.startswith(("/", ".", "~", "\\", "//"))
        or "/" in source
        or "\\" in source
        or re.match(r"^[A-Za-z]:", value)
    ):
        return source
    return None


def _validate_project_path(raw: Any, code_dir: Path, *, label: str) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    if "${" in value:
        return [f"{label} may not use variable interpolation"]
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = code_dir / candidate
    if not _inside_project(candidate, code_dir):
        return [f"{label} escapes the generated project: {value[:120]}"]
    return []


def validate_generated_compose(compose_file: Path, code_dir: Path) -> list[str]:
    """Reject Compose features that cross the untrusted-preview boundary.

    This is intentionally a deny-by-capability policy rather than a linter. A
    model-authored stack may build and talk to sibling services, but it may not
    select host namespaces, mount host state, attach existing Docker resources,
    or make Compose read paths outside its generated project.
    """
    try:
        if compose_file.stat().st_size > _MAX_COMPOSE_BYTES:
            return [f"compose file exceeds {_MAX_COMPOSE_BYTES} bytes"]
        raw = compose_file.read_text(encoding="utf-8")
        doc = yaml.safe_load(raw)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return [f"compose file is not safe YAML: {str(exc)[:160]}"]
    if not isinstance(doc, dict):
        return ["compose document must be a mapping"]
    services = doc.get("services")
    if not isinstance(services, dict) or not services:
        return ["compose document has no services mapping"]

    issues: list[str] = []
    for var in sorted(set(_INTERPOLATION_RE.findall(raw))):
        if is_sensitive(var) or var.startswith("DOCKER_"):
            issues.append(f"compose references protected factory variable {var}")

    for top_key in ("include", "secrets", "configs"):
        if doc.get(top_key):
            issues.append(f"top-level {top_key} is not allowed in generated compose")

    top_networks = doc.get("networks") or {}
    if not isinstance(top_networks, dict):
        issues.append("top-level networks must be a mapping")
    else:
        for name, cfg in top_networks.items():
            if str(name) != "default":
                issues.append(f"custom network {name!s} is not allowed")
                continue
            if isinstance(cfg, dict) and any(cfg.get(k) for k in ("external", "name", "driver_opts", "attachable")):
                issues.append("default network may not select an existing/custom Docker network")

    top_volumes = doc.get("volumes") or {}
    if not isinstance(top_volumes, dict):
        issues.append("top-level volumes must be a mapping")
    else:
        for name, cfg in top_volumes.items():
            if isinstance(cfg, dict) and any(cfg.get(k) for k in ("external", "name", "driver_opts")):
                issues.append(f"volume {name!s} may not select an existing/custom Docker volume")

    for service_name, service in services.items():
        prefix = f"service {service_name!s}"
        if not isinstance(service, dict):
            issues.append(f"{prefix} must be a mapping")
            continue
        for key in sorted(_FORBIDDEN_SERVICE_KEYS):
            value = service.get(key)
            if value not in (None, False, "", [], {}):
                issues.append(f"{prefix} uses forbidden capability {key}")

        restart = str(service.get("restart") or "").strip().lower()
        if restart not in ("", "no", "none"):
            issues.append(f"{prefix} may not install restart policy {restart}")

        networks = service.get("networks")
        if isinstance(networks, list):
            network_names = [str(x) for x in networks]
        elif isinstance(networks, dict):
            network_names = [str(x) for x in networks]
        elif networks in (None, ""):
            network_names = []
        else:
            network_names = ["<invalid>"]
        if any(name != "default" for name in network_names):
            issues.append(f"{prefix} may only join the isolated default network")

        volumes = service.get("volumes") or []
        if not isinstance(volumes, list):
            issues.append(f"{prefix} volumes must be a list")
        else:
            for volume in volumes:
                source = _host_bind_source(volume)
                if source is not None:
                    issues.append(f"{prefix} uses forbidden host bind/volume source {source[:120]}")

        build = service.get("build")
        if isinstance(build, str):
            issues.extend(_validate_project_path(build, code_dir, label=f"{prefix} build context"))
        elif isinstance(build, dict):
            issues.extend(
                _validate_project_path(build.get("context", "."), code_dir, label=f"{prefix} build context")
            )
            for key in (
                "additional_contexts",
                "entitlements",
                "isolation",
                "network",
                "privileged",
                "secrets",
                "ssh",
            ):
                if build.get(key):
                    issues.append(f"{prefix} build uses forbidden capability {key}")
            dockerfile = build.get("dockerfile")
            if dockerfile:
                context_raw = str(build.get("context") or ".")
                context = Path(context_raw)
                if not context.is_absolute():
                    context = code_dir / context
                issues.extend(
                    _validate_project_path(context / str(dockerfile), code_dir, label=f"{prefix} dockerfile")
                )
        elif build is not None:
            issues.append(f"{prefix} build must be a path or mapping")

        env_files = service.get("env_file") or []
        if isinstance(env_files, (str, dict)):
            env_files = [env_files]
        if not isinstance(env_files, list):
            issues.append(f"{prefix} env_file must be a path or list")
        else:
            for item in env_files:
                value = item.get("path") if isinstance(item, dict) else item
                issues.extend(_validate_project_path(value, code_dir, label=f"{prefix} env_file"))

    return list(dict.fromkeys(issues))


def _compose_cli_env(base: Optional[dict[str, str]] = None) -> dict[str, str]:
    # Docker's client connection variables are required by the trusted CLI, but
    # validate_generated_compose rejects any attempt to interpolate them into a
    # generated service. All other factory credentials are removed.
    env = scrub_child_env(base or os.environ, keep=_DOCKER_CLIENT_ENV)
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"
    return docker_cli_env(env)


def _compose_project_name(sandbox_id: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", sandbox_id.lower()).strip("-")
    return (base or "sb")[:56]


def _parse_host_port(line: str) -> Optional[int]:
    line = line.strip()
    if not line:
        return None
    # "0.0.0.0:55432" or "[::]:55432"
    m = re.search(r":(\d+)\s*$", line)
    if m:
        return int(m.group(1))
    return None


def _discover_compose_http_port(
    project: str,
    code_dir: Path,
    compose_fname: str,
    override_path: Optional[str] = None,
    compose_env: Optional[dict[str, str]] = None,
) -> Optional[int]:
    tries = [
        ("web", 5173),
        ("frontend", 5173),
        ("ui", 5173),
        ("client", 5173),
        ("api", 8000),
        ("backend", 8000),
        ("app", 8000),
        ("server", 8000),
    ]
    base_cmd = ["docker", "compose", "-p", project, "-f", compose_fname]
    if override_path:
        base_cmd.extend(["-f", override_path])
    for svc, internal in tries:
        r = subprocess.run(
            [*base_cmd, "port", svc, str(internal)],
            cwd=str(code_dir),
            capture_output=True,
            text=True,
            timeout=25,
            env=compose_env or _compose_cli_env(),
        )
        if r.returncode != 0:
            continue
        hp = _parse_host_port((r.stdout or "").splitlines()[0] if r.stdout else "")
        if hp is not None:
            return hp

    # Fallback: inspect docker compose ps JSON (Compose v2)
    r = subprocess.run(
        [*base_cmd, "ps", "--format", "json"],
        cwd=str(code_dir),
        capture_output=True,
        text=True,
        timeout=60,
        env=compose_env or _compose_cli_env(),
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    best: Optional[int] = None
    for raw_line in r.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        publishers = row.get("Publishers") or row.get("Ports")
        blob = ""
        if isinstance(publishers, list):
            blob = " ".join(str(x) for x in publishers)
        elif isinstance(publishers, str):
            blob = publishers
        if not blob and isinstance(row.get("State"), str):
            blob = str(row.get("State", ""))
        for m in re.finditer(r"0\.0\.0\.0:(\d+)->(\d+)/tcp", blob):
            host_p = int(m.group(1))
            inner = int(m.group(2))
            if inner in (5173, 4173, 3000, 8080, 8000, 5000):
                return host_p
            if best is None:
                best = host_p
        if best is None:
            for m in re.finditer(r":(\d+)->(\d+)/tcp", blob):
                host_p = int(m.group(1))
                inner = int(m.group(2))
                if inner in (5173, 8000, 3000):
                    return host_p
                if best is None:
                    best = host_p
    return best


def compose_up_timeout_sec(*, storefront: bool = False) -> float:
    if storefront:
        try:
            return max(30.0, float(os.environ.get("AIFACTORY_SANDBOX_STOREFRONT_COMPOSE_TIMEOUT", "90")))
        except ValueError:
            return 90.0
    try:
        return max(60.0, float(os.environ.get("AIFACTORY_SANDBOX_COMPOSE_UP_TIMEOUT", "420")))
    except ValueError:
        return 420.0


def start_compose_preview(
    code_dir: Path,
    sandbox_id: str,
    *,
    storefront: bool = False,
) -> tuple[Optional[int], str, Optional[str]]:
    """
    ``docker compose up -d --build`` with env-injected host ports.
    Returns (loopback port to reverse-proxy, status token, compose project name for teardown).
    """
    if not compose_preview_enabled():
        return None, "compose_preview_disabled", None
    if not docker_available():
        return None, "docker_cli_missing", None
    cf = find_compose_file(code_dir)
    if cf is None:
        return None, "no_compose_file", None
    compose_issues = validate_generated_compose(cf, code_dir)
    if compose_issues:
        logger.warning(
            "sandbox compose: rejected unsafe compose sandbox=%s issues=%s",
            sandbox_id[:16],
            "; ".join(compose_issues[:8]),
        )
        return None, "compose_security_rejected", None

    project = _compose_project_name(sandbox_id)
    override_path_str, isolation_network = prepare_isolation_for_compose(project)
    if preview_network_isolation_enabled() and (not override_path_str or not isolation_network):
        logger.error("sandbox compose: isolation setup failed; refusing sandbox=%s", sandbox_id[:16])
        return None, "compose_isolation_failed", None

    api_port = pick_loopback_port()
    web_port = pick_loopback_port()
    pg_port = pick_loopback_port()

    env = _compose_cli_env(os.environ)
    env["API_HOST_PORT"] = str(api_port)
    env["WEB_HOST_PORT"] = str(web_port)
    env["FRONTEND_HOST_PORT"] = str(web_port)
    env["BACKEND_HOST_PORT"] = str(api_port)
    env["HTTP_HOST_PORT"] = str(web_port)
    env["SANDBOX_HTTP_PORT"] = str(web_port)
    env["POSTGRES_HOST_PORT"] = str(pg_port)
    env["MYSQL_HOST_PORT"] = str(pick_loopback_port())
    env["REDIS_HOST_PORT"] = str(pick_loopback_port())

    from core.demo_identity import sandbox_demo_email

    demo_email = sandbox_demo_email()
    demo_pw = effective_sandbox_demo_password_for_compose()
    env["SANDBOX_DEMO_EMAIL"] = demo_email
    env["SANDBOX_DEMO_PASSWORD"] = demo_pw
    env["VITE_SANDBOX_DEMO_EMAIL"] = demo_email
    env["VITE_SANDBOX_DEMO_PASSWORD"] = demo_pw

    compose_fname = cf.name
    cmd = ["docker", "compose", "-p", project, "-f", compose_fname]
    if override_path_str:
        cmd.extend(["-f", override_path_str])
    cmd.extend(["up", "-d", "--build"])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(code_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=compose_up_timeout_sec(storefront=storefront),
        )
    except subprocess.TimeoutExpired:
        logger.warning("sandbox compose: up timed out sandbox=%s", sandbox_id[:16])
        _compose_down(
            project,
            code_dir,
            compose_fname,
            override_path=override_path_str,
            isolation_network=isolation_network,
            compose_env=env,
        )
        return None, "compose_up_timeout", project
    except FileNotFoundError:
        if isolation_network:
            remove_internal_network(isolation_network)
        if override_path_str:
            try:
                Path(override_path_str).unlink(missing_ok=True)
            except OSError as _suppressed_exc:
                log_suppressed(logger, "non-fatal (web/backend/services/sandbox_compose_preview.py)", exc_info=_suppressed_exc)
        return None, "docker_cli_missing", None

    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or ""))[:1200]
        logger.warning("sandbox compose: up failed sandbox=%s err=%s", sandbox_id[:16], err)
        _compose_down(
            project,
            code_dir,
            compose_fname,
            override_path=override_path_str,
            isolation_network=isolation_network,
            compose_env=env,
        )
        return None, "compose_up_failed", project

    meta = {
        "project": project,
        "code_dir": str(code_dir),
        "compose_file": compose_fname,
        "network_override_path": override_path_str,
        "isolation_network": isolation_network,
        "compose_env": env,
    }
    _compose_meta[sandbox_id] = meta

    deadline = time.time() + 45.0
    host_port: Optional[int] = None
    while time.time() < deadline:
        host_port = _discover_compose_http_port(
            project, code_dir, compose_fname, override_path_str, compose_env=env
        )
        if host_port is not None:
            break
        time.sleep(0.7)

    if host_port is None:
        logger.warning("sandbox compose: no published HTTP port sandbox=%s project=%s", sandbox_id[:16], project)
        stop_compose_for_sandbox(sandbox_id)
        return None, "compose_no_published_port", project

    logger.info(
        "sandbox compose: proxy localhost:%s sandbox=%s project=%s",
        host_port,
        sandbox_id[:16],
        project,
    )
    return host_port, "ok", project


def _compose_down(
    project: str,
    code_dir: Path,
    compose_fname: str,
    *,
    override_path: Optional[str] = None,
    isolation_network: Optional[str] = None,
    compose_env: Optional[dict[str, str]] = None,
) -> None:
    cmd = ["docker", "compose", "-p", project, "-f", compose_fname]
    if override_path:
        cmd.extend(["-f", override_path])
    cmd.extend(["down", "--volumes", "--remove-orphans"])
    subprocess.run(
        cmd,
        cwd=str(code_dir),
        capture_output=True,
        text=True,
        timeout=180,
        env=compose_env or _compose_cli_env(),
    )
    if isolation_network:
        remove_internal_network(isolation_network)
    if override_path:
        try:
            Path(override_path).unlink(missing_ok=True)
        except OSError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/services/sandbox_compose_preview.py)", exc_info=_suppressed_exc)


def stop_compose_for_sandbox(sandbox_id: str) -> None:
    meta = _compose_meta.pop(sandbox_id, None)
    if not meta:
        return
    code_dir = Path(meta["code_dir"])
    project = meta["project"]
    compose_fname = meta.get("compose_file") or "docker-compose.yml"
    _compose_down(
        project,
        code_dir,
        compose_fname,
        override_path=meta.get("network_override_path"),
        isolation_network=meta.get("isolation_network"),
        compose_env=meta.get("compose_env"),
    )
    logger.info("sandbox compose: stopped project=%s sandbox=%s", project, sandbox_id[:16])
