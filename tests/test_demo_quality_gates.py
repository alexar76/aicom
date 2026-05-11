"""Tests for demo/sandbox quality gates (pipeline QA integration)."""

from __future__ import annotations

import pytest

from web.backend.services.browser_preview_e2e import run_browser_preview_e2e
from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass


def test_quality_gates_pass_min_score(monkeypatch):
    monkeypatch.setenv("AIFACTORY_DEMO_QUALITY_MIN_SCORE", "55")
    r = {
        "score": 60,
        "has_index_html": True,
        "issues": [],
    }
    assert quality_gates_pass(r) is True

    r2 = {**r, "score": 40}
    assert quality_gates_pass(r2) is False


def test_quality_gates_fail_placeholder():
    r = assess_product_demo(
        "nonexistent-prod-xyz",
        {"core_features": [{"name": "API", "description": "x"}]},
    )
    # No code dir
    assert quality_gates_pass(r) is False


def test_assess_detects_stub_phrase(tmp_path):
    pid = "prod-gate-test"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    bad_html = """<!DOCTYPE html><html><head><title>t</title></head><body>
    Full application deployed. Check the admin panel for details.
    </body></html>"""
    (code / "index.html").write_text(bad_html)
    spec = {"description": "hello world product", "core_features": [{"name": "Auth"}]}
    rep = assess_product_demo(pid, spec, data_root=str(tmp_path))
    assert any(i.get("code") == "marketing_stub" for i in rep["issues"])
    assert quality_gates_pass(rep) is False


def test_browser_e2e_disabled(monkeypatch):
    monkeypatch.setenv("AIFACTORY_BROWSER_E2E", "0")
    r = run_browser_preview_e2e("any", "/nonexistent")
    assert r.get("skipped") is True
    assert r.get("passed") is True


def test_assess_detects_missing_cta_and_thin_structure(tmp_path):
    pid = "prod-ux-thin"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><body>
    <section><h1>Product</h1><p>Just text</p></section>
    </body></html>"""
    (code / "index.html").write_text(html)
    rep = assess_product_demo(pid, {"description": "landing page"}, data_root=str(tmp_path))
    codes = {i.get("code") for i in rep["issues"]}
    assert "ux_missing_cta" in codes
    assert quality_gates_pass(rep) is False


def test_assess_detects_low_contrast_cta_gradient_fill_dark_label(tmp_path):
    """Gradient CTAs must not skip contrast — first hex stop approximates fill (regression)."""
    pid = "prod-contrast-gradient"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><head><title>x</title></head><body>
    <section><h1>HealthIQ</h1><a class="btn cta" href="#pricing">Start Free Trial</a></section>
    </body></html>"""
    css = (
        ".btn.cta {\n"
        "  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);\n"
        "  color: #475569;\n"
        "}\n"
    )
    (code / "index.html").write_text(html)
    (code / "style.css").write_text(css)
    rep = assess_product_demo(pid, {"description": "landing"}, data_root=str(tmp_path))
    assert any(i.get("code") == "ux_low_contrast_cta" for i in rep["issues"])
    assert quality_gates_pass(rep) is False


def test_assess_detects_low_contrast_cta_theme_var_on_gradient_button(tmp_path):
    pid = "prod-contrast-var-cta"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><head><title>x</title></head><body>
    <section><h1>Acme</h1><a class="btn-primary" href="#x">Start Free Trial</a></section>
    </body></html>"""
    css = (
        ".btn-primary {\n"
        "  background: linear-gradient(135deg, #6366f1 0%, #4338ca 100%);\n"
        "  color: var(--text-primary);\n"
        "}\n"
    )
    (code / "index.html").write_text(html)
    (code / "style.css").write_text(css)
    rep = assess_product_demo(pid, {"description": "landing"}, data_root=str(tmp_path))
    assert any(i.get("code") == "ux_low_contrast_cta" for i in rep["issues"])


def test_assess_detects_low_contrast_cta_pale_on_bright_green(tmp_path):
    """Regression: old heuristic only caught dark-on-dark; pale gray on saturated green must fail."""
    pid = "prod-contrast-cta"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><head><title>x</title></head><body>
    <section><h1>HealthIQ</h1><a class="btn primary" href="mailto:hello@example.com">Start Free Trial</a></section>
    </body></html>"""
    css = """.btn.primary {\n  background-color: #22c55e;\n  color: #d1d5db;\n}\n"""
    (code / "index.html").write_text(html)
    (code / "style.css").write_text(css)
    rep = assess_product_demo(pid, {"description": "landing"}, data_root=str(tmp_path))
    assert any(i.get("code") == "ux_low_contrast_cta" for i in rep["issues"])
    assert quality_gates_pass(rep) is False


def test_assess_detects_dead_hash_cta(tmp_path):
    pid = "prod-dead-hash-cta"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><head><title>x</title></head><body>
    <section><h1>Acme</h1><a class="btn" href="#">Start free trial</a></section>
    <section id="pricing"><h2>Pricing</h2></section>
    </body></html>"""
    (code / "index.html").write_text(html)
    rep = assess_product_demo(pid, {"description": "calls to notes"}, data_root=str(tmp_path))
    assert any(i.get("code") == "cta_dead_hash_link" for i in rep["issues"])
    assert quality_gates_pass(rep) is False


def test_assess_detects_sandbox_localhost_hrefs(tmp_path):
    pid = "prod-localhost-href"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><body>
    <header><nav><a href="//localhost/faq">FAQ</a></nav></header>
    <section><h1>x</h1><button class="btn">Start Free Trial</button></section>
    <section><h2>Pricing</h2></section>
    </body></html>"""
    (code / "index.html").write_text(html)
    rep = assess_product_demo(pid, {"description": "landing"}, data_root=str(tmp_path))
    assert any(i.get("code") == "sandbox_localhost_urls" for i in rep["issues"])
    assert quality_gates_pass(rep) is False


def test_assess_detects_sandbox_localhost_urls_in_bundled_artifacts(tmp_path):
    pid = "prod-localhost-bundle"
    code = tmp_path / "code" / pid
    assets = code / "frontend" / "dist" / "assets"
    assets.mkdir(parents=True)
    (code / "index.html").write_text(
        """<!doctype html><html><body>
        <header><nav><a href="#pricing">Pricing</a></nav></header>
        <section><h1>IncidentOps</h1><button>Start Free Trial</button></section>
        <section id="pricing"><h2>Pricing</h2></section>
        </body></html>""",
        encoding="utf-8",
    )
    (assets / "app.js").write_text(
        "const API_BASE = 'http://localhost:5173/api'; fetch(API_BASE + '/incidents');",
        encoding="utf-8",
    )
    rep = assess_product_demo(pid, {"description": "IncidentOps pricing"}, data_root=str(tmp_path))
    issue = next(i for i in rep["issues"] if i.get("code") == "sandbox_localhost_urls")
    assert "frontend/dist/assets/app.js" in issue.get("detail", "")
    assert quality_gates_pass(rep) is False


def test_assess_detects_broken_internal_file_link(tmp_path):
    pid = "prod-broken-link"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    (code / "index.html").write_text(
        """<!doctype html><html><body>
        <header><nav><a href="#pricing">Pricing</a></nav></header>
        <section><h1>IncidentOps</h1><a class="btn" href="missing.html">Start Free Trial</a></section>
        <section id="pricing"><h2>Pricing</h2></section>
        </body></html>""",
        encoding="utf-8",
    )
    rep = assess_product_demo(pid, {"description": "IncidentOps pricing"}, data_root=str(tmp_path))
    issue = next(i for i in rep["issues"] if i.get("code") == "broken_internal_link")
    assert "missing.html" in issue.get("detail", "")
    assert quality_gates_pass(rep) is False


def test_assess_detects_low_contrast_nav_links_on_dark_header(tmp_path):
    pid = "prod-contrast-nav"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    html = """<!doctype html><html><body>
    <header><nav><a href="#x">How It Works</a></nav></header>
    <section><h1>Pricing</h1><button>Ok</button></section>
    </body></html>"""
    css = """header { background-color: #0f172a; }\nnav a { color: #64748b; }\n"""
    (code / "index.html").write_text(html)
    (code / "style.css").write_text(css)
    rep = assess_product_demo(pid, {"description": "landing"}, data_root=str(tmp_path))
    assert any(i.get("code") == "ux_low_contrast_cta" for i in rep["issues"])
    assert quality_gates_pass(rep) is False
