"""Marketplace listing quality — stub demos must not be public storefront catalog."""

from __future__ import annotations

import json

import pytest

from web.backend.services.marketplace_quality import evaluate_marketplace_quality


def test_marketplace_rejects_stub_html(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.delenv("AIFACTORY_MARKETPLACE_REQUIRE_FULL_QA", raising=False)
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-stub-test"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    (code / "index.html").write_text(
        "<!DOCTYPE html><html><body>Full application deployed. Admin panel.</body></html>",
        encoding="utf-8",
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
    assert "demo_quality_gates_failed" in ev["reasons"]


def test_marketplace_accepts_solid_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")

    pid = "prod-good-test"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!DOCTYPE html><html><head><title>T</title><link rel="stylesheet" href="./style.css"/></head>
<body><main><h1>CloudOps Dashboard</h1><p>Task management for teams who need reliability.</p>
<section><h2>Dashboard</h2><p>Main dashboard with metrics.</p></section>
<section id="env"><h2>Environments</h2><p>Environment management for production workflows.</p></section>
<a href="#env">Environments</a><button type="button">Save</button></main></body></html>"""
    (code / "index.html").write_text(html, encoding="utf-8")
    (code / "style.css").write_text("body{font-family:sans-serif}", encoding="utf-8")

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
    code.mkdir(parents=True)
    html = """<!DOCTYPE html><html><head><title>ShipReady</title><link href="./app.css" rel="stylesheet"/></head>
<body><main><h1>ShipReady Control</h1>
<p>Task management for teams who need reliability and dashboards every day.</p>
<section><h2>Dashboard</h2><p>Analytics dashboard with live metrics and alerts.</p></section>
<section><h2>Environments</h2><p>Staging and production environment tracking.</p></section>
<button type="button">Deploy</button></main></body></html>"""
    (code / "index.html").write_text(html, encoding="utf-8")
    (code / "app.css").write_text("main { max-width: 720px; margin: 0 auto; }", encoding="utf-8")

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
    code.mkdir(parents=True)
    html = """<!DOCTYPE html><html><head><title>A Product</title><link rel="stylesheet" href="./app.css"/></head>
    <body><main><h1>A product</h1><p>A serious product page with meaningful structure and copy.</p>
    <section><h2>Value</h2><p>Solid copy about benefits and outcomes for users.</p></section>
    <section><h2>How it works</h2><p>Step-by-step onboarding details and feature highlights.</p></section>
    <button type="button">Start</button></main></body></html>"""
    (code / "index.html").write_text(html, encoding="utf-8")
    (code / "app.css").write_text("main { max-width: 760px; margin: 0 auto; }", encoding="utf-8")

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
    code.mkdir(parents=True)
    html = """<!DOCTYPE html><html><head><title>T</title></head>
<body><main><h1>CloudOps Dashboard</h1>
<p>Task management for teams who need reliability.</p>
<section><h2>Dashboard</h2><p>Main dashboard with metrics.</p></section>
<section><h2>How it works</h2><p>One two three.</p></section>
<button type="button">Start</button></main></body></html>"""
    (code / "index.html").write_text(html, encoding="utf-8")

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
    code.mkdir(parents=True)
    html = """<!DOCTYPE html><html><head><title>T</title></head>
<body><main><h1>CloudOps Dashboard</h1>
<p>Task management for teams who need reliability.</p>
<section><h2>Dashboard</h2><p>Main dashboard with metrics.</p></section>
<section><h2>How it works</h2><p>One two three.</p></section>
<button type="button">Start</button></main></body></html>"""
    (code / "index.html").write_text(html, encoding="utf-8")

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
