from web.backend.services.traceability_matrix import build_traceability_matrix


def test_traceability_matrix_builds_rows():
    spec = {
        "specification": {
            "core_features": [{"name": "Upload"}, {"name": "Search"}],
            "functional_requirements": [{"id": "FR-01"}, {"id": "FR-02"}],
            "user_stories": [{"story": "As user upload"}, {"story": "As user search"}],
        }
    }
    rep = build_traceability_matrix(spec)
    assert rep["feature_count"] == 2
    assert len(rep["rows"]) == 2
    assert rep["passed"] is True
