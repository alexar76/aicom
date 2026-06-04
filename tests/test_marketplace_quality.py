"""Marketplace listing quality — stub demos must not be public storefront catalog."""

from __future__ import annotations

import json

import pytest

from web.backend.services.marketplace_quality import evaluate_marketplace_quality

# A storefront-ready full_software code tree: a ≥400-byte sandbox-ready front page,
# real CSS, a FastAPI app-stack signal, and a code manifest. This clears the upstream
# gates (storefront_front_page_ready + full_software_storefront_preview_capable) so a
# test can exercise the *specific* downstream gate it targets.
_READY_INDEX_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>CloudOps</title><link href="./style.css" rel="stylesheet"/></head>
<body><main><h1>CloudOps Dashboard</h1>
<p>Task management for teams who need reliability, with analytics every day.</p>
<section id="dash"><h2>Dashboard</h2><p>Analytics dashboard with live metrics and alerts.</p></section>
<section id="env"><h2>Environments</h2><p>Staging and production environment tracking for teams.</p></section>
<a href="#env">Environments</a><footer><p>Contact and onboarding for new users.</p></footer>
<button type="button">Get started</button></main></body></html>"""

_READY_CSS = """:root{--bg:#020617;--fg:#e2e8f0;--accent:#38bdf8}
body{background:var(--bg);color:var(--fg);font-family:system-ui,sans-serif;margin:0}
main{max-width:760px;margin:0 auto;padding:24px}
button:focus-visible{outline:3px solid var(--accent)}@media(max-width:720px){main{padding:16px}}"""


def _seed_ready_code(code_dir):
    """Write a storefront-ready full_software tree (front page + app stack + manifest)."""
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "index.html").write_text(_READY_INDEX_HTML, encoding="utf-8")
    (code_dir / "style.css").write_text(_READY_CSS, encoding="utf-8")
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    import json as _json

    (code_dir / "code_manifest.json").write_text(
        _json.dumps({"files": [{"path": p} for p in ("index.html", "style.css", "main.py")]}),
        encoding="utf-8",
    )


def test_marketplace_rejects_stub_html(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.delenv("AIFACTORY_MARKETPLACE_REQUIRE_FULL_QA", raising=False)
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-stub-test"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    # Openable (≥400 bytes, valid HTML → passes the front-page gate) but a low-quality
    # stub: no sections, no CTA, no styling → fails the demo quality gate.
    stub_body = "<p>Full application deployed. Admin panel placeholder copy. </p>" * 12
    (code / "index.html").write_text(
        f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\" />"
        f"<title>Admin</title></head><body>{stub_body}</body></html>",
        encoding="utf-8",
    )
    # App-stack signal so the full_software preview gate passes and evaluation reaches
    # the demo quality gate.
    (code / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (code / "code_manifest.json").write_text(
        json.dumps({"files": [{"path": "index.html"}, {"path": "main.py"}]}), encoding="utf-8"
    )
    spec_path = tmp_path / "specs" / pid
    spec_path.mkdir(parents=True)
    inner = {
        "specification": {
            "product_name": "X",
            "description": "Task management for teams who need reliability",
            "core_features": [{"name": "Dashboard", "description": "Main dashboard"}],
        }
    }
    (spec_path / "specification.json").write_text(json.dumps(inner), encoding="utf-8")

    spec_inner = inner["specification"]
    ev = evaluate_marketplace_quality(pid, specification=spec_inner, data_root=str(tmp_path))
    assert ev["eligible"] is False
    # A content stub is rejected on demo-quality grounds. The front-page gate (which runs
    # the same demo assessment) now catches stubs first, so accept any of the equivalent
    # quality signals rather than over-specifying a single gate.
    quality_reasons = {
        "demo_quality_gates_failed",
        "front_page_not_sandbox_ready",
        "marketing_stub",
        "ux_structure_thin",
        "ux_missing_cta",
    }
    assert quality_reasons & set(ev["reasons"]), ev["reasons"]


def test_marketplace_accepts_solid_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-good-test"
    code = tmp_path / "code" / pid
    _seed_ready_code(code)

    spec_inner = {
        "product_name": "CloudOps",
        "description": "Task management for teams who need reliability",
        "core_features": [
            {"name": "Dashboard", "description": "Main dashboard with metrics"},
            {"name": "Environments", "description": "Environment management"},
        ],
    }
    spec_path = tmp_path / "specs" / pid
    spec_path.mkdir(parents=True)
    (spec_path / "specification.json").write_text(
        json.dumps({"specification": spec_inner}), encoding="utf-8"
    )

    ev = evaluate_marketplace_quality(pid, specification=spec_inner, data_root=str(tmp_path))
    assert ev["eligible"] is True
    assert ev["demo_quality"]["score"] >= 55


def test_require_full_qa_blocks_without_telemetry(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_FULL_QA", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-no-tel"
    code = tmp_path / "code" / pid
    _seed_ready_code(code)

    spec_inner = {
        "description": "Task management for teams who need reliability and dashboards every day",
        "core_features": [
            {"name": "Dashboard", "description": "Analytics dashboard with live metrics"},
            {"name": "Environments", "description": "Staging and production environment tracking"},
        ],
    }
    spec_path = tmp_path / "specs" / pid
    spec_path.mkdir(parents=True)
    (spec_path / "specification.json").write_text(
        json.dumps({"specification": spec_inner}), encoding="utf-8"
    )

    ev = evaluate_marketplace_quality(pid, specification=spec_inner, data_root=str(tmp_path))
    assert ev["eligible"] is False
    assert "pipeline_qa_gates_not_passed_or_missing_telemetry" in ev["reasons"]


def test_marketplace_rejects_low_design_novelty_when_available(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_DESIGN_NOVELTY", "0.18")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-low-novelty"
    code = tmp_path / "code" / pid
    _seed_ready_code(code)

    # Minimal architecture artifact with low novelty score.
    arch = tmp_path / "arch" / pid
    arch.mkdir(parents=True)
    (arch / "architecture.json").write_text(
        json.dumps({"architecture": {"architecture_name": "x"}, "novelty_score": 0.12}),
        encoding="utf-8",
    )

    spec_inner = {"description": "A product", "core_features": [{"name": "Start", "description": "Start flow"}]}
    ev = evaluate_marketplace_quality(pid, specification=spec_inner, data_root=str(tmp_path))
    assert ev["eligible"] is False
    assert "design_novelty_below_marketplace_minimum" in ev["reasons"]


def test_marketplace_rejects_high_severity_qa_realism_findings(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_QA_REALISM", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-qa-realism-fail"
    code = tmp_path / "code" / pid
    _seed_ready_code(code)

    bugs = tmp_path / "bugs" / pid
    bugs.mkdir(parents=True)
    (bugs / "qa_report.json").write_text(
        json.dumps(
            {
                "qa_result": {
                    "bugs_found": [
                        {
                            "severity": "high",
                            "title": "Backend realism: constant-only API responses",
                            "description": "stub",
                        }
                    ],
                    "security_issues": [],
                }
            }
        ),
        encoding="utf-8",
    )

    spec_inner = {"description": "A product", "core_features": [{"name": "Start", "description": "Start flow"}]}
    ev = evaluate_marketplace_quality(pid, specification=spec_inner, data_root=str(tmp_path))
    assert ev["eligible"] is False
    assert "qa_realism_high_severity_failed" in ev["reasons"]


def test_marketplace_rejects_low_release_score_when_available(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_RELEASE_SCORE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_RELEASE_SCORE", "70")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_QA_REALISM", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-low-release-score"
    code = tmp_path / "code" / pid
    _seed_ready_code(code)

    bugs = tmp_path / "bugs" / pid
    bugs.mkdir(parents=True)
    (bugs / "qa_report.json").write_text(
        json.dumps({"qa_result": {"release_score": 42, "bugs_found": [], "security_issues": []}}),
        encoding="utf-8",
    )

    spec_inner = {"description": "A product", "core_features": [{"name": "Start", "description": "Start flow"}]}
    ev = evaluate_marketplace_quality(pid, specification=spec_inner, data_root=str(tmp_path))
    assert ev["eligible"] is False
    assert "release_score_below_marketplace_minimum" in ev["reasons"]
