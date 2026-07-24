"""Architect agent system role prompt (loaded from markdown for reviewability)."""

from __future__ import annotations

from agents.prompts.load_prompt import load_prompt

ARCHITECT_SYSTEM_PROMPT = load_prompt("architect_role_prompt.md")
