"""
CRM / Sales pipeline domain methodology pack.

A real CRM is judged by whether reps can capture leads, qualify them, advance
deals through stages with attribution, log meaningful activity, and managers
can report on pipeline health by stage / owner. The pack below encodes that
contract as required entities, lifecycle (new → qualified → … → won/lost),
acceptance scenarios, expected API endpoints and red flags (static landing
only, no owner field, free-text status …).
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


CRM_SALES = DomainPack(
    domain_id="crm_sales",
    label="CRM / Sales pipeline",
    description=(
        "Customer relationship management with leads, deals, activities and ownership. "
        "A real CRM tracks deals through stages, attributes ownership and activities, "
        "reports on conversion, and lets reps prioritise their pipeline."
    ),
    keywords=(
        "crm", "sales pipeline", "lead", "deal", "opportunity", "kanban deals",
        "account management", "client management", "pipeline stages", "sales rep",
    ),
    categories=("crm", "sales", "customer"),
    entities=(
        DomainEntity(
            name="lead",
            description="Unqualified inbound interest awaiting qualification.",
            aliases=("prospect",),
            fields=(
                EntityField(name="source", description="Where the lead came from"),
                EntityField(name="contact", description="Contact details (email/phone/name)"),
                EntityField(name="status", description="qualification status", aliases=("stage", "state")),
                EntityField(name="owner", description="Sales rep responsible"),
            ),
        ),
        DomainEntity(
            name="contact",
            description="Person at a company we are talking to.",
            fields=(
                EntityField(name="email"),
                EntityField(name="phone", required=False),
                EntityField(name="company"),
                EntityField(name="role"),
            ),
        ),
        DomainEntity(
            name="company",
            description="Account / company record contacts and deals are linked to.",
            aliases=("account",),
            fields=(
                EntityField(name="name"),
                EntityField(name="industry", required=False),
                EntityField(name="size", required=False),
            ),
        ),
        DomainEntity(
            name="deal",
            description="Tracked sales opportunity moving through pipeline stages.",
            aliases=("opportunity",),
            fields=(
                EntityField(name="amount", aliases=("value", "price")),
                EntityField(name="stage", aliases=("status",)),
                EntityField(name="owner"),
                EntityField(name="expected_close_date", aliases=("close_date", "due_date")),
                EntityField(name="probability", required=False),
            ),
        ),
        DomainEntity(
            name="activity",
            description="Logged interaction tied to a deal/contact (call, email, meeting, note).",
            aliases=("task", "note", "interaction"),
            fields=(
                EntityField(name="type", aliases=("kind",)),
                EntityField(name="subject"),
                EntityField(name="due_at", required=False),
                EntityField(name="owner"),
            ),
        ),
    ),
    roles=(
        DomainRole(name="sales rep", aliases=("rep", "sales person", "ae", "account executive")),
        DomainRole(name="manager", aliases=("sales manager", "team lead")),
        DomainRole(name="admin", aliases=("system admin",)),
    ),
    capabilities=(
        Capability(id="create_lead", label="create lead", aliases=("add lead", "capture lead")),
        Capability(id="qualify_lead", label="qualify lead", aliases=("disqualify", "mark qualified")),
        Capability(id="convert_lead", label="convert lead to deal", aliases=("convert lead",)),
        Capability(id="move_stage", label="move deal between stages", aliases=("change stage", "update stage")),
        Capability(id="log_activity", label="log activity", aliases=("log call", "log email", "log meeting")),
        Capability(id="assign_owner", label="assign owner", aliases=("reassign", "change owner")),
        Capability(id="report_pipeline", label="report by stage", aliases=("pipeline report", "sales dashboard")),
        Capability(id="filter_search", label="filter and search", aliases=("search deal", "filter pipeline")),
        Capability(id="forecast", label="forecast revenue", severity="medium", aliases=("revenue forecast",)),
    ),
    lifecycle_states=(
        LifecycleState(name="new", is_initial=True, aliases=("open", "uncontacted")),
        LifecycleState(name="qualified", aliases=("qualifying",)),
        LifecycleState(name="proposal", aliases=("quote sent", "proposal sent")),
        LifecycleState(name="negotiation", aliases=("negotiating",)),
        LifecycleState(name="won", is_terminal=True, aliases=("closed won",)),
        LifecycleState(name="lost", is_terminal=True, aliases=("closed lost",)),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="new", to_state="qualified", label="qualify lead"),
        LifecycleTransition(from_state="new", to_state="lost", label="disqualify"),
        LifecycleTransition(from_state="qualified", to_state="proposal", label="send proposal"),
        LifecycleTransition(from_state="proposal", to_state="negotiation", label="enter negotiation"),
        LifecycleTransition(from_state="negotiation", to_state="won", label="close won"),
        LifecycleTransition(from_state="negotiation", to_state="lost", label="close lost"),
        LifecycleTransition(from_state="qualified", to_state="lost", label="disqualify"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="onboard-rep",
            title="Onboard a sales rep and let them work their pipeline",
            journey_type="onboarding",
            steps=(
                "Sales rep signs in",
                "Sales rep imports or creates a contact and company",
                "Sales rep creates a lead linked to the contact",
                "Sales rep qualifies the lead and converts it to a deal",
            ),
            expected_outcome="Rep has at least one deal in 'qualified' or later stage with an owner.",
        ),
        AcceptanceScenario(
            id="advance-deal",
            title="Advance a deal through the pipeline",
            journey_type="core_action",
            steps=(
                "Open a deal in 'qualified'",
                "Log a call/email activity",
                "Move deal to 'proposal', then 'negotiation'",
                "Close deal as 'won' with amount and close date",
            ),
            expected_outcome="Deal records final stage 'won'/'lost', amount, close date, owner.",
        ),
        AcceptanceScenario(
            id="reassign-owner",
            title="Manager reassigns ownership of a deal",
            journey_type="operational",
            steps=(
                "Manager opens pipeline filter by rep",
                "Manager reassigns a deal to another rep",
                "New owner sees deal in their pipeline",
            ),
            expected_outcome="Audit trail shows owner change and new owner has access.",
        ),
        AcceptanceScenario(
            id="pipeline-report",
            title="Generate a pipeline report by stage",
            journey_type="reporting",
            steps=(
                "Manager opens pipeline report",
                "Report shows total amount and count per stage",
                "Manager filters by owner and time window",
            ),
            expected_outcome="Stage totals and conversion rates are visible.",
        ),
        AcceptanceScenario(
            id="lost-recovery",
            title="Reopen a lost deal as a new opportunity",
            journey_type="recovery",
            steps=(
                "Sales rep finds lost deal",
                "Sales rep clones / reopens it as a new opportunity",
                "New deal starts from 'qualified' (or earlier) with prior history visible",
            ),
            expected_outcome="History is preserved; closed-lost cannot be silently re-marked as won.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="GET", path_pattern="/api/leads", purpose="list leads"),
        ApiEndpoint(method="POST", path_pattern="/api/leads", purpose="create lead"),
        ApiEndpoint(method="GET", path_pattern="/api/deals", purpose="list deals"),
        ApiEndpoint(method="POST", path_pattern="/api/deals", purpose="create deal"),
        ApiEndpoint(method="POST", path_pattern="/api/deals/{id}/stage", purpose="move stage", severity="high"),
        ApiEndpoint(method="POST", path_pattern="/api/deals/{id}/activities", purpose="log activity"),
        ApiEndpoint(method="GET", path_pattern="/api/reports/pipeline", purpose="pipeline report"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="conversion_rate",
            label="conversion rate",
            formula="won_deals / total_deals_entered_pipeline",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="win_rate",
            label="win rate",
            formula="won_deals / (won_deals + lost_deals)",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="avg_deal_size",
            label="average deal size",
            formula="sum(amount) / count(won_deals)",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="stage_duration",
            label="average stage duration",
            formula="avg(time_in_stage)",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="static_landing_only",
            severity="high",
            description="The product is just a marketing landing page with no pipeline UI.",
            keywords=("hero", "subscribe", "request demo only"),
            regex=(r"\bcontact\s+sales\b\s*$",),
            fix_hint="Add a pipeline view (kanban/list) with deal records and stage transitions.",
        ),
        RedFlagPattern(
            id="no_owner_field",
            severity="high",
            description="Deals have no owner / assignment concept.",
            keywords=("no owner", "anyone can edit"),
            regex=(r"shared\s+inbox", r"no\s+ownership"),
            fix_hint="Every deal must have an owner that managers can reassign.",
        ),
        RedFlagPattern(
            id="single_status_field",
            severity="medium",
            description="Deal status is a free-text field rather than an enum / lifecycle state.",
            keywords=("status: text", "freeform status"),
            regex=(r"status\s*:\s*string\b",),
            fix_hint="Use enumerated stages aligned with the lifecycle state machine.",
        ),
    ),
    references=(
        Reference(title="Sales Pipeline Management — HubSpot Academy"),
        Reference(title="Predictable Revenue (Aaron Ross)"),
        Reference(title="The Challenger Sale (Dixon & Adamson)"),
    ),
    methodology_notes=(
        "A CRM is judged by whether reps can capture leads, qualify them, "
        "advance deals through stages with attribution, log meaningful activity, "
        "and managers can report on pipeline health by stage / owner."
    ),
)
