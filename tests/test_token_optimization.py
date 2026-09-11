"""Tests for the factory token-spend optimizations.

Covers:
- prompt_json compact serialization (#4)
- per-task output soft caps (#5)
- Anthropic prompt-caching content split (#1/#2)
- base_agent context ordering + lesson gating (#1/#6)
"""

import json

import pytest

from agents.prompt_utils import prompt_json
from llm.provider import GenerationConfig
from llm.token_budget import task_output_soft_cap


# ── #4: prompt_json ───────────────────────────────────────────────────────────

def test_prompt_json_is_compact():
    obj = {"a": 1, "b": [1, 2, 3], "c": {"d": "x"}}
    out = prompt_json(obj)
    # No indentation newlines and no space after separators.
    assert "\n" not in out
    assert ", " not in out
    assert ": " not in out
    # Still round-trips to the same data.
    assert json.loads(out) == obj


def test_prompt_json_compact_shorter_than_indented():
    obj = {"files": [{"path": f"f{i}.py", "content": "x" * 20} for i in range(20)]}
    compact = prompt_json(obj)
    indented = json.dumps(obj, indent=2)
    assert len(compact) < len(indented)


def test_prompt_json_preserves_unicode():
    out = prompt_json({"name": "Привет"})
    assert "Привет" in out


def test_prompt_json_limit_truncates_with_marker():
    out = prompt_json({"k": "x" * 1000}, limit=50)
    assert len(out) <= 50 + len("\n…[truncated]")
    assert out.endswith("…[truncated]")


def test_prompt_json_no_limit_keeps_full():
    out = prompt_json({"k": "x" * 100})
    assert "truncated" not in out


# ── #5: per-task output soft caps ─────────────────────────────────────────────

def test_soft_cap_known_tasks():
    assert task_output_soft_cap("code_generation") == 64_000
    assert task_output_soft_cap("marketing_copy") == 8_000
    assert task_output_soft_cap("sales_response") == 6_000


def test_soft_cap_unknown_task_is_none():
    assert task_output_soft_cap("totally_unknown_task") is None
    assert task_output_soft_cap(None) is None


def test_soft_cap_disabled_by_env(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TASK_OUTPUT_CAPS_ENABLED", "off")
    assert task_output_soft_cap("code_generation") is None


def test_soft_cap_env_override(monkeypatch):
    monkeypatch.setenv("AIFACTORY_TASK_OUTPUT_CAPS_JSON", json.dumps({"marketing_copy": 1234}))
    assert task_output_soft_cap("marketing_copy") == 1234


def test_soft_cap_caps_are_below_heavy_budget():
    # The whole point: every cap is well under the 128k heavy request.
    from llm.token_budget import _TASK_OUTPUT_SOFT_CAPS

    assert all(0 < cap <= 64_000 for cap in _TASK_OUTPUT_SOFT_CAPS.values())


# ── #1/#2: Anthropic prompt-caching content split ─────────────────────────────

def test_anthropic_user_content_splits_on_prefix():
    from llm.anthropic_provider import AnthropicProvider

    prompt = "STABLE_PREFIX_BYTES" + "VARIABLE_TAIL"
    n = len("STABLE_PREFIX_BYTES")
    cfg = GenerationConfig(cache_prefix_len=n)
    content = AnthropicProvider._build_user_content(prompt, cfg)
    assert isinstance(content, list)
    assert content[0]["text"] == "STABLE_PREFIX_BYTES"
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[1]["text"] == "VARIABLE_TAIL"
    assert "cache_control" not in content[1]


def test_anthropic_user_content_plain_when_no_prefix():
    from llm.anthropic_provider import AnthropicProvider

    cfg = GenerationConfig(cache_prefix_len=0)
    content = AnthropicProvider._build_user_content("hello world", cfg)
    assert content == "hello world"


def test_anthropic_user_content_plain_when_prefix_covers_all():
    from llm.anthropic_provider import AnthropicProvider

    prompt = "everything"
    cfg = GenerationConfig(cache_prefix_len=len(prompt))
    # No variable tail → nothing to cache separately, fall back to plain string.
    assert AnthropicProvider._build_user_content(prompt, cfg) == prompt


# ── #1: base_agent context ordering ───────────────────────────────────────────

def _make_agent(tmp_path):
    from agents.base_agent import AgentInput, AgentOutput, BaseAgent

    class _Stub(BaseAgent):
        async def execute(self, agent_input: AgentInput) -> AgentOutput:  # pragma: no cover
            return AgentOutput(
                task_id="t", product_id="p", agent_type=self.agent_type, success=True
            )

    return _Stub(agent_type="developer", llm_router=None, data_root=str(tmp_path))


def test_augment_puts_lessons_after_stable_and_returns_prefix_len(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_CODE_STYLE_JSON", json.dumps({"style": "pep8"}))
    agent = _make_agent(tmp_path)
    lessons = [{"summary": "do not repeat X"}]
    text, stable_len = agent._augment_prompt_with_context("THE_PROMPT", None, lessons)
    # Stable style block leads; lessons sit after the stable boundary; prompt last.
    style_pos = text.index("Code style")
    lessons_pos = text.index("Cross-product lessons")
    prompt_pos = text.index("THE_PROMPT")
    assert style_pos < lessons_pos < prompt_pos
    # The reported stable prefix ends before the rotating lessons block.
    assert stable_len <= lessons_pos
    assert text[:stable_len].find("Cross-product lessons") == -1


def test_augment_no_context_returns_prompt_and_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_CODE_STYLE_JSON", raising=False)
    agent = _make_agent(tmp_path)
    text, stable_len = agent._augment_prompt_with_context("ONLY_PROMPT", None, [])
    assert text == "ONLY_PROMPT"
    assert stable_len == 0


# ── #6: lesson gating ─────────────────────────────────────────────────────────

def test_lesson_recipients_default_excludes_content_agents():
    from agents.base_agent import _lesson_recipients

    recipients = _lesson_recipients()
    assert "developer" in recipients
    assert "qa" in recipients
    assert "marketing" not in recipients
    assert "sales" not in recipients


def test_lesson_recipients_env_override(monkeypatch):
    from agents.base_agent import _lesson_recipients

    monkeypatch.setenv("AIFACTORY_LESSON_AGENTS", "marketing, sales")
    recipients = _lesson_recipients()
    assert recipients == frozenset({"marketing", "sales"})


def test_lesson_limit_env_override(monkeypatch):
    from agents.base_agent import _lesson_limit

    monkeypatch.setenv("AIFACTORY_LESSON_LIMIT", "3")
    assert _lesson_limit() == 3
    monkeypatch.setenv("AIFACTORY_LESSON_LIMIT", "0")
    assert _lesson_limit() == 0


def test_lesson_limit_default(monkeypatch):
    from agents.base_agent import _lesson_limit

    monkeypatch.delenv("AIFACTORY_LESSON_LIMIT", raising=False)
    assert _lesson_limit() == 8


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
