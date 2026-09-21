"""Public Hub MCP / WARDEN skills stay identical and match live tools/list text."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aimarket-hub"))
SKILLS = ("aimarket-hub-mcp", "warden-mcp-firewall")


def _skill(rel: str, name: str) -> Path:
    return ROOT / rel / name / "SKILL.md"


def test_cursor_skills_match_agent_skills_byte_for_byte():
    for name in SKILLS:
        cursor = _skill(".cursor/skills", name).read_bytes()
        plugin = _skill("agent-skills/skills", name).read_bytes()
        assert cursor == plugin, name


def test_hub_skill_quotes_live_tool_descriptions():
    from aimarket_hub.mcp_gateway import TOOLS

    body = _skill("agent-skills/skills", "aimarket-hub-mcp").read_text(encoding="utf-8")
    assert "https://modelmarket.dev/mcp" in body
    assert "source_hub" in body
    assert "free_trial.max_invokes_per_visitor" in body
    for tool in TOOLS:
        assert tool["description"] in body, tool["name"]


def test_warden_skill_is_not_a_proxy():
    body = _skill("agent-skills/skills", "warden-mcp-firewall").read_text(encoding="utf-8")
    assert "npx -y @aimarket/warden" in body
    assert "does not start, proxy, or sandbox" in body.lower()


def test_agent_install_is_curl_from_github_raw():
    text = (ROOT / "docs" / "agent-install" / "README.md").read_text(encoding="utf-8")
    assert "curl -fsSL" in text
    assert "raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md" in text
    assert "raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md" in text
    assert "cp /path/to/aicom/.cursor/skills" not in text
