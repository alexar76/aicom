"""Helios-inspired premium UI chrome — glass panels, glow shadows, cosmic atmosphere."""

from __future__ import annotations

from skopos.themes import Theme, _widget_palette, is_cosmic_theme, is_light_theme, theme_shell_bg


def _tokens(theme: Theme) -> dict[str, str]:
    """Design tokens aligned with helios/landing/index.html."""
    th = theme
    light = is_light_theme(theme.id)
    if theme.id == "premium":
        return {
            "panel": "rgba(255, 254, 249, 0.78)",
            "panel_border": "rgba(184, 134, 11, 0.28)",
            "tip_bg": "rgba(44, 36, 22, 0.94)",
            "tip_text": "#fff4e8",
            "tip_border": "rgba(255, 213, 106, 0.42)",
            "tip_shadow": "0 18px 48px rgba(44, 36, 22, 0.28), 0 0 0 1px rgba(255, 213, 106, 0.12)",
            "nebula": (
                "radial-gradient(42vw 42vw at 12% 8%, rgba(255, 140, 42, 0.10), transparent 62%),"
                "radial-gradient(38vw 38vw at 88% 14%, rgba(184, 134, 11, 0.08), transparent 58%),"
                "radial-gradient(55vw 55vw at 50% 100%, rgba(255, 213, 106, 0.05), transparent 55%)"
            ),
            "rays": "none",
            "stars": "none",
            "btn_primary": "linear-gradient(100deg, #c9920f, #ffd56a)",
            "btn_primary_text": "#1a0e04",
            "btn_primary_glow": "0 0 28px rgba(255, 140, 42, 0.35)",
            "btn_ghost": "rgba(255, 254, 249, 0.72)",
            "card_glow": "0 10px 40px rgba(44, 36, 22, 0.08)",
            "card_glow_hover": "0 16px 48px rgba(184, 134, 11, 0.16)",
        }
    if theme.id == "midnight":
        return {
            "panel": "rgba(18, 12, 22, 0.72)",
            "panel_border": "rgba(255, 160, 80, 0.22)",
            "tip_bg": "rgba(6, 5, 8, 0.96)",
            "tip_text": "#fff4e8",
            "tip_border": "rgba(255, 160, 80, 0.38)",
            "tip_shadow": "0 18px 48px rgba(0, 0, 0, 0.55), 0 0 28px rgba(255, 140, 42, 0.15)",
            "nebula": (
                "radial-gradient(50vw 50vw at 18% 12%, rgba(255, 140, 42, 0.18), transparent 62%),"
                "radial-gradient(44vw 44vw at 82% 20%, rgba(232, 74, 26, 0.12), transparent 60%),"
                "radial-gradient(60vw 60vw at 50% 100%, rgba(255, 213, 106, 0.07), transparent 55%)"
            ),
            "rays": (
                "conic-gradient(from 200deg at 14% 8%, transparent 0deg, rgba(255, 179, 71, 0.08) 18deg,"
                " transparent 36deg, rgba(255, 140, 42, 0.06) 52deg, transparent 70deg)"
            ),
            "stars": (
                "radial-gradient(1px 1px at 12% 18%, rgba(255,244,232,0.55), transparent),"
                "radial-gradient(1px 1px at 28% 72%, rgba(255,213,106,0.45), transparent),"
                "radial-gradient(1.5px 1.5px at 44% 34%, rgba(255,244,232,0.65), transparent),"
                "radial-gradient(1px 1px at 62% 12%, rgba(255,179,71,0.5), transparent),"
                "radial-gradient(1px 1px at 78% 58%, rgba(255,244,232,0.4), transparent),"
                "radial-gradient(1.5px 1.5px at 88% 28%, rgba(255,213,106,0.55), transparent),"
                "radial-gradient(1px 1px at 6% 88%, rgba(255,244,232,0.35), transparent),"
                "radial-gradient(1px 1px at 52% 92%, rgba(255,179,71,0.4), transparent),"
                "radial-gradient(1px 1px at 94% 82%, rgba(255,244,232,0.45), transparent),"
                "radial-gradient(1px 1px at 36% 48%, rgba(255,213,106,0.35), transparent)"
            ),
            "btn_primary": "linear-gradient(100deg, #ff8c2a, #ffd56a)",
            "btn_primary_text": "#1a0e04",
            "btn_primary_glow": "0 0 32px rgba(255, 140, 42, 0.42)",
            "btn_ghost": "rgba(18, 12, 22, 0.72)",
            "card_glow": "0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,160,80,0.08)",
            "card_glow_hover": "0 18px 52px rgba(0,0,0,0.55), 0 0 32px rgba(255,140,42,0.18)",
        }
    if theme.id == "aurora":
        return {
            "panel": "rgba(16, 10, 28, 0.72)",
            "panel_border": "rgba(124, 77, 255, 0.24)",
            "tip_bg": "rgba(8, 6, 18, 0.96)",
            "tip_text": "#ede7f6",
            "tip_border": "rgba(124, 77, 255, 0.38)",
            "tip_shadow": "0 18px 48px rgba(0, 0, 0, 0.55), 0 0 28px rgba(124, 77, 255, 0.18)",
            "nebula": (
                "radial-gradient(48vw 48vw at 16% 10%, rgba(124, 77, 255, 0.20), transparent 62%),"
                "radial-gradient(42vw 42vw at 84% 18%, rgba(105, 240, 174, 0.14), transparent 60%),"
                "radial-gradient(58vw 58vw at 50% 100%, rgba(179, 157, 219, 0.08), transparent 55%)"
            ),
            "rays": (
                "conic-gradient(from 210deg at 12% 6%, transparent 0deg, rgba(124, 77, 255, 0.10) 20deg,"
                " transparent 40deg, rgba(105, 240, 174, 0.08) 58deg, transparent 78deg)"
            ),
            "stars": (
                "radial-gradient(1px 1px at 10% 20%, rgba(237,231,246,0.50), transparent),"
                "radial-gradient(1px 1px at 30% 70%, rgba(179,157,219,0.45), transparent),"
                "radial-gradient(1.5px 1.5px at 48% 30%, rgba(105,240,174,0.55), transparent),"
                "radial-gradient(1px 1px at 66% 14%, rgba(237,231,246,0.40), transparent),"
                "radial-gradient(1px 1px at 82% 62%, rgba(124,77,255,0.45), transparent),"
                "radial-gradient(1.5px 1.5px at 90% 24%, rgba(105,240,174,0.50), transparent)"
            ),
            "btn_primary": "linear-gradient(100deg, #7c4dff, #69f0ae)",
            "btn_primary_text": "#120818",
            "btn_primary_glow": "0 0 32px rgba(124, 77, 255, 0.38)",
            "btn_ghost": "rgba(16, 10, 28, 0.72)",
            "card_glow": "0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px rgba(124,77,255,0.10)",
            "card_glow_hover": "0 18px 52px rgba(0,0,0,0.55), 0 0 32px rgba(124,77,255,0.20)",
        }
    if light:
        return {
            "panel": "rgba(255, 255, 255, 0.82)",
            "panel_border": "rgba(66, 133, 244, 0.18)",
            "tip_bg": "rgba(32, 33, 36, 0.94)",
            "tip_text": "#f8f9fa",
            "tip_border": "rgba(66, 133, 244, 0.35)",
            "tip_shadow": "0 16px 40px rgba(60, 64, 67, 0.22), 0 0 0 1px rgba(255, 255, 255, 0.08)",
            "nebula": (
                "radial-gradient(42vw 42vw at 14% 10%, rgba(66, 133, 244, 0.08), transparent 62%),"
                "radial-gradient(38vw 38vw at 86% 16%, rgba(52, 168, 83, 0.06), transparent 58%)"
            ),
            "rays": "none",
            "stars": "none",
            "btn_primary": f"linear-gradient(100deg, {th.accent}, #5a9bff)",
            "btn_primary_text": "#ffffff",
            "btn_primary_glow": "0 0 24px rgba(66, 133, 244, 0.32)",
            "btn_ghost": "rgba(255, 255, 255, 0.78)",
            "card_glow": "0 4px 24px rgba(60,64,67,0.06)",
            "card_glow_hover": "0 10px 36px rgba(66,133,244,0.12)",
        }
    return {
        "panel": "rgba(22, 27, 34, 0.82)",
        "panel_border": "rgba(88, 166, 255, 0.28)",
        "tip_bg": "rgba(13, 17, 23, 0.96)",
        "tip_text": "#e6edf3",
        "tip_border": "rgba(88, 166, 255, 0.38)",
        "tip_shadow": "0 18px 48px rgba(0, 0, 0, 0.48), 0 0 20px rgba(88, 166, 255, 0.12)",
        "nebula": (
            "radial-gradient(44vw 44vw at 14% 8%, rgba(88, 166, 255, 0.12), transparent 62%),"
            "radial-gradient(40vw 40vw at 86% 16%, rgba(63, 185, 80, 0.08), transparent 58%),"
            "radial-gradient(55vw 55vw at 50% 100%, rgba(88, 166, 255, 0.05), transparent 55%)"
        ),
        "rays": "none",
        "stars": "none",
        "btn_primary": f"linear-gradient(115deg, {th.accent}, {th.accent2})",
        "btn_primary_text": "#ffffff",
        "btn_primary_glow": "0 0 28px rgba(88, 166, 255, 0.35)",
        "btn_ghost": "rgba(22, 27, 34, 0.78)",
        "card_glow": "0 8px 32px rgba(0,0,0,0.35)",
        "card_glow_hover": "0 12px 40px rgba(88,166,255,0.15)",
    }


def build_premium_chrome_css(theme: Theme) -> str:
    th = theme
    tok = _tokens(theme)
    pal = _widget_palette(theme)
    cosmic = is_cosmic_theme(theme.id)
    rays_block = ""
    stars_block = ""
    if cosmic and tok["rays"] != "none":
        rays_block = f"""
  [data-testid="stAppViewContainer"]::after {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    opacity: 0.35;
    background: {tok["rays"]};
  }}
"""
    if cosmic and tok["stars"] != "none":
        stars_block = f"""
  .stApp::before {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    background-image: {tok["stars"]};
    background-size: 100% 100%;
    opacity: 0.7;
    animation: skoposStarTwinkle 8s ease-in-out infinite alternate;
  }}
  @keyframes skoposStarTwinkle {{
    from {{ opacity: 0.45; }}
    to   {{ opacity: 0.85; }}
  }}
"""
    hero_font = "'Cinzel', 'Sora', Georgia, serif" if cosmic else "'Sora', 'Outfit', system-ui, sans-serif"
    # One local stylesheet covers Outfit, Sora, Cinzel and the Material Symbols icon face, so
    # the cosmic variant no longer needs a conditional import — Cinzel is simply present and
    # only used when hero_font asks for it. Served by metis-nginx from /fonts/ on this host;
    # importing it from Google announced every operator's address to Google on each rerun.
    return f"""
<style id="skopos-premium-chrome">
  @import url('/fonts/fonts.css');

  .stApp,
  [data-testid="stAppViewContainer"],
  [data-testid="stMain"],
  section.main {{
    font-family: 'Outfit', system-ui, sans-serif !important;
  }}

  /* Cosmic void base (Helios landing) */
  [data-testid="stAppViewContainer"] {{
    background-color: {theme_shell_bg(th)} !important;
  }}

  /* Nebula atmosphere */
  [data-testid="stAppViewContainer"]::before {{
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    background: {tok["nebula"]};
    opacity: 0.95;
  }}
  {rays_block}
  {stars_block}
  [data-testid="stMain"],
  section[data-testid="stSidebar"] {{
    position: relative;
    z-index: 1;
  }}

  /* Hide Streamlit header strip — white bar artifact */
  header[data-testid="stHeader"] {{
    display: none !important;
    height: 0 !important;
    background: transparent !important;
    border: none !important;
  }}

  /* Kill native Streamlit chrome on desktop (keep stToolbar for Running… pill) */
  @media (min-width: 769px) {{
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"],
    [data-testid="stToolbarActions"],
    [data-testid="stToolbarAppName"],
    [data-testid="stMainMenu"],
    #MainMenu,
    button[kind="headerNoPadding"] {{
      display: none !important;
    }}
  }}
  @media (max-width: 768px) {{
    [data-testid="stToolbarActions"],
    [data-testid="stToolbarAppName"],
    [data-testid="stMainMenu"],
    #MainMenu,
    button[kind="headerNoPadding"] {{
      display: none !important;
    }}
  }}

  /* Glass cards & panels with depth */
  div[data-testid="stMetric"],
  div[data-testid="stVerticalBlockBorderWrapper"],
  .stApp [data-testid="stExpander"] details,
  .stApp [data-testid="stAlert"],
  section[data-testid="stSidebar"] [data-testid="stAlert"],
  .stApp [data-testid="stForm"],
  .stApp [data-testid="stChatMessage"],
  .stApp [data-testid="stChatMessageContent"] {{
    background: {tok["panel"]} !important;
    backdrop-filter: blur(14px) saturate(1.15) !important;
    -webkit-backdrop-filter: blur(14px) saturate(1.15) !important;
    border-color: {tok["panel_border"]} !important;
    box-shadow: {tok.get("card_glow", th.card_shadow)} !important;
    transition: transform 0.22s ease, box-shadow 0.28s ease, border-color 0.22s ease !important;
  }}
  div[data-testid="stMetric"]:hover,
  div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
    transform: translateY(-2px) !important;
    box-shadow: {tok.get("card_glow_hover", th.card_hover_shadow)} !important;
    border-color: color-mix(in srgb, {th.accent} 45%, transparent) !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlockBorderWrapper"],
  section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlockBorderWrapper"]:hover {{
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    padding: 0 !important;
    margin: 0 !important;
    transform: none !important;
  }}

  .hero-title {{
    font-family: {hero_font} !important;
    letter-spacing: 0.06em !important;
  }}

  /* Premium buttons */
  .stApp .stButton > button,
  .stApp button[data-testid="baseButton-secondary"] {{
    border-radius: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition:
      transform 0.15s ease,
      box-shadow 0.25s ease,
      border-color 0.2s ease,
      background 0.2s ease !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18) !important;
    background: {tok["btn_ghost"]} !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
  }}
  .stApp .stButton > button:hover,
  .stApp button[data-testid="baseButton-secondary"]:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28) !important;
    border-color: {th.accent} !important;
  }}
  .stApp .stButton > button:active,
  .stApp button[data-testid="baseButton-secondary"]:active {{
    transform: translateY(0) !important;
  }}
  .stApp button[kind="primary"],
  .stApp button[data-testid="baseButton-primary"] {{
    background: {tok["btn_primary"]} !important;
    color: {tok["btn_primary_text"]} !important;
    border: none !important;
    box-shadow: {tok["btn_primary_glow"]} !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
  }}
  .stApp button[kind="primary"]:hover,
  .stApp button[data-testid="baseButton-primary"]:hover {{
    transform: translateY(-2px) !important;
    filter: brightness(1.06) !important;
  }}

  /* Inputs — soft glass with focus glow */
  .stApp [data-baseweb="input"] > div,
  .stApp [data-baseweb="select"] > div,
  .stApp [data-baseweb="textarea"] > div,
  .stApp input,
  .stApp textarea {{
    border-radius: 12px !important;
    transition: box-shadow 0.2s ease, border-color 0.2s ease !important;
  }}
  .stApp [data-testid="stTextInput"] [data-baseweb="input"] {{
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    padding: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
  }}
  .stApp [data-testid="stTextInput"] [data-baseweb="input"] > div {{
    border: 1.5px solid {pal["input_inset_border"]} !important;
    border-style: solid !important;
    border-width: 1.5px !important;
    background-color: {pal["input_inset_bg"]} !important;
    min-height: 2.85rem !important;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.14) !important;
    box-sizing: border-box !important;
    overflow: visible !important;
  }}
  .stApp [data-testid="stTextInput"] input {{
    color: {pal["widget_text"]} !important;
    -webkit-text-fill-color: {pal["widget_text"]} !important;
    caret-color: {pal["widget_text"]} !important;
    background: transparent !important;
  }}
  .stApp [data-testid="stTextInput"] input::placeholder {{
    color: {pal["widget_muted"]} !important;
    opacity: 1 !important;
  }}
  .stApp [data-baseweb="input"] > div:focus-within,
  .stApp [data-baseweb="select"] > div:focus-within,
  .stApp [data-baseweb="textarea"] > div:focus-within {{
    box-shadow: 0 0 0 3px color-mix(in srgb, {th.accent} 24%, transparent), 0 8px 24px rgba(0,0,0,0.2) !important;
  }}

  /* Tabs — pill rail */
  div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 0.35rem !important;
    padding: 0.25rem !important;
    border-radius: 14px !important;
    background: {tok["panel"]} !important;
    border: 1px solid {tok["panel_border"]} !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 28px rgba(0,0,0,0.2) !important;
  }}
  div[data-testid="stTabs"] [data-baseweb="tab"] {{
    border-radius: 10px !important;
    transition: background 0.2s ease, color 0.2s ease !important;
  }}
  div[data-testid="stTabs"] [aria-selected="true"] {{
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2) !important;
  }}

  /* Status / rerun banner */
  [data-testid="stStatusWidget"],
  [data-testid="stConnectionStatus"] {{
    background: {tok["panel"]} !important;
    color: {th.text} !important;
    border-radius: 14px !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    border: 1px solid {tok["panel_border"]} !important;
    box-shadow: {th.card_shadow} !important;
    animation: skoposFadeUp 0.28s ease-out !important;
  }}
  [data-testid="stStatusWidget"] label,
  [data-testid="stStatusWidget"] span,
  [data-testid="stStatusWidget"] p,
  [data-testid="stStatusWidget"] div,
  [data-testid="stConnectionStatus"] label,
  [data-testid="stConnectionStatus"] span {{
    color: {th.text} !important;
  }}
  [data-testid="stStatusWidget"] button,
  [data-testid="stConnectionStatus"] button {{
    color: {th.text_muted} !important;
    background: transparent !important;
    border-color: {tok["panel_border"]} !important;
  }}

  /* Streamlit help-icon tooltips (BaseWeb portal) */
  [data-baseweb="tooltip"] > div,
  [data-baseweb="popover"] [data-baseweb="tooltip"] > div,
  [data-testid="stTooltip"] > div,
  [data-testid="stTooltip"] p {{
    background: {tok["tip_bg"]} !important;
    color: {tok["tip_text"]} !important;
    border: 1px solid {tok["tip_border"]} !important;
    border-radius: 12px !important;
    padding: 0.55rem 0.85rem !important;
    font-size: 0.82rem !important;
    line-height: 1.45 !important;
    font-family: 'Outfit', system-ui, sans-serif !important;
    box-shadow: {tok["tip_shadow"]} !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    animation: skoposTipIn 0.18s ease-out !important;
    max-width: 280px !important;
  }}

  /* Dropdown / select menus */
  [data-testid="stSelectboxVirtualDropdown"],
  [data-testid="stVirtualDropdown"],
  [data-testid="stMultiSelectVirtualDropdown"],
  div[data-baseweb="popover"] [data-baseweb="menu"] {{
    border-radius: 14px !important;
    backdrop-filter: blur(16px) saturate(1.1) !important;
    -webkit-backdrop-filter: blur(16px) saturate(1.1) !important;
    animation: skoposTipIn 0.16s ease-out !important;
    box-shadow: 0 16px 48px rgba(0,0,0,0.45) !important;
  }}

  /* Custom floating tooltip (replaces native title=) */
  .skopos-float-tip {{
    position: fixed;
    z-index: 10000000;
    pointer-events: none;
    max-width: 260px;
    padding: 0.55rem 0.9rem;
    border-radius: 12px;
    font-family: 'Outfit', system-ui, sans-serif;
    font-size: 0.82rem;
    font-weight: 500;
    line-height: 1.45;
    letter-spacing: 0.01em;
    color: {tok["tip_text"]};
    background: {tok["tip_bg"]};
    border: 1px solid {tok["tip_border"]};
    box-shadow: {tok["tip_shadow"]};
    backdrop-filter: blur(16px) saturate(1.2);
    -webkit-backdrop-filter: blur(16px) saturate(1.2);
    opacity: 0;
    transform: translateY(6px) scale(0.98);
    transition: opacity 0.16s ease, transform 0.16s ease;
  }}
  .skopos-float-tip.is-visible {{
    opacity: 1;
    transform: translateY(0) scale(1);
  }}

  @keyframes skoposTipIn {{
    from {{ opacity: 0; transform: translateY(8px) scale(0.98); }}
    to   {{ opacity: 1; transform: translateY(0) scale(1); }}
  }}
  @keyframes skoposFadeUp {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  /* Sidebar — glass edge + glow on active nav */
  section[data-testid="stSidebar"] {{
    border-right: 1px solid {tok["panel_border"]} !important;
    box-shadow: 8px 0 32px rgba(0,0,0,0.25) !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{
    border-radius: 12px !important;
    transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.22) !important;
    transform: translateX(2px) !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a.skopos-nav-active {{
    box-shadow: 0 0 20px color-mix(in srgb, {th.accent} 35%, transparent) !important;
  }}

  /* Security alert cards — glass, glow edge */
  .sec-alert-critical,
  .sec-alert-high,
  .sec-alert-medium {{
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border-radius: 12px !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.22) !important;
    transition: transform 0.2s ease, box-shadow 0.25s ease !important;
  }}
  .sec-alert-critical:hover,
  .sec-alert-high:hover,
  .sec-alert-medium:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 14px 36px rgba(0, 0, 0, 0.32) !important;
  }}

  .stTooltipIcon {{
    display: inline-flex !important;
    align-items: center !important;
  }}
  .stTooltipIcon [data-testid="stTooltipHoverTarget"] {{
    display: inline-flex !important;
  }}

  .theme-badge {{
    backdrop-filter: blur(8px) !important;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.18) !important;
  }}
</style>
"""


def build_premium_tooltip_js() -> str:
    """Replace ugly native title= tooltips with styled floating tips."""
    return """
<script id="skopos-premium-tooltips">
(function () {
  if (window.__skoposTipsReady) return;
  window.__skoposTipsReady = true;

  var tipEl = null;
  var hideTimer = null;

  function ensureTip() {
    if (!tipEl) {
      tipEl = document.createElement("div");
      tipEl.className = "skopos-float-tip";
      tipEl.setAttribute("role", "tooltip");
      document.body.appendChild(tipEl);
    }
    return tipEl;
  }

  function hijack(el) {
    if (!el || el.closest("[data-skopos-tip-ignore]")) return;
    var title = el.getAttribute("title");
    if (!title || !String(title).trim()) return;
    el.setAttribute("data-skopos-tip", String(title).trim());
    el.removeAttribute("title");
  }

  function scan(root) {
    var node = root || document.body;
    if (!node.querySelectorAll) return;
    node.querySelectorAll("[title]").forEach(hijack);
  }

  function place(target) {
    var tip = ensureTip();
    var rect = target.getBoundingClientRect();
    var tipRect = tip.getBoundingClientRect();
    var gap = 10;
    var top = rect.bottom + gap;
    var left = rect.left + (rect.width - tipRect.width) / 2;
    left = Math.max(10, Math.min(left, window.innerWidth - tipRect.width - 10));
    if (top + tipRect.height > window.innerHeight - 10) {
      top = rect.top - tipRect.height - gap;
    }
    tip.style.left = Math.round(left) + "px";
    tip.style.top = Math.round(top) + "px";
  }

  function show(target) {
    var text = target.getAttribute("data-skopos-tip");
    if (!text) return;
    clearTimeout(hideTimer);
    var tip = ensureTip();
    tip.textContent = text;
    tip.classList.add("is-visible");
    requestAnimationFrame(function () { place(target); });
  }

  function hide() {
    hideTimer = setTimeout(function () {
      if (tipEl) tipEl.classList.remove("is-visible");
    }, 60);
  }

  document.addEventListener("mouseover", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("[data-skopos-tip]") : null;
    if (t) show(t);
  }, true);

  document.addEventListener("mouseout", function (e) {
    var t = e.target && e.target.closest ? e.target.closest("[data-skopos-tip]") : null;
    if (!t) return;
    var rel = e.relatedTarget;
    if (!rel || !t.contains(rel)) hide();
  }, true);

  scan();
  function tagCollapsedNav() {
    var collapsed = document.documentElement.classList.contains("skopos-sidebar-collapsed");
    document.querySelectorAll('section[data-testid="stSidebar"] [data-testid="stPageLink"] a').forEach(function (a) {
      if (!collapsed) {
        a.removeAttribute("data-skopos-tip");
        return;
      }
      var label = a.getAttribute("aria-label") || "";
      if (!label) {
        var p = a.querySelector("p");
        if (p) label = p.textContent.trim();
      }
      if (label) a.setAttribute("data-skopos-tip", label);
    });
  }
  tagCollapsedNav();
  new MutationObserver(function () {
    tagCollapsedNav();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.hasAttribute && n.hasAttribute("title")) hijack(n);
        scan(n);
      });
    });
    tagCollapsedNav();
  }).observe(document.body, { childList: true, subtree: true });
})();
</script>
"""
