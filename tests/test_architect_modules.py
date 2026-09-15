"""Unit tests for architect helpers split out of architect.py."""

from __future__ import annotations

from agents.architect_contracts import _ensure_implementation_contract
from agents.architect_ui import (
    _build_design_pipeline,
    _build_design_system,
    _default_ui_experience,
    _design_variants,
    _ensure_ui_experience,
    _needs_ui_experience,
    _rank_design_variants,
    _ui_experience_substantial,
)


def test_default_ui_experience_is_substantial():
    ux = _default_ui_experience("Boutique fitness promo")
    assert _ui_experience_substantial(ux)
    assert len(ux["css_variables"]) >= 4
    assert ux["svg_creative_brief"]


def test_needs_ui_experience_for_landing_and_react():
    assert _needs_ui_experience({}, {}, landing_charter=True)
    assert _needs_ui_experience(
        {"tech_stack": {"frontend": "React + Vite"}},
        {"delivery_profile": "full_software"},
        landing_charter=False,
    )


def test_ensure_ui_experience_fills_missing():
    arch: dict = {"tech_stack": {"frontend": "html/css"}}
    applied = _ensure_ui_experience(arch, {"delivery_profile": "marketing_landing"}, True, "idea")
    assert applied is True
    assert _ui_experience_substantial(arch["ui_experience"])
    # second pass should not overwrite substantial brief
    assert _ensure_ui_experience(arch, {"delivery_profile": "marketing_landing"}, True, "idea") is False


def test_design_system_and_pipeline_shape():
    arch = {"ui_experience": _default_ui_experience("ocean product")}
    ds = _build_design_system(arch)
    pipe = _build_design_pipeline(arch)
    assert ds["version"] == 1
    assert "tokens" in ds
    assert set(pipe["stages"]) == {"moodboard", "layout_system", "final_ui"}


def test_design_variants_ranking():
    ux = _default_ui_experience("base")
    ranked, selected = _rank_design_variants(_design_variants("base", 3), ux)
    assert len(ranked) == 3
    assert "score" in ranked[0]
    assert selected.get("variant_id")


def test_implementation_contract_synthesized_for_full_software():
    arch: dict = {
        "tech_stack": {
            "frontend": "React + Vite",
            "backend": "FastAPI",
            "database": "postgresql",
        }
    }
    _ensure_implementation_contract(
        arch,
        {"delivery_profile": "full_software"},
        "CRM demo",
        landing_charter=False,
    )
    ic = arch["implementation_contract"]
    assert ic["docker_compose"]["required"] is True
    assert "postgres" in ic["docker_compose"]["services_outline"]
    assert ic["testing_contract"]["layers_ordered"][0] == "component_unit"
    assert ic["testing_contract"]["sandbox_demo_credentials"]["required"] is True
    layout = ic["repository_layout"].lower()
    for needle in (
        "readme.md",
        "license",
        "changelog.md",
        "docs/en.md",
        "docs/badges",
        "docs/gallery",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "tests/",
    ):
        assert needle in layout, needle
    assert any("GITHUB_HOUSE_CONTRACT" in s for s in ic["forbidden_shortcuts"])


def test_github_house_paths_appended_to_thin_layout():
    arch: dict = {
        "content_language": "ru",
        "ui_experience": {"mood": "calm"},
        "tech_stack": {"frontend": "React + Vite", "backend": "FastAPI", "database": "sqlite"},
        "implementation_contract": {
            "runnable_services": [
                {"name": "api", "runtime": "python", "framework": "FastAPI", "entrypoint": "backend/app/main.py"}
            ],
            "repository_layout": "repo-root/\n  backend/\n  README.md\n",
            "forbidden_shortcuts": ["x"],
        },
    }
    _ensure_implementation_contract(
        arch,
        {"delivery_profile": "full_software"},
        "thin",
        landing_charter=False,
    )
    layout = arch["implementation_contract"]["repository_layout"].lower()
    assert "docs/en.md" in layout
    assert "readme.ru.md" in layout
    assert "docs/ru.md" in layout
    assert ".github/workflows/release.yml" in layout
    assert "docs/gallery" in layout


def test_implementation_contract_skipped_for_landing():
    arch: dict = {"tech_stack": {"frontend": "html"}}
    _ensure_implementation_contract(
        arch,
        {"delivery_profile": "full_software"},
        "landing",
        landing_charter=True,
    )
    assert "implementation_contract" not in arch
