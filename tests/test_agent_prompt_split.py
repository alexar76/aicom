"""Architect / Developer prompt split: data-only user JSON + VISUAL_QUALITY_SYSTEM in system."""

from llm.agent_prompt_split import (
    USER_DATA_JSON_MARKER,
    build_architect_system_prompt,
    build_architect_user_data,
    build_developer_system_prompt,
    build_developer_user_data,
    format_user_data_message,
)
from llm.content_languages import LANGUAGE_SYSTEM
from llm.visual_quality_system import VISUAL_QUALITY_SYSTEM


def test_architect_user_payload_shape():
    payload = build_architect_user_data(
        idea="AI note app",
        spec={"product_name": "Notes", "delivery_profile": "marketing_landing"},
        admin_instructions="landing only",
        landing_charter=True,
        peer_feedback=None,
        research_context="",
        methodology_block="",
        landing_note="note",
        full_note="",
        ux_note="ux",
    )
    assert "user_brief" in payload
    assert "style_preset" in payload
    assert payload["user_brief"]["idea"] == "AI note app"
    msg = format_user_data_message(payload)
    assert msg.startswith(USER_DATA_JSON_MARKER)
    assert "VISUAL_QUALITY_SYSTEM" not in msg


def test_architect_system_includes_visual_quality():
    sys = build_architect_system_prompt("ROLE: architect")
    assert "ROLE: architect" in sys
    assert VISUAL_QUALITY_SYSTEM in sys
    assert LANGUAGE_SYSTEM in sys


def test_developer_user_payload_shape():
    payload = build_developer_user_data(
        idea="x",
        category="",
        tags=[],
        admin_instructions="",
        architecture={"ui_experience": {"mood": "warm"}},
        specification={},
        delivery_mode="web_app",
        delivery_profile="full_software",
        implementation_plan={},
        analyst_brief=None,
        remediation={"quality_gates": {"passed": False}},
    )
    assert "architecture" in payload
    assert "user_brief" in payload
    assert payload["user_brief"]["remediation"]["quality_gates"]["passed"] is False


def test_developer_system_includes_visual_and_stack():
    sys = build_developer_system_prompt(
        core_prompt="DEV CORE",
        stack_rules="STACK",
        reference_shell_block="",
        fs_appendix="",
        polyglot_block="",
        patch_mode_note="",
    )
    assert "DEV CORE" in sys
    assert "STACK" in sys
    assert VISUAL_QUALITY_SYSTEM in sys
    assert LANGUAGE_SYSTEM in sys
