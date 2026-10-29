"""CSS for widgets and the agent widget."""

from __future__ import annotations

from .catalog import is_light_theme, Theme


def _agent_widget_selector() -> str:
    """Target only the innermost Streamlit block that hosts the floating agent."""
    return (
        'section.main div[data-testid="stVerticalBlock"]'
        ":has(> div.element-container:has(.stats-agent-anchor))"
        ':not(:has(> div.element-container > div[data-testid="stVerticalBlock"]'
        ":has(> div.element-container:has(.stats-agent-anchor))))"
    )


def _widget_palette(theme: Theme) -> dict[str, str]:
    """Shared input/dropdown/alert colors for app shell and portaled overlays."""
    light_ui = is_light_theme(theme.id)
    th = theme
    if theme.id == "premium":
        chip_bg = "rgba(184,134,11,0.14)"
        chip_text = "#8a6914"
    elif theme.id == "midnight":
        chip_bg = "rgba(255,140,42,0.16)"
        chip_text = "#ffd56a"
    elif theme.id == "aurora":
        chip_bg = "rgba(124,77,255,0.18)"
        chip_text = "#b388ff"
    elif theme.id == "ocean":
        chip_bg = "rgba(38,198,218,0.16)"
        chip_text = "#4dd0e1"
    elif theme.id == "forest":
        chip_bg = "rgba(102,187,106,0.16)"
        chip_text = "#81c784"
    elif theme.id == "rose":
        chip_bg = "rgba(236,64,122,0.16)"
        chip_text = "#f48fb1"
    elif light_ui:
        chip_bg = "#e8f0fe" if theme.id == "light" else "rgba(84,110,122,0.12)"
        chip_text = "#1967d2" if theme.id == "light" else "#455a64"
    else:
        chip_bg = "rgba(88,166,255,0.18)"
        chip_text = "#58a6ff"

    if light_ui:
        widget_bg = "#ffffff"
        input_inset_bg = "#ffffff"
        input_inset_border = "rgba(0,0,0,0.22)"
    elif theme.id == "midnight":
        widget_bg = "rgba(18,12,22,0.92)"
        input_inset_bg = "rgba(255,244,232,0.10)"
        input_inset_border = "rgba(255,160,80,0.55)"
    elif theme.id == "aurora":
        widget_bg = "rgba(16,10,28,0.92)"
        input_inset_bg = "rgba(237,231,246,0.10)"
        input_inset_border = "rgba(124,77,255,0.55)"
    else:
        widget_bg = "#1c2128"
        input_inset_bg = "rgba(255,255,255,0.08)"
        input_inset_border = th.border if th.border else "rgba(88,166,255,0.45)"
    return {
        "widget_bg": widget_bg,
        "input_inset_bg": input_inset_bg,
        "input_inset_border": input_inset_border,
        "widget_text": th.text,
        "widget_border": "rgba(0,0,0,0.10)" if light_ui else th.border,
        "widget_muted": th.text_muted,
        "chip_bg": chip_bg,
        "chip_text": chip_text,
        "menu_shadow": "0 4px 16px rgba(60,64,67,0.16)" if light_ui else "0 8px 24px rgba(0,0,0,0.45)",
        "alert_info_bg": chip_bg if light_ui else "rgba(88,166,255,0.12)",
        "alert_info_text": chip_text if light_ui else th.accent,
        "alert_success_bg": "#e6f4ea" if light_ui else "rgba(63,185,80,0.14)",
        "alert_success_text": "#137333" if light_ui else th.accent2,
        "alert_warning_bg": th.sec_high_bg,
        "alert_warning_text": th.sec_high_text,
        "alert_error_bg": th.sec_crit_bg,
        "alert_error_text": th.sec_crit_text,
        "table_header_bg": th.metric_bg,
        "table_row_hover": chip_bg,
    }


def build_widget_css(theme: Theme) -> str:
    """Native Streamlit widgets not fully covered by shell/portal CSS."""
    th = theme
    pal = _widget_palette(theme)
    widget_bg = pal["widget_bg"]
    widget_text = pal["widget_text"]
    widget_border = pal["widget_border"]
    widget_muted = pal["widget_muted"]
    chip_bg = pal["chip_bg"]
    chip_text = pal["chip_text"]
    toggle_on = th.accent
    slider_fill = th.accent
    return f"""
<style id="stats-widget-theme">
  /* Radio & checkbox */
  .stApp [data-testid="stRadio"] label,
  .stApp [data-testid="stRadio"] [role="radiogroup"] label,
  .stApp [data-testid="stCheckbox"] label,
  .stApp [data-testid="stCheckbox"] span,
  .stApp [data-testid="stToggle"] label,
  .stApp [data-testid="stToggle"] span,
  .stApp [data-testid="stToggle"] p {{
    color: {widget_text} !important;
  }}

  .stApp [data-testid="stRadio"] [data-baseweb="radio"] svg,
  .stApp [data-testid="stCheckbox"] [data-baseweb="checkbox"] svg {{
    fill: {toggle_on} !important;
  }}

  /* Toggle track */
  .stApp [data-testid="stToggle"] [data-baseweb="toggle"] > div {{
    background-color: {th.progress_track} !important;
  }}
  .stApp [data-testid="stToggle"] [data-baseweb="toggle"][aria-checked="true"] > div {{
    background-color: {toggle_on} !important;
  }}

  /* Slider */
  .stApp [data-testid="stSlider"] label,
  .stApp [data-testid="stSlider"] [data-testid="stTickBarMin"],
  .stApp [data-testid="stSlider"] [data-testid="stTickBarMax"] {{
    color: {widget_muted} !important;
  }}
  .stApp [data-testid="stSlider"] [data-baseweb="slider"] div[data-testid="stThumbValue"] {{
    color: {widget_text} !important;
    background-color: {widget_bg} !important;
    border: 1px solid {widget_border} !important;
  }}
  .stApp [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
    background: {slider_fill} !important;
  }}
  .stApp [data-testid="stSlider"] [data-baseweb="slider"] > div > div {{
    background: {th.progress_track} !important;
  }}

  /* Number input steppers */
  .stApp [data-testid="stNumberInput"] label {{
    color: {widget_text} !important;
  }}
  .stApp [data-testid="stNumberInput"] input {{
    color: {widget_text} !important;
    background-color: {widget_bg} !important;
  }}
  .stApp [data-testid="stNumberInput"] button {{
    background-color: {widget_bg} !important;
    color: {widget_text} !important;
    border-color: {widget_border} !important;
  }}

  /* Date / time triggers */
  .stApp [data-testid="stDateInput"] label,
  .stApp [data-testid="stTimeInput"] label {{
    color: {widget_text} !important;
  }}
  .stApp [data-testid="stDateInput"] input,
  .stApp [data-testid="stTimeInput"] input {{
    color: {widget_text} !important;
    background-color: {widget_bg} !important;
  }}

  /* Alerts — base card surface */
  .stApp [data-testid="stAlert"],
  section[data-testid="stSidebar"] [data-testid="stAlert"] {{
    background-color: {th.card_bg} !important;
    color: {widget_text} !important;
    border: 1px solid {th.card_border} !important;
    border-radius: 10px !important;
  }}
  .stApp [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
  .stApp [data-testid="stAlert"] [data-testid="stMarkdownContainer"] span,
  section[data-testid="stSidebar"] [data-testid="stAlert"] p {{
    color: inherit !important;
  }}

  /* Alert variants (override base) */
  .stApp [data-testid="stAlert"]:has(svg[aria-label="Info"]) {{
    background-color: {pal["alert_info_bg"]} !important;
    color: {pal["alert_info_text"]} !important;
  }}
  .stApp [data-testid="stAlert"]:has(svg[aria-label="Success"]) {{
    background-color: {pal["alert_success_bg"]} !important;
    color: {pal["alert_success_text"]} !important;
  }}
  .stApp [data-testid="stAlert"]:has(svg[aria-label="Warning"]) {{
    background-color: {pal["alert_warning_bg"]} !important;
    color: {pal["alert_warning_text"]} !important;
  }}
  .stApp [data-testid="stAlert"]:has(svg[aria-label="Error"]) {{
    background-color: {pal["alert_error_bg"]} !important;
    color: {pal["alert_error_text"]} !important;
  }}

  /* Dataframes */
  .stApp [data-testid="stDataFrame"],
  .stApp [data-testid="stDataFrame"] [data-testid="stTable"] {{
    background-color: {th.card_bg} !important;
    border: 1px solid {th.card_border} !important;
  }}
  .stApp [data-testid="stDataFrame"] table {{
    color: {widget_text} !important;
  }}
  .stApp [data-testid="stDataFrame"] th {{
    background-color: {pal["table_header_bg"]} !important;
    color: {widget_text} !important;
    border-color: {widget_border} !important;
  }}
  .stApp [data-testid="stDataFrame"] td {{
    color: {widget_text} !important;
    border-color: {widget_border} !important;
    background-color: {th.card_bg} !important;
  }}
  .stApp [data-testid="stDataFrame"] tr:hover td {{
    background-color: {pal["table_row_hover"]} !important;
  }}

  /* Chat messages (agent widget) */
  .stApp [data-testid="stChatMessage"],
  .stApp [data-testid="stChatMessageContent"] {{
    background-color: {th.card_bg} !important;
    color: {widget_text} !important;
    border: 1px solid {th.card_border} !important;
  }}

  /* Spinner / progress — large enough to see in the empty analytics well */
  .stApp [data-testid="stSpinner"] {{
    color: {th.accent} !important;
    font-size: 1.05rem !important;
    min-height: 3.25rem !important;
    padding: 0.85rem 0.25rem !important;
  }}
  .stApp [data-testid="stSpinner"] svg {{
    width: 1.55rem !important;
    height: 1.55rem !important;
    stroke: {th.accent} !important;
  }}
  .stApp [data-testid="stProgress"] > div > div {{
    background-color: {th.accent} !important;
  }}
  .stApp [data-testid="stProgress"] > div {{
    background-color: {th.progress_track} !important;
  }}

  /* Page links in sidebar nav */
  .stApp [data-testid="stPageLink"] a,
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a {{
    color: {widget_text} !important;
  }}
  .stApp [data-testid="stPageLink"] a:hover,
  section[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{
    color: {th.accent} !important;
    background-color: {chip_bg} !important;
  }}

  /* Form submit area */
  .stApp [data-testid="stForm"] {{
    border-color: {th.card_border} !important;
  }}

  /* Text inputs — single inset border on inner shell only (avoid double frame) */
  .stApp div.element-container:has([data-testid="stTextInput"]),
  .stApp [data-testid="stTextInput"] {{
    overflow: visible !important;
    margin-bottom: 0.4rem !important;
    padding-bottom: 2px !important;
  }}
  .stApp [data-testid="stTextInput"] [data-baseweb="input"] {{
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    padding: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
  }}
  .stApp [data-testid="stTextInput"] [data-baseweb="input"] > div,
  .stApp [data-testid="stForm"] [data-testid="stTextInput"] [data-baseweb="input"] > div {{
    background-color: {pal["input_inset_bg"]} !important;
    border: 1.5px solid {pal["input_inset_border"]} !important;
    border-style: solid !important;
    border-width: 1.5px !important;
    min-height: 2.85rem !important;
    border-radius: 10px !important;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.12) !important;
    box-sizing: border-box !important;
    overflow: visible !important;
  }}
  .stApp [data-testid="stTextInput"] input,
  .stApp [data-testid="stForm"] [data-testid="stTextInput"] input {{
    color: {widget_text} !important;
    -webkit-text-fill-color: {widget_text} !important;
    caret-color: {widget_text} !important;
    background-color: transparent !important;
    min-height: 2.5rem !important;
    font-size: 1rem !important;
  }}
  .stApp [data-testid="stTextInput"] input::placeholder {{
    color: {widget_muted} !important;
    opacity: 1 !important;
  }}

  /* File uploader */
  .stApp [data-testid="stFileUploader"] section {{
    background-color: {widget_bg} !important;
    border-color: {widget_border} !important;
  }}
  .stApp [data-testid="stFileUploader"] label,
  .stApp [data-testid="stFileUploader"] small {{
    color: {widget_muted} !important;
  }}
</style>
"""


def build_agent_widget_css(theme: Theme) -> str:
    th = theme
    agent = _agent_widget_selector()
    fragment_root = (
        'section.main [data-testid="stFragment"]:has(.stats-agent-root), '
        'section.main div[data-testid="stVerticalBlock"]:has(.stats-agent-root)'
    )
    fab_host = (
        'section.main div.element-container:has(.stats-agent-fab-slot), '
        'section.main div.element-container:has(.stats-agent-fab-slot) + div.element-container, '
        'section.main [data-testid="stFragment"]:has(.stats-agent-fab-slot), '
        f'{fragment_root}:has(.stats-agent-root--closed)'
    )
    fab_btn = (
        'section.main [data-testid="stFragment"]:has(.stats-agent-anchor) [data-testid="stButton"] > button, '
        'section.main div.element-container:has(.stats-agent-fab-slot) + div.element-container [data-testid="stButton"] > button, '
        'section.main [data-testid="stFragment"]:has(.stats-agent-fab-slot) [data-testid="stButton"] > button, '
        f'{fragment_root}:has(.stats-agent-root--closed) [data-testid="stButton"] > button'
    )
    panel_host = (
        f'{agent}:has(.stats-agent-panel), '
        f'{fragment_root}:has(.stats-agent-panel), '
        'section.main div[data-testid="stVerticalBlock"]:has(.stats-agent-panel), '
        'section.main [data-testid="stFragment"]:has(.stats-agent-panel)'
    )
    return f"""
<style>
  /* Agent mount slot — zero layout footprint; never collapse page-level vertical blocks */
  section.main div.element-container:has(> .skopos-agent-mount),
  section.main div.element-container:has(> .skopos-agent-float-root) {{
    height: 0 !important;
    min-height: 0 !important;
    max-height: 0 !important;
    overflow: visible !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
  }}

  section.main div.element-container:has(> .stats-agent-fab-slot) {{
    display: none !important;
  }}

  section.main div.element-container:has(> .stats-agent-root) {{
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
  }}

  /* FAB — only the JS-tagged chat button (never broad :has() on page blocks) */
  button.skopos-agent-fab {{
    width: 3.5rem !important;
    height: 3.5rem !important;
    min-width: 3.5rem !important;
    min-height: 3.5rem !important;
    border-radius: 999px !important;
    padding: 0 !important;
    font-size: 0 !important;
    line-height: 0 !important;
    color: transparent !important;
    background: linear-gradient(145deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 27, 75, 0.95) 100%) !important;
    border: 1px solid rgba(34, 211, 238, 0.4) !important;
    box-shadow: 0 10px 32px rgba(8, 47, 73, 0.45) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease !important;
    position: fixed !important;
    bottom: 2rem !important;
    right: 1.25rem !important;
    left: auto !important;
    top: auto !important;
    z-index: 2147483646 !important;
    margin: 0 !important;
    pointer-events: auto !important;
  }}

  button.skopos-agent-fab::after {{
    content: "";
    position: absolute;
    inset: 0;
    margin: auto;
    width: 1.35rem;
    height: 1.35rem;
    background-repeat: no-repeat;
    background-position: center;
    background-size: contain;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2367e8f9' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7.9 20A9 9 0 1 0 4 16.1L2 22Z'/%3E%3C/svg%3E");
    pointer-events: none;
  }}

  button.skopos-agent-fab:hover {{
    transform: scale(1.05) !important;
    border-color: rgba(34, 211, 238, 0.65) !important;
    box-shadow: 0 14px 40px rgba(8, 47, 73, 0.55) !important;
  }}

  body > .skopos-agent-portal.skopos-agent-portal--open,
  {panel_host} {{
    position: fixed !important;
    bottom: 1.25rem !important;
    right: 1.25rem !important;
    left: auto !important;
    top: auto !important;
    z-index: 999999 !important;
    width: min(22rem, calc(100vw - 2.5rem)) !important;
    max-height: min(640px, calc(100vh - 2.5rem)) !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    background: rgba(2, 6, 23, 0.95) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 1rem !important;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.55) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    animation: statsAgentIn 0.22s ease-out;
    color: #e2e8f0 !important;
  }}

  @keyframes statsAgentIn {{
    from {{ opacity: 0; transform: translateY(12px) scale(0.96); }}
    to {{ opacity: 1; transform: translateY(0) scale(1); }}
  }}

  /* Legacy innermost-block — layout neutral; FAB uses button.skopos-agent-fab only */
  {agent}:not(:has(.stats-agent-panel)) {{
    width: auto !important;
    max-height: none !important;
    overflow: visible !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    animation: none !important;
  }}

  {agent}:has(.stats-agent-panel) > div.element-container:first-of-type {{
    display: none !important;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stHorizontalBlock"]:first-of-type {{
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding: 0.75rem 1rem 0.65rem;
    margin: 0 !important;
    align-items: center !important;
  }}

  {agent} .stats-agent-head-title {{
    font-size: 0.875rem;
    font-weight: 600;
    color: #fff;
    letter-spacing: -0.01em;
  }}

  {agent} .stats-agent-head-sub,
  {fragment_root} .stats-agent-head-sub {{
    font-size: 0.68rem;
    color: #94a3b8;
    margin-top: 0.15rem;
    line-height: 1.35;
  }}

  {agent} .stats-agent-intro,
  {fragment_root} .stats-agent-intro {{
    margin: 0 0.85rem 0.65rem;
    font-size: 0.75rem;
    line-height: 1.45;
    color: #64748b;
  }}

  {agent} .stats-agent-footnote,
  {fragment_root} .stats-agent-footnote {{
    margin: 0;
    font-size: 0.62rem;
    color: #64748b;
    line-height: 1.3;
  }}

  {fragment_root}:has(.stats-agent-root--open) [data-testid="stHorizontalBlock"]:first-of-type {{
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding: 0.65rem 0.75rem 0.5rem !important;
    margin: 0 !important;
    align-items: flex-start !important;
  }}

  {fragment_root}:has(.stats-agent-root--open) [data-testid="stExpander"],
  {fragment_root}:has(.stats-agent-root--open) [data-testid="stTextArea"],
  {fragment_root}:has(.stats-agent-root--open) [data-testid="stHorizontalBlock"] {{
    color: #e2e8f0 !important;
  }}

  {fragment_root}:has(.stats-agent-root--open) [data-testid="column"] {{
    padding: 0 0.15rem !important;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child [data-testid="stButton"] > button {{
    min-width: 2rem !important;
    width: 2rem !important;
    height: 2rem !important;
    min-height: 2rem !important;
    padding: 0 !important;
    border-radius: 0.5rem !important;
    background: transparent !important;
    color: #94a3b8 !important;
    border: none !important;
    font-size: 1rem !important;
    box-shadow: none !important;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child [data-testid="stButton"] > button:hover {{
    background: rgba(255, 255, 255, 0.08) !important;
    color: #fff !important;
  }}

  {agent}:has(.stats-agent-panel) [data-baseweb="select"] {{
    background: rgba(0, 0, 0, 0.25) !important;
    border-color: rgba(255, 255, 255, 0.12) !important;
    color: #cbd5e1 !important;
    font-size: 0.72rem !important;
    min-height: 2rem !important;
  }}

  {agent} .stats-agent-model {{
    margin: 0 1rem 0.35rem;
    font-size: 0.68rem;
    color: #64748b;
    line-height: 1.3;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stCaptionContainer"] {{
    padding: 0 1rem 0.35rem;
    color: #fbbf24 !important;
  }}

  {agent} .stats-agent-messages {{
    max-height: 18rem;
    overflow-y: auto;
    padding: 0.75rem 0.75rem 0.35rem;
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }}

  {agent} .stats-agent-row {{
    display: flex;
  }}

  {agent} .stats-agent-row--user {{
    justify-content: flex-end;
  }}

  {agent} .stats-agent-row--assistant {{
    justify-content: flex-start;
  }}

  {agent} .stats-agent-bubble {{
    max-width: 92%;
    border-radius: 0.75rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    line-height: 1.45;
    word-break: break-word;
  }}

  {agent} .stats-agent-bubble--user {{
    background: rgba(8, 145, 178, 0.35);
    color: #ecfeff;
    border: 1px solid rgba(34, 211, 238, 0.25);
  }}

  {agent} .stats-agent-bubble--assistant {{
    background: rgba(255, 255, 255, 0.06);
    color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }}

  {agent} .stats-agent-suggestions-label {{
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
    margin: 0.15rem 0.75rem 0.45rem;
  }}

  {agent}:has(.stats-agent-panel) .stats-agent-suggestions-label ~ div [data-testid="stButton"] > button {{
    border-radius: 999px !important;
    font-size: 0.68rem !important;
    padding: 0.4rem 0.6rem !important;
    min-height: 2rem !important;
    height: auto !important;
    white-space: normal !important;
    line-height: 1.25 !important;
    text-align: left !important;
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.14) !important;
    color: #cbd5e1 !important;
    box-shadow: none !important;
  }}

  {agent}:has(.stats-agent-panel) .stats-agent-suggestions-label ~ div [data-testid="stButton"] > button:hover {{
    background: rgba(255, 255, 255, 0.1) !important;
    color: #fff !important;
  }}

  {agent}:has(.stats-agent-footer) [data-testid="stTextArea"] {{
    border-top: 1px solid rgba(255, 255, 255, 0.1) !important;
    padding: 0.65rem 0.75rem 0.35rem !important;
    background: transparent !important;
  }}

  {agent}:has(.stats-agent-footer) [data-testid="stTextArea"] textarea {{
    background: rgba(0, 0, 0, 0.3) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 0.75rem !important;
    color: #fff !important;
    font-size: 0.875rem !important;
    min-height: 5.5rem !important;
    resize: none !important;
  }}

  {agent}:has(.stats-agent-footer) [data-testid="stTextArea"] textarea::placeholder {{
    color: #64748b !important;
  }}

  {agent}:has(.stats-agent-footer) [data-testid="stTextArea"] label {{
    display: none !important;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stButton"] > button[kind="primary"] {{
    margin: 0 0.75rem 0.5rem !important;
    border-radius: 0.5rem !important;
    background: rgba(8, 145, 178, 0.85) !important;
    border: none !important;
    color: #fff !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    min-height: 2.25rem !important;
    box-shadow: none !important;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stButton"] > button[kind="primary"]:hover {{
    background: rgba(34, 211, 238, 0.75) !important;
  }}

  {agent}:has(.stats-agent-panel) [data-testid="stButton"] > button[kind="secondary"] {{
    margin: 0 0.75rem 0.75rem !important;
    border-radius: 0.5rem !important;
    background: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: #94a3b8 !important;
    font-size: 0.72rem !important;
    min-height: 2rem !important;
    box-shadow: none !important;
  }}

  /* Portaled to body via agent_portal.js — selectors must not rely on section.main */
  body > .skopos-agent-portal.skopos-agent-portal--open {{
    background: rgba(2, 6, 23, 0.95) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 1rem !important;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.55) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    color: #e2e8f0 !important;
  }}

  body > .skopos-agent-portal.skopos-agent-portal--closed {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
  }}

  @media (max-width: 768px) {{
    {panel_host} {{
      width: calc(100vw - 1rem) !important;
      right: 0.5rem !important;
      left: 0.5rem !important;
      bottom: 0.5rem !important;
      max-height: calc(100vh - 1rem) !important;
    }}
    .skopos-agent-fab {{
      right: 0.75rem !important;
      bottom: 0.75rem !important;
    }}
    body > .skopos-agent-portal.skopos-agent-portal--open {{
      width: calc(100vw - 1rem) !important;
      right: 0.5rem !important;
      left: 0.5rem !important;
      bottom: 0.5rem !important;
      max-height: calc(100vh - 1rem) !important;
    }}
    body > .skopos-agent-portal.skopos-agent-portal--closed {{
      right: 0.75rem !important;
      bottom: 0.75rem !important;
    }}
  }}
</style>
"""
