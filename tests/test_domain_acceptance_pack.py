from web.backend.services.domain_acceptance_pack import build_domain_acceptance_pack


def test_domain_acceptance_pack_builds_scenarios():
    spec = {
        "specification": {
            "delivery_profile": "full_software",
            "user_stories": [
                {"story": "As user", "acceptance_criteria": "User can register with email and password."},
                {"story": "As user", "acceptance_criteria": "User can login and view dashboard."},
            ],
            "functional_requirements": [
                {"id": "FR-01", "title": "Register", "acceptance_criteria": "System stores account and returns profile."},
            ],
        }
    }
    rep = build_domain_acceptance_pack(spec)
    assert rep["scenario_count"] >= 3
    assert rep["minimum_required"] == 3
    assert rep["passed"] is False
    assert "edge_case" in rep["missing_journeys"]
    assert "recovery" in rep["missing_journeys"]


def test_domain_acceptance_pack_requires_full_journey_coverage():
    spec = {
        "specification": {
            "delivery_profile": "full_software",
            "user_stories": [
                {"story": "As user", "acceptance_criteria": "User can register account and login to dashboard."},
            ],
            "functional_requirements": [
                {"id": "FR-01", "title": "Analyze", "acceptance_criteria": "System can upload CSV and analyze sentiment."},
                {"id": "FR-02", "title": "Validation", "acceptance_criteria": "System rejects invalid payload with clear error."},
                {"id": "FR-03", "title": "Recovery", "acceptance_criteria": "System can retry and recover after timeout."},
            ],
        }
    }
    rep = build_domain_acceptance_pack(spec)
    assert rep["scenario_count"] >= 4
    assert rep["missing_journeys"] == []
    assert rep["passed"] is True
