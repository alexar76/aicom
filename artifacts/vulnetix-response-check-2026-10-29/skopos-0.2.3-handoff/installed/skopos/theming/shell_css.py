"""CSS for the app shell: status bar, the critical shell and theme boot script, portal
overlays, the login gate and the sidebar layout.
"""

from __future__ import annotations

from .catalog import (
    _theme_ids_json,
    _theme_shell_colors,
    DEFAULT_THEME,
    is_dark_theme,
    Theme,
    theme_shell_bg,
    ThemeId,
)
from .widget_css import _widget_palette


def _status_bar_palette() -> dict[ThemeId, dict[str, str]]:
    """Header + Running… bar colors keyed by data-skopos-theme (survives rerun flash)."""
    return {
        "light": {
            "header_bg": "rgba(255,255,255,0.92)",
            "status_bg": "rgba(255,255,255,0.96)",
            "text": "#202124",
            "muted": "#5f6368",
            "border": "rgba(0,0,0,0.10)",
        },
        "dark": {
            "header_bg": "rgba(13,17,23,0.96)",
            "status_bg": "rgba(22,27,34,0.98)",
            "text": "#e6edf3",
            "muted": "#8b949e",
            "border": "rgba(88,166,255,0.28)",
        },
        "premium": {
            "header_bg": "rgba(255,254,249,0.92)",
            "status_bg": "rgba(255,254,249,0.96)",
            "text": "#1a1408",
            "muted": "#3d3528",
            "border": "rgba(184,134,11,0.28)",
        },
        "midnight": {
            "header_bg": "transparent",
            "status_bg": "rgba(18,12,22,0.88)",
            "text": "#fff4e8",
            "muted": "#c4a88a",
            "border": "rgba(255,160,80,0.28)",
        },
        "ocean": {
            "header_bg": "rgba(4,16,24,0.96)",
            "status_bg": "rgba(10,28,40,0.98)",
            "text": "#e0f7fa",
            "muted": "#80cbc4",
            "border": "rgba(38,198,218,0.28)",
        },
        "forest": {
            "header_bg": "rgba(10,18,12,0.96)",
            "status_bg": "rgba(20,32,24,0.98)",
            "text": "#e8f5e9",
            "muted": "#a5d6a7",
            "border": "rgba(102,187,106,0.28)",
        },
        "slate": {
            "header_bg": "rgba(238,241,245,0.92)",
            "status_bg": "rgba(248,249,251,0.96)",
            "text": "#1c2333",
            "muted": "#5c6578",
            "border": "rgba(84,110,122,0.28)",
        },
        "rose": {
            "header_bg": "rgba(20,8,16,0.96)",
            "status_bg": "rgba(30,16,24,0.98)",
            "text": "#fce4ec",
            "muted": "#f48fb1",
            "border": "rgba(236,64,122,0.28)",
        },
        "aurora": {
            "header_bg": "transparent",
            "status_bg": "rgba(16,10,28,0.88)",
            "text": "#ede7f6",
            "muted": "#b39ddb",
            "border": "rgba(124,77,255,0.28)",
        },
    }


def build_status_bar_css() -> str:
    """Theme-aware Running… / stStatusWidget chrome — uses html[data-skopos-theme] for first paint."""
    blocks: list[str] = [
        """
  /* Streamlit header strip — hidden; SKOPOS topbar + floating Running… pill replace it. */
  header[data-testid="stHeader"] {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    max-height: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    overflow: hidden !important;
  }

  /* Keep the last complete dashboard readable while Streamlit reruns. The
     active section has its own progress bar, so dimming every old element to
     33% only makes the application look disabled. */
  [data-testid="element-container"][data-stale="true"] {
    opacity: 1 !important;
    transition: none !important;
  }
  [data-testid="stTabs"] [data-baseweb="tab-list"] {
    opacity: 1 !important;
    transition: none !important;
  }
"""
    ]
    for tid, pal in _status_bar_palette().items():
        blocks.append(
            f"""
  html[data-skopos-theme="{tid}"] header[data-testid="stHeader"] {{
    display: none !important;
    background: transparent !important;
    border: none !important;
  }}
  /* Theme the "Running… / _load_df(…)" status pill on FIRST PAINT so it never
     flashes Streamlit's default dark toast over a light theme (the brown bar). */
  html[data-skopos-theme="{tid}"] [data-testid="stStatusWidget"],
  html[data-skopos-theme="{tid}"] [data-testid="stConnectionStatus"] {{
    background: {pal["status_bg"]} !important;
    color: {pal["text"]} !important;
    border: 1px solid {pal["border"]} !important;
    border-radius: 999px !important;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12) !important;
    backdrop-filter: blur(10px) saturate(1.1) !important;
    -webkit-backdrop-filter: blur(10px) saturate(1.1) !important;
  }}
  html[data-skopos-theme="{tid}"] [data-testid="stStatusWidget"] *,
  html[data-skopos-theme="{tid}"] [data-testid="stConnectionStatus"] * {{
    color: {pal["text"]} !important;
    fill: {pal["text"]} !important;
  }}
  html[data-skopos-theme="{tid}"] [data-testid="stStatusWidget"] svg,
  html[data-skopos-theme="{tid}"] [data-testid="stConnectionStatus"] svg {{
    stroke: {pal["text"]} !important;
  }}
"""
        )
    return f"""
<style id="skopos-status-bar">
{"".join(blocks)}
</style>
"""



def _build_theme_boot_script() -> str:
    return f"""
<script id="skopos-theme-boot">
(function() {{
  var valid = {_theme_ids_json()};
  try {{
    var stored = localStorage.getItem("skopos-theme-id");
    if (stored && valid.indexOf(stored) >= 0) {{
      document.documentElement.setAttribute("data-skopos-theme", stored);
    }} else {{
      document.documentElement.setAttribute("data-skopos-theme", "{DEFAULT_THEME}");
    }}
  }} catch (e) {{}}
}})();
</script>
"""


def build_critical_shell_css(theme: Theme, *, collapsed: bool = False) -> str:
    """First-paint shell: full background + text before Streamlit widgets render."""
    th = theme
    shell = theme_shell_bg(th)
    scheme = "dark" if is_dark_theme(theme.id) else "light"
    shells_json = __import__("json").dumps(_theme_shell_colors())
    _ = collapsed  # sidebar is always expanded; kept for call-site compatibility
    return (
        _build_theme_boot_script()
        + build_status_bar_css()
        + f"""
<style id="stats-critical-shell">
  :root {{
    --skopos-sidebar-expanded-width: 17rem;
    --skopos-sidebar-collapsed-width: 4rem;
    --skopos-sidebar-collapsed: var(--skopos-sidebar-collapsed-width);
    --skopos-sidebar-expanded: var(--skopos-sidebar-expanded-width);
    --sidebar-width: var(--skopos-sidebar-expanded-width);
  }}
  html.skopos-sidebar-expanded {{
    --sidebar-width: var(--skopos-sidebar-expanded-width) !important;
  }}
  html.skopos-sidebar-collapsed {{
    --sidebar-width: var(--skopos-sidebar-collapsed-width) !important;
  }}
  html {{
    color-scheme: {scheme};
    background-color: {shell} !important;
  }}
  body,
  [data-testid="stAppViewContainer"],
  [data-testid="stApp"],
  .stApp,
  [data-testid="stMain"],
  section.main {{
    background-color: {shell} !important;
    background-image: {th.app_bg} !important;
    color: {th.text} !important;
    transition: none !important;
  }}
  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"] > div,
  [data-testid="stSidebarUserContent"] {{
    background: {th.sidebar_bg} !important;
    transition:
      width 0.28s cubic-bezier(0.4, 0, 0.2, 1),
      min-width 0.28s cubic-bezier(0.4, 0, 0.2, 1),
      max-width 0.28s cubic-bezier(0.4, 0, 0.2, 1),
      flex-basis 0.28s cubic-bezier(0.4, 0, 0.2, 1),
      padding 0.28s cubic-bezier(0.4, 0, 0.2, 1) !important;
  }}
  section[data-testid="stSidebar"] .stMarkdown,
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] span,
  section[data-testid="stSidebar"] small {{
    color: {th.text} !important;
  }}
</style>
<script>
(function() {{
  var id = "{theme.id}";
  var collapsed = false;
  var valid = {_theme_ids_json()};
  var shells = {shells_json};
  var expandedW = "17rem";
  function isMobileViewport() {{
    return window.matchMedia("(max-width: 768px)").matches;
  }}
  function applySidebarWidth() {{
    if (isMobileViewport()) {{
      var sbMobile = document.querySelector('section[data-testid="stSidebar"]');
      if (sbMobile) {{
        sbMobile.style.removeProperty("width");
        sbMobile.style.removeProperty("min-width");
        sbMobile.style.removeProperty("max-width");
        var inner = sbMobile.querySelector(":scope > div");
        if (inner) {{
          inner.style.removeProperty("width");
          inner.style.removeProperty("min-width");
          inner.style.removeProperty("max-width");
        }}
      }}
      document.documentElement.style.setProperty("--sidebar-width", "0px");
      return;
    }}
    document.documentElement.style.setProperty("--sidebar-width", expandedW);
    var sb = document.querySelector('section[data-testid="stSidebar"]');
    if (sb) {{
      sb.style.setProperty("width", expandedW, "important");
      sb.style.setProperty("min-width", expandedW, "important");
      sb.style.setProperty("max-width", expandedW, "important");
      var measured = sb.getBoundingClientRect().width;
      if (measured > 32) {{
        document.documentElement.style.setProperty("--sidebar-width", measured + "px");
      }}
    }}
  }}
  try {{
    if (valid.indexOf(id) < 0) {{
      id = "{DEFAULT_THEME}";
    }}
    document.documentElement.setAttribute("data-skopos-theme", id);
    if (!isMobileViewport()) {{
      document.documentElement.classList.remove("skopos-sidebar-collapsed");
      document.documentElement.classList.add("skopos-sidebar-expanded");
      localStorage.setItem("skopos-sidebar-collapsed", "0");
    }} else {{
      document.documentElement.classList.remove("skopos-sidebar-collapsed");
      document.documentElement.classList.remove("skopos-sidebar-expanded");
    }}
    applySidebarWidth();
    if (shells[id]) {{
      document.documentElement.style.backgroundColor = shells[id];
    }}
    localStorage.setItem("skopos-theme-id", id);
    if (!isMobileViewport()) {{
      localStorage.setItem("skopos-sidebar-collapsed", "0");
    }}
    if (window.__skoposSidebarObs) {{
      window.__skoposSidebarObs.disconnect();
    }}
    var pending = null;
    window.__skoposSidebarObs = new MutationObserver(function() {{
      if (pending) return;
      pending = requestAnimationFrame(function() {{
        pending = null;
        applySidebarWidth();
      }});
    }});
    window.__skoposSidebarObs.observe(document.documentElement, {{ childList: true, subtree: true }});
  }} catch (e) {{}}
}})();
</script>
"""
    )


def build_portal_overlay_css(theme: Theme) -> str:
    """Selectbox/multiselect menus render in a body portal — outside .stApp."""
    th = theme
    pal = _widget_palette(theme)
    menu_bg = pal["widget_bg"]
    menu_text = pal["widget_text"]
    menu_border = pal["widget_border"]
    hover_bg = pal["chip_bg"]
    hover_text = pal["chip_text"]
    selected_bg = th.accent
    selected_text = "#ffffff"
    return f"""
<style id="stats-portal-overlays">
  /* Streamlit virtual dropdowns (portal to body, not inside .stApp) */
  [data-testid="stSelectboxVirtualDropdown"],
  [data-testid="stVirtualDropdown"],
  [data-testid="stMultiSelectVirtualDropdown"],
  [data-testid="stSelectboxVirtualDropdown"] > div,
  [data-testid="stVirtualDropdown"] > div,
  [data-testid="stMultiSelectVirtualDropdown"] > div,
  [data-testid="stSelectboxVirtualDropdown"] [role="listbox"],
  [data-testid="stVirtualDropdown"] [role="listbox"],
  [data-testid="stMultiSelectVirtualDropdown"] [role="listbox"],
  div[data-baseweb="popover"] [data-baseweb="menu"],
  div[data-baseweb="popover"] [data-baseweb="menu"] ul {{
    background-color: {menu_bg} !important;
    color: {menu_text} !important;
    border-color: {menu_border} !important;
  }}

  [data-testid="stSelectboxVirtualDropdown"],
  [data-testid="stVirtualDropdown"],
  [data-testid="stMultiSelectVirtualDropdown"] {{
    border: 1px solid {menu_border} !important;
    box-shadow: {pal["menu_shadow"]} !important;
    border-radius: 8px !important;
  }}

  [data-testid="stSelectboxVirtualDropdown"] li[role="option"],
  [data-testid="stVirtualDropdown"] li[role="option"],
  [data-testid="stMultiSelectVirtualDropdown"] li[role="option"],
  div[data-baseweb="menu"] li,
  div[data-baseweb="menu"] li[role="option"],
  div[role="listbox"] [role="option"] {{
    background-color: transparent !important;
    color: {menu_text} !important;
  }}

  [data-testid="stSelectboxVirtualDropdown"] li[role="option"]:hover,
  [data-testid="stVirtualDropdown"] li[role="option"]:hover,
  [data-testid="stMultiSelectVirtualDropdown"] li[role="option"]:hover,
  div[data-baseweb="menu"] li:hover,
  div[role="listbox"] [role="option"]:hover {{
    background-color: {hover_bg} !important;
    color: {hover_text} !important;
  }}

  [data-testid="stSelectboxVirtualDropdown"] li[role="option"][aria-selected="true"],
  [data-testid="stVirtualDropdown"] li[role="option"][aria-selected="true"],
  [data-testid="stMultiSelectVirtualDropdown"] li[role="option"][aria-selected="true"],
  div[data-baseweb="menu"] li[aria-selected="true"],
  div[role="listbox"] [role="option"][aria-selected="true"] {{
    background-color: {selected_bg} !important;
    color: {selected_text} !important;
  }}

  /* Date/time pickers, tooltips, popovers — also portaled to body */
  [data-testid="stDateInputPopover"],
  [data-testid="stDateInputCalendar"],
  [data-testid="stTimeInputPopover"],
  [data-testid="stTooltip"],
  [data-testid="stTooltipIcon"],
  [data-baseweb="tooltip"],
  div[data-baseweb="calendar"],
  div[data-baseweb="calendar"] header,
  div[data-baseweb="calendar"] div {{
    background-color: {menu_bg} !important;
    color: {menu_text} !important;
    border-color: {menu_border} !important;
  }}

  div[data-baseweb="calendar"] abbr,
  div[data-baseweb="calendar"] span,
  div[data-baseweb="calendar"] button {{
    color: {menu_text} !important;
  }}

  div[data-baseweb="calendar"] [aria-selected="true"],
  div[data-baseweb="calendar"] [data-baseweb="calendar-day"]:hover {{
    background-color: {hover_bg} !important;
    color: {hover_text} !important;
  }}

  [data-baseweb="tooltip"] > div,
  [data-baseweb="tooltip"] div,
  [data-testid="stTooltip"] > div,
  [data-testid="stTooltip"] p {{
    background-color: transparent !important;
    color: inherit !important;
    border: none !important;
    box-shadow: none !important;
  }}
</style>
"""


def build_login_gate_css(theme: Theme) -> str:
    """Centered login card — one panel, no empty column chrome."""
    th = theme
    pal = _widget_palette(theme)
    widget_text = pal["widget_text"]
    widget_muted = pal["widget_muted"]
    return f"""
<style id="skopos-login-gate">
  .stApp:has(.skopos-login-page-marker) section[data-testid="stSidebar"] {{
    display: none !important;
  }}
  .stApp:has(.skopos-login-page-marker) [data-testid="stToolbar"],
  .stApp:has(.skopos-login-page-marker) [data-testid="stToolbarAppName"] {{
    display: none !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main .block-container {{
    max-width: 26rem !important;
    width: min(26rem, calc(100vw - 2rem)) !important;
    margin: clamp(2.5rem, 10vh, 5rem) auto 2rem !important;
    padding: 2.1rem 2rem 2.35rem !important;
    background: {th.card_bg} !important;
    border: 1.5px solid {th.card_border} !important;
    border-radius: 18px !important;
    box-shadow: {th.card_shadow}, 0 18px 42px rgba(0, 0, 0, 0.28) !important;
    overflow: visible !important;
  }}

  .stApp:has(.skopos-login-page-marker) .main [data-testid="stVerticalBlockBorderWrapper"],
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"],
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] > div,
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] [data-testid="stVerticalBlock"],
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] [data-testid="stTextInput"],
  .stApp:has(.skopos-login-page-marker) .main div.element-container:has([data-testid="stTextInput"]) {{
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    padding: 0 !important;
    margin: 0 !important;
    overflow: visible !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:hover {{
    transform: none !important;
    box-shadow: none !important;
  }}

  .stApp:has(.skopos-login-page-marker) .main [data-testid="stExpander"] details {{
    border: 1px solid {th.border} !important;
    border-radius: 12px !important;
    box-shadow: none !important;
    background: color-mix(in srgb, {th.card_bg} 88%, {th.accent} 12%) !important;
    margin: 0.85rem 0 1.1rem !important;
  }}

  .stApp:has(.skopos-login-page-marker) .main h3 {{
    text-align: center !important;
    margin: 0 0 0.35rem !important;
    color: {widget_text} !important;
    font-size: 1.35rem !important;
    letter-spacing: 0.01em !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stCaptionContainer"] {{
    text-align: center !important;
    margin-bottom: 0.35rem !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stCaptionContainer"] p {{
    color: {widget_muted} !important;
    font-size: 0.92rem !important;
  }}

  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] {{
    margin-top: 0.35rem !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] [data-testid="stTextInput"] {{
    margin-bottom: 0.5rem !important;
    padding-bottom: 0.15rem !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stTextInput"] [data-baseweb="input"],
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="input"] {{
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    overflow: visible !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stTextInput"] [data-baseweb="input"] > div,
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="input"] > div {{
    background-color: {pal["input_inset_bg"]} !important;
    border: 1.5px solid {pal["input_inset_border"]} !important;
    border-radius: 10px !important;
    min-height: 2.85rem !important;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.12) !important;
    overflow: visible !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stFormSubmitButton"] > button {{
    margin-top: 0.65rem !important;
    min-height: 2.85rem !important;
    font-weight: 600 !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    position: relative !important;
    z-index: 5 !important;
  }}
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stFormSubmitButton"] > button p,
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stFormSubmitButton"] > button span {{
    opacity: 1 !important;
    color: inherit !important;
  }}

  /* Hide chrome columns on login, but never hide the form submit row. */
  .stApp:has(.skopos-login-page-marker) .main [data-testid="stHorizontalBlock"]:not(:has([data-testid="stFormSubmitButton"])) {{
    display: none !important;
  }}
</style>
"""


def build_sidebar_layout_css(theme: Theme, *, collapsed: bool = False) -> str:
    """Sidebar layout — always expanded full panel."""
    th = theme
    pal = _widget_palette(theme)
    _ = collapsed
    return f"""
<style id="stats-sidebar-layout">
  @media (min-width: 769px) {{
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {{
      display: none !important;
    }}
  }}

  section[data-testid="stSidebar"] {{
    overflow-x: hidden !important;
    overflow-y: auto !important;
  }}

  section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    display: flex !important;
    flex-direction: column !important;
    min-height: calc(100vh - 1rem) !important;
    padding-top: 0.65rem !important;
    padding-bottom: 1rem !important;
  }}
  .skopos-sidebar-bottom-start {{
    margin-top: auto !important;
    padding-top: 1rem !important;
    border-top: 1px solid {th.border} !important;
    width: 100% !important;
  }}

  .skopos-hidden-page-links {{
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    padding: 0 !important;
    margin: -1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
    white-space: nowrap !important;
    border: 0 !important;
  }}

  /* GA-style nav links */
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{
    display: flex !important;
    align-items: center !important;
    gap: 0.65rem !important;
    border-radius: 0 999px 999px 0 !important;
    padding: 0.5rem 0.85rem 0.5rem 0.65rem !important;
    margin-right: 0.25rem !important;
    text-decoration: none !important;
    font-family: 'Outfit', system-ui, sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    min-height: 2.5rem !important;
    transition: background-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active {{
    background: color-mix(in srgb, {th.accent} 14%, transparent) !important;
    color: {th.accent} !important;
    font-weight: 600 !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active [data-testid="stIconMaterial"],
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active svg {{
    color: {th.accent} !important;
    fill: {th.accent} !important;
  }}

  section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{
    background-color: {pal["chip_bg"]} !important;
    color: {pal["chip_text"]} !important;
  }}

  section[data-testid="stSidebar"] div.element-container:has([data-testid="stTextInput"]) {{
    overflow: visible !important;
    margin-bottom: 0.65rem !important;
    padding-bottom: 2px !important;
  }}

  .skopos-sidebar-brand {{
    margin: 0 0 1rem !important;
    padding: 0 0.15rem !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]:has(.skopos-sidebar-brand),
  section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]:has(.skopos-sidebar-brand) p,
  section[data-testid="stSidebar"] [data-testid="stHtml"] .skopos-sidebar-brand,
  section[data-testid="stSidebar"] [data-testid="stHtml"] .skopos-sidebar-brand p {{
    margin: 0 !important;
    padding: 0 !important;
  }}
  .skopos-brand-row {{
    display: flex !important;
    flex-direction: row !important;
    align-items: flex-start !important;
    gap: 0.75rem !important;
    width: 100% !important;
  }}
  .skopos-logo-mark {{
    flex: 0 0 auto !important;
    width: 2.25rem !important;
    height: 2.25rem !important;
    display: block !important;
  }}
  .skopos-brand-text {{
    display: flex !important;
    flex-direction: column !important;
    gap: 0.28rem !important;
    min-width: 0 !important;
    flex: 1 1 auto !important;
    overflow: hidden !important;
  }}
  .skopos-sidebar-title {{
    display: block !important;
    font-family: 'Sora', 'Outfit', system-ui, sans-serif !important;
    font-size: 0.98rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.2 !important;
    color: {th.text} !important;
    white-space: nowrap !important;
  }}
  .skopos-sidebar-tagline {{
    display: block !important;
    font-family: 'Outfit', system-ui, sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 400 !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.45 !important;
    color: {th.text_muted} !important;
    opacity: 1 !important;
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
    hyphens: auto !important;
  }}
  html.skopos-sidebar-collapsed .skopos-brand-text,
  html.skopos-sidebar-collapsed .skopos-sidebar-title,
  html.skopos-sidebar-collapsed .skopos-sidebar-tagline {{
    display: none !important;
  }}
  html.skopos-sidebar-collapsed .skopos-brand-row {{
    justify-content: center !important;
  }}
  html.skopos-sidebar-collapsed .skopos-logo-mark {{
    width: 2rem !important;
    height: 2rem !important;
  }}
  .skopos-sidebar-divider {{
    height: 1px;
    margin: 0.65rem 0 0.85rem;
    background: {th.border};
  }}

  @media (min-width: 769px) {{
    html.skopos-sidebar-expanded section[data-testid="stSidebar"],
    html.skopos-sidebar-expanded section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div {{
      width: var(--skopos-sidebar-expanded-width) !important;
      min-width: var(--skopos-sidebar-expanded-width) !important;
      max-width: var(--skopos-sidebar-expanded-width) !important;
      transform: none !important;
      visibility: visible !important;
      pointer-events: auto !important;
    }}
  }}

  html.skopos-sidebar-collapsed .skopos-sidebar-divider {{
    display: none !important;
  }}

  /* Collapsed: narrow icon rail */
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"],
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] > div {{
    width: var(--skopos-sidebar-collapsed) !important;
    min-width: var(--skopos-sidebar-collapsed) !important;
    max-width: var(--skopos-sidebar-collapsed) !important;
    padding-left: 0.35rem !important;
    padding-right: 0.35rem !important;
  }}

  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{
    justify-content: center !important;
    padding-left: 0.35rem !important;
    padding-right: 0.35rem !important;
  }}

  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] p,
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] a > span:not(:has(svg)) {{
    display: none !important;
  }}

  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active {{
    background: {th.accent} !important;
    color: #ffffff !important;
    border-radius: 50% !important;
    width: 2.5rem !important;
    height: 2.5rem !important;
    min-height: 2.5rem !important;
    padding: 0 !important;
    margin: 0.2rem auto !important;
    box-shadow: 0 4px 14px color-mix(in srgb, {th.accent} 40%, transparent) !important;
  }}
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active [data-testid="stIconMaterial"],
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active svg {{
    color: #ffffff !important;
    fill: #ffffff !important;
  }}
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] [data-testid="stIconMaterial"],
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stPageLink"] svg {{
    display: inline-flex !important;
    font-size: 1.15rem !important;
    width: 1.15rem !important;
    height: 1.15rem !important;
    margin: 0 !important;
    flex-shrink: 0 !important;
  }}

  /* Hide page-specific sidebar widgets in icon-rail mode */
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stSelectbox"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stMultiSelect"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stSlider"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stCheckbox"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stToggle"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stTextInput"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stNumberInput"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stExpander"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stAlert"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stRadio"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has(.sec-score-ring),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stCaptionContainer"]),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has([data-testid="stMarkdownContainer"] h3),
  html.skopos-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="element-container"]:has(hr) {{
    display: none !important;
  }}
</style>
<script>
(function() {{
  try {{
    var mobile = window.matchMedia("(max-width: 768px)").matches;
    if (mobile) return;
    document.documentElement.classList.remove("skopos-sidebar-collapsed");
    document.documentElement.classList.add("skopos-sidebar-expanded");
    localStorage.setItem("skopos-sidebar-collapsed", "0");
  }} catch (e) {{}}
}})();
</script>
"""
