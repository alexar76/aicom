"""Architect agent system role prompt (loaded from markdown for reviewability)."""

from __future__ import annotations

from pathlib import Path

_PROMPT_FILE = Path(__file__).with_name("architect_role_prompt.md")

ARCHITECT_SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")
