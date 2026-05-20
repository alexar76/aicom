"""
Canonical public storefront URL for watermarks, referral links, and embed badges.

Priority: ``NEXT_PUBLIC_SITE_URL`` / ``AIFACTORY_PUBLIC_SITE_URL`` env →
``general.public_site_url`` in merged config → default production host.
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_PUBLIC_SITE_URL = "https://magic-ai-factory.com"

_LEGACY_WATERMARK_HOSTS = ("https://aifactory.dev", "http://aifactory.dev")


def _is_http_url(url: str) -> bool:
    u = (url or "").strip()
    return u.startswith("http://") or u.startswith("https://")


def _normalize_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _from_config() -> str:
    try:
        from core.config_merge import load_merged_config
        from core.paths import config_path

        raw = load_merged_config(config_path())
        if not isinstance(raw, dict):
            return ""
        general = raw.get("general")
        if not isinstance(general, dict):
            return ""
        cfg = _normalize_base(str(general.get("public_site_url") or ""))
        return cfg if _is_http_url(cfg) else ""
    except Exception:
        return ""


def resolve_public_site_url(*, config: dict[str, Any] | None = None) -> str:
    """
    Base URL (no trailing slash) used in generated HTML watermarks and share links.
    """
    for key in ("NEXT_PUBLIC_SITE_URL", "AIFACTORY_PUBLIC_SITE_URL"):
        env = _normalize_base(os.environ.get(key) or "")
        if _is_http_url(env):
            return env

    if config is not None:
        general = config.get("general") if isinstance(config.get("general"), dict) else {}
        cfg = _normalize_base(str(general.get("public_site_url") or ""))
        if _is_http_url(cfg):
            return cfg

    cfg = _from_config()
    if cfg:
        return cfg

    return DEFAULT_PUBLIC_SITE_URL


def watermark_badge_html(link_url: str | None = None, *, platform_name: str = "AI-Factory") -> str:
    """Footer block injected into generated static HTML on free-tier watermark policy."""
    base = _normalize_base(link_url or resolve_public_site_url())
    safe_href = html.escape(base, quote=True)
    safe_name = html.escape(platform_name, quote=True)
    return (
        '<div class="aifactory-badge" style="margin-top:24px;padding:8px 12px;font:12px/1.4 system-ui;opacity:.85;">'
        f'Made with <a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_name}</a>'
        "</div>"
    )


_BADGE_HREF_RE = re.compile(
    r'(<div class="aifactory-badge"[^>]*>[\s\S]*?href=")[^"]+(")',
    re.IGNORECASE,
)

_WATERMARK_HREF_CAPTURE = re.compile(
    r'<div\s+class="aifactory-badge"[^>]*>[\s\S]*?href="([^"]+)"',
    re.IGNORECASE,
)


def audit_watermark_in_html(
    content: str,
    *,
    expected: str | None = None,
    source: str = "index.html",
) -> dict[str, str] | None:
    """
    If pipeline watermark markup is present, href must match configured public site URL.
    """
    if "aifactory-badge" not in content.lower():
        return None

    expected_norm = _normalize_base(expected or resolve_public_site_url())
    for legacy in _LEGACY_WATERMARK_HOSTS:
        if legacy in content:
            return {
                "code": "watermark_wrong_public_url",
                "detail": (
                    f"Watermark in {source} still points at legacy {legacy}; "
                    f"expected {expected_norm} (Admin → Public site URL / NEXT_PUBLIC_SITE_URL)."
                ),
            }

    match = _WATERMARK_HREF_CAPTURE.search(content)
    if not match:
        return {
            "code": "watermark_wrong_public_url",
            "detail": (
                f"Watermark block in {source} has no parseable href; "
                f"expected {expected_norm}."
            ),
        }

    href = _normalize_base(match.group(1))
    if href != expected_norm:
        return {
            "code": "watermark_wrong_public_url",
            "detail": (
                f"Watermark in {source} links to {href}; "
                f"configured public site is {expected_norm}."
            ),
        }
    return None


def audit_watermark_links_in_tree(code_dir: Path) -> list[dict[str, str]]:
    """Scan all generated HTML for misaligned pipeline watermarks."""
    issues: list[dict[str, str]] = []
    if not code_dir.is_dir():
        return issues
    expected = resolve_public_site_url()
    for html_file in sorted(code_dir.rglob("*.html")):
        try:
            content = html_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(html_file.relative_to(code_dir))
        row = audit_watermark_in_html(content, expected=expected, source=rel)
        if row:
            issues.append(row)
    return issues


def sync_watermark_in_html(content: str, link_url: str | None = None) -> str:
    """
    Inject or refresh the pipeline watermark block. Replaces legacy ``aifactory.dev`` hrefs.
    """
    base = _normalize_base(link_url or resolve_public_site_url())
    badge = watermark_badge_html(base)

    if "aifactory-badge" in content:
        updated = _BADGE_HREF_RE.sub(rf"\1{html.escape(base, quote=True)}\2", content, count=1)
        for legacy in _LEGACY_WATERMARK_HOSTS:
            updated = updated.replace(legacy, base)
        return updated

    for legacy in _LEGACY_WATERMARK_HOSTS:
        if legacy in content:
            content = content.replace(legacy, base)

    lower = content.lower()
    if "</body>" in lower:
        idx = lower.rfind("</body>")
        return content[:idx] + badge + content[idx:]
    return content + badge
