"""The main application stylesheet."""

from __future__ import annotations

from .catalog import is_light_theme, Theme, theme_shell_bg
from .widget_css import _widget_palette


def build_app_css(theme: Theme) -> str:
    th = theme
    light_ui = is_light_theme(theme.id)
    pal = _widget_palette(theme)
    widget_bg = pal["widget_bg"]
    widget_text = pal["widget_text"]
    widget_border = pal["widget_border"]
    widget_muted = pal["widget_muted"]
    button_bg = "#ffffff" if light_ui else "#21262d"
    button_text = th.text
    button_border = widget_border
    header_bg = "rgba(255,255,255,0.85)" if light_ui else "rgba(13,17,23,0.92)"
    chip_bg = pal["chip_bg"]
    chip_text = pal["chip_text"]
    code_bg = "#0f1419"
    code_text = "#e6edf3"
    if theme.id == "premium":
        inline_code_bg = "#f5efe3"
        inline_code_text = "#5c4a1f"
        inline_code_border = "rgba(184,134,11,0.28)"
    elif light_ui:
        inline_code_bg = "#e8f0fe"
        inline_code_text = "#174ea6"
        inline_code_border = "rgba(66,133,244,0.22)"
    else:
        inline_code_bg = "#21262d"
        inline_code_text = "#79c0ff"
        inline_code_border = th.border

    return f"""
<style>
  /* Local; metis-nginx serves /fonts/ on this host. See scripts/selfhost_google_fonts.py. */
  @import url('/fonts/fonts.css');

  .stApp,
  [data-testid="stAppViewContainer"],
  [data-testid="stMain"],
  section.main {{
    font-family: 'Outfit', system-ui, -apple-system, sans-serif;
    color: {th.text} !important;
    background-color: {theme_shell_bg(th)} !important;
    background-image: {th.app_bg} !important;
    transition: none !important;
  }}

  /* Legacy selector kept for older Streamlit builds */
  .stApp {{
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    color: {th.text};
    background-color: {theme_shell_bg(th)};
    background-image: {th.app_bg};
  }}

  header[data-testid="stHeader"] {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
  }}

  section[data-testid="stSidebar"] {{
    background: {th.sidebar_bg} !important;
    border-right: 1px solid {th.border};
  }}
  section[data-testid="stSidebar"] .stMarkdown,
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] span,
  section[data-testid="stSidebar"] small {{
    color: {th.text} !important;
  }}

  /* Hide Streamlit auto page list (English filenames); we render translated nav. */
  [data-testid="stSidebarNav"],
  [data-testid="stSidebarNav"] + div {{
    display: none !important;
  }}

  /* Streamlit deploy / ⋮ menu — SKOPOS uses sidebar + top bar */
  [data-testid="stToolbarActions"],
  [data-testid="stToolbarAppName"],
  [data-testid="stMainMenu"],
  #MainMenu {{
    display: none !important;
  }}

  /* Streamlit markdown / captions / labels */
  .stApp [data-testid="stMarkdownContainer"],
  .stApp [data-testid="stMarkdownContainer"] p,
  .stApp [data-testid="stMarkdownContainer"] li,
  .stApp [data-testid="stMarkdownContainer"] span,
  .stApp [data-testid="stMarkdownContainer"] h1,
  .stApp [data-testid="stMarkdownContainer"] h2,
  .stApp [data-testid="stMarkdownContainer"] h3,
  .stApp [data-testid="stMarkdownContainer"] h4,
  .stApp [data-testid="stMarkdownContainer"] h5,
  .stApp [data-testid="stMarkdownContainer"] h6,
  .stApp [data-testid="stCaptionContainer"],
  .stApp [data-testid="stCaptionContainer"] p,
  .stApp label[data-testid="stWidgetLabel"],
  .stApp label[data-testid="stWidgetLabel"] p {{
    color: {th.text} !important;
  }}

  .stApp [data-testid="stCaptionContainer"] p {{
    color: {th.text_muted} !important;
  }}

  /* Inputs, selects, multiselects — text fields use inset shell in build_widget_css */
  .stApp [data-baseweb="select"] > div,
  .stApp [data-baseweb="select"] div[data-baseweb="select"] > div,
  .stApp [data-baseweb="textarea"] > div,
  .stApp [data-baseweb="popover"] [data-baseweb="input"] > div,
  .stApp [data-baseweb="popover"] [data-baseweb="select"] > div {{
    background-color: {widget_bg} !important;
    color: {widget_text} !important;
    border-color: {widget_border} !important;
  }}

  /* Selectbox selected value (BaseWeb + React Aria combobox) */
  .stApp [data-testid="stSelectbox"] [data-baseweb="select"] > div,
  .stApp [data-testid="stSelectbox"] [data-baseweb="select"] span,
  .stApp [data-testid="stSelectbox"] input,
  .stApp [data-testid="stSelectbox"] [role="combobox"],
  section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
  section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] span,
  section[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
  section[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"] {{
    color: {widget_text} !important;
    -webkit-text-fill-color: {widget_text} !important;
    caret-color: {widget_text} !important;
    background-color: {widget_bg} !important;
    opacity: 1 !important;
  }}

  .stApp [data-baseweb="select"] span {{
    color: {widget_text} !important;
    -webkit-text-fill-color: {widget_text} !important;
  }}
  .stApp input, .stApp textarea {{
    color: {widget_text} !important;
    background-color: {widget_bg} !important;
  }}
  .stApp [data-testid="stTextInput"] input {{
    background-color: transparent !important;
  }}
  .stApp [data-baseweb="select"] svg {{
    fill: {widget_muted} !important;
  }}

  /* Multiselect chips */
  .stApp [data-baseweb="tag"] {{
    background-color: {chip_bg} !important;
    color: {chip_text} !important;
  }}

  /* Buttons */
  .stApp button[kind="secondary"],
  .stApp button[data-testid="baseButton-secondary"],
  .stApp .stButton > button {{
    background-color: {button_bg} !important;
    color: {button_text} !important;
    border: 1px solid {button_border} !important;
  }}
  .stApp button[kind="primary"],
  .stApp button[data-testid="baseButton-primary"] {{
    background-color: {th.accent} !important;
    color: #ffffff !important;
    border: none !important;
  }}

  /* Expanders */
  .stApp [data-testid="stExpander"] details {{
    background: {th.card_bg} !important;
    border: 1px solid {th.card_border} !important;
    border-radius: 12px !important;
  }}

  .block-container {{
    padding-top: 1rem !important;
    padding-bottom: 3rem !important;
    max-width: 1400px !important;
    margin-left: 0 !important;
    margin-right: auto !important;
  }}

  /* Quick Start — centered step rail */
  .skopos-wizard-steps {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: center;
    gap: 0.4rem 0.75rem;
    margin: 0.5rem 0 1rem;
    text-align: center;
  }}
  .skopos-wizard-step {{
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.82rem;
    font-weight: 500;
    color: {th.text_muted};
    padding: 0.28rem 0.65rem;
    border-radius: 999px;
    border: 1px solid transparent;
    background: transparent;
    white-space: nowrap;
  }}
  .skopos-wizard-step.is-done {{
    color: {th.accent2};
    border-color: color-mix(in srgb, {th.accent2} 35%, transparent);
    background: color-mix(in srgb, {th.accent2} 10%, transparent);
  }}
  .skopos-wizard-step.is-current {{
    color: {th.accent};
    font-weight: 700;
    border-color: color-mix(in srgb, {th.accent} 45%, transparent);
    background: color-mix(in srgb, {th.accent} 14%, transparent);
    box-shadow: 0 4px 16px color-mix(in srgb, {th.accent} 22%, transparent);
  }}
  .skopos-wizard-step.is-todo {{
    opacity: 0.72;
  }}

  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(18px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes fadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
  }}
  @keyframes glowPulse {{
    0%, 100% {{ opacity: 0.55; }}
    50%      {{ opacity: 1; }}
  }}
  @keyframes skoposSpin {{
    to {{ transform: rotate(360deg); }}
  }}
  .skopos-page-loading {{
    display: flex;
    align-items: center;
    gap: 0.9rem;
    min-height: 4.25rem;
    margin: 0.35rem 0 1rem;
    padding: 1rem 1.2rem;
    border-radius: 16px;
    border: 1px solid {th.card_border};
    background: {th.card_bg};
    color: {th.text};
    font-size: 1.05rem;
    font-weight: 600;
    box-shadow: {th.card_shadow};
  }}
  .skopos-page-loading-wheel {{
    width: 1.7rem;
    height: 1.7rem;
    flex: 0 0 1.7rem;
    border: 3px solid color-mix(in srgb, {th.accent} 28%, transparent);
    border-top-color: {th.accent};
    border-radius: 50%;
    animation: skoposSpin 0.7s linear infinite;
  }}
  .skopos-section-loading {{
    min-height: 3rem;
    margin: 0.25rem 0 0.35rem;
    padding: 0.65rem 0.85rem;
    box-shadow: none;
  }}
  .skopos-section-loading .skopos-page-loading-wheel {{
    width: 1.25rem;
    height: 1.25rem;
    flex-basis: 1.25rem;
  }}
  .skopos-cache-note {{
    display: inline-flex;
    align-items: center;
    margin: 0.1rem 0 0.7rem;
    padding: 0.45rem 0.7rem;
    border: 1px solid color-mix(in srgb, {th.accent2} 38%, transparent);
    border-radius: 999px;
    background: color-mix(in srgb, {th.accent2} 10%, {th.card_bg});
    color: {th.text_muted};
    font-size: 0.82rem;
    font-weight: 650;
  }}
  .skopos-cache-note--loading {{
    border-color: color-mix(in srgb, {th.accent} 38%, transparent);
    background: color-mix(in srgb, {th.accent} 10%, {th.card_bg});
  }}
  .skopos-dashboard-skeleton {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
  }}
  .skopos-dashboard-skeleton-card {{
    min-height: 17rem;
    padding: 1rem;
    border: 1px solid {th.card_border};
    border-radius: 16px;
    background: {th.card_bg};
    box-shadow: {th.card_shadow};
  }}
  .skopos-dashboard-skeleton-card:first-child {{
    grid-column: 1 / -1;
  }}
  .skopos-dashboard-skeleton-card span,
  .skopos-dashboard-skeleton-card i {{
    display: block;
    height: 0.8rem;
    margin-bottom: 1rem;
    border-radius: 999px;
    background: linear-gradient(90deg,
      color-mix(in srgb, {th.text_muted} 10%, transparent),
      color-mix(in srgb, {th.accent} 20%, transparent),
      color-mix(in srgb, {th.text_muted} 10%, transparent));
    background-size: 220% 100%;
    animation: skoposSkeleton 1.35s ease-in-out infinite;
  }}
  .skopos-dashboard-skeleton-card span {{ width: 42%; }}
  .skopos-dashboard-skeleton-card i {{ height: 5rem; margin-top: 2.1rem; }}
  .skopos-dashboard-skeleton-card i:last-child {{ height: 2.5rem; width: 74%; }}
  @keyframes skoposSkeleton {{
    from {{ background-position: 100% 0; }}
    to {{ background-position: -120% 0; }}
  }}
  @media (max-width: 800px) {{
    .skopos-dashboard-skeleton {{ grid-template-columns: 1fr; }}
    .skopos-dashboard-skeleton-card:first-child {{ grid-column: auto; }}
  }}

  /* Lazy dashboard rail. It looks like tabs, but unlike st.tabs only the
     selected section exists on the server. */
  .element-container:has(.skopos-lazy-tabs-marker) {{
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
  }}
  .element-container:has(.skopos-lazy-tabs-marker)
    + .element-container [data-testid="stRadio"] > div[role="radiogroup"] {{
    display: grid !important;
    grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
    gap: 0.5rem !important;
    width: 100%;
    padding: 0.35rem;
    margin: 0.25rem 0 1rem;
    border-radius: 15px;
    border: 1px solid {th.card_border};
    background: {th.card_bg};
    box-shadow: {th.card_shadow};
  }}
  .element-container:has(.skopos-lazy-tabs-marker)
    + .element-container [data-testid="stRadio"] label {{
    display: flex !important;
    justify-content: center;
    min-height: 2.75rem;
    margin: 0 !important;
    padding: 0.65rem 0.8rem !important;
    border: 1px solid {th.card_border};
    border-radius: 11px;
    background: color-mix(in srgb, {th.card_bg} 88%, transparent);
    cursor: pointer;
    transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
  }}
  .element-container:has(.skopos-lazy-tabs-marker)
    + .element-container [data-testid="stRadio"] label > div:first-child {{
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    opacity: 0 !important;
    pointer-events: none !important;
  }}
  .element-container:has(.skopos-lazy-tabs-marker)
    + .element-container [data-testid="stRadio"] label:has(input:checked) {{
    border-color: {th.accent};
    background: color-mix(in srgb, {th.accent} 18%, {th.card_bg});
    box-shadow: 0 5px 18px color-mix(in srgb, {th.accent} 20%, transparent);
  }}
  .element-container:has(.skopos-lazy-tabs-marker)
    + .element-container [data-testid="stRadio"] label:hover {{
    border-color: color-mix(in srgb, {th.accent} 70%, {th.card_border});
    transform: translateY(-1px);
  }}
  .element-container:has(.skopos-lazy-tabs-marker)
    + .element-container [data-testid="stRadio"] label p {{
    color: {th.text} !important;
    font-weight: 700 !important;
    text-align: center;
  }}

  .hero-title {{
    font-size: 2.1rem;
    font-weight: 700;
    font-family: 'Sora', 'Outfit', system-ui, sans-serif;
    letter-spacing: -0.02em;
    background: {th.hero_gradient};
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
  }}
  .hero-sub {{
    color: {th.text_muted};
    font-size: 0.95rem;
    margin-bottom: 1.5rem;
  }}

  .theme-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {th.text_muted};
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    border: 1px solid {th.border};
    background: {th.card_bg};
    margin-bottom: 0.75rem;
  }}

  div[data-testid="stMetric"] {{
    background: {th.metric_bg};
    border: 1px solid {th.metric_border};
    border-radius: 16px;
    padding: 1.25rem 1.5rem !important;
    box-shadow: {th.card_shadow};
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    backdrop-filter: blur(8px);
  }}
  div[data-testid="stMetric"]:hover {{
    transform: translateY(-3px);
    box-shadow: {th.card_hover_shadow};
  }}
  div[data-testid="stMetric"] label {{
    color: {th.metric_label} !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
    color: {th.metric_value} !important;
    font-size: 1.75rem !important;
    font-weight: 700 !important;
  }}

  div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 0.5rem;
    background: transparent;
    border-bottom: 2px solid {th.border};
    padding-bottom: 0;
  }}
  div[data-testid="stTabs"] [data-baseweb="tab"] {{
    padding: 0.75rem 1.25rem;
    font-weight: 500;
    border-radius: 8px 8px 0 0;
    color: {th.text_muted};
  }}
  div[data-testid="stTabs"] [aria-selected="true"] {{
    background: {th.tab_active_bg};
    color: {th.text} !important;
  }}

  .section-head {{
    font-size: 1.15rem;
    font-weight: 600;
    color: {th.text};
    margin: 2rem 0 1rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid transparent;
    border-image: {th.section_border} 1;
  }}

  div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 16px !important;
    border: 1px solid {th.card_border} !important;
    box-shadow: {th.card_shadow} !important;
    padding: 1.5rem !important;
    margin-bottom: 1.5rem !important;
    background: {th.card_bg} !important;
    transition: box-shadow 0.3s ease, transform 0.25s ease;
    backdrop-filter: blur(10px);
  }}
  div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
    box-shadow: {th.card_hover_shadow} !important;
  }}

  /* Sidebar expanders already have a card frame — drop nested border wrappers */
  section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlockBorderWrapper"] {{
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
    backdrop-filter: none !important;
    padding: 0 !important;
    margin: 0 !important;
    transform: none !important;
  }}
  section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlockBorderWrapper"]:hover {{
    box-shadow: none !important;
    transform: none !important;
    border-color: transparent !important;
  }}

  .stPlotlyChart {{
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
    min-height: 220px;
  }}
  div[data-testid="column"] .stPlotlyChart {{
    min-width: 160px;
  }}

  h1, h2, h3, h4, h5, h6, p, label {{
    color: {th.text} !important;
  }}

  /* Do not let global span styling break st.code / syntax highlighting */
  .stApp span {{
    color: inherit;
  }}
  .stApp [data-testid="stSelectbox"] span,
  section[data-testid="stSidebar"] [data-testid="stSelectbox"] span {{
    color: {widget_text} !important;
    -webkit-text-fill-color: {widget_text} !important;
  }}

  .stApp [data-testid="stCode"],
  .stApp [data-testid="stCodeBlock"],
  .stApp .stCode {{
    border-radius: 10px !important;
  }}
  .stApp [data-testid="stCode"] pre,
  .stApp [data-testid="stCode"] code,
  .stApp [data-testid="stCodeBlock"] pre,
  .stApp [data-testid="stCodeBlock"] code,
  .stApp .stCode pre,
  .stApp .stCode code {{
    background-color: {code_bg} !important;
    color: {code_text} !important;
    border: 1px solid {th.border} !important;
    font-size: 0.82rem !important;
    line-height: 1.45 !important;
  }}
  .stApp [data-testid="stCode"] pre *,
  .stApp [data-testid="stCode"] code *,
  .stApp [data-testid="stCodeBlock"] pre *,
  .stApp [data-testid="stCodeBlock"] code *,
  .stApp .stCode pre *,
  .stApp .stCode code * {{
    color: {code_text} !important;
  }}

  /* Fenced code blocks rendered via st.markdown (docs, help text). These are
     plain <pre><code> inside stMarkdownContainer and are NOT caught by the
     stCode rules above; without this the global `span {{ color: inherit }}`
     collapses Streamlit's syntax-highlight token colors to the page text
     color, leaving unreadable text on the dark code background. */
  .stApp [data-testid="stMarkdownContainer"] pre,
  .stApp [data-testid="stMarkdownContainer"] pre code {{
    background-color: {code_bg} !important;
    color: {code_text} !important;
    border-radius: 10px !important;
    font-size: 0.82rem !important;
    line-height: 1.45 !important;
  }}
  .stApp [data-testid="stMarkdownContainer"] pre {{
    border: 1px solid {th.border} !important;
    padding: 0.85rem 1rem !important;
  }}
  .stApp [data-testid="stMarkdownContainer"] pre code,
  .stApp [data-testid="stMarkdownContainer"] pre code * {{
    color: {code_text} !important;
    -webkit-text-fill-color: {code_text} !important;
    background: transparent !important;
    border: 0 !important;
  }}

  /* Inline `code` in markdown / expander labels (SSH host badges).
     Exclude fenced-block code: Streamlit nests it as pre>div>code, so the
     direct parent is a <div> (not <pre>) and a naive :not(pre) > code would
     wrongly paint the block <code> with the light inline background. */
  .stApp [data-testid="stMarkdownContainer"] :not(pre) > code:not(pre code),
  .stApp [data-testid="stExpander"] summary code,
  .stApp details[data-testid="stExpander"] summary code,
  .stApp [data-baseweb="accordion"] summary code {{
    background-color: {inline_code_bg} !important;
    color: {inline_code_text} !important;
    border: 1px solid {inline_code_border} !important;
    border-radius: 6px !important;
    padding: 0.12rem 0.45rem !important;
    font-size: 0.82em !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
  }}

  .stApp [data-testid="stException"],
  .stApp [data-testid="stException"] pre,
  .stApp [data-testid="stException"] code,
  .stApp [data-testid="stException"] p,
  .stApp [data-testid="stException"] span {{
    color: #3b1219 !important;
  }}

  .hero-sub, .sec-remark {{
    color: {th.text_muted} !important;
  }}

  .stDataFrame, [data-testid="stDataFrame"] {{
    border-radius: 12px;
    overflow: hidden;
  }}

  hr.section-divider {{
    border: none;
    height: 1px;
    background: {th.divider};
    margin: 2.5rem 0;
  }}

  /* Mobile-first responsive layout */
  @media (max-width: 768px) {{
    .hero-title {{ font-size: 1.55rem !important; }}
    .hero-sub {{ font-size: 0.92rem !important; }}
    div[data-testid="column"] {{
      min-width: 100% !important;
      flex: 1 1 100% !important;
    }}
    div[data-testid="stHorizontalBlock"] {{
      flex-wrap: wrap !important;
      gap: 0.5rem !important;
    }}
    div[data-testid="stTabs"] [data-baseweb="tab"] {{
      padding: 0.5rem 0.65rem !important;
      font-size: 0.82rem !important;
    }}
    .stPlotlyChart {{
      min-height: 280px !important;
    }}
    .sec-score-value {{ font-size: 2rem !important; }}
    .sec-alert-counts {{
      flex-wrap: wrap;
    }}
    .sec-count-pill {{
      flex: 1 1 45%;
    }}
    section[data-testid="stSidebar"] {{
      min-width: 280px;
    }}
    /* Do not force collapsed rail widths on mobile — drawer CSS owns this. */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
      padding: 1rem !important;
    }}
    div[data-testid="stSidebar"] .stButton > button,
    div[data-testid="stSidebar"] [data-testid="stPageLink"] a {{
      min-height: 44px;
    }}
    .main .block-container {{
      padding-left: 1rem !important;
      padding-right: 1rem !important;
      max-width: 100% !important;
    }}
    div[data-testid="stForm"] button {{
      min-height: 44px;
    }}
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input {{
      font-size: 16px !important;
    }}
  }}
  @media (max-width: 480px) {{
    .hero-title {{ font-size: 1.35rem !important; }}
    div[data-testid="stMetric"] {{
      padding: 0.35rem 0 !important;
    }}
    .sec-count-pill {{
      flex: 1 1 100%;
    }}
    section[data-testid="stSidebar"] {{
      min-width: 0 !important;
    }}
    .stButton > button {{
      min-height: 44px;
      width: 100%;
    }}
  }}
</style>
"""
