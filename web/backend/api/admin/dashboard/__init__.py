"""
Admin Dashboard API package.
"""

from ._router import router
from .helpers import (
    _build_full_metrics,
    _build_full_metrics_async,
    _build_quick_dashboard_metrics,
    _admin_sqlite_db_path,
    _refresh_full_dashboard_cache,
    get_live_metrics_stream_payload,
)

from . import (  # noqa: F401 — register routes on shared router
    routes_agents,
    routes_compliance,
    routes_director,
    routes_director_reports,
    routes_discovery,
    routes_llm_logs,
    routes_metrics,
    routes_metis,
    routes_pipeline,
    routes_products,
    routes_providers,
    routes_factory_backup,
    routes_platform,
)

__all__ = [
    "router",
    "_build_full_metrics",
    "_build_full_metrics_async",
    "_build_quick_dashboard_metrics",
    "_admin_sqlite_db_path",
    "_refresh_full_dashboard_cache",
    "get_live_metrics_stream_payload",
]
