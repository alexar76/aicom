"""
HR / Recruiting (ATS) domain methodology pack.

An applicant tracking system is judged by funnel integrity (applied →
screening → interview → offer → hired/rejected), structured interview
scoring, offer / rejection capture, and reportable conversion. Anchored to
SHRM talent acquisition body of knowledge, OFCCP / EEOC compliance and the
Greenhouse / Lever workflow patterns common in the industry.
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


HR_RECRUITING = DomainPack(
    domain_id="hr_recruiting",
    label="HR / Recruiting (ATS)",
    description=(
        "Applicant tracking system: openings, candidates, interviews, offers. "
        "Honest ATS supports the standard recruiting funnel with stage tracking, "
        "interview feedback, and offer / rejection handling."
    ),
    keywords=(
        "hr", "ats", "applicant tracking", "recruiting", "candidates",
        "job opening", "vacancy", "interview pipeline", "offer letter",
        "talent acquisition",
    ),
    categories=("hr", "recruiting", "people"),
    entities=(
        DomainEntity(
            name="job opening",
            aliases=("vacancy", "requisition", "job"),
            fields=(
                EntityField(name="title"),
                EntityField(name="department", required=False),
                EntityField(name="hiring_manager"),
                EntityField(name="status"),
            ),
        ),
        DomainEntity(
            name="candidate",
            aliases=("applicant",),
            fields=(
                EntityField(name="name"),
                EntityField(name="email"),
                EntityField(name="resume", aliases=("cv",)),
                EntityField(name="stage"),
            ),
        ),
        DomainEntity(
            name="application",
            fields=(
                EntityField(name="candidate_id"),
                EntityField(name="opening_id"),
                EntityField(name="stage"),
                EntityField(name="created_at"),
            ),
        ),
        DomainEntity(
            name="interview",
            fields=(
                EntityField(name="application_id"),
                EntityField(name="interviewer"),
                EntityField(name="scheduled_at"),
                EntityField(name="scorecard", aliases=("feedback",)),
            ),
        ),
        DomainEntity(
            name="offer",
            fields=(
                EntityField(name="application_id"),
                EntityField(name="amount"),
                EntityField(name="status"),
                EntityField(name="sent_at"),
            ),
        ),
    ),
    roles=(
        DomainRole(name="recruiter"),
        DomainRole(name="hiring manager", aliases=("manager",)),
        DomainRole(name="candidate", aliases=("applicant",)),
        DomainRole(name="admin", required=False),
    ),
    capabilities=(
        Capability(id="post_opening", label="post opening", aliases=("open vacancy",)),
        Capability(id="apply", label="apply", aliases=("submit cv", "submit application")),
        Capability(id="screen", label="screen candidate", aliases=("screening", "shortlist")),
        Capability(id="schedule", label="schedule interview"),
        Capability(id="score_interview", label="score interview", aliases=("submit feedback", "scorecard")),
        Capability(id="send_offer", label="send offer"),
        Capability(id="reject", label="reject candidate", aliases=("decline candidate",)),
        Capability(id="report_funnel", label="report by stage", severity="medium"),
    ),
    lifecycle_states=(
        LifecycleState(name="new", is_initial=True, aliases=("applied", "submitted")),
        LifecycleState(name="screening", aliases=("phone screen",)),
        LifecycleState(name="interview", aliases=("interviewing",)),
        LifecycleState(name="offer", aliases=("offer extended",)),
        LifecycleState(name="hired", is_terminal=True),
        LifecycleState(name="rejected", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="new", to_state="screening"),
        LifecycleTransition(from_state="screening", to_state="interview"),
        LifecycleTransition(from_state="interview", to_state="offer"),
        LifecycleTransition(from_state="offer", to_state="hired"),
        LifecycleTransition(from_state="screening", to_state="rejected"),
        LifecycleTransition(from_state="interview", to_state="rejected"),
        LifecycleTransition(from_state="offer", to_state="rejected", label="offer declined"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="apply",
            title="Candidate applies to an opening",
            journey_type="onboarding",
            steps=(
                "Candidate sees opening",
                "Candidate submits an application + CV",
                "Application appears in recruiter inbox",
            ),
            expected_outcome="Application persisted with candidate, opening, stage='new'.",
        ),
        AcceptanceScenario(
            id="screen",
            title="Recruiter screens and schedules an interview",
            journey_type="core_action",
            steps=(
                "Recruiter screens application",
                "Application moves to 'screening' or 'rejected'",
                "Interview scheduled with interviewer and time",
            ),
            expected_outcome="Interview entity exists with scorecard placeholder.",
        ),
        AcceptanceScenario(
            id="offer",
            title="Hiring manager extends an offer",
            journey_type="core_action",
            steps=(
                "Application reaches 'offer' stage",
                "Offer entity created with amount",
                "Candidate accepts or declines",
            ),
            expected_outcome="Offer status reflected in application; final state hired/rejected.",
        ),
        AcceptanceScenario(
            id="reject",
            title="Recruiter rejects with reason",
            journey_type="edge_case",
            steps=(
                "Recruiter rejects candidate",
                "Reason captured",
                "Stage updated to 'rejected'",
            ),
            expected_outcome="Rejection reason recorded for funnel reporting.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="GET", path_pattern="/api/openings", purpose="list openings"),
        ApiEndpoint(method="POST", path_pattern="/api/openings/{id}/applications", purpose="submit application"),
        ApiEndpoint(method="POST", path_pattern="/api/applications/{id}/stage", purpose="advance stage"),
        ApiEndpoint(method="POST", path_pattern="/api/applications/{id}/interviews", purpose="schedule interview"),
        ApiEndpoint(method="POST", path_pattern="/api/applications/{id}/offer", purpose="send offer"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="time_to_hire",
            label="time to hire",
            formula="avg(hired_at - applied_at)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="offer_acceptance",
            label="offer acceptance rate",
            formula="accepted_offers / sent_offers",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="funnel_conversion",
            label="pipeline conversion",
            formula="hires / applications",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="candidates_per_opening",
            label="candidates per opening",
            formula="count(applications) / count(openings)",
            target_direction="higher_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="static_jobs_page",
            severity="high",
            description="Static jobs listing only — no application pipeline.",
            keywords=("apply by email only",),
            fix_hint="Add application + stage entities.",
        ),
        RedFlagPattern(
            id="no_stages",
            severity="high",
            description="Applications have no stage tracking.",
            keywords=("no stages", "manual spreadsheet"),
            fix_hint="Track stages from new to hired/rejected.",
        ),
        RedFlagPattern(
            id="no_interview_entity",
            severity="medium",
            description="No interview / scorecard concept.",
            fix_hint="Capture interview events with structured scorecards.",
        ),
    ),
    references=(
        Reference(title="SHRM Talent Acquisition body of knowledge"),
        Reference(title="OFCCP / EEOC compliance guidance"),
        Reference(title="Greenhouse / Lever recruiting workflow patterns"),
    ),
    methodology_notes=(
        "An ATS is judged by funnel integrity (stages), structured interview scoring, "
        "offer/rejection capture and reportable conversion."
    ),
)
