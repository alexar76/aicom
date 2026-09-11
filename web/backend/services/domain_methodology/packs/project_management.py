"""
Project / task management domain methodology pack.

A real project tool needs status flow + assignment + reportable cycle time
(throughput, WIP, cycle time). Backlog → todo → in progress → blocked →
review → done with rework support. Aligned with the Kanban Method
(Anderson), the Scrum Guide 2020 and Atlassian Jira workflow patterns.
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


PROJECT_MANAGEMENT = DomainPack(
    domain_id="project_management",
    label="Project / Task management",
    description=(
        "Projects, tasks, boards, milestones, dependencies and collaboration. "
        "Honest project tools allow assignment, status flow, and reporting."
    ),
    keywords=(
        "project management", "task tracker", "issue tracker", "kanban", "scrum",
        "agile board", "milestones", "todo app", "task management",
    ),
    categories=("productivity", "project_management", "tasks"),
    entities=(
        DomainEntity(
            name="project",
            fields=(
                EntityField(name="name"),
                EntityField(name="status"),
                EntityField(name="owner"),
            ),
        ),
        DomainEntity(
            name="task",
            aliases=("issue", "ticket", "story"),
            fields=(
                EntityField(name="project_id"),
                EntityField(name="title"),
                EntityField(name="status"),
                EntityField(name="assignee"),
                EntityField(name="due_date", required=False),
                EntityField(name="priority", required=False),
            ),
        ),
        DomainEntity(
            name="board",
            aliases=("list",),
            fields=(EntityField(name="project_id"), EntityField(name="columns"))
        ),
        DomainEntity(
            name="comment",
            fields=(
                EntityField(name="task_id"),
                EntityField(name="author"),
                EntityField(name="body"),
            ),
        ),
        DomainEntity(
            name="milestone",
            required=False,
            fields=(
                EntityField(name="project_id"),
                EntityField(name="due_date"),
            ),
        ),
    ),
    roles=(
        DomainRole(name="owner", aliases=("project owner",)),
        DomainRole(name="member", aliases=("contributor",)),
        DomainRole(name="viewer", required=False),
    ),
    capabilities=(
        Capability(id="create_project", label="create project"),
        Capability(id="create_task", label="create task"),
        Capability(id="assign_task", label="assign task"),
        Capability(id="change_status", label="change status"),
        Capability(id="set_due", label="set due date", severity="medium"),
        Capability(id="comment", label="comment on task"),
        Capability(id="filter_board", label="filter board"),
        Capability(id="report_progress", label="report progress", severity="medium"),
    ),
    lifecycle_states=(
        LifecycleState(name="backlog", is_initial=True),
        LifecycleState(name="todo", aliases=("to do",)),
        LifecycleState(name="in progress", aliases=("doing",)),
        LifecycleState(name="blocked", aliases=("on hold",)),
        LifecycleState(name="review", aliases=("in review",)),
        LifecycleState(name="done", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="backlog", to_state="todo"),
        LifecycleTransition(from_state="todo", to_state="in progress"),
        LifecycleTransition(from_state="in progress", to_state="blocked"),
        LifecycleTransition(from_state="blocked", to_state="in progress"),
        LifecycleTransition(from_state="in progress", to_state="review"),
        LifecycleTransition(from_state="review", to_state="done"),
        LifecycleTransition(from_state="review", to_state="in progress", label="rework"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="create-project",
            title="Owner creates a project and adds a task",
            journey_type="onboarding",
            steps=(
                "Owner creates a project",
                "Owner adds a task and assigns it to a member",
            ),
            expected_outcome="Project + task persisted with assignee.",
        ),
        AcceptanceScenario(
            id="board-flow",
            title="Member moves task across the board",
            journey_type="core_action",
            steps=(
                "Member opens board",
                "Member drags task from todo -> in progress -> review -> done",
            ),
            expected_outcome="Status transitions reflected and persisted.",
        ),
        AcceptanceScenario(
            id="blocker",
            title="Task blocked and unblocked",
            journey_type="edge_case",
            steps=(
                "Member sets task to 'blocked' with a reason",
                "Member resumes task to 'in progress' once unblocked",
            ),
            expected_outcome="Block/unblock transitions exist and are reportable.",
        ),
        AcceptanceScenario(
            id="report",
            title="Owner sees throughput / WIP",
            journey_type="reporting",
            severity="medium",
            steps=(
                "Owner opens project dashboard",
                "Owner sees throughput, WIP, completed in time window",
            ),
            expected_outcome="Throughput / WIP visible.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="POST", path_pattern="/api/projects", purpose="create project"),
        ApiEndpoint(method="POST", path_pattern="/api/projects/{id}/tasks", purpose="create task"),
        ApiEndpoint(method="POST", path_pattern="/api/tasks/{id}/status", purpose="change status"),
        ApiEndpoint(method="POST", path_pattern="/api/tasks/{id}/assign", purpose="assign task"),
        ApiEndpoint(method="POST", path_pattern="/api/tasks/{id}/comments", purpose="comment"),
        ApiEndpoint(method="GET", path_pattern="/api/projects/{id}/report", purpose="project report"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="throughput",
            label="throughput",
            formula="count(tasks done in window)",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="cycle_time",
            label="cycle time",
            formula="median(done_at - in_progress_at)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="wip",
            label="work in progress",
            formula="count(tasks where status='in progress')",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="no_status",
            severity="high",
            description="Tasks have no status field.",
            fix_hint="Add a status field tied to the lifecycle.",
        ),
        RedFlagPattern(
            id="no_assignment",
            severity="high",
            description="Tasks have no assignee / ownership.",
            fix_hint="Assign every task to a person; collective ownership is not enough.",
        ),
        RedFlagPattern(
            id="no_columns",
            severity="medium",
            description="Boards exist but have no columns / transitions.",
            fix_hint="Boards should have columns reflecting workflow states.",
        ),
    ),
    references=(
        Reference(title="Kanban Method (Anderson)"),
        Reference(title="Scrum Guide 2020"),
        Reference(title="Atlassian Jira workflow patterns"),
    ),
    methodology_notes=(
        "A real project tool needs status flow + assignment + reportable cycle time."
    ),
)
