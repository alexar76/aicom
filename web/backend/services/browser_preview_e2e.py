"""
Headless browser E2E for generated product previews.

Serves ``data/code/{product_id}/`` via a local ThreadingHTTPServer (same layout as
sandbox file API) and drives Chromium through Playwright: load index.html, detect
blank pages, JS exceptions, console errors, then either:

- **Deep crawl** (default): BFS over **all same-origin** ``<a href>`` targets (incl. ``#anchors``),
  per-page screenshots (optional), button clicks, and heuristic **form fills + submit**
  (uses ``AIFACTORY_E2E_*`` credentials for login-like flows).
- **Legacy probe** (``AIFACTORY_BROWSER_DEEP_CRAWL=0``): a handful of hash-only anchors + buttons.

Env:
  ``AIFACTORY_BROWSER_E2E=0`` — disable entire browser pass (or ``quality.browser_e2e_enabled`` in YAML).
  ``AIFACTORY_BROWSER_DEEP_CRAWL=1`` (default) — full link crawl; ``0`` restores shallow clicks only.
  ``AIFACTORY_BROWSER_MAX_PAGES`` — max distinct URLs to visit in BFS (default **100**). Raise for large sites.
  ``AIFACTORY_BROWSER_MAX_DEPTH`` — max BFS depth from start URL (default 10).
  ``AIFACTORY_BROWSER_PER_NAV_TIMEOUT_MS`` — per navigation timeout (default 18000).
  ``AIFACTORY_BROWSER_FORMS_PER_PAGE`` — max forms exercised per page (default 4).
  ``AIFACTORY_BROWSER_BUTTONS_PER_PAGE`` — max miscellaneous button clicks per page (default 14).
  ``AIFACTORY_BROWSER_SCREENSHOTS=1`` — PNG captures under ``telemetry/<product_id>/browser_e2e/``.
  ``AIFACTORY_BROWSER_UI_CLICKS=N`` — legacy: max clicks when deep crawl is off (default 6).
  ``AIFACTORY_E2E_EMAIL``, ``AIFACTORY_E2E_USERNAME``, ``AIFACTORY_E2E_PASSWORD``, ``AIFACTORY_E2E_FULL_NAME``
  ``AIFACTORY_VISUAL_DOM_AUDIT=1`` — DOM/svg structural audit (initial + after crawl).
  ``AIFACTORY_VISUAL_SCREENSHOT_PROBE=0`` — set ``1`` for crude viewport dark-mass heuristic (requires Pillow).

**Full_software mobile gate:**
  When ``data/specs/<product_id>/specification.json`` has ``delivery_profile: full_software`` and
  ``AIFACTORY_BROWSER_FS_MOBILE_GATE=1`` (default), after the desktop crawl Playwright opens a **390×844**
  viewport, visits ``AIFACTORY_BROWSER_FS_MOBILE_ROUTES`` (default ``/,/login,/tasks,/settings``), and fails
  the check if **horizontal overflow** (scrollWidth ≫ innerWidth) is detected. Missing ``<meta name="viewport">``
  is reported as a warning only (does not fail by default).

**Preview runtime (sessions / real app, not only static files):**
  ``AIFACTORY_BROWSER_E2E_SERVE_MODE=auto|static|fastapi|docker`` — default ``auto`` prefers **FastAPI** (uvicorn
  subprocess, same as sandbox preview API) when ``main.py`` + FastAPI is detected; else static ``index.html``.
  ``docker`` builds ``Dockerfile`` in the product code dir (needs Docker daemon; slower).
  ``AIFACTORY_BROWSER_E2E_AUTO_DOCKER=1`` — in ``auto`` mode, prefer Docker when a ``Dockerfile`` exists.
  ``AIFACTORY_BROWSER_E2E_ENTRY_PATH=/`` — first URL path for FastAPI/Docker (default ``/``).
  ``AIFACTORY_BROWSER_E2E_DOCKER_CONTAINER_PORT=8000`` — container port to map for Docker mode (match ``EXPOSE`` in the product Dockerfile).
  ``AIFACTORY_BROWSER_E2E_DOCKER_BUILD_TIMEOUT_SEC`` / ``AIFACTORY_BROWSER_E2E_DOCKER_READY_TIMEOUT_SEC`` — tuning.

**Scenario tests (SPA / login flows, after BFS):**
  Drop ``e2e-scenarios.json`` in the product code dir or set ``AIFACTORY_BROWSER_SCENARIO_FILE``.
  ``AIFACTORY_BROWSER_SCENARIOS=0`` disables. See ``browser_e2e_scenarios`` module.

Structural/visual QA runs through ``web.backend.services.visual_render_audit`` (shared thresholds with static demo_quality SVG spike checks).
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from web.backend.services.browser_e2e_deep import (
    deep_crawl_gate_issues,
    env_bool as deep_env_bool,
    env_int as deep_env_int,
    run_deep_crawl,
)
from web.backend.services.visual_render_audit import (
    classify_visual_findings,
    merge_visual_phases,
    run_playwright_visual_audit,
    screenshot_viewport_dark_mass_ratio,
)
from web.backend.services.browser_e2e_scenarios import (
    load_scenario_specs,
    run_declarative_scenarios,
    scenarios_enabled,
)
from web.backend.services.sandbox_preview_api import (
    detect_fastapi_backend,
    start_fastapi_preview,
    terminate_preview_process,
    wait_port_open,
)

from core.quality_settings import browser_e2e_enabled, browser_max_depth, browser_max_pages

logger = logging.getLogger(__name__)

MIN_VISIBLE_TEXT_LEN = 20

DEFAULT_BROWSER_MAX_PAGES = 100

DEFAULT_UI_CLICKS = 6


def _read_spec_delivery_profile(data_root: Path, product_id: str) -> str | None:
    p = data_root / "specs" / product_id / "specification.json"
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


def _full_software_mobile_viewport_gate(browser: Any, start_url: str) -> dict[str, Any]:
    """
    Narrow viewport checks for dashboard-style apps (full_software): horizontal overflow probe.
    """
    routes_raw = os.environ.get(
        "AIFACTORY_BROWSER_FS_MOBILE_ROUTES",
        "/,/login,/tasks,/settings",
    )
    routes = []
    for r in routes_raw.split(","):
        s = r.strip()
        routes.append(s if s else "/")
    if not routes:
        routes = ["/"]
    parsed = urlparse(start_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    strict_meta = deep_env_bool("AIFACTORY_BROWSER_FS_MOBILE_META_STRICT", False)

    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page_m = ctx.new_page()
    issues: list[str] = []
    warnings: list[str] = []
    checked = 0
    try:
        for route in routes:
            path = route if route.startswith("/") else f"/{route}"
            target = urljoin(origin + "/", path.lstrip("/"))
            try:
                page_m.goto(target, wait_until="domcontentloaded", timeout=30_000)
                page_m.wait_for_timeout(350)
            except Exception as e:
                issues.append(f"mobile_nav_failed:{path}:{str(e)[:160]}")
                continue
            checked += 1
            try:
                metrics = page_m.evaluate(
                    """() => {
                      const de = document.documentElement;
                      const body = document.body;
                      const sw = Math.max(de.scrollWidth, body ? body.scrollWidth : 0);
                      const sh = Math.max(de.scrollHeight, body ? body.scrollHeight : 0);
                      const iw = window.innerWidth;
                      const ih = window.innerHeight;
                      const meta = document.querySelector('meta[name="viewport"]');
                      return {
                        scrollWidth: sw,
                        scrollHeight: sh,
                        innerWidth: iw,
                        innerHeight: ih,
                        hasViewportMeta: !!meta,
                        overflowX: sw > iw + 32
                      };
                    }"""
                )
            except Exception as e:
                issues.append(f"mobile_metrics_failed:{path}:{str(e)[:120]}")
                continue
            if not isinstance(metrics, dict):
                continue
            if metrics.get("overflowX"):
                issues.append(
                    f"mobile_horizontal_overflow:{path}:sw={metrics.get('scrollWidth')} iw={metrics.get('innerWidth')}"
                )
            if not metrics.get("hasViewportMeta"):
                wmsg = f"mobile_missing_viewport_meta:{path}"
                if strict_meta:
                    issues.append(wmsg)
                else:
                    warnings.append(wmsg)
    finally:
        try:
            ctx.close()
        except Exception:
            pass

    fatal = bool(issues)
    return {
        "skipped": False,
        "viewport": "390x844",
        "routes_checked": checked,
        "issues": issues,
        "warnings": warnings,
        "fatal": fatal,
    }


def _max_ui_clicks() -> int:
    raw = os.environ.get("AIFACTORY_BROWSER_UI_CLICKS", str(DEFAULT_UI_CLICKS)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_UI_CLICKS


def _probe_ui_interactions(page: Any, max_clicks: int) -> dict[str, Any]:
    """
    Click up to ``max_clicks`` visible in-page controls (no external navigations).
    Auto-dismisses dialog/alert so legacy onclick=alert() does not hang the run.
    """
    if max_clicks <= 0:
        return {"skipped": True, "clicks_attempted": 0, "click_log": [], "issues": []}

    click_log: list[dict[str, Any]] = []
    issues: list[str] = []

    def _on_dialog(dialog: Any) -> None:
        try:
            dialog.dismiss()
        except Exception:
            try:
                dialog.accept()
            except Exception:
                pass

    page.on("dialog", _on_dialog)

    # In-page only: hash links and controls; exclude mailto/tel/javascript: off-site
    combined = (
        "button, [role='button'], input[type='button'], input[type='submit'], "
        "a[href^='#'], a:not([href]), a[href='']"
    )
    try:
        loc = page.locator(combined)
        n = loc.count()
        for i in range(min(n, max_clicks * 3)):  # scan wider; stop after max_clicks successes
            if len(click_log) >= max_clicks:
                break
            item = loc.nth(i)
            try:
                if not item.is_visible():
                    continue
                tag = item.evaluate("el => el.tagName.toUpperCase()") or ""
                if tag == "A":
                    href = (item.get_attribute("href") or "").strip()
                    low = href.lower()
                    if low.startswith(("http://", "https://", "mailto:", "tel:", "javascript:")):
                        continue
                snippet = (item.inner_text() or "")[:40].replace("\n", " ")
                item.click(timeout=5_000)
                page.wait_for_timeout(350)
                click_log.append({"tag": tag, "snippet": snippet, "ok": True})
            except Exception as e:
                err = str(e)[:180]
                click_log.append({"index": i, "ok": False, "error": err})
                issues.append(f"ui_click_failed: {err}")

    except Exception as e:
        issues.append(f"ui_probe_error: {str(e)[:200]}")

    return {
        "skipped": False,
        "clicks_attempted": sum(1 for c in click_log if c.get("ok") is True),
        "click_log": click_log[:20],
        "issues": issues,
    }


def _pick_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    _, port = s.getsockname()
    s.close()
    return port


def _resolve_e2e_serve_mode(code_dir: Path) -> str:
    raw = os.environ.get("AIFACTORY_BROWSER_E2E_SERVE_MODE", "auto").strip().lower()
    if raw in ("static", "fastapi", "docker"):
        return raw
    if os.environ.get("AIFACTORY_BROWSER_E2E_AUTO_DOCKER", "").strip().lower() in ("1", "true", "yes"):
        if (code_dir / "Dockerfile").is_file():
            return "docker"
    if detect_fastapi_backend(code_dir):
        return "fastapi"
    return "static"


def _e2e_entry_path() -> str:
    ep = os.environ.get("AIFACTORY_BROWSER_E2E_ENTRY_PATH", "/").strip() or "/"
    return ep if ep.startswith("/") else f"/{ep}"


def _fallback_preview_mode(code_dir: Path) -> str:
    if detect_fastapi_backend(code_dir):
        return "fastapi"
    return "static"


def _e2e_start_docker_preview(code_dir: Path, product_id: str) -> tuple[str | None, str | None, str]:
    """Return (start_url, container_id, status). On failure url and cid are None."""
    if not (code_dir / "Dockerfile").is_file():
        return None, None, "no_dockerfile"
    safe_tag = re.sub(r"[^a-zA-Z0-9_.-]", "-", f"aicom-e2e-{product_id}")[:120].strip("-") or "aicom-e2e-unknown"
    host_port = _pick_port()
    try:
        cport = int(os.environ.get("AIFACTORY_BROWSER_E2E_DOCKER_CONTAINER_PORT", "8000"))
    except ValueError:
        cport = 8000
    try:
        build_timeout = int(os.environ.get("AIFACTORY_BROWSER_E2E_DOCKER_BUILD_TIMEOUT_SEC", "600"))
    except ValueError:
        build_timeout = 600
    try:
        ready_timeout = float(os.environ.get("AIFACTORY_BROWSER_E2E_DOCKER_READY_TIMEOUT_SEC", "90"))
    except ValueError:
        ready_timeout = 90.0

    logger.info("browser E2E docker build image=%s", safe_tag)
    br = subprocess.run(
        ["docker", "build", "-t", safe_tag, str(code_dir)],
        capture_output=True,
        text=True,
        timeout=max(60, build_timeout),
    )
    if br.returncode != 0:
        logger.warning("browser E2E docker build failed: %s", (br.stderr or "")[:900])
        return None, None, "docker_build_failed"

    rr = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            f"{host_port}:{cport}",
            "--label",
            "aicom.browser_e2e=1",
            safe_tag,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if rr.returncode != 0:
        logger.warning("browser E2E docker run failed: %s", (rr.stderr or "")[:500])
        return None, None, "docker_run_failed"
    cid = (rr.stdout or "").strip()
    if not cid:
        return None, None, "docker_no_container_id"

    if not wait_port_open("127.0.0.1", host_port, timeout_sec=ready_timeout):
        subprocess.run(["docker", "stop", cid], capture_output=True, text=True, timeout=90)
        return None, None, "docker_port_timeout"

    entry = _e2e_entry_path()
    url = f"http://127.0.0.1:{host_port}{entry}"
    return url, cid, "ok"


def run_browser_preview_e2e(
    product_id: str,
    data_root: str | Path = "/app/data",
) -> dict[str, Any]:
    """
    Run Playwright Chromium against the product code tree.

    **Serve modes:** static ``index.html``, **FastAPI** (uvicorn on loopback, cookies/sessions work), or **Docker**
    (``docker build`` + ``docker run``) — see module docstring.

    Returns a dict with at least ``passed: bool`` and diagnostic fields.
    """
    if not browser_e2e_enabled():
        return {
            "passed": True,
            "skipped": True,
            "reason": "Browser E2E disabled (quality.browser_e2e_enabled / AIFACTORY_BROWSER_E2E)",
        }

    root = Path(data_root)
    code_dir = root / "code" / product_id
    index_html = code_dir / "index.html"

    if not code_dir.is_dir():
        return {
            "passed": False,
            "skipped": False,
            "error": "no_code_dir",
            "detail": str(code_dir),
        }

    serve_mode = _resolve_e2e_serve_mode(code_dir)
    docker_cid: str | None = None
    uvicorn_proc: Any | None = None
    httpd: ThreadingHTTPServer | None = None
    url: str | None = None

    try:
        if serve_mode == "docker":
            d_url, d_cid, d_st = _e2e_start_docker_preview(code_dir, product_id)
            if d_url and d_cid:
                url = d_url
                docker_cid = d_cid
            else:
                logger.warning("browser E2E docker mode failed (%s), falling back", d_st)
                serve_mode = _fallback_preview_mode(code_dir)

        if url is None and serve_mode == "fastapi":
            sid = f"e2e-{product_id}".replace(" ", "")[:40]
            bp, uv_proc, pst = start_fastapi_preview(sandbox_id=sid, code_dir=code_dir)
            if bp and uv_proc:
                uvicorn_proc = uv_proc
                entry = _e2e_entry_path()
                url = f"http://127.0.0.1:{bp}{entry}"
                logger.info("browser E2E FastAPI preview port=%s status=%s", bp, pst)
            else:
                logger.warning("browser E2E FastAPI preview failed (%s), falling back to static", pst)
                serve_mode = "static"

        if url is None:
            if not index_html.is_file():
                return {
                    "passed": False,
                    "skipped": False,
                    "error": "no_index_html",
                    "hint": "Add index.html or enable FastAPI/Docker serve mode (see AIFACTORY_BROWSER_E2E_SERVE_MODE).",
                    "serve_mode": serve_mode,
                }
            port = _pick_port()

            class _StaticHandler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=str(code_dir), **kwargs)

                def log_message(self, *args) -> None:
                    pass

            httpd = ThreadingHTTPServer(("127.0.0.1", port), _StaticHandler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{port}/index.html"
            serve_mode = "static"

        assert url is not None
        return _playwright_check(
            url,
            product_id=str(product_id),
            data_root=root,
            code_dir=code_dir,
            serve_mode=serve_mode,
        )
    except Exception as e:
        return {
            "passed": False,
            "skipped": False,
            "error": "playwright_failure",
            "detail": str(e),
        }
    finally:
        terminate_preview_process(uvicorn_proc)
        if docker_cid:
            subprocess.run(
                ["docker", "stop", docker_cid],
                capture_output=True,
                text=True,
                timeout=120,
            )
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass


def _playwright_check(
    url: str,
    *,
    product_id: str,
    data_root: Path,
    code_dir: Path,
    serve_mode: str,
) -> dict[str, Any]:
    scenario_summary: dict[str, Any] = {"ran": False}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return {
            "passed": False,
            "skipped": False,
            "error": "playwright_not_installed",
            "detail": str(e),
        }

    console_errors: list[dict[str, str]] = []
    page_errors: list[str] = []
    interaction: dict[str, Any] = {
        "skipped": True,
        "clicks_attempted": 0,
        "click_log": [],
        "issues": [],
    }
    perf: dict[str, Any] = {}
    visual_render_audit: dict[str, Any] = {"skipped": True, "reason": "not_started"}
    text_len = 0
    has_visible = False
    deep_summary: dict[str, Any] | None = None
    mobile_gate: dict[str, Any] = {"skipped": True}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        nav_err: Exception | None = None
        try:
            page = browser.new_page()

            def on_console(msg) -> None:
                if msg.type == "error":
                    console_errors.append({"type": msg.type, "text": msg.text})

            page.on("console", on_console)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            def _on_dialog(dlg: Any) -> None:
                try:
                    dlg.dismiss()
                except Exception:
                    try:
                        dlg.accept()
                    except Exception:
                        pass

            page.on("dialog", _on_dialog)

            parsed = urlparse(url)
            base_origin = f"{parsed.scheme}://{parsed.netloc}"

            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(800)

            if scenarios_enabled():
                specs = load_scenario_specs(code_dir)
                if specs:
                    scenario_summary = run_declarative_scenarios(page, base_origin, specs)

            text_len = page.evaluate(
                """() => {
                const b = document.body;
                if (!b) return 0;
                return (b.innerText || '').trim().length;
            }"""
            )
            has_visible = page.evaluate(
                """() => {
                const b = document.body;
                if (!b) return false;
                return (b.innerText || '').trim().length > 0 || b.children.length > 0;
            }"""
            )
            perf = page.evaluate(
                """() => {
                const nav = performance.getEntriesByType('navigation')[0];
                if (!nav) return {};
                return {
                  ttfb_ms: Math.round(nav.responseStart || 0),
                  dom_content_loaded_ms: Math.round(nav.domContentLoadedEventEnd || 0),
                  load_event_ms: Math.round(nav.loadEventEnd || 0),
                  transfer_size: Math.round(nav.transferSize || 0),
                };
            }"""
            )

            visual_dom_on = os.environ.get("AIFACTORY_VISUAL_DOM_AUDIT", "1").strip().lower() not in (
                "0",
                "false",
                "no",
            )
            audit_initial: dict[str, Any] = {"viewport": {}, "findings": []}
            if visual_dom_on:
                try:
                    audit_initial = run_playwright_visual_audit(page, phase_label="initial")
                except Exception as ve:
                    audit_initial = {"viewport": {}, "findings": [], "audit_error": str(ve)[:240]}

            screenshot_ratio: float | None = None
            screenshot_fail = False
            if (
                os.environ.get("AIFACTORY_VISUAL_SCREENSHOT_PROBE", "0").strip().lower()
                in ("1", "true", "yes")
            ):
                try:
                    screenshot_ratio = screenshot_viewport_dark_mass_ratio(page)
                    if screenshot_ratio is not None and screenshot_ratio > 0.72:
                        screenshot_fail = True
                except Exception:
                    screenshot_ratio = None

            screenshot_dir = data_root / "telemetry" / product_id / "browser_e2e"

            if deep_env_bool("AIFACTORY_BROWSER_DEEP_CRAWL", True):
                crawl_start = page.url
                deep_summary = run_deep_crawl(
                    page,
                    base_origin=base_origin,
                    start_url=crawl_start,
                    screenshot_dir=screenshot_dir,
                    max_pages=deep_env_int("AIFACTORY_BROWSER_MAX_PAGES", browser_max_pages()),
                    max_depth=deep_env_int("AIFACTORY_BROWSER_MAX_DEPTH", browser_max_depth()),
                    per_nav_timeout_ms=deep_env_int("AIFACTORY_BROWSER_PER_NAV_TIMEOUT_MS", 18_000),
                    max_forms_per_page=deep_env_int("AIFACTORY_BROWSER_FORMS_PER_PAGE", 4),
                    max_button_clicks_per_page=deep_env_int("AIFACTORY_BROWSER_BUTTONS_PER_PAGE", 14),
                )
                try:
                    tel_dir = data_root / "telemetry" / product_id
                    tel_dir.mkdir(parents=True, exist_ok=True)
                    (tel_dir / "browser_e2e_deep.json").write_text(
                        json.dumps(deep_summary, indent=2, ensure_ascii=False)[:480_000],
                        encoding="utf-8",
                    )
                except OSError:
                    pass
                deep_issues = deep_crawl_gate_issues(deep_summary)
                btn_clicks = sum(
                    int((p.get("button_probe") or {}).get("clicks") or 0)
                    for p in (deep_summary.get("pages") or [])
                )
                interaction = {
                    "skipped": False,
                    "mode": "deep_crawl",
                    "deep_crawl": deep_summary,
                    "clicks_attempted": btn_clicks + int(deep_summary.get("pages_visited") or 0),
                    "issues": deep_issues,
                    "click_log": [],
                }
            else:
                interaction = _probe_ui_interactions(page, _max_ui_clicks())
                interaction["mode"] = "legacy_probe"

            if deep_env_bool("AIFACTORY_BROWSER_FS_MOBILE_GATE", True):
                dp_fs = _read_spec_delivery_profile(data_root, product_id)
                if dp_fs == "full_software":
                    try:
                        mobile_gate = _full_software_mobile_viewport_gate(browser, url)
                    except Exception as me:
                        mobile_gate = {
                            "skipped": False,
                            "error": str(me)[:240],
                            "fatal": True,
                            "issues": [f"mobile_gate_exception:{str(me)[:180]}"],
                        }

            audit_after: dict[str, Any] = {"viewport": {}, "findings": []}
            if visual_dom_on:
                try:
                    audit_after = run_playwright_visual_audit(page, phase_label="after_ui_crawl")
                except Exception as ve:
                    audit_after = {"viewport": {}, "findings": [], "audit_error_after": str(ve)[:240]}

            merged = merge_visual_phases(audit_initial, audit_after) if visual_dom_on else {"findings": []}
            dp_e2e = _read_spec_delivery_profile(data_root, product_id)
            fatal_vis, warn_vis, vis_gate_fail = classify_visual_findings(
                merged.get("findings") or [],
                delivery_profile=dp_e2e,
            )
            if screenshot_fail and screenshot_ratio is not None:
                fatal_vis.append(f"visual_viewport_dark_mass_ratio:{screenshot_ratio:.4f}")

            visual_render_audit = {
                "skipped": not visual_dom_on,
                "merged": merged if visual_dom_on else {},
                "fatal_issues": fatal_vis,
                "warnings": warn_vis,
                "fatal": vis_gate_fail or screenshot_fail,
                "screenshot_dark_ratio_center": screenshot_ratio,
            }
        except Exception as e:
            nav_err = e
        finally:
            try:
                browser.close()
            except Exception:
                pass
        if nav_err is not None:
            return {
                "passed": False,
                "skipped": False,
                "url": url,
                "serve_mode": serve_mode,
                "scenario_e2e": scenario_summary,
                "visual_render_audit": visual_render_audit,
                "mobile_viewport_gate": mobile_gate,
                "issues": [f"playwright_navigation_or_script: {nav_err}"],
            }

    issues: list[str] = []
    passed = True

    if text_len < MIN_VISIBLE_TEXT_LEN:
        passed = False
        issues.append(f"blank_or_tiny_ui: visible text length {text_len} < {MIN_VISIBLE_TEXT_LEN}")

    if not has_visible and text_len < MIN_VISIBLE_TEXT_LEN:
        passed = False
        if "blank_or_tiny_ui" not in " ".join(issues):
            issues.append("no_visible_content")

    if page_errors:
        passed = False
        for pe in page_errors[:8]:
            issues.append(f"pageerror: {pe[:300]}")

    # Strict: any console.error from scripts
    if console_errors:
        passed = False
        for ce in console_errors[:12]:
            t = ce.get("text", "")[:400]
            issues.append(f"console_error: {t}")

    for ui_issue in interaction.get("issues") or []:
        if ui_issue and ui_issue not in issues:
            issues.append(ui_issue)
    if interaction.get("issues"):
        passed = False

    if not mobile_gate.get("skipped"):
        for mi in mobile_gate.get("issues") or []:
            if mi and mi not in issues:
                issues.append(mi)
        if mobile_gate.get("fatal"):
            passed = False

    if scenario_summary.get("ran") and scenario_summary.get("issues"):
        passed = False
        for s_issue in scenario_summary["issues"]:
            if s_issue and s_issue not in issues:
                issues.append(s_issue)

    vb = visual_render_audit if isinstance(visual_render_audit, dict) else {}
    if not vb.get("skipped") and vb.get("fatal"):
        passed = False
        for line in vb.get("fatal_issues") or []:
            if line and line not in issues:
                issues.append(line)

    # Basic a11y checks (cheap but high-value): labels, alt text, heading structure.
    try:
        import re

        html = ""
        from urllib.request import urlopen as _u
        with _u(url, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        lower = html.lower()
        if "<form" in lower:
            input_ids = set(re.findall(r"<input[^>]*id=['\"]([^'\"]+)['\"]", lower))
            labels_for = set(re.findall(r"<label[^>]*for=['\"]([^'\"]+)['\"]", lower))
            unlabeled = input_ids - labels_for
            if unlabeled:
                passed = False
                issues.append(f"a11y_unlabeled_inputs:{len(unlabeled)}")
        imgs = re.findall(r"<img\b[^>]*>", lower)
        missing_alt = [img for img in imgs if "alt=" not in img]
        if missing_alt:
            passed = False
            issues.append(f"a11y_images_missing_alt:{len(missing_alt)}")
        has_h1 = "<h1" in lower
        if not has_h1:
            passed = False
            issues.append("a11y_missing_h1")
    except Exception as e:
        issues.append(f"a11y_probe_error:{str(e)[:120]}")

    return {
        "passed": passed,
        "skipped": False,
        "url": url,
        "serve_mode": serve_mode,
        "scenario_e2e": scenario_summary,
        "visible_text_length": text_len,
        "has_visible_structure": bool(has_visible),
        "page_errors": page_errors[:12],
        "console_errors": console_errors[:20],
        "ui_interaction": interaction,
        "performance": perf if isinstance(perf, dict) else {},
        "visual_render_audit": visual_render_audit if isinstance(visual_render_audit, dict) else {},
        "issues": issues,
        "deep_crawl": deep_summary,
        "mobile_viewport_gate": mobile_gate,
    }
