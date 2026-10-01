"""
Healthcare / wellness domain methodology pack.

Even lightweight wellness apps must respect patient consent and audit
access to records. Lifecycle covers scheduled → confirmed → checked-in →
completed with cancelled / no-show as terminal exits. Red flags: no consent,
no audit log, public PHI. Grounded in HIPAA Privacy Rule, GDPR Article 9
(special categories of personal data) and HL7 FHIR baselines.
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


HEALTHCARE_WELLNESS = DomainPack(
    domain_id="healthcare_wellness",
    label="Healthcare / Wellness",
    description=(
        "Patient records, appointments, consent and privacy/audit posture. "
        "Even lightweight wellness apps must respect patient consent and "
        "audit access to records."
    ),
    keywords=(
        "health", "healthcare", "clinic", "patient", "appointment", "telemedicine",
        "wellness", "medical records", "ehr", "phr", "telehealth",
    ),
    categories=("health", "healthcare", "wellness"),
    entities=(
        DomainEntity(
            name="patient",
            fields=(
                EntityField(name="name"),
                EntityField(name="dob", aliases=("date_of_birth",)),
                EntityField(name="contact"),
                EntityField(name="consent_status"),
            ),
        ),
        DomainEntity(
            name="provider",
            aliases=("clinician", "doctor", "therapist"),
            fields=(EntityField(name="name"), EntityField(name="specialty", required=False)),
        ),
        DomainEntity(
            name="appointment",
            aliases=("visit",),
            fields=(
                EntityField(name="patient_id"),
                EntityField(name="provider_id"),
                EntityField(name="status"),
                EntityField(name="scheduled_at"),
                EntityField(name="notes", required=False),
            ),
        ),
        DomainEntity(
            name="record",
            aliases=("medical record", "note", "encounter"),
            fields=(
                EntityField(name="patient_id"),
                EntityField(name="created_by"),
                EntityField(name="created_at"),
                EntityField(name="content"),
            ),
        ),
        DomainEntity(
            name="consent",
            fields=(
                EntityField(name="patient_id"),
                EntityField(name="purpose"),
                EntityField(name="granted_at"),
                EntityField(name="revoked_at", required=False),
            ),
        ),
        DomainEntity(
            name="audit log",
            description="Access log for protected health information.",
            aliases=("phi access log", "audit entry"),
            fields=(
                EntityField(name="actor"),
                EntityField(name="record_id"),
                EntityField(name="action"),
                EntityField(name="created_at"),
            ),
        ),
    ),
    roles=(
        DomainRole(name="patient"),
        DomainRole(name="provider", aliases=("clinician", "doctor")),
        DomainRole(name="admin"),
    ),
    capabilities=(
        Capability(id="register", label="register patient"),
        Capability(id="book", label="book appointment"),
        Capability(id="record_visit", label="record visit"),
        Capability(id="manage_consent", label="manage consent"),
        Capability(id="share_record", label="share record with consent"),
        Capability(id="audit_access", label="audit data access"),
    ),
    lifecycle_states=(
        LifecycleState(name="scheduled", is_initial=True),
        LifecycleState(name="confirmed"),
        LifecycleState(name="checked in"),
        LifecycleState(name="completed", is_terminal=True),
        LifecycleState(name="cancelled", is_terminal=True),
        LifecycleState(name="no-show", is_terminal=True),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="scheduled", to_state="confirmed"),
        LifecycleTransition(from_state="confirmed", to_state="checked in"),
        LifecycleTransition(from_state="checked in", to_state="completed"),
        LifecycleTransition(from_state="scheduled", to_state="cancelled"),
        LifecycleTransition(from_state="confirmed", to_state="cancelled"),
        LifecycleTransition(from_state="confirmed", to_state="no-show"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="register-book",
            title="Patient registers and books an appointment",
            journey_type="onboarding",
            steps=(
                "Patient registers with consent",
                "Patient books appointment with provider",
                "Provider sees appointment scheduled",
            ),
            expected_outcome="Patient + consent + appointment persisted.",
        ),
        AcceptanceScenario(
            id="visit",
            title="Visit is completed and recorded",
            journey_type="core_action",
            steps=(
                "Provider checks patient in",
                "Provider records a visit note",
                "Audit log captures who created the note",
            ),
            expected_outcome="Record + audit log entries exist.",
        ),
        AcceptanceScenario(
            id="consent-revoke",
            title="Patient revokes consent",
            journey_type="compliance",
            steps=(
                "Patient revokes a specific consent",
                "Future sharing is blocked",
                "Audit log records the change",
            ),
            expected_outcome="Consent revocation affects subsequent record sharing.",
        ),
        AcceptanceScenario(
            id="no-show",
            title="Cancellation / no-show handling",
            journey_type="edge_case",
            steps=(
                "Patient cancels appointment",
                "Status moves to 'cancelled'",
                "Provider sees freed slot",
            ),
            expected_outcome="Cancellation/no-show statuses are first-class.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="POST", path_pattern="/api/patients", purpose="register patient"),
        ApiEndpoint(method="POST", path_pattern="/api/appointments", purpose="book appointment"),
        ApiEndpoint(method="POST", path_pattern="/api/appointments/{id}/status", purpose="update status"),
        ApiEndpoint(method="POST", path_pattern="/api/records", purpose="record visit"),
        ApiEndpoint(method="POST", path_pattern="/api/consents", purpose="capture consent"),
        ApiEndpoint(method="GET", path_pattern="/api/audit/logs", purpose="audit access"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="no_show",
            label="no-show rate",
            formula="no_shows / scheduled",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="wait_time",
            label="average wait time",
            formula="avg(checked_in_at - scheduled_at)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="follow_up_adherence",
            label="follow-up adherence",
            formula="completed_follow_ups / scheduled_follow_ups",
            target_direction="higher_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="no_consent",
            severity="high",
            description="Patient data persisted without consent / privacy concept.",
            keywords=("no consent", "share without consent"),
            fix_hint="Add consent entity gating record sharing.",
        ),
        RedFlagPattern(
            id="no_audit_log",
            severity="high",
            description="No audit log of record access.",
            keywords=("no audit log",),
            fix_hint="Audit who accessed which record and when.",
        ),
        RedFlagPattern(
            id="open_phi",
            severity="high",
            description="PHI accessible without authentication.",
            keywords=("public records",),
            regex=(r"public\s+phi", r"unauthenticated\s+access"),
            fix_hint="Authenticate and authorise access to all PHI.",
        ),
    ),
    references=(
        Reference(title="HIPAA Privacy Rule"),
        Reference(title="GDPR Article 9 (special categories)"),
        Reference(title="HL7 FHIR baseline"),
    ),
    methodology_notes=(
        "Healthcare/wellness products are judged by consent + audit + status of "
        "encounters, regardless of how lightweight the UI is."
    ),
)
