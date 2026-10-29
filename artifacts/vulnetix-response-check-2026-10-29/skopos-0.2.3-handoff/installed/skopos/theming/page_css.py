"""CSS for the security page and full-screen charts."""

from __future__ import annotations

from .catalog import Theme


def build_security_css(theme: Theme) -> str:
    th = theme
    return f"""
<style>
  .sec-score-ring {{
    text-align: center;
    padding: 1rem 0.5rem;
    border-radius: 16px;
    background: {th.sec_ring_bg};
    border: 1px solid {th.sec_ring_border};
    margin-bottom: 0.75rem;
    box-shadow: {th.card_shadow};
  }}
  .sec-score-value {{
    font-size: 2.5rem;
    font-weight: 800;
    line-height: 1;
  }}
  .sec-score-grade {{
    font-size: 1.1rem;
    font-weight: 600;
    opacity: 0.85;
  }}
  .sec-alert-critical {{
    background: {th.sec_alert_crit_bg};
    border-left: 4px solid #EA4335;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 0.5rem;
    color: {th.text};
  }}
  .sec-alert-high {{
    background: {th.sec_alert_high_bg};
    border-left: 4px solid #FF6D00;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 0.5rem;
    color: {th.text};
  }}
  .sec-alert-medium {{
    background: {th.sec_alert_med_bg};
    border-left: 4px solid #FBBC04;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 0.5rem;
    color: {th.text};
  }}
  .sec-remark {{
    font-size: 0.9rem;
    color: {th.sec_remark};
    padding: 0.5rem 0;
    border-bottom: 1px solid {th.border};
  }}
  .sec-alert-counts {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }}
  .sec-count-pill {{
    flex: 1;
    min-width: 0;
    text-align: center;
    padding: 0.55rem 0.35rem;
    border-radius: 10px;
    border: 1px solid transparent;
  }}
  .sec-count-num {{
    display: block;
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1.1;
  }}
  .sec-count-label {{
    display: block;
    margin-top: 0.15rem;
    font-size: 0.62rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    line-height: 1.2;
    opacity: 0.85;
  }}
  .sec-count-critical {{
    background: {th.sec_crit_bg};
    border-color: {th.sec_crit_border};
    color: {th.sec_crit_text};
  }}
  .sec-count-high {{
    background: {th.sec_high_bg};
    border-color: {th.sec_high_border};
    color: {th.sec_high_text};
  }}
</style>
"""


def build_fullscreen_chart_css(theme: Theme) -> str:
    """Hide app chrome and card frames so a 3D chart fills the viewport."""
    th = theme
    scene_bg = th.globe_scene_bg
    return f"""
<style>
  section[data-testid="stSidebar"] {{ display: none !important; }}
  header[data-testid="stHeader"] {{ display: none !important; }}
  [data-testid="stToolbar"] {{ display: none !important; }}
  [data-testid="stDecoration"] {{ display: none !important; }}
  .stApp {{
    background: {th.app_bg} !important;
  }}
  .stApp:has(.skopos-fs-marker) .main .block-container {{
    padding: 0 !important;
    max-width: 100% !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlock"]:not(:has(.skopos-fs-marker)) {{
    display: none !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) {{
    position: fixed !important;
    inset: 0 !important;
    z-index: 8000 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    border-radius: 0 !important;
    background: {th.app_bg} !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    transform: none !important;
    overflow: hidden !important;
    max-height: 100vh !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker):hover {{
    box-shadow: none !important;
    transform: none !important;
    border-color: transparent !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) > div > [data-testid="stHorizontalBlock"]:first-child {{
    display: none !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) [data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) {{
    position: fixed !important;
    top: 0.75rem !important;
    right: 0.85rem !important;
    left: auto !important;
    width: auto !important;
    min-width: 11rem !important;
    z-index: 9010 !important;
    margin: 0 !important;
    padding: 0 !important;
    pointer-events: none !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) [data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) [data-testid="column"],
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) [data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) [data-testid="stButton"],
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) [data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) button {{
    pointer-events: auto !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .stPlotlyChart {{
    margin: 0 !important;
    min-height: 100vh !important;
    padding-top: 3.25rem !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .stPlotlyChart > div,
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .stPlotlyChart iframe {{
    height: calc(100vh - 3.25rem) !important;
    min-height: calc(100vh - 3.25rem) !important;
    border: none !important;
    border-radius: 0 !important;
    background: {scene_bg} !important;
  }}
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .js-plotly-plot,
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .plotly,
  .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .user-select-none {{
    background: {scene_bg} !important;
  }}
  @media (max-width: 768px) {{
    .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) [data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) {{
      top: 0.55rem !important;
      right: 0.55rem !important;
      min-width: 9.5rem !important;
    }}
    .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .stPlotlyChart {{
      padding-top: 3.75rem !important;
    }}
    .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .stPlotlyChart > div,
    .stApp:has(.skopos-fs-marker) .main [data-testid="stVerticalBlockBorderWrapper"]:has(.skopos-fs-marker) .stPlotlyChart iframe {{
      height: calc(100vh - 3.75rem) !important;
      min-height: calc(100vh - 3.75rem) !important;
    }}
  }}
</style>
"""
