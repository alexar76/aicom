"""
Runtime backend E2E checks for generated products.

Purpose:
- catch "looks-valid but not runnable" backend outputs;
- ensure generated API can boot and serve at least health plus one route.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _is_backend_like(py_files: list[Path]) -> bool:
    blob = ""
    for p in py_files[:30]:
        try:
            blob += p.read_text(encoding="utf-8", errors="replace").lower() + "\n"
        except OSError:
            continue
    return any(tok in blob for tok in ("fastapi", "flask", "django", "@app.", "apirouter"))


def _extract_routes(py_files: list[Path]) -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    patt = re.compile(r"@(?:app|router)\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]")
    for p in py_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in patt.finditer(text):
            method = m.group(1).upper()
            path = m.group(2).strip()
            if not path.startswith("/"):
                continue
            routes.append({"method": method, "path": path})
    # de-dup while preserving order
    seen: set[tuple[str, str]] = set()
    uniq: list[dict[str, str]] = []
    for r in routes:
        key = (r["method"], r["path"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _wait_for_port(host: str, port: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            s.close()
            return True
        except OSError:
            time.sleep(0.25)
        finally:
            try:
                s.close()
            except Exception:
                pass
    return False


def _http_call(method: str, url: str, timeout: float = 4.0, body: dict[str, Any] | None = None) -> tuple[bool, int, str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as r:
            return True, int(getattr(r, "status", 200)), ""
    except HTTPError as e:
        # 4xx/5xx still proves route is live
        return True, int(getattr(e, "code", 500)), ""
    except (URLError, TimeoutError, OSError) as e:
        return False, 0, str(e)


def _load_smoke(url: str, requests_count: int = 20) -> dict[str, Any]:
    lat_ms: list[int] = []
    errors = 0
    for _ in range(max(1, requests_count)):
        t0 = time.time()
        ok, status, _err = _http_call("GET", url, timeout=2.5)
        elapsed = int((time.time() - t0) * 1000)
        if ok:
            lat_ms.append(elapsed)
        else:
            errors += 1
        if status >= 500:
            errors += 1
    lat_ms.sort()
    p95 = lat_ms[int(len(lat_ms) * 0.95) - 1] if lat_ms else 0
    avg = int(sum(lat_ms) / len(lat_ms)) if lat_ms else 0
    threshold = int(os.environ.get("AIFACTORY_BACKEND_LOAD_P95_MS_MAX", "1200"))
    passed = bool(lat_ms) and errors == 0 and p95 <= threshold
    issues = []
    if not lat_ms:
        issues.append("load_smoke_no_successful_requests")
    if errors > 0:
        issues.append(f"load_smoke_errors:{errors}")
    if p95 > threshold:
        issues.append(f"load_smoke_p95_too_high:{p95}>{threshold}")
    return {
        "passed": passed,
        "requests": requests_count,
        "errors": errors,
        "avg_ms": avg,
        "p95_ms": p95,
        "threshold_p95_ms_max": threshold,
        "issues": issues,
    }


def _append_perf_history(product_id: str, data_root: str | Path, sample: dict[str, Any]) -> None:
    """
    Append one runtime performance sample to per-product history.
    """
    from core.paths import resolve_data_root

    root = resolve_data_root(data_root)
    tdir = root / "telemetry" / product_id
    tdir.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": time.time(),
        "avg_ms": int(sample.get("avg_ms") or 0),
        "p95_ms": int(sample.get("p95_ms") or 0),
        "errors": int(sample.get("errors") or 0),
        "passed": bool(sample.get("passed")),
    }
    hist = tdir / "load_perf_history.jsonl"
    with open(hist, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_spec_delivery_profile(product_id: str, root: Path) -> str | None:
    p = root / "specs" / product_id / "specification.json"
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            raw = doc.get("delivery_profile")
            return str(raw).strip() if raw else None
    except Exception:
        return None
    return None


def _probe_full_software_endpoints(base: str, routes: list[dict[str, str]]) -> list[str]:
    """
    Extra probes when specification says full_software — auth + DB connectivity signals.
    Uses permissive matching on declared FastAPI routes (best-effort).
    """
    issues: list[str] = []
    if not _truthy("AIFACTORY_BACKEND_FS_RUNTIME_PROBES", "1"):
        return issues

    route_blob = [(r.get("method", "").upper(), r.get("path", "")) for r in routes]

    # GET …/health/db or similar
    for method, path in route_blob:
        if method != "GET":
            continue
        pl = path.lower()
        if "health" in pl and "db" in pl:
            ok, status, err = _http_call("GET", f"{base}{path}")
            if not ok:
                issues.append(f"fs_probe_db_health_unreachable:{path}:{err[:120]}")
            elif status >= 500:
                issues.append(f"fs_probe_db_health_5xx:{path}:{status}")
            break

    # POST auth register / login — connection + non-timeout proves handler mounted
    demo_body_reg = {
        "email": "runtime.probe@aicom.local",
        "password": "RuntimeProbe!2026",
        "name": "Runtime Probe",
    }
    demo_body_login = {"email": "runtime.probe@aicom.local", "password": "RuntimeProbe!2026"}

    for method, path in route_blob:
        if method != "POST":
            continue
        pl = path.lower()
        if "register" in pl and "auth" in pl:
            ok, status, err = _http_call("POST", f"{base}{path}", body=demo_body_reg)
            if not ok:
                issues.append(f"fs_probe_register_unreachable:{path}:{err[:120]}")
            elif status == 404:
                issues.append(f"fs_probe_register_404:{path}")
            break

    for method, path in route_blob:
        if method != "POST":
            continue
        pl = path.lower()
        if "login" in pl and "auth" in pl:
            ok, status, err = _http_call("POST", f"{base}{path}", body=demo_body_login)
            if not ok:
                issues.append(f"fs_probe_login_unreachable:{path}:{err[:120]}")
            break

    return issues


def run_backend_runtime_e2e(product_id: str, data_root: str | Path | None = None) -> dict[str, Any]:
    """
    Attempt to boot generated backend and probe live HTTP routes.

    Returns:
      {
        passed: bool,
        skipped: bool,
        issues: list[str],
        details: {...}
      }
    """
    if not _truthy("AIFACTORY_BACKEND_RUNTIME_E2E", "1"):
        return {"passed": True, "skipped": True, "reason": "AIFACTORY_BACKEND_RUNTIME_E2E disabled"}

    from core.paths import resolve_data_root

    root = resolve_data_root(data_root)
    code_dir = root / "code" / product_id
    if not code_dir.is_dir():
        return {"passed": False, "skipped": False, "error": "no_code_dir", "issues": ["no_code_dir"]}

    py_files = list(code_dir.rglob("*.py"))
    if not py_files:
        return {"passed": True, "skipped": True, "reason": "no_python_backend_files"}

    if not _is_backend_like(py_files):
        return {"passed": True, "skipped": True, "reason": "not_backend_like"}

    entry = None
    for name in ("main.py", "app.py"):
        p = code_dir / name
        if p.is_file():
            entry = p
            break
    if entry is None:
        entry = py_files[0]

    # Use a stable port; generated backends often hardcode 8000.
    host = "127.0.0.1"
    port = 8000
    base = f"http://{host}:{port}"
    issues: list[str] = []
    details: dict[str, Any] = {"entrypoint": str(entry), "base_url": base}

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = f"{code_dir}:{env.get('PYTHONPATH', '')}"

    proc = subprocess.Popen(
        [sys.executable, str(entry.name)],
        cwd=str(code_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        if not _wait_for_port(host, port, timeout_sec=15.0):
            issues.append("backend_did_not_bind_port_8000")
            return {"passed": False, "skipped": False, "issues": issues, "details": details}

        # Health checks
        health_ok = False
        health_status = 0
        for hp in ("/api/health", "/health"):
            ok, status, err = _http_call("GET", f"{base}{hp}")
            if ok:
                health_ok = status < 500
                health_status = status
                details["health_path"] = hp
                break
            if err:
                issues.append(f"health_call_error:{hp}:{err[:160]}")
        details["health_status"] = health_status
        if not health_ok:
            issues.append("backend_health_endpoint_not_ready")
        load_smoke = _load_smoke(f"{base}{details.get('health_path') or '/health'}", requests_count=20)
        details["load_smoke"] = load_smoke
        if not load_smoke.get("passed", False):
            issues.extend(load_smoke.get("issues") or [])
        try:
            _append_perf_history(product_id, data_root, load_smoke)
        except Exception:
            pass

        # Probe one non-health business route if present.
        routes = _extract_routes(py_files)
        details["declared_routes"] = routes[:20]
        business = [r for r in routes if r["path"] not in ("/api/health", "/health")]
        business_ok = False
        if business:
            target = business[0]
            body = {} if target["method"] in ("POST", "PUT", "PATCH") else None
            ok, status, err = _http_call(target["method"], f"{base}{target['path']}", body=body)
            details["business_probe"] = {"route": target, "status": status, "ok": ok}
            # Any HTTP response means route handler is alive; connection errors mean dead backend.
            if ok:
                business_ok = True
            elif err:
                issues.append(f"business_route_unreachable:{target['method']} {target['path']}:{err[:160]}")
        else:
            issues.append("no_business_routes_declared")

        spec_dp = _read_spec_delivery_profile(product_id, root)
        details["spec_delivery_profile"] = spec_dp
        if spec_dp == "full_software":
            fs_issues = _probe_full_software_endpoints(base, routes)
            details["full_software_runtime_probes"] = fs_issues
            issues.extend(fs_issues)
            if fs_issues and _truthy("AIFACTORY_BACKEND_FS_GATE_STRICT", "0"):
                business_ok = False

        passed = health_ok and business_ok and bool(load_smoke.get("passed", False))
        if not passed and not issues:
            issues.append("backend_runtime_e2e_failed")
        return {"passed": passed, "skipped": False, "issues": issues, "details": details}
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
