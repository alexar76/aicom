"""The theme catalogue: theme ids and families, each theme's palette, the order and default,
the active theme, and contrast checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ThemeId = Literal[
    "light",
    "dark",
    "premium",
    "midnight",
    "ocean",
    "forest",
    "slate",
    "rose",
    "aurora",
]

LIGHT_THEME_IDS: frozenset[str] = frozenset({"light", "premium", "slate"})
DARK_THEME_IDS: frozenset[str] = frozenset({"dark", "midnight", "ocean", "forest", "rose", "aurora"})
COSMIC_THEME_IDS: frozenset[str] = frozenset({"midnight", "aurora"})


@dataclass(frozen=True)
class Theme:
    id: ThemeId
    label_key: str
    icon: str
    # Shell
    app_bg: str
    sidebar_bg: str
    text: str
    text_muted: str
    accent: str
    accent2: str
    border: str
    # Cards & metrics
    card_bg: str
    card_border: str
    card_shadow: str
    card_hover_shadow: str
    metric_bg: str
    metric_border: str
    metric_label: str
    metric_value: str
    # Typography accents
    hero_gradient: str
    section_border: str
    tab_active_bg: str
    divider: str
    # Plotly
    plotly_template: str
    chart_paper_bg: str
    chart_plot_bg: str
    chart_font: str
    chart_grid: str
    chart_title: str
    # Globe
    globe_scene_bg: str
    globe_paper_bg: str
    globe_title: str
    # Security widgets
    sec_ring_bg: str
    sec_ring_border: str
    sec_ring_label: str
    sec_crit_bg: str
    sec_crit_border: str
    sec_crit_text: str
    sec_high_bg: str
    sec_high_border: str
    sec_high_text: str
    sec_alert_crit_bg: str
    sec_alert_high_bg: str
    sec_alert_med_bg: str
    sec_remark: str
    progress_track: str


THEMES: dict[ThemeId, Theme] = {
    "light": Theme(
        id="light",
        label_key="theme.light",
        icon="☀️",
        app_bg="linear-gradient(160deg, #f4f7fb 0%, #eef2f7 45%, #f8fafc 100%)",
        sidebar_bg="linear-gradient(180deg, #ffffff 0%, #f8faff 100%)",
        text="#202124",
        text_muted="#5f6368",
        accent="#4285F4",
        accent2="#34A853",
        border="rgba(66,133,244,0.12)",
        card_bg="#ffffff",
        card_border="rgba(0,0,0,0.06)",
        card_shadow="0 4px 24px rgba(60,64,67,0.06)",
        card_hover_shadow="0 10px 36px rgba(66,133,244,0.12)",
        metric_bg="linear-gradient(145deg, #ffffff 0%, #f8faff 100%)",
        metric_border="rgba(66,133,244,0.12)",
        metric_label="#5f6368",
        metric_value="#202124",
        hero_gradient="linear-gradient(135deg, #1a1a2e 0%, #4285F4 50%, #34A853 100%)",
        section_border="linear-gradient(90deg, #4285F4, #34A853)",
        tab_active_bg="linear-gradient(180deg, rgba(66,133,244,0.10) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, #dadce0, transparent)",
        plotly_template="plotly_white",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#202124",
        chart_grid="#eef0f2",
        chart_title="#202124",
        globe_scene_bg="rgba(4,8,20,1)",
        globe_paper_bg="rgba(4,8,20,0.95)",
        globe_title="#e8eaed",
        sec_ring_bg="linear-gradient(145deg, #f8faff 0%, #fff 100%)",
        sec_ring_border="rgba(66,133,244,0.15)",
        sec_ring_label="#5f6368",
        sec_crit_bg="#fce8e6",
        sec_crit_border="#f5c6c2",
        sec_crit_text="#c5221f",
        sec_high_bg="#fff3e0",
        sec_high_border="#ffe0b2",
        sec_high_text="#e65100",
        sec_alert_crit_bg="#fce8e6",
        sec_alert_high_bg="#fff3e0",
        sec_alert_med_bg="#fef7e0",
        sec_remark="#5f6368",
        progress_track="#e8eaed",
    ),
    "dark": Theme(
        id="dark",
        label_key="theme.dark",
        icon="🌙",
        app_bg="linear-gradient(165deg, #0d1117 0%, #121820 50%, #0f1419 100%)",
        sidebar_bg="linear-gradient(180deg, #161b22 0%, #0d1117 100%)",
        text="#e6edf3",
        text_muted="#9aa4b2",
        accent="#58a6ff",
        accent2="#3fb950",
        border="rgba(88,166,255,0.18)",
        card_bg="#161b22",
        card_border="rgba(48,54,61,0.9)",
        card_shadow="0 8px 32px rgba(0,0,0,0.35)",
        card_hover_shadow="0 12px 40px rgba(88,166,255,0.15)",
        metric_bg="linear-gradient(145deg, #1c2128 0%, #161b22 100%)",
        metric_border="rgba(88,166,255,0.2)",
        metric_label="#8b949e",
        metric_value="#f0f6fc",
        hero_gradient="linear-gradient(135deg, #58a6ff 0%, #79c0ff 45%, #3fb950 100%)",
        section_border="linear-gradient(90deg, #58a6ff, #3fb950)",
        tab_active_bg="linear-gradient(180deg, rgba(88,166,255,0.14) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, #30363d, transparent)",
        plotly_template="plotly_dark",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#e6edf3",
        chart_grid="#21262d",
        chart_title="#f0f6fc",
        globe_scene_bg="rgba(2,4,12,1)",
        globe_paper_bg="rgba(2,4,12,0.98)",
        globe_title="#e6edf3",
        sec_ring_bg="#161b22",
        sec_ring_border="rgba(88,166,255,0.22)",
        sec_ring_label="#9aa4b2",
        sec_crit_bg="rgba(248,81,73,0.15)",
        sec_crit_border="rgba(248,81,73,0.35)",
        sec_crit_text="#ff7b72",
        sec_high_bg="rgba(210,153,34,0.15)",
        sec_high_border="rgba(210,153,34,0.35)",
        sec_high_text="#e3b341",
        sec_alert_crit_bg="#2a1215",
        sec_alert_high_bg="#2a1f0e",
        sec_alert_med_bg="#252115",
        sec_remark="#9aa4b2",
        progress_track="#30363d",
    ),
    "premium": Theme(
        id="premium",
        label_key="theme.premium",
        icon="✨",
        app_bg="linear-gradient(155deg, #faf6ef 0%, #f3ebe0 40%, #efe4d4 100%)",
        sidebar_bg="linear-gradient(180deg, #fffdf8 0%, #f7f0e6 100%)",
        text="#2c2416",
        text_muted="#3d3528",
        accent="#b8860b",
        accent2="#1a6b4a",
        border="rgba(184,134,11,0.22)",
        card_bg="#fffef9",
        card_border="rgba(184,134,11,0.18)",
        card_shadow="0 10px 40px rgba(44,36,22,0.08), inset 0 1px 0 rgba(255,255,255,0.8)",
        card_hover_shadow="0 16px 48px rgba(184,134,11,0.16)",
        metric_bg="linear-gradient(145deg, #fffef9 0%, #f5efe3 100%)",
        metric_border="rgba(184,134,11,0.25)",
        metric_label="#3d3528",
        metric_value="#1a1408",
        hero_gradient="linear-gradient(135deg, #2c2416 0%, #b8860b 40%, #1a6b4a 100%)",
        section_border="linear-gradient(90deg, #b8860b, #1a6b4a)",
        tab_active_bg="linear-gradient(180deg, rgba(184,134,11,0.12) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, rgba(184,134,11,0.35), transparent)",
        plotly_template="plotly_white",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#1a1408",
        chart_grid="#b8a890",
        chart_title="#1a1408",
        globe_scene_bg="rgba(12,10,8,1)",
        globe_paper_bg="rgba(12,10,8,0.96)",
        globe_title="#f5efe3",
        sec_ring_bg="linear-gradient(145deg, #fffef9 0%, #f5efe3 100%)",
        sec_ring_border="rgba(184,134,11,0.28)",
        sec_ring_label="#3d3528",
        sec_crit_bg="rgba(183,28,28,0.1)",
        sec_crit_border="rgba(183,28,28,0.28)",
        sec_crit_text="#b71c1c",
        sec_high_bg="rgba(230,126,34,0.12)",
        sec_high_border="rgba(230,126,34,0.3)",
        sec_high_text="#c45c00",
        sec_alert_crit_bg="#fce8e6",
        sec_alert_high_bg="#fff3e0",
        sec_alert_med_bg="#fef7e0",
        sec_remark="#3d3528",
        progress_track="#ebe4d8",
    ),
    "midnight": Theme(
        id="midnight",
        label_key="theme.midnight",
        icon="🌌",
        app_bg="#060508",
        sidebar_bg="linear-gradient(180deg, rgba(14,10,18,0.96) 0%, rgba(6,5,8,0.98) 100%)",
        text="#fff4e8",
        text_muted="#c4a88a",
        accent="#ff8c2a",
        accent2="#ffd56a",
        border="rgba(255,160,80,0.22)",
        card_bg="rgba(18,12,22,0.78)",
        card_border="rgba(255,160,80,0.22)",
        card_shadow="0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,160,80,0.08), inset 0 1px 0 rgba(255,244,232,0.05)",
        card_hover_shadow="0 18px 52px rgba(0,0,0,0.55), 0 0 32px rgba(255,140,42,0.18), inset 0 1px 0 rgba(255,244,232,0.08)",
        metric_bg="linear-gradient(145deg, rgba(26,18,24,0.92) 0%, rgba(14,10,18,0.96) 100%)",
        metric_border="rgba(255,160,80,0.28)",
        metric_label="#c4a88a",
        metric_value="#fff4e8",
        hero_gradient="linear-gradient(95deg, #ffb347 0%, #ffd56a 45%, #fff4e8 100%)",
        section_border="linear-gradient(90deg, #ff8c2a, #ffd56a)",
        tab_active_bg="linear-gradient(180deg, rgba(255,140,42,0.16) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, rgba(255,160,80,0.35), transparent)",
        plotly_template="plotly_dark",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#fff4e8",
        chart_grid="#1a1218",
        chart_title="#ffd56a",
        globe_scene_bg="rgba(6,5,8,1)",
        globe_paper_bg="rgba(6,5,8,0.98)",
        globe_title="#fff4e8",
        sec_ring_bg="linear-gradient(145deg, rgba(26,18,24,0.95) 0%, rgba(14,10,18,0.98) 100%)",
        sec_ring_border="rgba(255,160,80,0.32)",
        sec_ring_label="#c4a88a",
        sec_crit_bg="rgba(232,74,26,0.16)",
        sec_crit_border="rgba(232,74,26,0.38)",
        sec_crit_text="#ffb4a0",
        sec_high_bg="rgba(255,140,42,0.14)",
        sec_high_border="rgba(255,140,42,0.35)",
        sec_high_text="#ffcc80",
        sec_alert_crit_bg="#2a1210",
        sec_alert_high_bg="#2a1a0e",
        sec_alert_med_bg="#1a1410",
        sec_remark="#c4a88a",
        progress_track="#1a1218",
    ),
    "ocean": Theme(
        id="ocean",
        label_key="theme.ocean",
        icon="🌊",
        app_bg="linear-gradient(165deg, #041018 0%, #061820 50%, #030c12 100%)",
        sidebar_bg="linear-gradient(180deg, #0a1c28 0%, #041018 100%)",
        text="#e0f7fa",
        text_muted="#80cbc4",
        accent="#26c6da",
        accent2="#4dd0e1",
        border="rgba(38,198,218,0.22)",
        card_bg="#0a1c28",
        card_border="rgba(38,198,218,0.18)",
        card_shadow="0 8px 32px rgba(0,0,0,0.4)",
        card_hover_shadow="0 12px 40px rgba(38,198,218,0.18)",
        metric_bg="linear-gradient(145deg, #0d2430 0%, #0a1c28 100%)",
        metric_border="rgba(38,198,218,0.24)",
        metric_label="#80cbc4",
        metric_value="#e0f7fa",
        hero_gradient="linear-gradient(135deg, #006064 0%, #26c6da 50%, #4dd0e1 100%)",
        section_border="linear-gradient(90deg, #00838f, #26c6da)",
        tab_active_bg="linear-gradient(180deg, rgba(38,198,218,0.14) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, #1a3a44, transparent)",
        plotly_template="plotly_dark",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#e0f7fa",
        chart_grid="#123040",
        chart_title="#b2ebf2",
        globe_scene_bg="rgba(2,8,16,1)",
        globe_paper_bg="rgba(2,8,16,0.98)",
        globe_title="#e0f7fa",
        sec_ring_bg="#0a1c28",
        sec_ring_border="rgba(38,198,218,0.28)",
        sec_ring_label="#80cbc4",
        sec_crit_bg="rgba(239,83,80,0.16)",
        sec_crit_border="rgba(239,83,80,0.38)",
        sec_crit_text="#ff8a80",
        sec_high_bg="rgba(255,183,77,0.14)",
        sec_high_border="rgba(255,183,77,0.35)",
        sec_high_text="#ffcc80",
        sec_alert_crit_bg="#1a1010",
        sec_alert_high_bg="#1a160e",
        sec_alert_med_bg="#101820",
        sec_remark="#80cbc4",
        progress_track="#123040",
    ),
    "forest": Theme(
        id="forest",
        label_key="theme.forest",
        icon="🌲",
        app_bg="linear-gradient(165deg, #0a120c 0%, #0e1810 50%, #081008 100%)",
        sidebar_bg="linear-gradient(180deg, #142018 0%, #0a120c 100%)",
        text="#e8f5e9",
        text_muted="#a5d6a7",
        accent="#66bb6a",
        accent2="#81c784",
        border="rgba(102,187,106,0.22)",
        card_bg="#142018",
        card_border="rgba(102,187,106,0.18)",
        card_shadow="0 8px 32px rgba(0,0,0,0.38)",
        card_hover_shadow="0 12px 40px rgba(102,187,106,0.16)",
        metric_bg="linear-gradient(145deg, #182820 0%, #142018 100%)",
        metric_border="rgba(102,187,106,0.24)",
        metric_label="#a5d6a7",
        metric_value="#e8f5e9",
        hero_gradient="linear-gradient(135deg, #1b5e20 0%, #66bb6a 50%, #a5d6a7 100%)",
        section_border="linear-gradient(90deg, #2e7d32, #66bb6a)",
        tab_active_bg="linear-gradient(180deg, rgba(102,187,106,0.14) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, #2a4030, transparent)",
        plotly_template="plotly_dark",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#e8f5e9",
        chart_grid="#1a3020",
        chart_title="#c8e6c9",
        globe_scene_bg="rgba(4,10,6,1)",
        globe_paper_bg="rgba(4,10,6,0.98)",
        globe_title="#e8f5e9",
        sec_ring_bg="#142018",
        sec_ring_border="rgba(102,187,106,0.28)",
        sec_ring_label="#a5d6a7",
        sec_crit_bg="rgba(239,83,80,0.16)",
        sec_crit_border="rgba(239,83,80,0.38)",
        sec_crit_text="#ff8a80",
        sec_high_bg="rgba(255,183,77,0.14)",
        sec_high_border="rgba(255,183,77,0.35)",
        sec_high_text="#ffcc80",
        sec_alert_crit_bg="#1a1010",
        sec_alert_high_bg="#1a160e",
        sec_alert_med_bg="#121810",
        sec_remark="#a5d6a7",
        progress_track="#1a3020",
    ),
    "slate": Theme(
        id="slate",
        label_key="theme.slate",
        icon="🪨",
        app_bg="linear-gradient(160deg, #eef1f5 0%, #e4e8ee 45%, #f0f2f5 100%)",
        sidebar_bg="linear-gradient(180deg, #f8f9fb 0%, #eef1f5 100%)",
        text="#1c2333",
        text_muted="#5c6578",
        accent="#546e7a",
        accent2="#78909c",
        border="rgba(84,110,122,0.18)",
        card_bg="#ffffff",
        card_border="rgba(28,35,51,0.08)",
        card_shadow="0 4px 20px rgba(28,35,51,0.06)",
        card_hover_shadow="0 10px 32px rgba(84,110,122,0.12)",
        metric_bg="linear-gradient(145deg, #ffffff 0%, #f4f6f8 100%)",
        metric_border="rgba(84,110,122,0.16)",
        metric_label="#5c6578",
        metric_value="#1c2333",
        hero_gradient="linear-gradient(135deg, #263238 0%, #546e7a 50%, #78909c 100%)",
        section_border="linear-gradient(90deg, #455a64, #78909c)",
        tab_active_bg="linear-gradient(180deg, rgba(84,110,122,0.10) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, #cfd8dc, transparent)",
        plotly_template="plotly_white",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#1c2333",
        chart_grid="#dfe3e8",
        chart_title="#1c2333",
        globe_scene_bg="rgba(18,24,32,1)",
        globe_paper_bg="rgba(18,24,32,0.96)",
        globe_title="#eceff1",
        sec_ring_bg="linear-gradient(145deg, #f8f9fb 0%, #fff 100%)",
        sec_ring_border="rgba(84,110,122,0.20)",
        sec_ring_label="#5c6578",
        sec_crit_bg="#ffebee",
        sec_crit_border="#ffcdd2",
        sec_crit_text="#c62828",
        sec_high_bg="#fff8e1",
        sec_high_border="#ffe082",
        sec_high_text="#ef6c00",
        sec_alert_crit_bg="#ffebee",
        sec_alert_high_bg="#fff8e1",
        sec_alert_med_bg="#f5f5f5",
        sec_remark="#5c6578",
        progress_track="#dfe3e8",
    ),
    "rose": Theme(
        id="rose",
        label_key="theme.rose",
        icon="🌹",
        app_bg="linear-gradient(165deg, #140810 0%, #1a0c14 50%, #100610 100%)",
        sidebar_bg="linear-gradient(180deg, #1e1018 0%, #140810 100%)",
        text="#fce4ec",
        text_muted="#f48fb1",
        accent="#ec407a",
        accent2="#f06292",
        border="rgba(236,64,122,0.24)",
        card_bg="#1e1018",
        card_border="rgba(236,64,122,0.20)",
        card_shadow="0 8px 32px rgba(0,0,0,0.42)",
        card_hover_shadow="0 12px 40px rgba(236,64,122,0.18)",
        metric_bg="linear-gradient(145deg, #241420 0%, #1e1018 100%)",
        metric_border="rgba(236,64,122,0.26)",
        metric_label="#f48fb1",
        metric_value="#fce4ec",
        hero_gradient="linear-gradient(135deg, #880e4f 0%, #ec407a 50%, #f8bbd0 100%)",
        section_border="linear-gradient(90deg, #ad1457, #ec407a)",
        tab_active_bg="linear-gradient(180deg, rgba(236,64,122,0.14) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, #3a2030, transparent)",
        plotly_template="plotly_dark",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#fce4ec",
        chart_grid="#281820",
        chart_title="#f8bbd0",
        globe_scene_bg="rgba(12,4,8,1)",
        globe_paper_bg="rgba(12,4,8,0.98)",
        globe_title="#fce4ec",
        sec_ring_bg="#1e1018",
        sec_ring_border="rgba(236,64,122,0.30)",
        sec_ring_label="#f48fb1",
        sec_crit_bg="rgba(239,83,80,0.16)",
        sec_crit_border="rgba(239,83,80,0.38)",
        sec_crit_text="#ff8a80",
        sec_high_bg="rgba(255,183,77,0.14)",
        sec_high_border="rgba(255,183,77,0.35)",
        sec_high_text="#ffcc80",
        sec_alert_crit_bg="#2a1018",
        sec_alert_high_bg="#2a1810",
        sec_alert_med_bg="#1a1018",
        sec_remark="#f48fb1",
        progress_track="#281820",
    ),
    "aurora": Theme(
        id="aurora",
        label_key="theme.aurora",
        icon="🌈",
        app_bg="#080612",
        sidebar_bg="linear-gradient(180deg, rgba(16,10,28,0.96) 0%, rgba(8,6,18,0.98) 100%)",
        text="#ede7f6",
        text_muted="#b39ddb",
        accent="#7c4dff",
        accent2="#69f0ae",
        border="rgba(124,77,255,0.24)",
        card_bg="rgba(16,10,28,0.82)",
        card_border="rgba(124,77,255,0.22)",
        card_shadow="0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px rgba(124,77,255,0.08)",
        card_hover_shadow="0 18px 52px rgba(0,0,0,0.55), 0 0 32px rgba(124,77,255,0.18)",
        metric_bg="linear-gradient(145deg, rgba(22,14,36,0.92) 0%, rgba(12,8,22,0.96) 100%)",
        metric_border="rgba(124,77,255,0.28)",
        metric_label="#b39ddb",
        metric_value="#ede7f6",
        hero_gradient="linear-gradient(95deg, #7c4dff 0%, #69f0ae 50%, #ede7f6 100%)",
        section_border="linear-gradient(90deg, #7c4dff, #69f0ae)",
        tab_active_bg="linear-gradient(180deg, rgba(124,77,255,0.16) 0%, transparent 100%)",
        divider="linear-gradient(90deg, transparent, rgba(124,77,255,0.35), transparent)",
        plotly_template="plotly_dark",
        chart_paper_bg="rgba(0,0,0,0)",
        chart_plot_bg="rgba(0,0,0,0)",
        chart_font="#ede7f6",
        chart_grid="#1a1028",
        chart_title="#b388ff",
        globe_scene_bg="rgba(8,6,18,1)",
        globe_paper_bg="rgba(8,6,18,0.98)",
        globe_title="#ede7f6",
        sec_ring_bg="linear-gradient(145deg, rgba(22,14,36,0.95) 0%, rgba(12,8,22,0.98) 100%)",
        sec_ring_border="rgba(124,77,255,0.32)",
        sec_ring_label="#b39ddb",
        sec_crit_bg="rgba(239,83,80,0.16)",
        sec_crit_border="rgba(239,83,80,0.38)",
        sec_crit_text="#ff8a80",
        sec_high_bg="rgba(255,183,77,0.14)",
        sec_high_border="rgba(255,183,77,0.35)",
        sec_high_text="#ffcc80",
        sec_alert_crit_bg="#1a1020",
        sec_alert_high_bg="#1a1820",
        sec_alert_med_bg="#121018",
        sec_remark="#b39ddb",
        progress_track="#1a1028",
    ),
}

THEME_ORDER: tuple[ThemeId, ...] = (
    "light",
    "slate",
    "premium",
    "dark",
    "ocean",
    "forest",
    "rose",
    "aurora",
    "midnight",
)
DEFAULT_THEME: ThemeId = "midnight"


def is_light_theme(theme_id: str) -> bool:
    return theme_id in LIGHT_THEME_IDS


def is_dark_theme(theme_id: str) -> bool:
    return theme_id in DARK_THEME_IDS


def is_cosmic_theme(theme_id: str) -> bool:
    return theme_id in COSMIC_THEME_IDS


def get_active_theme() -> Theme:
    try:
        import streamlit as st

        from skopos.theme_prefs import SKOPOS_THEME_KEY, SKOPOS_THEME_WIDGET

        theme_id = st.session_state.get(SKOPOS_THEME_KEY)
        if not theme_id or theme_id not in THEMES:
            theme_id = st.session_state.get(SKOPOS_THEME_WIDGET, DEFAULT_THEME)
        if theme_id not in THEMES and "app_theme_selector" in st.session_state:
            theme_id = st.session_state.app_theme_selector
        return THEMES.get(theme_id, THEMES[DEFAULT_THEME])
    except Exception:
        return THEMES[DEFAULT_THEME]


def theme_surface_bg(theme: Theme) -> str:
    """Solid surface color for contrast checks (card backgrounds)."""
    return {
        "light": "#ffffff",
        "dark": "#161b22",
        "premium": "#fffef9",
        "midnight": "#120c16",
        "ocean": "#0a1c28",
        "forest": "#142018",
        "slate": "#ffffff",
        "rose": "#1e1018",
        "aurora": "#100a1c",
    }[theme.id]


def theme_shell_bg(theme: Theme) -> str:
    """Solid app background for first paint (avoids flash on navigation)."""
    return {
        "light": "#f4f7fb",
        "dark": "#0d1117",
        "premium": "#faf8f3",
        "midnight": "#060508",
        "ocean": "#041018",
        "forest": "#0a120c",
        "slate": "#eef1f5",
        "rose": "#140810",
        "aurora": "#080612",
    }[theme.id]


def _theme_shell_colors() -> dict[str, str]:
    return {tid: theme_shell_bg(th) for tid, th in THEMES.items()}


def _theme_ids_json() -> str:
    import json

    return json.dumps(list(THEMES.keys()))


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG relative luminance contrast ratio."""

    def _lum(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

        def lin(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b = lin(r), lin(g), lin(b)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    l1, l2 = _lum(fg_hex), _lum(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def theme_label(theme: Theme, locale: str) -> str:
    from skopos.i18n import t

    return t(theme.label_key, locale)
