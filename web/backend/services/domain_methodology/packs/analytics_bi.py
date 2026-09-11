"""
Analytics / BI domain methodology pack.

Analytics is judged by metric definitions (formula + dataset lineage),
filter / drill-down support, and export integrity — *not* by chart
aesthetics. Red flags include hardcoded numbers, screenshot dashboards and
the absence of any filter dimension. Aligned with the dbt metrics layer,
OpenMetrics naming, and Looker / Cube semantic-layer patterns.
"""

from web.backend.services.domain_methodology.base import (
    AcceptanceScenario,
    ApiEndpoint,
    Capability,
    DomainEntity,
    DomainPack,
    DomainRole,
    EntityField,
    LifecycleState,
    LifecycleTransition,
    ProcessMetric,
    RedFlagPattern,
    Reference,
)


ANALYTICS_BI = DomainPack(
    domain_id="analytics_bi",
    label="Analytics / BI",
    description=(
        "Dashboards, metrics with definitions, filters and export. "
        "Honest analytics tools attach formulas/lineage to numbers, "
        "not screenshots."
    ),
    keywords=(
        "analytics", "bi", "business intelligence", "dashboard", "reporting",
        "metrics", "kpi", "data exploration", "data viz",
    ),
    categories=("analytics", "data", "reporting"),
    entities=(
        DomainEntity(
            name="dataset",
            aliases=("source", "data source"),
            fields=(
                EntityField(name="name"),
                EntityField(name="schema"),
                EntityField(name="connection", required=False),
            ),
        ),
        DomainEntity(
            name="metric",
            description="Named numerical KPI with formula and lineage.",
            aliases=("measure", "kpi"),
            fields=(
                EntityField(name="name"),
                EntityField(name="formula"),
                EntityField(name="dataset_id"),
                EntityField(name="unit", required=False),
            ),
        ),
        DomainEntity(
            name="dashboard",
            fields=(
                EntityField(name="name"),
                EntityField(name="charts"),
                EntityField(name="filters", required=False),
                EntityField(name="status"),
            ),
        ),
        DomainEntity(
            name="filter",
            fields=(
                EntityField(name="dimension"),
                EntityField(name="value"),
            ),
        ),
        DomainEntity(
            name="user",
            aliases=("viewer", "editor"),
            fields=(EntityField(name="role"), EntityField(name="email"))
        ),
    ),
    roles=(
        DomainRole(name="viewer"),
        DomainRole(name="editor"),
        DomainRole(name="admin"),
    ),
    capabilities=(
        Capability(id="connect_data", label="load data", aliases=("connect dataset", "import data")),
        Capability(id="define_metric", label="define metric", aliases=("create kpi", "metric definition")),
        Capability(id="build_chart", label="build chart"),
        Capability(id="build_dashboard", label="build dashboard"),
        Capability(id="filter", label="filter and drill down", aliases=("drill down",)),
        Capability(id="export", label="export csv/xlsx", aliases=("download csv",)),
        Capability(id="share", label="share dashboard"),
    ),
    lifecycle_states=(
        LifecycleState(name="draft", is_initial=True),
        LifecycleState(name="published"),
        LifecycleState(name="archived", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="draft", to_state="published"),
        LifecycleTransition(from_state="published", to_state="archived"),
        LifecycleTransition(from_state="archived", to_state="published", label="restore"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="define-metric",
            title="Editor defines a metric and adds a chart",
            journey_type="onboarding",
            steps=(
                "Editor connects a dataset",
                "Editor defines a metric with formula",
                "Editor builds a chart from the metric",
            ),
            expected_outcome="Metric persists with formula; chart references it.",
        ),
        AcceptanceScenario(
            id="filter-drill",
            title="Viewer filters and drills down",
            journey_type="core_action",
            steps=(
                "Viewer opens dashboard",
                "Viewer applies a filter (e.g. region)",
                "Charts update with filtered values",
            ),
            expected_outcome="Filter affects charts and persists in URL/state.",
        ),
        AcceptanceScenario(
            id="export",
            title="Viewer exports data",
            journey_type="reporting",
            steps=(
                "Viewer exports underlying chart data to CSV",
                "Export contains rows aligned with chart values",
            ),
            expected_outcome="Export available, matches displayed values.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="POST", path_pattern="/api/datasets", purpose="register dataset"),
        ApiEndpoint(method="POST", path_pattern="/api/metrics", purpose="define metric"),
        ApiEndpoint(method="POST", path_pattern="/api/dashboards", purpose="create dashboard"),
        ApiEndpoint(method="GET", path_pattern="/api/dashboards/{id}/data", purpose="load dashboard data"),
        ApiEndpoint(method="GET", path_pattern="/api/dashboards/{id}/export", purpose="export csv"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="query_latency",
            label="query latency",
            formula="p95(query_duration_ms)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="dashboard_load",
            label="dashboard load time",
            formula="p95(dashboard_render_ms)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="data_freshness",
            label="data freshness",
            formula="now() - max(dataset.last_loaded_at)",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="no_formula",
            severity="high",
            description="Metrics have no formula or lineage.",
            keywords=("hardcoded number", "static screenshot"),
            fix_hint="Persist formula + dataset reference for every metric.",
        ),
        RedFlagPattern(
            id="static_dashboard",
            severity="high",
            description="Dashboards are screenshots / static images.",
            keywords=("dashboard screenshot",),
            regex=(r"<img[^>]+dashboard",),
            fix_hint="Render charts from data, not images.",
        ),
        RedFlagPattern(
            id="no_filter",
            severity="medium",
            description="No filter / drill-down.",
            fix_hint="Add at least one filter dimension and drill-down.",
        ),
    ),
    references=(
        Reference(title="dbt metrics layer / semantic layer"),
        Reference(title="OpenMetrics / Prometheus naming guide"),
        Reference(title="Looker / Cube.dev metric modelling"),
    ),
    methodology_notes=(
        "Analytics is judged by metric definitions, filter/drill-down, and "
        "export integrity — not by chart aesthetics."
    ),
)
