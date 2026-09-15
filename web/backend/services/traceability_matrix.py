"""
Feature -> requirement -> story traceability matrix.
"""

from __future__ import annotations

from typing import Any


def build_traceability_matrix(spec_payload: dict[str, Any]) -> dict[str, Any]:
    spec = spec_payload.get("specification") if isinstance(spec_payload, dict) and "specification" in spec_payload else spec_payload
    if not isinstance(spec, dict):
        spec = {}
    features = spec.get("core_features") or []
    frs = spec.get("functional_requirements") or []
    stories = spec.get("user_stories") or []
    rows = []
    for idx, feat in enumerate(features):
        fname = str(feat.get("name") if isinstance(feat, dict) else feat or f"Feature {idx+1}").strip()
        fr_id = None
        if idx < len(frs) and isinstance(frs[idx], dict):
            fr_id = frs[idx].get("id") or f"FR-{idx+1:02d}"
        story = None
        if idx < len(stories) and isinstance(stories[idx], dict):
            story = stories[idx].get("story")
        rows.append(
            {
                "feature": fname,
                "functional_requirement_id": fr_id,
                "user_story": story,
                "expected_test_id": f"T-{idx+1:02d}",
            }
        )
    return {
        "rows": rows,
        "feature_count": len(features),
        "coverage_ratio": round(len(rows) / max(1, len(features)), 3),
        "passed": len(rows) >= max(1, min(3, len(features))) if features else False,
    }
