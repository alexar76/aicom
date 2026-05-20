"""
Admin Dashboard API package.
"""

from ._router import router
from .helpers import (
    _build_full_metrics,
    _build_full_metrics_async,
    _build_quick_dashboard_metrics,
    _admin_sqlite_db_path,
)

from . import (  # noqa: F401 — register routes on shared router
    routes_agents,
    routes_compliance,
    routes_director,
    routes_director_reports,
    routes_discovery,
    routes_llm_logs,
    routes_metrics,
    routes_pipeline,
    routes_products,
    routes_providers,
)

__all__ = [
    "router",
    "_build_full_metrics",
    "_build_full_metrics_async",
    "_build_quick_dashboard_metrics",
    "_admin_sqlite_db_path",
]
