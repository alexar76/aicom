"""Module-level pieces QAAgent and its mixins share: the logger, the QA system prompt, a float
env reader and the JSON-object extractor for LLM answers.
"""

from __future__ import annotations

import json
import logging
import os

from agents.prompts.load_prompt import load_prompt

# Logged as agents.qa, where QAAgent lives and where log filters point.
logger = logging.getLogger(__name__.rsplit(".", 2)[0] + ".qa")


def _qa_extract_json_object(text: str) -> dict | None:
    """Best-effort JSON object parse from an LLM reply."""
    raw = text.strip()
    if "```" in raw:
        parts = raw.split("```")
        for block in parts:
            b = block.strip()
            if b.lower().startswith("json"):
                b = b[4:].lstrip()
            if b.startswith("{"):
                try:
                    return json.loads(b)
                except json.JSONDecodeError:
                    continue
    try:
        s = raw.index("{")
        e = raw.rindex("}") + 1
        return json.loads(raw[s:e])
    except (ValueError, json.JSONDecodeError):
        return None


QA_SYSTEM_PROMPT = (
    load_prompt("qa_system_prompt.md")
    + "\n\n"
    + load_prompt("github_house_contract.md")
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default
