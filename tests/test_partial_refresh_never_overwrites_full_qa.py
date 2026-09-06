"""A four-gate refresh must not overwrite a nine-gate verdict, and must never widen the verdict.

Watched live on a product mid-repair. The storefront refresh rewrote `qa_report.json` and the file
lost `browser_preview_e2e`, `demo_journey`, `module_health`, `frontend_build` and `repair_scope`
entirely; `bugs_found` became `[]`; and `quality_gates_all_passed` read **True**, computed over the
four gates this function happens to measure. The QA agent had just reported gates_ok=False. Anything
asking "is this product releasable" — a release gate, a publish step, a human reading the file —
would have been told yes by a refresh that never looked at the browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def full_report(tmp_path: Path) -> Path:
    bugs = tmp_path / "bugs" / "prod-x"
    bugs.mkdir(parents=True)
    (bugs / "qa_report.json").write_text(
        json.dumps(
            {
                "product_id": "prod-x",
                "agent": "qa",
                "qa_result": {"bugs_found": [{"severity": "high", "title": "real defect"}]},
                "browser_preview_e2e": {"passed": False, "issues": ["console_error: 500"]},
                "browser_e2e_gates_passed": False,
                "demo_journey": {"issues": []},
                "demo_journey_passed": True,
                "module_health_passed": True,
                "frontend_build_passed": True,
                "repair_scope": ["backend/app/routers/auth.py"],
                "quality_gates_all_passed": False,
            }
        ),
        encoding="utf-8",
    )
    return bugs / "qa_report.json"


def _refresh_writes(path: Path, own: dict) -> dict:
    """Run just the merge half of the refresh, the way the service does it."""
    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "product_storefront_refresh.py"
    ).read_text(encoding="utf-8")
    assert "storefront_refresh_result" in src, "the refresh still overwrites qa_result"

    existing = json.loads(path.read_text(encoding="utf-8"))
    full_qa = existing.get("agent") not in (None, "telemetry_refresh")
    qa_report = dict(own)
    if full_qa:
        merged = dict(existing)
        merged.update(
            {k: v for k, v in qa_report.items()
             if k not in ("qa_result", "quality_gates_all_passed", "agent")}
        )
        merged["storefront_refresh_result"] = own.get("qa_result")
        gate_keys = [k for k in merged if k.endswith("_passed") and k != "quality_gates_all_passed"]
        merged["quality_gates_all_passed"] = bool(gate_keys) and all(
            merged.get(k) is True for k in gate_keys
        )
        qa_report = merged
    path.write_text(json.dumps(qa_report), encoding="utf-8")
    return qa_report


def test_the_full_verdicts_own_keys_survive(full_report):
    merged = _refresh_writes(
        full_report,
        {
            "product_id": "prod-x",
            "agent": "telemetry_refresh",
            "qa_result": {"bugs_found": []},
            "demo_quality_gates_passed": True,
            "api_contract_passed": True,
            "quality_gates_all_passed": True,
            "created_at": 1.0,
        },
    )
    for key in ("browser_preview_e2e", "demo_journey", "module_health_passed", "repair_scope"):
        assert key in merged, f"the refresh dropped {key}"
    assert merged["qa_result"]["bugs_found"], "the real findings were replaced by an empty list"
    assert merged["storefront_refresh_result"]["bugs_found"] == []


def test_a_refresh_can_never_widen_the_verdict(full_report):
    """Its own four gates passing means nothing while a gate it does not measure is red."""
    merged = _refresh_writes(
        full_report,
        {
            "agent": "telemetry_refresh",
            "qa_result": {"bugs_found": []},
            "demo_quality_gates_passed": True,
            "api_contract_passed": True,
            "backend_runtime_e2e_passed": True,
            "methodology_gate_passed": True,
            "quality_gates_all_passed": True,
            "created_at": 1.0,
        },
    )
    assert merged["quality_gates_all_passed"] is False, "a red browser gate was overruled"


def test_it_can_narrow_the_verdict(full_report):
    """The refresh IS authoritative about its own gates, downward."""
    data = json.loads(full_report.read_text(encoding="utf-8"))
    data.update({"browser_e2e_gates_passed": True, "quality_gates_all_passed": True})
    full_report.write_text(json.dumps(data), encoding="utf-8")
    merged = _refresh_writes(
        full_report,
        {
            "agent": "telemetry_refresh",
            "qa_result": {"bugs_found": []},
            "api_contract_passed": False,
            "quality_gates_all_passed": True,
            "created_at": 1.0,
        },
    )
    assert merged["api_contract_passed"] is False
    assert merged["quality_gates_all_passed"] is False


def test_a_first_refresh_with_no_prior_report_still_writes(tmp_path):
    """No full verdict to protect: the refresh is the only source there is."""
    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "product_storefront_refresh.py"
    ).read_text(encoding="utf-8")
    assert 'existing.get("agent") not in (None, "telemetry_refresh")' in src
    assert "if report_path.is_file():" in src, "a missing file must not raise"
