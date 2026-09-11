"""A pack path is a shape, not a mount contract.

The analytics_bi pack demands `POST /api/dashboards`; the live product serves exactly that resource at
`/api/analytics/dashboards` — the difference is one router prefix. The literal match failed the
methodology gate on every run of the night, which kept `gates_ok` unreachable for a product whose six
other gates were green.
"""

from __future__ import annotations

from web.backend.services.domain_methodology.base import ApiEndpoint
from web.backend.services.methodology_review import _eval_api


def _ep(method: str, path: str) -> ApiEndpoint:
    return ApiEndpoint(method=method, path_pattern=path)


def test_a_mounted_prefix_still_counts_as_covered():
    raw = 'const r = await fetch("/api/analytics/dashboards", {method: "POST"})'
    present, missing = _eval_api(raw, (_ep("POST", "/api/dashboards"),))
    assert present == ["POST /api/dashboards"], (present, missing)


def test_the_resource_tail_must_still_match_in_full():
    raw = 'fetch("/api/analytics/dash", {method: "POST"})'
    present, missing = _eval_api(raw, (_ep("POST", "/api/dashboards"),))
    assert missing == ["POST /api/dashboards"]


def test_path_parameters_survive_the_relaxation():
    raw = 'GET "/api/analytics/dashboards/42/export"'
    present, missing = _eval_api(raw, (_ep("GET", "/api/dashboards/{id}/export"),))
    assert present == ["GET /api/dashboards/{id}/export"], (present, missing)


def test_an_exact_match_still_works():
    raw = '@router.post("/api/dashboards")'
    present, _ = _eval_api(raw, (_ep("POST", "/api/dashboards"),))
    assert present == ["POST /api/dashboards"]


def test_a_genuinely_absent_endpoint_is_still_missing():
    present, missing = _eval_api("nothing here", (_ep("POST", "/api/dashboards"),))
    assert present == [] and missing == ["POST /api/dashboards"]


def test_non_api_pack_paths_are_untouched():
    raw = 'fetch("/healthz")'
    present, _ = _eval_api(raw, (_ep("GET", "/healthz"),))
    assert present == ["GET /healthz"]


def test_fastapi_relative_route_under_api_prefix_counts():
    """Pack wants POST /api/datasets; the router is mounted at /api/analytics."""
    raw = """
app.include_router(analytics.router, prefix="/api/analytics")
@router.post("/datasets", status_code=201)
@router.get("/dashboards/{dashboard_id}/data")
@router.get("/dashboards/{dashboard_id}/export")
"""
    present, missing = _eval_api(
        raw,
        (
            _ep("POST", "/api/datasets"),
            _ep("GET", "/api/dashboards/{id}/data"),
            _ep("GET", "/api/dashboards/{id}/export"),
        ),
    )
    assert missing == [], (present, missing)
    assert "POST /api/datasets" in present
    assert "GET /api/dashboards/{id}/data" in present
    assert "GET /api/dashboards/{id}/export" in present


def test_relative_decorator_still_requires_the_matching_method():
    raw = '@router.get("/datasets")'
    present, missing = _eval_api(raw, (_ep("POST", "/api/datasets"),))
    assert present == [] and missing == ["POST /api/datasets"]
