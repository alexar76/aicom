"""Sandbox serves spec-built landings when index.html is the factory placeholder."""

from __future__ import annotations

from web.backend.services import sandbox_spec_landing as ssl


def test_detects_factory_boilerplate():
    html = (
        "<p>shipped preview bundle</p><p>illustrative capability cards</p>"
        "<p>a modern web application built by the ai-factory pipeline</p>" * 20
    )
    assert ssl.is_factory_boilerplate_index(html) is True
    assert ssl.is_factory_boilerplate_index("<h1>Real landing</h1>") is False


def test_build_spec_landing_from_spec(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-test-landing"
    spec_dir = tmp_path / "specs" / pid
    spec_dir.mkdir(parents=True)
    (spec_dir / "specification.json").write_text(
        """{
      "product_id": "prod-test-landing",
      "specification": {
        "delivery_profile": "marketing_landing",
        "product_name": "CyberShield MDR",
        "description": "Dark blue #0a2540 and cyan #00d4aa MDR for SMB.",
        "target_audience": "SMB IT managers",
        "core_features": [
          {"name": "Hero", "description": "Threat stats bar"},
          {"name": "Pricing", "description": "Three tiers"}
        ]
      }
    }""",
        encoding="utf-8",
    )
    html = ssl.build_spec_landing_html(pid)
    assert html is not None
    assert "CyberShield MDR" in html
    assert "Hero" in html
    assert "Threat stats bar" in html
    assert "AI-Factory" in html


def test_terracotta_palette_from_named_colors(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.sandbox_spec_landing import build_spec_landing_html_from_spec

    spec = {
        "product_name": "Sweat Season Pass",
        "description": "warm terracotta and deep olive palette with serif headings",
        "core_features": [{"name": "Hero", "description": "headline 'Your Spring Movement Pass'"}],
    }
    html = build_spec_landing_html_from_spec("prod-sweat", spec)
    assert "#c4725a" in html or "terracotta" in html.lower() or "--primary: #c4725a" in html
    assert "Your Spring Movement Pass" in html
    assert "illustrative capability" not in html.lower()


def test_materialize_writes_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-mat"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    stub = (
        "shipped preview bundle illustrative capability cards "
        "a modern web application built by the ai-factory pipeline " * 12
    )
    (code / "index.html").write_text(stub, encoding="utf-8")
    spec_dir = tmp_path / "specs" / pid
    spec_dir.mkdir(parents=True)
    (spec_dir / "specification.json").write_text(
        '{"specification": {"product_name": "Acme", "description": "Acme landing", "core_features": []}}',
        encoding="utf-8",
    )
    from web.backend.services.sandbox_spec_landing import (
        is_factory_boilerplate_index,
        materialize_spec_landing_on_disk,
    )

    assert materialize_spec_landing_on_disk(pid, code_root=code)
    out = (code / "index.html").read_text(encoding="utf-8")
    assert not is_factory_boilerplate_index(out)
    assert "Acme" in out


def test_resolve_replaces_boilerplate(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-x"
    spec_dir = tmp_path / "specs" / pid
    spec_dir.mkdir(parents=True)
    (spec_dir / "specification.json").write_text(
        '{"specification": {"product_name": "Acme", "description": "Acme product", "core_features": []}}',
        encoding="utf-8",
    )
    stub = (
        "shipped preview bundle illustrative capability cards "
        "a modern web application built by the ai-factory pipeline " * 15
    )
    out = ssl.resolve_sandbox_index_html(pid, stub)
    assert "Acme" in out
    assert "shipped preview bundle" not in out.lower() or "placeholder" in out.lower()


def test_resolve_replaces_vite_dev_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-vite"
    spec_dir = tmp_path / "specs" / pid
    spec_dir.mkdir(parents=True)
    (spec_dir / "specification.json").write_text(
        '{"specification": {"product_name": "RecoverCoach", "description": "Recovery app", "core_features": []}}',
        encoding="utf-8",
    )
    vite_shell = (
        "<!DOCTYPE html><html><body><div id='root'></div>"
        '<script type="module" src="./src/main.tsx"></script>'
        "</body></html>"
    )
    out = ssl.resolve_sandbox_index_html(pid, vite_shell)
    assert "RecoverCoach" in out
    assert "./src/main.tsx" not in out
