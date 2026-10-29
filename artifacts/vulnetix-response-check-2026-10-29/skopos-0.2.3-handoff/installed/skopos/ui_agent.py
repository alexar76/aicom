"""Global floating security agent — bottom-right chat widget.

This is now a thin wrapper around :mod:`skopos.agent_widget`, a self-contained
overlay that talks to the SKOPOS ``/agent/chat`` backend. The previous
Streamlit-native chat (portaled into ``<body>`` via DOM surgery) has been
retired in favour of the factory-style widget.
"""

from __future__ import annotations

import logging

from skopos.agent_widget import render_floating_agent
from skopos.app_auth import is_dashboard_authenticated
from skopos.config import AppConfig
from skopos.security.posture import SecurityPosture
from skopos.themes import get_active_theme

logger = logging.getLogger("skopos.ui_agent")


def _current_page_slug() -> str | None:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is None:
            return None
        main = str(getattr(ctx, "main_script_path", "") or "").replace("\\", "/")
        if main.endswith("dashboard.py"):
            return "Analytics"
        if "1_Security" in main:
            return "Security"
        if "6_Observability" in main:
            return "Observability"
        if "2_Settings" in main:
            return "Settings"
        if "3_Scan_History" in main:
            return "Scan History"
        if "5_Fleet" in main:
            return "Fleet"
        if "4_Documentation" in main:
            return "Documentation"
        if "0_Quick_Start" in main:
            return "Quick Start"
    except Exception:
        pass
    return None


def render_global_agent(
    cfg: AppConfig,
    agent_path: str,
    *,
    locale: str = "en",
    server_name: str | None = None,
    posture: SecurityPosture | None = None,
) -> None:
    """Floating AI agent — bottom-right on every authenticated page."""
    if not is_dashboard_authenticated():
        return
    render_floating_agent(
        locale=locale,
        page=_current_page_slug(),
        server_name=server_name,
        theme=get_active_theme(),
    )
