"""SKOPOS brand mark — inline SVG, no emoji dependencies."""

from __future__ import annotations

import html

from skopos.themes import Theme, get_active_theme


def logo_svg(*, accent: str, accent2: str, size: int = 36, uid: str = "skopos") -> str:
    """Premium gradient mark with analytics line."""
    grad = f"skopos-grad-{uid}"
    glow = f"skopos-glow-{uid}"
    return f"""
<svg class="skopos-logo-mark" width="{size}" height="{size}" viewBox="0 0 36 36"
     xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">
  <defs>
    <linearGradient id="{grad}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{html.escape(accent)}"/>
      <stop offset="100%" stop-color="{html.escape(accent2)}"/>
    </linearGradient>
    <filter id="{glow}" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="1.8" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect x="1" y="1" width="34" height="34" rx="11" fill="url(#{grad})"
        filter="url(#{glow})" opacity="0.98"/>
  <rect x="1" y="1" width="34" height="34" rx="11" fill="none"
        stroke="rgba(255,255,255,0.28)" stroke-width="0.75"/>
  <path d="M9 24.5 L15.5 18.5 L21 22 L27.5 11.5" fill="none"
        stroke="#ffffff" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="27.5" cy="11.5" r="2.2" fill="#ffffff"/>
  <path d="M9 27.5 H27" stroke="rgba(255,255,255,0.35)" stroke-width="1.2" stroke-linecap="round"/>
</svg>""".strip()


def sidebar_brand_html(*, title: str, tagline: str, theme: Theme | None = None) -> str:
    th = theme or get_active_theme()
    safe_title = html.escape(title)
    safe_tagline = html.escape(tagline)
    mark = logo_svg(accent=th.accent, accent2=th.accent2, uid=th.id)
    return (
        f'<div class="skopos-sidebar-brand">'
        f'<div class="skopos-brand-row">'
        f"{mark}"
        f'<div class="skopos-brand-text">'
        f'<p class="skopos-sidebar-title">{safe_title}</p>'
        f'<p class="skopos-sidebar-tagline">{safe_tagline}</p>'
        f"</div></div></div>"
    )


def render_sidebar_brand(*, title: str, tagline: str, theme: Theme | None = None) -> None:
    """Render brand block without Streamlit markdown <p> wrapping."""
    import streamlit as st

    body = sidebar_brand_html(title=title, tagline=tagline, theme=theme)
    if hasattr(st.sidebar, "html"):
        st.sidebar.html(body)
    else:
        st.sidebar.markdown(body, unsafe_allow_html=True)


def favicon_path() -> str:
    """Path to static favicon for st.set_page_config(page_icon=...)."""
    from pathlib import Path

    return str(Path(__file__).resolve().parent.parent / "assets" / "favicon.svg")
