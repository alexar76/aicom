"""
DevTools / Ops platform domain methodology pack.

DevOps platforms are judged by deployment + log + alert lifecycle integrity,
not by dashboard prettiness. Deployments transition queued → running →
succeeded / failed → rolled back, alerts move open → ack → resolved, and
DORA metrics (deploy frequency, MTTR, change failure rate) are first-class.
Grounded in the Google SRE Book and the DORA / Accelerate state-of-DevOps work.
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


DEVTOOLS_OPS = DomainPack(
    domain_id="devtools_ops",
    label="DevTools / Ops platform",
    description=(
        "Projects, environments, deployments, logs, alerts and integrations. "
        "DevOps platforms must reflect deploy lifecycle and incident response."
    ),
    keywords=(
        "devtools", "developer tools", "monitoring", "observability", "ci/cd",
        "deployment platform", "logs platform", "alerts", "incident response",
        "platform engineering",
    ),
    categories=("devtools", "infra", "platform"),
    entities=(
        DomainEntity(
            name="project",
            fields=(EntityField(name="name"), EntityField(name="repo", required=False)),
        ),
        DomainEntity(
            name="environment",
            fields=(
                EntityField(name="project_id"),
                EntityField(name="name", description="dev/staging/production"),
                EntityField(name="config", required=False),
            ),
        ),
        DomainEntity(
            name="deployment",
            fields=(
                EntityField(name="environment_id"),
                EntityField(name="status"),
                EntityField(name="version", aliases=("commit", "revision")),
                EntityField(name="started_at"),
                EntityField(name="finished_at", required=False),
            ),
        ),
        DomainEntity(
            name="log",
            aliases=("event",),
            fields=(
                EntityField(name="timestamp"),
                EntityField(name="level"),
                EntityField(name="message"),
                EntityField(name="source"),
            ),
        ),
        DomainEntity(
            name="alert rule",
            fields=(
                EntityField(name="name"),
                EntityField(name="condition"),
                EntityField(name="severity"),
                EntityField(name="state"),
            ),
        ),
        DomainEntity(
            name="integration",
            required=False,
            fields=(EntityField(name="kind"), EntityField(name="config", required=False)),
        ),
    ),
    roles=(
        DomainRole(name="developer", aliases=("engineer",)),
        DomainRole(name="ops", aliases=("sre", "site reliability engineer")),
        DomainRole(name="admin"),
    ),
    capabilities=(
        Capability(id="create_project", label="create project"),
        Capability(id="configure_env", label="configure environment"),
        Capability(id="ship_deployment", label="ship deployment", aliases=("deploy", "release")),
        Capability(id="view_logs", label="view logs"),
        Capability(id="configure_alert", label="configure alert"),
        Capability(id="ack_incident", label="acknowledge incident", aliases=("ack alert",)),
        Capability(id="manage_integration", label="manage integration"),
        Capability(id="rollback", label="rollback"),
    ),
    lifecycle_states=(
        LifecycleState(name="queued", is_initial=True),
        LifecycleState(name="running", aliases=("in_progress",)),
        LifecycleState(name="succeeded", is_terminal=True),
        LifecycleState(name="failed", is_terminal=True),
        LifecycleState(name="rolled back", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="queued", to_state="running"),
        LifecycleTransition(from_state="running", to_state="succeeded"),
        LifecycleTransition(from_state="running", to_state="failed"),
        LifecycleTransition(from_state="succeeded", to_state="rolled back", label="rollback"),
        LifecycleTransition(from_state="failed", to_state="rolled back"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="deploy",
            title="Deploy a new version to staging",
            journey_type="core_action",
            steps=(
                "Developer triggers a deployment to staging",
                "Deployment runs and either succeeds or fails",
                "Logs are captured per deployment",
            ),
            expected_outcome="Deployment record + logs persisted with status.",
        ),
        AcceptanceScenario(
            id="rollback",
            title="Roll back a failed deployment",
            journey_type="recovery",
            steps=(
                "Failed deployment detected",
                "Operator rolls back to previous version",
                "Status moves to 'rolled back'",
            ),
            expected_outcome="Rollback flow tracked end-to-end.",
        ),
        AcceptanceScenario(
            id="alert",
            title="Alert fires and gets acknowledged",
            journey_type="operational",
            steps=(
                "Alert rule triggers",
                "Operator acknowledges alert",
                "Resolution recorded",
            ),
            expected_outcome="Alert lifecycle (open -> ack -> resolved) tracked.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="POST", path_pattern="/api/projects/{id}/deployments", purpose="trigger deployment"),
        ApiEndpoint(method="GET", path_pattern="/api/deployments/{id}", purpose="deployment status"),
        ApiEndpoint(method="POST", path_pattern="/api/deployments/{id}/rollback", purpose="rollback"),
        ApiEndpoint(method="GET", path_pattern="/api/projects/{id}/logs", purpose="logs"),
        ApiEndpoint(method="POST", path_pattern="/api/alerts/{id}/ack", purpose="acknowledge alert"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="deploy_freq",
            label="deploy frequency",
            formula="count(deployments) / time_window",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="mttr",
            label="mttr",
            formula="avg(resolved_at - opened_at) for incidents",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="cfr",
            label="change failure rate",
            formula="failed_deployments / total_deployments",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="alert_noise",
            label="alert noise",
            formula="count(alerts auto-resolved within minutes) / count(alerts)",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="no_deployment_status",
            severity="high",
            description="Deployments have no status.",
            keywords=("blind deploy", "no deployment status"),
            fix_hint="Track queued / running / succeeded / failed for every deploy.",
        ),
        RedFlagPattern(
            id="no_logs",
            severity="high",
            description="No logs / events surface.",
            keywords=("no logs",),
            fix_hint="Persist and surface deployment + runtime logs.",
        ),
        RedFlagPattern(
            id="no_alert_lifecycle",
            severity="medium",
            description="Alerts cannot be acknowledged or resolved.",
            keywords=("alert is stateless",),
            fix_hint="Add ack/resolve states for alert rules.",
        ),
    ),
    references=(
        Reference(title="Google SRE Book"),
        Reference(title="DORA / Accelerate state of DevOps"),
        Reference(title="Operating System: incident command for IT (Limoncelli)"),
    ),
    methodology_notes=(
        "Devtools / ops platforms are judged by deployment + log + alert lifecycle, "
        "not by dashboard prettiness."
    ),
)
