"""
Helpdesk / IT support domain methodology pack.

A helpdesk product is judged by ticket lifecycle integrity (state machine),
ownership / assignment, two-way thread (public reply + internal note), SLA
policy with breach reporting, and reopen support. Aligned with ITIL 4
incident management and ISO/IEC 20000-1 service management practice.
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


HELPDESK_SUPPORT = DomainPack(
    domain_id="helpdesk_support",
    label="Helpdesk / IT support",
    description=(
        "Ticket-driven support workflow with SLA, assignment, communication thread "
        "and resolution lifecycle. Conforms to ITIL incident management practice."
    ),
    keywords=(
        "helpdesk", "support", "ticket", "incident", "service desk", "itsm",
        "sla", "queue", "request management", "case management",
    ),
    categories=("support", "helpdesk", "itsm", "operations"),
    entities=(
        DomainEntity(
            name="ticket",
            description="Customer-facing service request / incident.",
            aliases=("incident", "case", "support request"),
            fields=(
                EntityField(name="subject", aliases=("title",)),
                EntityField(name="description"),
                EntityField(name="status", aliases=("state",)),
                EntityField(name="priority", aliases=("urgency", "impact")),
                EntityField(name="assignee", aliases=("agent", "owner")),
                EntityField(name="requester", aliases=("customer", "user")),
                EntityField(name="created_at"),
                EntityField(name="resolved_at", required=False),
                EntityField(name="sla_due_at", required=False, aliases=("due_at",)),
            ),
        ),
        DomainEntity(
            name="customer",
            description="External requester / end user filing tickets.",
            aliases=("requester", "end user"),
            fields=(EntityField(name="name"), EntityField(name="email")),
        ),
        DomainEntity(
            name="agent",
            description="Support agent who picks up and resolves tickets.",
            aliases=("support agent", "support engineer"),
            fields=(EntityField(name="name"), EntityField(name="team", required=False)),
        ),
        DomainEntity(
            name="comment",
            description="Threaded message on a ticket (public reply or internal note).",
            aliases=("reply", "message", "note"),
            fields=(
                EntityField(name="ticket_id"),
                EntityField(name="author"),
                EntityField(name="body"),
                EntityField(name="public", description="public reply vs internal note"),
                EntityField(name="created_at"),
            ),
        ),
        DomainEntity(
            name="sla policy",
            description="Time-based commitment per priority/team.",
            aliases=("sla",),
            fields=(
                EntityField(name="priority"),
                EntityField(name="response_time"),
                EntityField(name="resolution_time"),
            ),
        ),
        DomainEntity(
            name="team",
            description="Group of agents with a queue of tickets.",
            aliases=("queue", "group"),
            fields=(EntityField(name="name"), EntityField(name="members")),
        ),
    ),
    roles=(
        DomainRole(name="requester", aliases=("customer", "end user")),
        DomainRole(name="agent", aliases=("support agent",)),
        DomainRole(name="manager", aliases=("team lead", "support manager")),
    ),
    capabilities=(
        Capability(id="create_ticket", label="create ticket", aliases=("submit ticket", "open ticket")),
        Capability(id="assign_ticket", label="assign ticket", aliases=("reassign ticket",)),
        Capability(id="change_priority", label="change priority"),
        Capability(id="reply_thread", label="thread comments", aliases=("reply", "post comment")),
        Capability(id="track_sla", label="track sla breach", aliases=("sla breach", "sla report")),
        Capability(id="escalate", label="escalate ticket"),
        Capability(id="close_reopen", label="close and reopen", aliases=("close ticket", "reopen ticket")),
        Capability(id="filter_search", label="search and filter", aliases=("search ticket", "filter queue")),
        Capability(id="csat", label="capture satisfaction", severity="medium", aliases=("csat", "satisfaction survey")),
    ),
    lifecycle_states=(
        LifecycleState(name="new", is_initial=True, aliases=("open", "received")),
        LifecycleState(name="triaged", aliases=("triage",)),
        LifecycleState(name="assigned"),
        LifecycleState(name="in progress", aliases=("in-progress", "working")),
        LifecycleState(name="waiting on customer", aliases=("pending customer", "waiting")),
        LifecycleState(name="resolved"),
        LifecycleState(name="closed", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="new", to_state="triaged"),
        LifecycleTransition(from_state="triaged", to_state="assigned"),
        LifecycleTransition(from_state="assigned", to_state="in progress"),
        LifecycleTransition(from_state="in progress", to_state="waiting on customer"),
        LifecycleTransition(from_state="waiting on customer", to_state="in progress"),
        LifecycleTransition(from_state="in progress", to_state="resolved"),
        LifecycleTransition(from_state="resolved", to_state="closed"),
        LifecycleTransition(from_state="resolved", to_state="in progress", label="reopen"),
        LifecycleTransition(from_state="closed", to_state="in progress", label="reopen"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="customer-creates-ticket",
            title="Customer files a ticket and gets a confirmation",
            journey_type="onboarding",
            steps=(
                "Customer opens portal and creates a ticket",
                "Ticket is acknowledged with an id and SLA timer",
                "Ticket appears in support queue in 'new' state",
            ),
            expected_outcome="Ticket persisted with id, status=new, sla_due_at set.",
        ),
        AcceptanceScenario(
            id="agent-assignment",
            title="Agent picks up a ticket from the queue",
            journey_type="core_action",
            steps=(
                "Agent filters their team's queue",
                "Agent assigns ticket to themselves",
                "Status moves to 'assigned' and then 'in progress'",
                "Agent posts a public reply to the customer",
            ),
            expected_outcome="Ticket has assignee, status moved past 'new', thread has reply.",
        ),
        AcceptanceScenario(
            id="sla-breach",
            title="SLA breach is visible and actionable",
            journey_type="reporting",
            steps=(
                "Manager opens SLA dashboard",
                "Tickets past sla_due_at are highlighted",
                "Manager escalates breached ticket to senior agent",
            ),
            expected_outcome="Breach metric and escalation flow are present.",
        ),
        AcceptanceScenario(
            id="resolve-and-reopen",
            title="Ticket resolves but customer reopens",
            journey_type="recovery",
            steps=(
                "Agent marks ticket 'resolved'",
                "Customer replies that the issue is back",
                "Status returns to 'in progress'",
            ),
            expected_outcome="Reopen is supported without losing history.",
        ),
        AcceptanceScenario(
            id="csat",
            title="Capture satisfaction after resolution",
            journey_type="operational",
            severity="medium",
            steps=(
                "Closed ticket triggers CSAT survey",
                "Customer rates the resolution",
                "CSAT shows in agent / team report",
            ),
            expected_outcome="CSAT signal is collected and reportable.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="POST", path_pattern="/api/tickets", purpose="create ticket"),
        ApiEndpoint(method="GET", path_pattern="/api/tickets", purpose="list tickets"),
        ApiEndpoint(method="GET", path_pattern="/api/tickets/{id}", purpose="ticket details"),
        ApiEndpoint(method="POST", path_pattern="/api/tickets/{id}/assign", purpose="assign agent"),
        ApiEndpoint(method="POST", path_pattern="/api/tickets/{id}/comments", purpose="reply / note"),
        ApiEndpoint(method="POST", path_pattern="/api/tickets/{id}/status", purpose="change status"),
        ApiEndpoint(method="GET", path_pattern="/api/reports/sla", purpose="SLA report"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="frt",
            label="first response time",
            formula="median(first_public_reply_at - created_at)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="rt",
            label="resolution time",
            formula="median(resolved_at - created_at)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="sla_breach",
            label="sla breach rate",
            formula="count(tickets where now() > sla_due_at) / count(tickets)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="csat",
            label="csat",
            formula="avg(csat_score)",
            target_direction="higher_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="no_status_field",
            severity="high",
            description="Tickets do not have a status field / lifecycle.",
            keywords=("status: optional", "no state machine"),
            regex=(r"status\s*=\s*null", r"\bstateless tickets?\b"),
            fix_hint="Tickets must always have an enumerated status from the lifecycle.",
        ),
        RedFlagPattern(
            id="no_assignment",
            severity="high",
            description="No agent assignment / ownership on tickets.",
            keywords=("no assignee", "anyone can pick"),
            regex=(r"unassigned\s+forever",),
            fix_hint="Every ticket must support assignment to an agent / team.",
        ),
        RedFlagPattern(
            id="no_thread",
            severity="high",
            description="No conversation thread between requester and agent.",
            keywords=("single message ticket", "no replies"),
            regex=(r"comments?\s*disabled",),
            fix_hint="Add comment / reply thread (public + internal) on tickets.",
        ),
        RedFlagPattern(
            id="no_sla",
            severity="medium",
            description="No SLA / priority concept.",
            keywords=("no sla", "no priority"),
            fix_hint="Introduce SLA policy with response/resolution time per priority.",
        ),
    ),
    references=(
        Reference(title="ITIL 4 Foundation — Incident Management"),
        Reference(title="ISO/IEC 20000-1:2018 service management"),
        Reference(title="HDI Customer Service & Support practices"),
    ),
    methodology_notes=(
        "A helpdesk product is judged by ticket lifecycle integrity (state machine), "
        "ownership / assignment, two-way thread, SLA policy with breach reporting, "
        "and reopen support."
    ),
)
