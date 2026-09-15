"""Tests for acceptance-criteria traceability heuristics in QA."""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.qa import QAAgent


def _mk():
    return QAAgent(llm_router=MagicMock())


def test_acceptance_traceability_fails_without_tests():
    qa = _mk()
    spec = {
        "specification": {
            "user_stories": [
                {"story": "As user", "acceptance_criteria": "User can register with email and password"},
            ],
            "functional_requirements": [
                {"id": "FR-01", "acceptance_criteria": "System stores profile and returns account details"},
            ],
        }
    }
    rep = qa._assess_acceptance_traceability(spec, code_files=[])
    assert rep["passed"] is False
    assert rep["criteria_total"] == 2


def test_acceptance_traceability_passes_with_keyword_coverage():
    qa = _mk()
    spec = {
        "specification": {
            "user_stories": [
                {"story": "As user", "acceptance_criteria": "User can register with email and password"},
                {"story": "As user", "acceptance_criteria": "User can update profile details"},
            ],
            "functional_requirements": [
                {"id": "FR-01", "acceptance_criteria": "System stores profile and returns account details"},
                {"id": "FR-02", "acceptance_criteria": "Login endpoint validates password and issues token"},
            ],
        }
    }
    code_files = [
        {
            "path": "/tmp/prod/tests/test_auth.py",
            "content": (
                "def test_register_email_password():\n"
                "    assert True\n\n"
                "def test_login_validates_password_token():\n"
                "    assert True\n"
            ),
        },
        {
            "path": "/tmp/prod/tests/test_profile.py",
            "content": "def test_update_profile_details():\n    assert True\n",
        },
    ]
    rep = qa._assess_acceptance_traceability(spec, code_files=code_files)
    assert rep["passed"] is True
    assert rep["covered"] >= 2
