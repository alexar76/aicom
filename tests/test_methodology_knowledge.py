"""Tests for the methodology knowledge store + search/learn loop."""

from __future__ import annotations

from pathlib import Path

from web.backend.services.methodology_knowledge import (
    MethodologyCase,
    MethodologyKnowledgeStore,
    MethodologyLesson,
)


def _store(tmp_path: Path) -> MethodologyKnowledgeStore:
    return MethodologyKnowledgeStore(data_root=str(tmp_path))


def test_lesson_crud_and_search(tmp_path):
    store = _store(tmp_path)
    lesson = store.add_lesson(
        MethodologyLesson(
            id="",
            domain="helpdesk_support",
            severity="high",
            title="No SLA timer",
            detail="Tickets without SLA escape the queue.",
            keywords=["no sla timer", "sla=null"],
            applies_to=["spec", "implementation"],
        )
    )
    assert lesson.id, "lesson id is auto-generated"
    listed = store.list_lessons(domain="helpdesk_support")
    assert len(listed) == 1 and listed[0].title == "No SLA timer"

    found = store.find_lessons_for("Our tickets have no sla timer at all", domain="helpdesk_support", stage="spec")
    assert len(found) == 1 and found[0].id == lesson.id

    updated = store.update_lesson(lesson.id, severity="medium", enabled=False)
    assert updated and updated.severity == "medium" and updated.enabled is False

    assert store.delete_lesson(lesson.id) is True
    assert store.list_lessons(domain="helpdesk_support") == []


def test_case_history_and_feedback_promotes_lesson(tmp_path):
    store = _store(tmp_path)
    case = store.append_case(
        MethodologyCase(
            case_id="case-1",
            product_id="prod-X",
            stage="post_implementation",
            domain="helpdesk_support",
            score=42,
            passed=False,
            findings=[
                {
                    "severity": "high",
                    "code": "domain_capability_missing",
                    "detail": "missing assign ticket and escalate",
                    "fix_hint": "implement the ticket assignment flow",
                }
            ],
        )
    )
    assert case.case_id == "case-1"
    history = store.get_case_history("prod-X")
    assert len(history) == 1

    entry = store.record_feedback(
        case_id="case-1",
        product_id="prod-X",
        was_correct=True,
        notes="confirmed gap",
        promote_finding_code="domain_capability_missing",
    )
    assert entry["promoted_lesson_id"]

    promoted = store.list_lessons(domain="helpdesk_support")
    assert len(promoted) == 1
    assert promoted[0].source == "auto"
    assert "implementation" in promoted[0].applies_to


def test_search_returns_lessons_and_cases(tmp_path):
    store = _store(tmp_path)
    store.add_lesson(
        MethodologyLesson(
            id="",
            domain="ecommerce",
            severity="high",
            title="No payment step",
            detail="Storefront must always capture payment before fulfilment.",
            keywords=["no payment step"],
        )
    )
    store.append_case(
        MethodologyCase(
            case_id="case-9",
            product_id="prod-9",
            stage="post_implementation",
            domain="ecommerce",
            score=10,
            passed=False,
            findings=[{"code": "red_flag:no_payment_step", "detail": "no payment captured"}],
        )
    )
    res = store.search("payment", kinds=("lessons", "cases"))
    assert any(l["title"] == "No payment step" for l in res["lessons"])
    assert any(c["case_id"] == "case-9" for c in res["cases"])
