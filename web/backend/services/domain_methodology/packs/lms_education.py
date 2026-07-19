"""
LMS / Education domain methodology pack.

A learning management system is judged by enrollment + progress + assessment
integrity (instructor authors a course → student enrolls → completes lessons
→ takes assessment → passes), not by how nicely the catalog renders. Aligned
with IMS Caliper Analytics, SCORM 2004 / xAPI, and the Quality Matters rubric.
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


LMS_EDUCATION = DomainPack(
    domain_id="lms_education",
    label="LMS / Education",
    description=(
        "Course delivery platform with enrollment, lessons, progress and assessment. "
        "Real LMS products support instructor authoring, learner enrollment, "
        "lesson completion tracking, and graded assessment."
    ),
    keywords=(
        "lms", "learning management", "course platform", "lesson", "module",
        "curriculum", "education platform", "student progress", "quiz", "assessment",
    ),
    categories=("education", "lms", "training"),
    entities=(
        DomainEntity(
            name="course",
            fields=(
                EntityField(name="title"),
                EntityField(name="description"),
                EntityField(name="instructor"),
                EntityField(name="status"),
                EntityField(name="lessons", aliases=("modules",)),
            ),
        ),
        DomainEntity(
            name="lesson",
            aliases=("module", "unit"),
            fields=(
                EntityField(name="course_id"),
                EntityField(name="order"),
                EntityField(name="content"),
                EntityField(name="duration_min", required=False),
            ),
        ),
        DomainEntity(
            name="enrollment",
            fields=(
                EntityField(name="student_id"),
                EntityField(name="course_id"),
                EntityField(name="status"),
                EntityField(name="enrolled_at"),
            ),
        ),
        DomainEntity(
            name="progress",
            fields=(
                EntityField(name="student_id"),
                EntityField(name="lesson_id"),
                EntityField(name="completed"),
                EntityField(name="completed_at", required=False),
            ),
        ),
        DomainEntity(
            name="assessment",
            aliases=("quiz", "exam", "assignment"),
            fields=(
                EntityField(name="course_id"),
                EntityField(name="questions"),
                EntityField(name="pass_threshold"),
            ),
        ),
        DomainEntity(
            name="assessment_attempt",
            aliases=("submission",),
            fields=(
                EntityField(name="student_id"),
                EntityField(name="assessment_id"),
                EntityField(name="score"),
                EntityField(name="passed"),
            ),
        ),
    ),
    roles=(
        DomainRole(name="student", aliases=("learner",)),
        DomainRole(name="instructor", aliases=("teacher", "author")),
        DomainRole(name="admin"),
    ),
    capabilities=(
        Capability(id="browse", label="browse catalog"),
        Capability(id="enroll", label="enroll", aliases=("enrol",)),
        Capability(id="view_lesson", label="view lesson"),
        Capability(id="complete_lesson", label="track lesson completion", aliases=("mark complete",)),
        Capability(id="take_assessment", label="take quiz", aliases=("take assessment", "submit assignment")),
        Capability(id="view_results", label="view results"),
        Capability(id="issue_certificate", label="issue certificate", severity="medium"),
        Capability(id="author_course", label="author course", aliases=("create course",)),
    ),
    lifecycle_states=(
        LifecycleState(name="draft course", is_initial=True, aliases=("draft",)),
        LifecycleState(name="published"),
        LifecycleState(name="enrolled"),
        LifecycleState(name="in progress", aliases=("studying",)),
        LifecycleState(name="completed"),
        LifecycleState(name="certified", is_terminal=True, aliases=("graduated",)),
    ),
    lifecycle_transitions=(
        LifecycleTransition(from_state="draft course", to_state="published"),
        LifecycleTransition(from_state="published", to_state="enrolled"),
        LifecycleTransition(from_state="enrolled", to_state="in progress"),
        LifecycleTransition(from_state="in progress", to_state="completed"),
        LifecycleTransition(from_state="completed", to_state="certified", label="pass assessment"),
    ),
    acceptance_scenarios=(
        AcceptanceScenario(
            id="author-course",
            title="Instructor creates and publishes a course",
            journey_type="onboarding",
            steps=(
                "Instructor creates a course",
                "Instructor adds lessons and an assessment",
                "Instructor publishes the course",
            ),
            expected_outcome="Course visible to students with at least one lesson and assessment.",
        ),
        AcceptanceScenario(
            id="learn-flow",
            title="Student enrolls and completes a course",
            journey_type="core_action",
            steps=(
                "Student enrolls in a published course",
                "Student opens lessons and marks them complete",
                "Student takes the assessment and passes",
            ),
            expected_outcome="Progress and assessment results recorded; course shows 'completed'.",
        ),
        AcceptanceScenario(
            id="failed-attempt",
            title="Failed attempt allows retry",
            journey_type="recovery",
            steps=(
                "Student fails an assessment",
                "Student is allowed a retry (or remediation lesson)",
                "Student passes on the second attempt",
            ),
            expected_outcome="Retry flow exists; failed attempt is recorded but not terminal.",
        ),
        AcceptanceScenario(
            id="report",
            title="Instructor sees per-lesson drop-off",
            journey_type="reporting",
            severity="medium",
            steps=(
                "Instructor opens course analytics",
                "Drop-off by lesson is visible",
            ),
            expected_outcome="Completion metric available per lesson.",
        ),
    ),
    api_endpoints=(
        ApiEndpoint(method="GET", path_pattern="/api/courses", purpose="catalog"),
        ApiEndpoint(method="POST", path_pattern="/api/courses", purpose="create course"),
        ApiEndpoint(method="POST", path_pattern="/api/courses/{id}/enroll", purpose="enrollment"),
        ApiEndpoint(method="POST", path_pattern="/api/lessons/{id}/complete", purpose="track completion"),
        ApiEndpoint(method="POST", path_pattern="/api/assessments/{id}/attempt", purpose="submit attempt"),
        ApiEndpoint(method="GET", path_pattern="/api/students/{id}/progress", purpose="progress report"),
    ),
    process_metrics_definitions=(
        ProcessMetric(
            id="completion_rate",
            label="completion rate",
            formula="completed_courses / enrollments",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="avg_score",
            label="average score",
            formula="avg(assessment_score)",
            target_direction="higher_is_better",
        ),
        ProcessMetric(
            id="time_to_complete",
            label="time to complete",
            formula="avg(completed_at - enrolled_at)",
            target_direction="lower_is_better",
        ),
        ProcessMetric(
            id="drop_off",
            label="drop-off by lesson",
            formula="lesson_starts - lesson_completes",
            target_direction="lower_is_better",
        ),
    ),
    red_flags=(
        RedFlagPattern(
            id="static_pages",
            severity="high",
            description="Course is a static webpage with no enrollment / progress.",
            keywords=("static course page", "html only course"),
            fix_hint="Add enrollment and progress tracking entities.",
        ),
        RedFlagPattern(
            id="no_assessment",
            severity="medium",
            description="No assessment / quiz support.",
            keywords=("no quiz", "no assessment"),
            fix_hint="Add at least quiz / assignment with scoring.",
        ),
        RedFlagPattern(
            id="no_progress",
            severity="high",
            description="No per-student progress.",
            keywords=("no progress tracking",),
            regex=(r"\bprogress\s*=\s*null\b",),
            fix_hint="Persist completion records per student per lesson.",
        ),
    ),
    references=(
        Reference(title="IMS Caliper Analytics specification"),
        Reference(title="SCORM 2004 / xAPI"),
        Reference(title="QM (Quality Matters) higher-ed rubric"),
    ),
    methodology_notes=(
        "An LMS is judged by enrollment + progress + assessment integrity, "
        "not by how nicely course pages render."
    ),
)
