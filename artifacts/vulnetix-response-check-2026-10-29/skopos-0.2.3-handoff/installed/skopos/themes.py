"""Dashboard theme system — light, dark, premium, midnight."""

from __future__ import annotations


from .theming.catalog import (  # noqa: F401 - re-exported
    _theme_ids_json,
    _theme_shell_colors,
    contrast_ratio,
    COSMIC_THEME_IDS,
    DARK_THEME_IDS,
    DEFAULT_THEME,
    get_active_theme,
    is_cosmic_theme,
    is_dark_theme,
    is_light_theme,
    LIGHT_THEME_IDS,
    Theme,
    theme_label,
    THEME_ORDER,
    theme_shell_bg,
    theme_surface_bg,
    ThemeId,
    THEMES,
)
from .theming.charts import (  # noqa: F401 - re-exported
    _plotly_hover_bg,
    _plotly_hover_font,
    _PLOTLY_TEMPLATES_READY,
    apply_chart_axes,
    apply_chart_theme,
    chart_layout_kwargs,
    ensure_plotly_templates,
    plotly_hover_bg,
    plotly_hover_font,
    skopos_plotly_template,
)
from .theming.widget_css import (  # noqa: F401 - re-exported
    _agent_widget_selector,
    _widget_palette,
    build_agent_widget_css,
    build_widget_css,
)
from .theming.shell_css import (  # noqa: F401 - re-exported
    _build_theme_boot_script,
    _status_bar_palette,
    build_critical_shell_css,
    build_login_gate_css,
    build_portal_overlay_css,
    build_sidebar_layout_css,
    build_status_bar_css,
)
from .theming.app_css import (  # noqa: F401 - re-exported
    build_app_css,
)
from .theming.page_css import (  # noqa: F401 - re-exported
    build_fullscreen_chart_css,
    build_security_css,
)
