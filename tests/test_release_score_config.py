"""Tests for env-configurable release score weights."""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.qa import QAAgent


def _mk() -> QAAgent:
    return QAAgent(llm_router=MagicMock())


def test_release_score_env_weights_affect_result(monkeypatch):
    qa = _mk()
    base = qa._compute_release_score(
        code_quality_score=80,
        demo_report={"score": 80},
        browser_ok=True,
        backend_ok=True,
        acceptance_report={"passed": True},
        bug_count=0,
        security_count=0,
        tests_total=10,
        tests_failed=0,
    )

    # Increase security penalty heavily; score should drop with same inputs when security_count > 0
    monkeypatch.setenv("AIFACTORY_RELEASE_SCORE_SECURITY_WEIGHT", "10")
    with_sec_penalty = qa._compute_release_score(
        code_quality_score=80,
        demo_report={"score": 80},
        browser_ok=True,
        backend_ok=True,
        acceptance_report={"passed": True},
        bug_count=0,
        security_count=2,
        tests_total=10,
        tests_failed=0,
    )
    assert with_sec_penalty < base


def test_release_score_handles_invalid_env(monkeypatch):
    qa = _mk()
    monkeypatch.setenv("AIFACTORY_RELEASE_SCORE_CODE_WEIGHT", "not-a-number")
    score = qa._compute_release_score(
        code_quality_score=70,
        demo_report={"score": 70},
        browser_ok=False,
        backend_ok=False,
        acceptance_report={"passed": False},
        bug_count=3,
        security_count=1,
        tests_total=0,
        tests_failed=0,
    )
    assert isinstance(score, int)
    assert 0 <= score <= 100
