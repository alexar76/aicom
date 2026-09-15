"""Architect agent: split system/user prompts and successful landing architecture path."""

from __future__ import annotations

import json

import pytest

from agents.architect import ArchitectAgent
from agents.base_agent import AgentInput
from llm.agent_prompt_split import USER_DATA_JSON_MARKER
from llm.content_languages import LANGUAGE_SYSTEM
from llm.visual_quality_system import VISUAL_QUALITY_SYSTEM


def _landing_architecture_json() -> str:
    return json.dumps(
        {
            "architecture_name": "Promo Landing",
            "overview": "Static marketing landing for boutique fitness.",
            "components": [
                {
                    "name": "Hero",
                    "description": "Above-the-fold offer",
                    "technology": "html",
                    "responsibilities": ["CTA"],
                }
            ],
            "data_models": [],
            "api_endpoints": [],
            "tech_stack": {
                "frontend": "vanilla HTML/CSS/JS",
                "backend": "none",
                "database": "none",
                "infrastructure": "static hosting",
            },
            "deployment": {"type": "static", "requirements": "CDN", "scaling": "none"},
            "diagrams": [],
            "content_language": "en",
            "ui_experience": {
                "mood": "Warm editorial paper for boutique fitness with calm trust and energetic accent",
                "strict_system_ui": True,
                "css_variables": {
                    "--bg-deep": "#f5f0e6",
                    "--surface": "#fffdf8",
                    "--text": "#1c1914",
                    "--text-muted": "rgba(28,25,20,0.62)",
                    "--accent": "#c45c26",
                    "--accent-2": "#2f4f4f",
                    "--radius-lg": "6px",
                },
                "typography": {
                    "display_google_font": "Fraunces",
                    "body_google_font": "Source Sans 3",
                    "notes": "Serif display + sans body",
                },
                "layout": {
                    "max_width": "1100px",
                    "hero_layout": "split",
                    "section_spacing": "large",
                    "grid_notes": "two-column benefits",
                },
                "motion": {
                    "page": "fade-in hero",
                    "micro_interactions": "button hover 200ms",
                    "scroll": "section reveal",
                    "respect_reduced_motion": True,
                },
                "signature_moment": "Paper grain band behind headline",
                "svg_creative_brief": "Layered SVG wave paths and ornamental frame around hero headline",
                "anti_patterns": ["generic cyan glass SaaS clone"],
            },
        }
    )


@pytest.mark.asyncio
async def test_architect_execute_uses_visual_quality_system_and_data_json(tmp_path):
    captured: dict = {}

    async def fake_generate(prompt, task_type=None, config=None, agent_input=None, system_prompt=None):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        return _landing_architecture_json()

    agent = ArchitectAgent(llm_router=object(), data_root=str(tmp_path))
    agent._generate = fake_generate  # type: ignore[method-assign]

    spec = {
        "product_name": "Fit Promo",
        "delivery_profile": "marketing_landing",
        "description": "Single scroll marketing landing page",
    }
    out = await agent.execute(
        AgentInput(
            task_id="t-arch",
            product_id="prod-arch-test",
            agent_type="architect",
            data={
                "idea": "Boutique fitness promo landing",
                "specification": spec,
                "admin_instructions": "marketing landing page only",
            },
        )
    )

    assert out.success is True
    assert out.data.get("architecture", {}).get("architecture_name") == "Promo Landing"
    assert USER_DATA_JSON_MARKER in captured["prompt"]
    assert "VISUAL_QUALITY_SYSTEM" not in captured["prompt"]
    assert captured["system_prompt"] and VISUAL_QUALITY_SYSTEM in captured["system_prompt"]
    assert LANGUAGE_SYSTEM in captured["system_prompt"]
    assert "GITHUB_HOUSE_CONTRACT" in captured["system_prompt"]
    arch = out.data.get("architecture", {})
    assert arch.get("content_language") == "en"
    assert (tmp_path / "arch" / "prod-arch-test" / "architecture.json").is_file()
