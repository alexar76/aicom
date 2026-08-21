"""Open the deployed site in a browser and decide whether it is actually a product.

Every gate in this pipeline measures a sandbox: uvicorn on loopback, a venv assembled for the run,
a preview build served from disk. That is the right place to catch most defects and the wrong place
to decide that a deployment works, because the two environments differ in exactly the ways that
break deployments.

This gate is the last word: it drives the LIVE URL the way a person would — every SPA route, every
form, every public API the OpenAPI document advertises — and it is allowed to un-publish. A page
that renders while its only feature answers 200 with a Python TypeError hidden as UNKNOWN is not a
product. Measured on Sentinel: `/api/health` was 200, the primary button was clicked on an empty
required form, styled_ratio passed, and the visitor still saw

    AtlasClient.get_situation_brief() got an unexpected keyword argument 'west'
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from web.backend.services.browser_e2e_deep import exception_in_product_output

logger = logging.getLogger(__name__)

# Measured on the real failure: the deployed page had 9 of 31 elements carrying any non-default
# styling — 29% — and looked like an unstyled document to the person who opened it. A designed page
# styles most of what it renders; a ratio this low means the markup is asking for rules that do not
# exist. Kept as a ratio rather than a count because a large page can fail while a small one passes.
_MIN_STYLED_RATIO = 0.45
_MIN_ELEMENTS_TO_JUDGE = 10

# Berlin: the same geo the demo journey uses, so an empty answer is a defect rather than a blank
# spot on the map. LA is the live-gate mesh probe: Berlin often has zero LIVE pins, which is an
# honest ATLAS refuse — not a deploy defect. Connection failures still fail the gate everywhere.
_LIVE_LAT = "52.52"
_LIVE_LON = "13.40"
_MESH_PROBE_LAT = "34.05"
_MESH_PROBE_LON = "-118.25"

_MESH_UNREACHABLE_RE = re.compile(
    r"All connection attempts failed|Connection refused|ConnectTimeout|ConnectError|"
    r"Name or service not known|nodename nor servname|Failed to establish a new connection|"
    r"Max retries exceeded|Network is unreachable|"
    r"Mesh unavailable:.*(localhost|127\.0\.0\.1|Connect|attempts failed)",
    re.I,
)


def _code_dir_for(product_id: str | None, data_root: str | Path | None) -> Path | None:
    if not product_id:
        return None
    try:
        from core.paths import code_dir as resolve_code_dir

        path = resolve_code_dir(product_id, data_root=data_root)
    except Exception:
        return None
    return path if path.is_dir() else None


def _auth_seed_repair_files(code_dir: Path | None) -> list[str]:
    """Files that must read SANDBOX_DEMO_* so the live gate can log in after publish."""
    if code_dir is None or not code_dir.is_dir():
        return []
    candidates = (
        "backend/app/seed.py",
        "backend/app/demo_seed.py",
        "backend/app/services/seeding.py",
        "backend/app/services/demo_seed.py",
        "backend/app/routers/auth.py",
        "backend/app/core/seed.py",
        "backend/app/db/seed.py",
    )
    found: list[str] = []
    for rel in candidates:
        if (code_dir / rel).is_file() and rel not in found:
            found.append(rel)
    if found:
        return found
    skip = {"tests", "test", "node_modules", ".venv", "venv"}
    try:
        for path in code_dir.rglob("*.py"):
            if any(part in skip for part in path.parts):
                continue
            name = path.name.lower()
            if "seed" not in name and path.name != "auth.py":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:40_000]
            except OSError:
                continue
            if "SANDBOX_DEMO" in text or "demo" in name:
                rel = path.relative_to(code_dir).as_posix()
                if rel not in found:
                    found.append(rel)
            if len(found) >= 6:
                break
    except Exception:
        return found
    return found


def _is_demo_auth_failure(status: int, path: str, body: str = "") -> bool:
    if status not in (401, 403):
        return False
    low_path = (path or "").lower()
    if any(tok in low_path for tok in ("/auth/login", "/api/auth", "/login", "/token")):
        return True
    low_body = (body or "").lower()
    return "invalid credentials" in low_body or "incorrect password" in low_body


def _issue_for_demo_auth(*, where: str, status: int, body: str = "") -> str:
    snippet = " ".join((body or "")[:160].split())
    return (
        f"live_demo_auth_mismatch:POST {where}:{status} on the DEPLOYED site. "
        "Factory live-gate credentials (SANDBOX_DEMO_EMAIL / SANDBOX_DEMO_PASSWORD) were rejected. "
        "The Vercel bundle must inject those env vars into api/index.py and vercel.json, and the "
        "product seed must create that user from env — not only local fallbacks like "
        "operator@….local. Fix publish injection / seed env wiring; do not treat this as a "
        "missing Python dependency. "
        f"Body: {snippet}"
    )


def _repair_scope_from_issues(issues: list[str], code_dir: Path | None) -> list[str]:
    """Name the files a repair round must open, so scope does not wander into operator TSX."""
    from core.repair_batches import _files_in

    named: list[str] = []
    blob = " ".join(issues)
    for rel in _files_in(blob):
        if rel not in named:
            named.append(rel)
    if re.search(
        r"live_demo_auth_mismatch|live_http_401|Invalid credentials|/auth/login|SANDBOX_DEMO",
        blob,
        re.I,
    ):
        for rel in _auth_seed_repair_files(code_dir):
            if rel not in named:
                named.append(rel)
    if re.search(r"live_mesh_unreachable|All connection attempts failed|/aimarket/invoke|ATLAS_BASE", blob, re.I):
        for rel in (
            "backend/app/services/atlas_client.py",
            "backend/app/config.py",
            "backend/app/routers/advisory.py",
        ):
            if code_dir is not None and (code_dir / rel).is_file() and rel not in named:
                named.append(rel)
    if code_dir is None:
        return named[:12]
    class_hits = re.findall(r"\b([A-Z][A-Za-z0-9]+)[.]([A-Za-z_][A-Za-z0-9_]*)\s*\(", blob)
    needles: list[str] = []
    for cls, method in class_hits:
        needles.append(f"class {cls}")
        needles.append(f"def {method}")
        needles.append(f"async def {method}")
        needles.append(f".{method}(")
    if not needles:
        return named[:12]
    skip = {"tests", "test", "node_modules", ".venv", "venv", "alembic", "migrations"}
    try:
        for path in code_dir.rglob("*.py"):
            if any(part in skip for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:80_000]
            except OSError:
                continue
            if any(n in text for n in needles):
                rel = path.relative_to(code_dir).as_posix()
                if rel not in named:
                    named.append(rel)
            if len(named) >= 12:
                break
    except Exception:
        return named[:12]
    return named[:12]


def _issue_for_mesh_unreachable(*, where: str, status: int, reason: str) -> str:
    snippet = " ".join((reason or "")[:220].split())
    return (
        f"live_mesh_unreachable:{where}:{status} on the DEPLOYED site: {snippet}. "
        "The serverless function cannot reach the public ATLAS mesh. Publish must inject "
        "ATLAS_BASE_URL=https://atlas.modelmarket.dev (not localhost) and call "
        "/ai-market/v2/invoke — not the legacy /aimarket/invoke path."
    )


def _issue_for_exception(*, where: str, status: int, hit: str, body: str) -> str:
    snippet = " ".join((body or "")[:220].split())
    return (
        f"live_exception_in_ui:{where}:{status} on the DEPLOYED site: {hit}. "
        "The endpoint answered 200 (or painted the page) with a Python exception in the body, "
        "which the honesty policy wrapped as UNKNOWN. This is a call/signature mismatch, not "
        "missing sensors. Fix the call site to match the method signature "
        "(backend/app/routers/advisory.py calling backend/app/services/atlas_client.py is the "
        "shape that shipped). Do NOT swallow TypeError/AttributeError into UNKNOWN. "
        f"Body: {snippet}"
    )


def _sweep_live_api(base: str) -> tuple[list[str], dict[str, Any]]:
    """Exercise every documented GET on the deployed origin, filling required query params."""
    from web.backend.services.product_demo_journey import (
        _find_login_paths,
        _openapi,
        attempt_login,
        sweep_get_endpoints,
    )
    from core.demo_identity import sandbox_demo_email
    from web.backend.services.demo_credentials import effective_sandbox_demo_password_for_compose

    issues: list[str] = []
    report: dict[str, Any] = {"base": base}
    doc = _openapi(base)
    paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
    report["openapi_path_count"] = len(paths)
    token = ""
    login_paths = _find_login_paths(paths) if paths else []
    report["login_paths"] = login_paths
    if login_paths:
        try:
            email = sandbox_demo_email()
            password = effective_sandbox_demo_password_for_compose()
            token, trace = attempt_login(base, login_paths[0], email, password)
            report["login"] = {k: v for k, v in trace.items() if k != "attempts"}
            report["login_attempts"] = (trace.get("attempts") or [])[:3]
        except Exception as exc:
            report["login_error"] = str(exc)[:160]
        # A 5xx on login is a dead product. A 401 means factory demo credentials were not
        # seeded on Vercel (missing SANDBOX_DEMO_* in the publish bundle, or seed ignores them).
        for attempt in (report.get("login_attempts") or []):
            if not isinstance(attempt, dict):
                continue
            status = int(attempt.get("status") or 0)
            body = str(attempt.get("body") or "")
            hit = exception_in_product_output(body)
            if hit:
                issues.append(_issue_for_exception(where=login_paths[0], status=status, hit=hit, body=body))
            elif _is_demo_auth_failure(status, login_paths[0], body):
                issues.append(
                    _issue_for_demo_auth(where=login_paths[0], status=status, body=body)
                )
            elif status >= 500:
                issues.append(
                    f"live_http_{status}:POST {login_paths[0]}:{status} on the DEPLOYED site. "
                    "Login is production, not the sandbox."
                )
    if paths:
        results, sweep_issues = sweep_get_endpoints(base, paths, token)
        report["endpoints"] = results
        issues.extend(sweep_issues)
    # Always hit the geo feature even when OpenAPI is missing or relocated: this is the
    # call a visitor makes from the widget, and health-only probes never reach it.
    # Use an ATLAS-hot bbox for the mesh reachability probe (Berlin is often empty LIVE).
    from web.backend.services.product_demo_journey import _call

    for path in (
        f"/api/advisory?lat={_MESH_PROBE_LAT}&lon={_MESH_PROBE_LON}",
        f"/advisory?lat={_MESH_PROBE_LAT}&lon={_MESH_PROBE_LON}",
        f"/api/advisory?lat={_LIVE_LAT}&lon={_LIVE_LON}",
        f"/advisory?lat={_LIVE_LAT}&lon={_LIVE_LON}",
    ):
        status, body = _call("GET", base.rstrip("/") + path, timeout=90.0)
        report.setdefault("feature_probes", []).append({"path": path, "status": status, "body": (body or "")[:300]})
        if status == 0:
            continue
        hit = exception_in_product_output(body)
        if hit:
            issues.append(_issue_for_exception(where=path, status=status, hit=hit, body=body))
        elif status >= 500:
            issues.append(
                f"live_api_dead:{path}:{status} on the DEPLOYED site — {(body or '')[:160]}. "
                "The page is static build output and renders regardless; the backend behind it "
                "does not run."
            )
        elif 200 <= status < 400:
            try:
                payload = json.loads(body) if body else {}
            except ValueError:
                payload = {}
            overall = payload.get("overall") if isinstance(payload, dict) else None
            reason = ""
            if isinstance(overall, dict):
                reason = str(overall.get("reason") or "")
            if _MESH_UNREACHABLE_RE.search(reason or body or ""):
                issues.append(_issue_for_mesh_unreachable(where=path, status=status, reason=reason or body))
            else:
                hit = exception_in_product_output(reason or body)
                if hit:
                    issues.append(_issue_for_exception(where=path, status=status, hit=hit, body=reason or body))
        break
    return issues, report


def check_live_deployment(
    url: str,
    *,
    product_id: str | None = None,
    data_root: str | Path | None = None,
    timeout_sec: float = 180.0,
) -> dict[str, Any]:
    """Drive a real browser against a deployed URL. Full UI of every route, not a load+click."""
    out: dict[str, Any] = {"url": url, "passed": False, "issues": [], "skipped": False}
    if not url:
        out["skipped"] = True
        out["reason"] = "no_url"
        return out

    issues: list[str] = out["issues"]
    code_dir = _code_dir_for(product_id, data_root)
    origin = url.rstrip("/")

    # HTTP sweep first: the TypeError in /api/advisory is visible without a browser, and a
    # missing Playwright must not skip a product that already leaked a Python exception.
    api_issues, api_report = _sweep_live_api(origin)
    out["api_sweep"] = api_report
    issues.extend(api_issues)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        out["repair_scope"] = _repair_scope_from_issues(issues, code_dir)
        out["reason"] = f"playwright_unavailable:{exc}"
        if issues:
            out["passed"] = False
            out["skipped"] = False
            return out
        out["skipped"] = True
        return out

    from web.backend.services.browser_e2e_deep import (
        deep_crawl_gate_issues,
        run_deep_crawl,
        spa_routes_from_source,
    )

    console_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    json_bodies: list[dict[str, Any]] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            try:
                page = browser.new_page()
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text[:300])
                    if msg.type == "error"
                    else None,
                )

                def _on_response(response) -> None:
                    try:
                        status = int(response.status)
                        path = urlparse(response.url).path or "/"
                        body = ""
                        try:
                            ct = (response.headers.get("content-type") or "").lower()
                            if status >= 400 or "json" in ct or "advisory" in path:
                                body = (response.text() or "")[:2000]
                        except Exception:
                            body = ""
                        if body:
                            json_bodies.append({"path": path, "status": status, "body": body[:800]})
                            hit = exception_in_product_output(body)
                            if hit:
                                issues.append(
                                    _issue_for_exception(where=path, status=status, hit=hit, body=body)
                                )
                        if status >= 400:
                            failed_requests.append(
                                {
                                    "method": (response.request.method or "GET").upper(),
                                    "path": path,
                                    "status": status,
                                    "body": body[:400],
                                }
                            )
                    except Exception:
                        pass

                page.on("response", _on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
                try:
                    page.wait_for_selector("h1, [role='heading'], #root > *", timeout=8_000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                text = (page.inner_text("body") or "").strip()
                out["text_length"] = len(text)
                if len(text) < 40:
                    issues.append(
                        f"live_blank_page:{url}: the deployed page renders {len(text)} characters of "
                        "text. Whatever the build produced, a visitor sees nothing."
                    )
                hit = exception_in_product_output(text)
                if hit:
                    issues.append(_issue_for_exception(where="/", status=200, hit=hit, body=text))

                # Is anything actually styled? Class names that resolve to no CSS rule leave every
                # element at browser defaults, which is precisely how a "successful" deploy looks
                # like a 1996 document.
                styled = page.evaluate(
                    """() => {
                        const els = Array.from(document.querySelectorAll('body *')).slice(0, 400);
                        let styled = 0;
                        for (const el of els) {
                            const cs = getComputedStyle(el);
                            const painted =
                            (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)'
                                && cs.backgroundColor !== 'transparent') ||
                                (cs.borderTopWidth && cs.borderTopWidth !== '0px') ||
                                (cs.borderRadius && cs.borderRadius !== '0px') ||
                                (cs.boxShadow && cs.boxShadow !== 'none') ||
                                cs.display === 'flex' || cs.display === 'grid' ||
                            (cs.padding && cs.padding !== '0px') ||
                            // Color/font are how a compact designed widget actually looks
                            // styled. Sentinel's public page hydrates 15 elements; 6 had
                            // padding/flex (40%) and the rest were painted only by
                            // `color: var(--text)` / Inter — below _MIN_STYLED_RATIO 0.45
                            // with a page that is visibly a product, not a 1996 document.
                            (cs.color && cs.color !== 'rgb(0, 0, 0)'
                                && cs.color !== 'rgba(0, 0, 0, 1)') ||
                            (cs.fontFamily && !/^(?:serif|sans-serif|monospace|Times)/i.test(cs.fontFamily));
                            if (painted) styled++;
                        }
                        return { total: els.length, styled };
                    }"""
                )
                out["styling"] = styled
                if isinstance(styled, dict) and styled.get("total", 0) >= _MIN_ELEMENTS_TO_JUDGE:
                    total = int(styled.get("total") or 0)
                    count = int(styled.get("styled") or 0)
                    ratio = count / total if total else 1.0
                    out["styled_ratio"] = round(ratio, 2)
                    if ratio < _MIN_STYLED_RATIO:
                        issues.append(
                            f"live_unstyled_page:{url}: only {count} of "
                            f"{total} elements ({int(ratio * 100)}%) have any non-default styling — no "
                            "background, border, radius, shadow, flex/grid or padding. The page is "
                            "rendering unstyled: the stylesheet the markup expects is not being "
                            "applied. Check that the classes used in the markup have rules behind "
                            "them (and that any utility framework the markup assumes is actually "
                            "installed and configured)."
                        )

                # The page load may touch no API at all — this product waits for input before it
                # calls anything, which is why a completely dead backend passed a green browser
                # gate. So ask the deployment directly.
                api_paths = ("/api/health", "/api/healthz", "/openapi.json", "/api")
                api_alive = None
                for path in api_paths:
                    try:
                        resp = page.request.get(url.rstrip("/") + path, timeout=20_000)
                        status = int(resp.status)
                        body = ""
                        try:
                            body = (resp.text() or "")[:300]
                        except Exception:
                            body = ""
                        crashed = (
                            "FUNCTION_INVOCATION_FAILED" in body
                            or "A server error has occurred" in body
                        )
                        if 200 <= status < 500 and not crashed:
                            api_alive = f"{path} -> {status}"
                            break
                        if status >= 500 or crashed:
                            api_alive = False
                            issues.append(
                                f"live_api_dead:{path}:{status} on the DEPLOYED site"
                                + (f" — {body.strip()[:160]}" if body.strip() else "")
                                + ". The page is static build output and renders regardless; the "
                                "backend behind it does not run. A dependency present in the "
                                "preview venv and absent from the deployment fails exactly here, "
                                "and every feature of the product is unreachable."
                            )
                            break
                    except Exception:
                        continue
                out["api"] = api_alive

                # Full UI of the deployed app: every React-Router route from source, every form
                # (lat/lon filled, login filled), every visible button. A gate that only clicks
                # the primary CTA on an empty required form certifies nothing — HTML5 validation
                # swallows the click and the TypeError behind Get Safety Status never runs.
                seed_urls = [origin]
                if code_dir is not None:
                    seed_urls.extend(
                        urljoin(origin + "/", route.lstrip("/"))
                        for route in spa_routes_from_source(code_dir)
                    )
                crawl = run_deep_crawl(
                    page,
                    base_origin=origin,
                    start_url=origin + "/",
                    screenshot_dir=None,
                    max_pages=24,
                    max_depth=6,
                    per_nav_timeout_ms=18_000,
                    max_forms_per_page=4,
                    max_button_clicks_per_page=10,
                    seed_urls=seed_urls,
                )
                out["ui_crawl"] = {
                    "pages_visited": crawl.get("pages_visited"),
                    "visited_unique": crawl.get("visited_unique"),
                    "pages": [
                        {
                            "url": p.get("url"),
                            "status": p.get("status"),
                            "text_snippet": (p.get("text_snippet") or "")[:400],
                        }
                        for p in (crawl.get("pages") or [])[:24]
                    ],
                }
                issues.extend(deep_crawl_gate_issues(crawl))
                for p in crawl.get("pages") or []:
                    snippet = str(p.get("text_snippet") or "")
                    hit = exception_in_product_output(snippet)
                    if hit:
                        issues.append(
                            _issue_for_exception(
                                where=str(p.get("url") or "/"),
                                status=int(p.get("status") or 200),
                                hit=hit,
                                body=snippet,
                            )
                        )

                for fr in failed_requests[:8]:
                    status = int(fr.get("status") or 0)
                    path = str(fr.get("path") or "")
                    body = str(fr.get("body") or "")
                    # Crawling /#/operator before the login form is submitted fires
                    # protected /api/* calls that 401. That is not a deploy defect when
                    # the API sweep already proved login returns a bearer token.
                    if status in (401, 403) and path.startswith("/api/"):
                        login_ok = any(
                            isinstance(a, dict)
                            and a.get("token")
                            and int(a.get("status") or 0) == 200
                            for a in ((out.get("api_sweep") or {}).get("login_attempts") or [])
                        )
                        if login_ok:
                            continue
                    if _is_demo_auth_failure(status, path, body):
                        issues.append(_issue_for_demo_auth(where=path, status=status, body=body))
                        continue
                    issues.append(
                        f"live_http_{status}:{fr.get('method')} {path}:{status} on the "
                        "DEPLOYED site. This is production, not the sandbox: a dependency that "
                        "exists in the preview venv and not in the deployment fails exactly here."
                    )
                for ce in console_errors[:6]:
                    low = ce.lower()
                    if "401" in low or "unauthorized" in low:
                        login_ok = any(
                            isinstance(a, dict)
                            and a.get("token")
                            and int(a.get("status") or 0) == 200
                            for a in ((out.get("api_sweep") or {}).get("login_attempts") or [])
                        )
                        if login_ok:
                            continue
                    issues.append(f"live_console_error: {ce}")
            finally:
                browser.close()
    except Exception as exc:
        out["skipped"] = True
        out["reason"] = f"browser_error:{str(exc)[:200]}"
        return out

    # Dedup: the same TypeError is reported from the HTTP sweep, the response listener, and the
    # crawl snippet. One finding is the instruction; three copies bury the file names.
    seen: set[str] = set()
    compact: list[str] = []
    for item in issues:
        key = item[:220]
        if key in seen:
            continue
        seen.add(key)
        compact.append(item)
    out["issues"] = compact
    out["failed_requests"] = failed_requests[:12]
    out["console_errors"] = console_errors[:12]
    out["json_bodies"] = json_bodies[:12]
    out["repair_scope"] = _repair_scope_from_issues(compact, code_dir)
    out["passed"] = not compact
    return out


def vercel_publish_failure_as_live_gate(
    *,
    product_id: str,
    exit_code: int | None = None,
    stderr: str = "",
    stdout: str = "",
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A Vercel CLI / requirements parse failure is the same class of defect as a live UI fail.

    The sandbox can still be green: preview used to install requirements line-by-line. The
    public --prod cannot. Without this payload the executor sees live_gate={} and walks to
    COMPLETED with vercel.ok: false.
    """
    bundle = bundle or {}
    blob = f"{stderr or ''}\n{stdout or ''}"
    issues: list[str] = []
    repair_scope: list[str] = []
    for raw in bundle.get("invalid_requirements") or []:
        issues.append(f"invalid_requirement:{raw}")
        repair_scope.append("backend/requirements.txt")
        repair_scope.append("requirements.txt")
    compact_err = ""
    for line in blob.splitlines():
        if "could not parse" in line.lower() or "couldn't parse" in line.lower():
            compact_err = line.strip()
            break
        if "error:" in line.lower() and "requirement" in line.lower():
            compact_err = line.strip()
            break
    if compact_err:
        issues.append(f"vercel_build_failed: {compact_err[:240]}")
        repair_scope.extend(["backend/requirements.txt", "requirements.txt"])
    elif exit_code not in (None, 0):
        tail = (stderr or stdout or "").strip().splitlines()
        last = next((ln.strip() for ln in reversed(tail) if ln.strip()), f"exit {exit_code}")
        issues.append(f"vercel_build_failed: exit {exit_code}: {last[:240]}")
        if "requirement" in blob.lower():
            repair_scope.extend(["backend/requirements.txt", "requirements.txt"])
    if not issues:
        issues.append("vercel_build_failed: production deploy did not publish")

    try:
        from core.paths import data_root

        code_dir = Path(data_root()) / "code" / product_id
        if code_dir.is_dir():
            from web.backend.services.requirements_manifest import iter_requirement_files

            for p in iter_requirement_files(code_dir):
                try:
                    rel = p.relative_to(code_dir).as_posix()
                except ValueError:
                    rel = p.name
                if rel not in repair_scope:
                    repair_scope.append(rel)
    except Exception:
        pass

    seen: set[str] = set()
    scope: list[str] = []
    for item in repair_scope:
        if item and item not in seen:
            seen.add(item)
            scope.append(item)

    return {
        "passed": False,
        "skipped": False,
        "source": "vercel_publish",
        "issues": issues[:12],
        "repair_scope": scope[:8],
        "exit_code": exit_code,
        "stderr_tail": (stderr or "")[-2000:],
    }


def live_gate_quality_feedback(live_gate: dict[str, Any]) -> dict[str, Any]:
    """The payload the developer agent already knows how to read."""
    issues = [str(i) for i in (live_gate.get("issues") or [])]
    return {
        "passed": False,
        "blocking_defects": issues,
        "repair_scope": list(live_gate.get("repair_scope") or []),
        "live_gate": live_gate,
        "reasons": issues,
    }


def live_gate_dev_fixing_task(product_id: str, product: dict[str, Any], live_gate: dict[str, Any]) -> dict[str, Any]:
    """A DEV_FIXING task whose findings name the Vercel UI failure, not a sandbox 401."""
    qg = live_gate_quality_feedback(live_gate)
    return {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": product_id,
        "agent_type": "developer",
        "state": "DEV_FIXING",
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "input_data": {
            "product_id": product_id,
            "idea": product.get("idea", ""),
            "qa_findings": [
                {"severity": "critical", "title": issue, "detail": issue}
                for issue in (qg.get("blocking_defects") or [])[:20]
            ],
            "quality_gates_feedback": qg,
            "qa_gate_blocked": True,
            "live_gate_blocked": True,
        },
        "created_at": time.time(),
        "priority": 5,
        "auto_requeue_reason": "live_deployment_gate",
    }


def mark_product_live_gate_failed(product: dict[str, Any], live_gate: dict[str, Any]) -> None:
    product["state"] = "BUG_FOUND"
    product["live_gate"] = live_gate
    product["last_bug_context"] = {
        "source": "live_deployment_gate",
        "quality_gates_feedback": live_gate_quality_feedback(live_gate),
    }
    product["updated_at"] = time.time()


_VERCEL_INFRA_MARKERS = (
    "VERCEL_TOKEN not set",
    "vercel CLI not found",
    "provider_none",
    "disabled",
    "not_marketing_landing",
)


def _read_auto_publish_record(product_id: str) -> dict[str, Any]:
    if not product_id:
        return {}
    try:
        from core.paths import data_root

        path = Path(data_root()) / "state" / product_id / "auto_publish.json"
        if not path.is_file():
            return {}
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def live_gate_from_saved_vercel_record(product_id: str) -> dict[str, Any] | None:
    """A saved ``vercel.ok: false`` is a product defect, not a reason to stay COMPLETED.

    The live URL gate cannot see it: the previous production alias still answers 200
    while the new ``--prod`` died on ``requirements.txt``. DevOps already finished,
    so the in-loop live_gate_failed flag is gone. This reads the publish receipt.
    """
    doc = _read_auto_publish_record(product_id)
    vercel = doc.get("vercel")
    if not isinstance(vercel, dict):
        return None
    if vercel.get("ok") is True:
        return None
    if vercel.get("skipped"):
        return None
    blob = " ".join(
        str(x) for x in (vercel.get("error"), doc.get("error"), vercel.get("stderr_tail")) if x
    )
    if any(m.lower() in blob.lower() for m in _VERCEL_INFRA_MARKERS):
        return None
    existing = vercel.get("live_gate")
    if isinstance(existing, dict) and existing.get("passed") is False and not existing.get("skipped"):
        return existing
    evidence = (
        vercel.get("exit_code") not in (None, 0)
        or bool(vercel.get("invalid_requirements") or (vercel.get("bundle") or {}).get("invalid_requirements"))
        or "could not parse" in blob.lower()
        or "couldn't parse" in blob.lower()
        or str(vercel.get("error") or "") == "invalid_requirements"
    )
    if not evidence:
        return None
    bundle = vercel.get("bundle") if isinstance(vercel.get("bundle"), dict) else {}
    if vercel.get("invalid_requirements") and "invalid_requirements" not in bundle:
        bundle = {**bundle, "invalid_requirements": vercel.get("invalid_requirements")}
    return vercel_publish_failure_as_live_gate(
        product_id=product_id,
        exit_code=vercel.get("exit_code") if isinstance(vercel.get("exit_code"), int) else None,
        stderr=str(vercel.get("stderr_tail") or ""),
        stdout=str(vercel.get("stdout_tail") or ""),
        bundle=bundle,
    )


def apply_vercel_publish_failure_to_snapshot(
    product_id: str,
    product: dict[str, Any],
    task_queue: list[dict[str, Any]],
) -> bool:
    """Reopen a COMPLETED product in the worker snapshot when Vercel --prod failed."""
    from core.agent_roles import is_developer_agent

    live_gate = live_gate_from_saved_vercel_record(product_id)
    if not live_gate:
        return False
    if any(
        t.get("product_id") == product_id
        and is_developer_agent(t.get("agent_type"))
        and str(t.get("state") or "").upper() == "DEV_FIXING"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        mark_product_live_gate_failed(product, live_gate)
        return True
    mark_product_live_gate_failed(product, live_gate)
    task_queue.append(live_gate_dev_fixing_task(product_id, product, live_gate))
    logger.warning(
        "Saved Vercel publish failure returned %s to DEV_FIXING (%s)",
        product_id,
        "; ".join(str(i)[:100] for i in (live_gate.get("issues") or [])[:2]),
    )
    return True


def enqueue_repair_from_live_gate(product_id: str, live_gate: dict[str, Any]) -> dict[str, Any]:
    """Send an already-published product back to DEV_FIXING. COMPLETED is allowed.

    DevOps only runs the live gate once. A TypeError that shipped sits on Vercel forever
    unless something can reopen a COMPLETED product — reopen_failed_product refuses
    anything that is not FAILED.
    """
    if live_gate.get("skipped") or live_gate.get("passed") is not False:
        return {"ok": False, "reason": "live_gate_did_not_fail"}

    from core.paths import pipeline_db_path
    from core.agent_roles import is_developer_agent

    pid = product_id.strip()
    from orchestrator.sqlite_manager import SQLiteManager

    db = pipeline_db_path()
    if db.is_file():
        sm = SQLiteManager(str(db))
        sm.connect()
        try:
            product = sm.get_product(pid)
            if not product:
                return {"ok": False, "reason": "product_not_found"}
            tasks = sm.get_tasks_by_product(pid)
            if any(
                is_developer_agent(t.get("agent_type"))
                and str(t.get("state") or "").upper() == "DEV_FIXING"
                and str(t.get("status") or "").lower() in ("pending", "running")
                for t in tasks
            ):
                mark_product_live_gate_failed(product, live_gate)
                sm.upsert_product(product)
                return {"ok": True, "recovery_already_pending": True, "product_state": "BUG_FOUND"}
            mark_product_live_gate_failed(product, live_gate)
            task = live_gate_dev_fixing_task(pid, product, live_gate)
            sm.upsert_product(product)
            sm.upsert_task(task)
            logger.warning(
                "Live Vercel gate returned %s to DEV_FIXING (%s)",
                pid,
                "; ".join(str(i)[:100] for i in (live_gate.get("issues") or [])[:2]),
            )
            return {"ok": True, "task_id": task["id"], "product_state": "BUG_FOUND"}
        finally:
            sm.close()

    from core.pipeline_state_writer import read_pipeline_state, write_pipeline_state

    data = read_pipeline_state()
    products = data.get("products") or {}
    task_queue = data.get("task_queue") or []
    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}
    if any(
        t.get("product_id") == pid
        and is_developer_agent(t.get("agent_type"))
        and str(t.get("state") or "").upper() == "DEV_FIXING"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        mark_product_live_gate_failed(product, live_gate)
        write_pipeline_state(data)
        return {"ok": True, "recovery_already_pending": True, "product_state": "BUG_FOUND"}
    mark_product_live_gate_failed(product, live_gate)
    task = live_gate_dev_fixing_task(pid, product, live_gate)
    task_queue.append(task)
    data["task_queue"] = task_queue
    write_pipeline_state(data)
    return {"ok": True, "task_id": task["id"], "product_state": "BUG_FOUND"}


def recheck_published_live_ui(product_id: str, url: str) -> dict[str, Any]:
    """Run the full Vercel UI gate against an existing URL and reopen on failure."""
    live_gate = check_live_deployment(url, product_id=product_id)
    out: dict[str, Any] = {"live_gate": live_gate}
    if live_gate.get("skipped") or live_gate.get("passed"):
        out["ok"] = True
        out["repaired"] = False
        return out
    enq = enqueue_repair_from_live_gate(product_id, live_gate)
    out.update(enq)
    out["repaired"] = bool(enq.get("ok"))
    return out

