#!/usr/bin/env python3
"""One-off splitter: admin/dashboard.py -> admin/dashboard/ package."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web/backend/api/admin/dashboard.py"
PKG = ROOT / "web/backend/api/admin/dashboard"

HEADER = '''"""
Admin Dashboard API (split module).
"""

from __future__ import annotations

'''

IMPORTS = Path(SRC).read_text(encoding="utf-8").splitlines()[7:87]
IMPORT_BLOCK = "\n".join(IMPORTS) + "\n"

SECTIONS: list[tuple[str, int, int]] = [
    ("models.py", 92, 146),
    ("helpers.py", 148, 857),
    ("routes_metrics.py", 859, 966),
    ("routes_director.py", 967, 1030),
    ("routes_providers.py", 1032, 1665),
    ("routes_agents.py", 1667, 1962),
    ("routes_llm_logs.py", 1964, 2034),
    ("routes_director_reports.py", 2036, 2231),
    ("routes_pipeline.py", 2233, 3097),
    ("routes_products.py", 3099, 3317),
    ("routes_discovery.py", 3319, 3530),
    ("routes_compliance.py", 3532, 10_000),
]

ROUTER_PY = '''"""Shared admin dashboard FastAPI router."""

from fastapi import APIRouter, Depends

from web.backend.core.admin_roles import require_admin_with_rbac

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_admin_with_rbac)],
)
'''

INIT_PY = '''"""
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
'''


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    PKG.mkdir(parents=True, exist_ok=True)
    (PKG / "_router.py").write_text(ROUTER_PY, encoding="utf-8")

    for filename, start, end in SECTIONS:
        body = "".join(lines[start - 1 : end])
        if filename == "models.py":
            prefix = HEADER + IMPORT_BLOCK
        elif filename == "helpers.py":
            prefix = (
                HEADER
                + IMPORT_BLOCK
                + "\nfrom .models import (\n"
                "    HumanReviewApproveBody,\n"
                "    HumanReviewRejectBody,\n"
                "    HumanReworkBody,\n"
                "    MarketplaceCopyPatch,\n"
                "    ReopenFailedBody,\n"
                "    StorefrontAdminPatch,\n"
                "    StorefrontFollowupPatch,\n"
                "    StorefrontPricingPatch,\n"
                ")\n\n"
            )
        else:
            prefix = HEADER + IMPORT_BLOCK + "\nfrom ._router import router\n"
            if filename != "routes_metrics.py":
                prefix += "from .models import *\n"  # noqa: F403\n"
            prefix += "from .helpers import *\n"  # noqa: F403\n"
        (PKG / filename).write_text(prefix + body, encoding="utf-8")
        print(f"wrote {filename}")

    (PKG / "__init__.py").write_text(INIT_PY, encoding="utf-8")
    print("wrote __init__.py")
    SRC.unlink()
    print(f"removed {SRC}")


if __name__ == "__main__":
    main()
