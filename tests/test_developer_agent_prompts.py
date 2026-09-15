"""Developer agent: split prompts, remediation payload, and web landing file write."""

from __future__ import annotations

import json

import pytest

from agents.base_agent import AgentInput
from agents.dev import DeveloperAgent
from llm.agent_prompt_split import USER_DATA_JSON_MARKER
from llm.visual_quality_system import VISUAL_QUALITY_SYSTEM


def _minimal_landing_code_json() -> str:
    html = """<!DOCTYPE html>
<html lang="en"><head>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces&family=Source+Sans+3&display=swap" rel="stylesheet">
<link rel="stylesheet" href="./style.css">
</head><body>
<nav><a href="#benefits">Benefits</a></nav>
<section id="hero"><h1>Fit Promo</h1><a class="cta" href="#benefits">Start</a></section>
<section id="benefits"><h2>Why us</h2></section>
<script src="./app.js"></script>
</body></html>"""
    return json.dumps(
        {
            "files": [
                {"path": "index.html", "content": html, "language": "html", "description": "Landing"},
                {"path": "style.css", "content": ":root{--accent:#c45} body{font-family:'Source Sans 3',sans-serif}", "language": "css", "description": "Styles"},
                {"path": "app.js", "content": "document.querySelectorAll('a').forEach(()=>{});", "language": "js", "description": "Motion"},
            ],
            "dependencies": [],
            "setup_instructions": "Open index.html",
            "test_commands": [],
            "documentation": "Static landing",
        }
    )


@pytest.mark.asyncio
async def test_developer_execute_split_prompt_and_writes_files(tmp_path):
    captured: dict = {}

    async def fake_generate(prompt, task_type=None, config=None, agent_input=None, system_prompt=None):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        return _minimal_landing_code_json()

    agent = DeveloperAgent(llm_router=object())
    agent.data_root = tmp_path
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    agent._generate = fake_generate  # type: ignore[method-assign]

    spec = {
        "product_name": "Fit Promo",
        "delivery_profile": "marketing_landing",
        "description": "Promotional landing page with hero and benefits",
        "core_features": [{"name": "Hero", "description": "CTA", "priority": 1}],
    }
    arch = {
        "ui_experience": {
            "mood": "Warm editorial",
            "css_variables": {"--accent": "#c45"},
            "svg_creative_brief": "SVG wave hero backdrop",
        }
    }

    out = await agent.execute(
        AgentInput(
            task_id="t-dev",
            product_id="prod-dev-test",
            agent_type="developer",
            data={
                "idea": "Boutique fitness promo",
                "specification": spec,
                "architecture": arch,
                "admin_instructions": "marketing landing page",
                "quality_gates_feedback": {"passed": False, "issues": ["weak hero"]},
                "quality_repair_round": 1,
                "quality_repair_max": 3,
            },
        )
    )

    assert out.success is True
    assert (tmp_path / "code" / "prod-dev-test" / "index.html").is_file()
    assert USER_DATA_JSON_MARKER in captured["prompt"]
    assert "VISUAL_QUALITY_SYSTEM" not in captured["prompt"]
    assert captured["system_prompt"] and VISUAL_QUALITY_SYSTEM in captured["system_prompt"]
    assert "quality_gates" in captured["prompt"]
    assert "architecture" in captured["prompt"]
