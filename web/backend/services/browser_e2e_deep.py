"""
Deep browser crawl for static demo QA: same-origin link closure, anchors, forms, buttons.

Used by ``browser_preview_e2e``. Keeps Playwright types as ``Any`` so tests can import URL helpers
without installing Playwright.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw == "":
        return default
    return raw in ("1", "true", "yes", "on")


def is_loopback_href(href: str) -> bool:
    """Detect localhost / loopback in an href string before resolution."""
    h = href.strip()
    if not h:
        return False
    low = h.lower()
    if low.startswith(("http://localhost", "https://localhost", "http://127.", "https://127.")):
        return True
    if low.startswith("//localhost") or low.startswith("//127.0.0.1") or low.startswith("//[::1]"):
        return True
    return False


def normalize_visit_key(url: str) -> str:
    """Stable key for visited set (scheme/host/port/path/query/fragment)."""
    p = urlparse(url)
    path = p.path or "/"
    # Strip default ports
    netloc = p.netloc
    if netloc.endswith(":80") and p.scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and p.scheme == "https":
        netloc = netloc[:-4]
    return urlunparse((p.scheme.lower(), netloc.lower(), path, "", p.query, p.fragment))


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return pa.scheme == pb.scheme and pa.netloc.lower() == pb.netloc.lower()


def origin_of(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, "", "", "", ""))


def e2e_credentials() -> dict[str, str]:
    return {
        "email": os.environ.get("AIFACTORY_E2E_EMAIL", "e2e-user@example.invalid"),
        "username": os.environ.get("AIFACTORY_E2E_USERNAME", "e2e_tester"),
        "password": os.environ.get("AIFACTORY_E2E_PASSWORD", "e2e-password-change-me"),
        "full_name": os.environ.get("AIFACTORY_E2E_FULL_NAME", "E2E Test User"),
    }


def _screenshot_path(shots_dir: Path, url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8", errors="replace")).hexdigest()[:20]
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", urlparse(url).path.replace("/", "_"))[:60]
    return shots_dir / f"{h}{safe}.png"


def _extract_hrefs(page: Any) -> list[str]:
    try:
        raw = page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]'))
                .map(a => (a.getAttribute('href')||'').trim())
                .filter(Boolean)"""
        )
        return list(raw) if isinstance(raw, list) else []
    except Exception:
        return []


def _visible_text_snippet(page: Any, limit: int = 1800) -> str:
    try:
        t = page.evaluate(
            """(lim) => {
            const b = document.body;
            if (!b) return '';
            return (b.innerText || '').trim().slice(0, lim);
        }""",
            limit,
        )
        return str(t or "")[:limit]
    except Exception:
        return ""


def _fill_and_submit_forms(
    page: Any,
    *,
    max_forms: int,
    creds: dict[str, str],
    nav_timeout_ms: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        forms = page.locator("form")
        n = forms.count()
        for fi in range(min(n, max_forms)):
            form = forms.nth(fi)
            try:
                if not form.is_visible():
                    continue
                before_url = page.url
                inputs = form.locator(
                    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]), textarea, select"
                )
                icount = inputs.count()
                filled = 0
                for ii in range(icount):
                    el = inputs.nth(ii)
                    try:
                        if not el.is_visible():
                            continue
                        tag = (el.evaluate("e => e.tagName") or "").upper()
                        typ = (el.get_attribute("type") or "text").lower()
                        name = (el.get_attribute("name") or el.get_attribute("id") or f"f{fi}_i{ii}").lower()
                        if tag == "SELECT":
                            try:
                                el.select_option(index=0, timeout=3_000)
                                filled += 1
                            except Exception:
                                pass
                            continue
                        if typ in ("checkbox", "radio"):
                            try:
                                el.check(timeout=2_000)
                                filled += 1
                            except Exception:
                                pass
                            continue
                        if typ == "file":
                            continue
                        if typ in ("email",) or "email" in name:
                            el.fill(creds["email"], timeout=3_000)
                        elif typ == "password":
                            el.fill(creds["password"], timeout=3_000)
                        elif "user" in name or name == "login" or typ == "text" and "user" in name:
                            el.fill(creds["username"], timeout=3_000)
                        elif "name" in name and "user" not in name:
                            el.fill(creds["full_name"], timeout=3_000)
                        elif typ in ("number", "range"):
                            el.fill("42", timeout=2_000)
                        elif typ in ("tel",):
                            el.fill("+15555550199", timeout=2_000)
                        elif typ in ("url",):
                            el.fill("https://example.invalid/demo", timeout=2_000)
                        else:
                            el.fill(f"e2e-{name[:24]}-value", timeout=3_000)
                        filled += 1
                    except Exception as fe:
                        out.append({"form_index": fi, "phase": "fill", "error": str(fe)[:200]})
                sub = form.locator("button[type='submit'], input[type='submit']").first
                clicked = False
                try:
                    if sub.count() > 0 and sub.is_visible():
                        sub.click(timeout=5_000)
                        clicked = True
                except Exception as ce:
                    out.append({"form_index": fi, "phase": "submit_click", "error": str(ce)[:200]})
                if not clicked:
                    try:
                        form.evaluate("f => { try { f.requestSubmit(); } catch(e) { try { f.submit(); } catch(_){} } }")
                        clicked = True
                    except Exception:
                        pass
                page.wait_for_timeout(min(1200, nav_timeout_ms // 5))
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=min(nav_timeout_ms, 12_000))
                except Exception:
                    pass
                out.append(
                    {
                        "form_index": fi,
                        "filled_fields": filled,
                        "submit_clicked": clicked,
                        "url_before": before_url,
                        "url_after": page.url,
                        "ok": True,
                    }
                )
            except Exception as e:
                out.append({"form_index": fi, "error": str(e)[:220], "ok": False})
    except Exception as e:
        out.append({"error": f"forms_probe: {str(e)[:200]}", "ok": False})
    return out


def _click_misc_controls(page: Any, *, max_clicks: int) -> dict[str, Any]:
    """Visible buttons / role=button not covered only by hash-only anchors."""
    log: list[dict[str, Any]] = []
    issues: list[str] = []
    if max_clicks <= 0:
        return {"clicks": 0, "log": [], "issues": []}
    sel = "button:visible, [role='button']:visible, input[type='button']:visible, input[type='submit']:visible"
    try:
        loc = page.locator(sel)
        cnt = loc.count()
        clicks = 0
        for i in range(min(cnt, max_clicks * 3)):
            if clicks >= max_clicks:
                break
            item = loc.nth(i)
            try:
                if not item.is_visible():
                    continue
                snippet = (item.inner_text() or "")[:48].replace("\n", " ")
                item.click(timeout=4_000)
                page.wait_for_timeout(280)
                clicks += 1
                log.append({"index": i, "snippet": snippet, "ok": True})
            except Exception as e:
                log.append({"index": i, "ok": False, "error": str(e)[:160]})
                issues.append(f"button_click_failed:{str(e)[:120]}")
    except Exception as e:
        issues.append(f"button_probe_error:{str(e)[:160]}")
    return {"clicks": clicks, "log": log[:40], "issues": issues}


def run_deep_crawl(
    page: Any,
    *,
    base_origin: str,
    start_url: str,
    screenshot_dir: Path | None,
    max_pages: int,
    max_depth: int,
    per_nav_timeout_ms: int,
    max_forms_per_page: int,
    max_button_clicks_per_page: int,
) -> dict[str, Any]:
    """
    BFS over same-origin URLs discoverable via <a href>; exercises anchors, forms, and buttons per page.
    """
    shot_on = screenshot_dir is not None and env_bool("AIFACTORY_BROWSER_SCREENSHOTS", True)
    if shot_on and screenshot_dir is not None:
        screenshot_dir.mkdir(parents=True, exist_ok=True)

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    creds = e2e_credentials()

    pages_out: list[dict[str, Any]] = []
    navigation_failures: list[dict[str, Any]] = []
    loopback_hrefs: list[dict[str, Any]] = []

    while queue and len(visited) < max_pages:
        cur, depth = queue.popleft()
        key = normalize_visit_key(cur)
        if key in visited:
            continue
        if depth > max_depth:
            continue
        visited.add(key)

        resp_status = None
        try:
            resp = page.goto(cur, wait_until="domcontentloaded", timeout=per_nav_timeout_ms)
            resp_status = getattr(resp, "status", None) if resp is not None else None
        except Exception as e:
            navigation_failures.append({"url": cur, "error": str(e)[:240], "phase": "goto"})
            pages_out.append({"url": cur, "depth": depth, "status": None, "error": str(e)[:120]})
            continue

        page.wait_for_timeout(350)

        shot_path_str = None
        if shot_on and screenshot_dir is not None:
            try:
                sp = _screenshot_path(screenshot_dir, page.url)
                page.screenshot(path=str(sp), full_page=False)
                shot_path_str = str(sp)
            except Exception:
                pass

        body_snippet = _visible_text_snippet(page)

        raw_hrefs = _extract_hrefs(page)
        resolved_discovered: list[str] = []
        for href in raw_hrefs:
            if is_loopback_href(href):
                loopback_hrefs.append({"page": page.url, "href": href[:200]})
                continue
            if href.strip().lower().startswith(("mailto:", "tel:", "javascript:")):
                continue
            abs_u = urljoin(page.url, href.strip())
            low = abs_u.lower()
            if low.startswith("http://") or low.startswith("https://"):
                if not same_origin(abs_u, base_origin):
                    continue
            elif abs_u.startswith("//"):
                abs_u = urlparse(base_origin).scheme + ":" + abs_u
                if not same_origin(abs_u, base_origin):
                    continue
            resolved_discovered.append(abs_u)

        btn = _click_misc_controls(page, max_clicks=max_button_clicks_per_page)
        forms = _fill_and_submit_forms(
            page,
            max_forms=max_forms_per_page,
            creds=creds,
            nav_timeout_ms=per_nav_timeout_ms,
        )

        # Second-pass links after UI mutations
        for href in _extract_hrefs(page):
            if is_loopback_href(href):
                loopback_hrefs.append({"page": page.url, "href": href[:200]})
                continue
            if href.strip().lower().startswith(("mailto:", "tel:", "javascript:")):
                continue
            abs_u = urljoin(page.url, href.strip())
            if abs_u.startswith("//"):
                abs_u = urlparse(base_origin).scheme + ":" + abs_u
            if abs_u.startswith("http") and not same_origin(abs_u, base_origin):
                continue
            resolved_discovered.append(abs_u)

        for tgt in resolved_discovered:
            nk = normalize_visit_key(tgt)
            if nk not in visited and len(visited) + sum(1 for _ in queue) < max_pages * 2:
                queue.append((tgt, depth + 1))

        pages_out.append(
            {
                "url": cur,
                "final_url": page.url,
                "depth": depth,
                "status": resp_status,
                "screenshot": shot_path_str,
                "text_snippet": body_snippet[:1600],
                "links_found": len(set(resolved_discovered)),
                "button_probe": btn,
                "forms": forms,
            }
        )

    summary = {
        "mode": "deep_crawl",
        "base_origin": base_origin,
        "pages_visited": len(pages_out),
        "visited_unique": len(visited),
        "navigation_failures": navigation_failures,
        "loopback_hrefs": loopback_hrefs,
        "pages": pages_out[:120],
        "credentials_profile": {k: ("***" if k == "password" else v) for k, v in creds.items()},
    }
    try:
        summary_json = json.dumps(summary, ensure_ascii=False)[:100_000]
    except Exception:
        summary_json = "{}"
    summary["_json_truncated_hint"] = len(summary.get("pages") or []) >= 120
    summary["_summary_chars"] = len(summary_json)
    return summary


def deep_crawl_gate_issues(summary: dict[str, Any]) -> list[str]:
    """
    Hard failures: unreachable URLs, loopback hrefs, HTTP error statuses.
    Optional (``AIFACTORY_BROWSER_DEEP_STRICT_UI=1``): flaky interactions — failed form/button clicks.
    """
    issues: list[str] = []
    strict_ui = env_bool("AIFACTORY_BROWSER_DEEP_STRICT_UI", False)
    for f in summary.get("navigation_failures") or []:
        issues.append(f"deep_nav_failed:{f.get('url','')}:{f.get('error','')}")
    for lh in summary.get("loopback_hrefs") or []:
        issues.append(f"deep_loopback_href:{lh.get('page','')}:{lh.get('href','')}")
    for p in summary.get("pages") or []:
        st = p.get("status")
        if isinstance(st, int) and st >= 400:
            issues.append(f"deep_http_{st}:{p.get('url','')}")
        err = p.get("error")
        if err:
            issues.append(f"deep_page_error:{p.get('url','')}:{err}")
        if strict_ui:
            for row in p.get("forms") or []:
                if isinstance(row, dict) and row.get("ok") is False:
                    issues.append(f"deep_form_failed:{row}")
            for bi in (p.get("button_probe") or {}).get("issues") or []:
                issues.append(f"deep_button:{bi}")
    return issues[:200]
