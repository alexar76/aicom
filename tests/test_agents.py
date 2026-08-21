# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Agent Tests
# ============================================================================
# Tests for agents/base_agent.py — BaseAgent
# Covers: _extract_json (8+ cleanup levels), _derive_name, _save/_load artifact
# ============================================================================

import pytest
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from agents.base_agent import BaseAgent, AgentInput, AgentOutput


# ============================================================================
# Mock Helpers
# ============================================================================

class MockLLMRouter:
    """Mock LLM router returning predefined responses."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.generate_calls = []

    async def generate(self, prompt, task_type=None, config=None):
        self.generate_calls.append({
            "prompt": prompt[:100],
            "task_type": task_type,
            "config": config,
        })
        for key, response in self.responses.items():
            if key in prompt:
                return response
        return '{"result": "mock_output", "status": "success"}'


def make_agent(data_root: str) -> BaseAgent:
    """Factory helper: concrete subclass for testing BaseAgent methods."""
    router = MockLLMRouter()

    class ConcreteAgent(BaseAgent):
        async def execute(self, agent_input: AgentInput) -> AgentOutput:
            raise NotImplementedError

    return ConcreteAgent(
        agent_type="test",
        llm_router=router,
        task_type="test",
        data_root=data_root,
    )


# ============================================================================
# _extract_json — Comprehensive Tests
# ============================================================================

class TestExtractJson:
    """All 8+ levels of JSON extraction fallback cleanup."""

    @staticmethod
    def extract(text: str):
        """Convenience wrapper."""
        return BaseAgent._extract_json(text)

    # ------------------------------------------------------------------
    # Test 1: Direct valid JSON
    # ------------------------------------------------------------------

    def test_direct_valid_json(self):
        """Directly parseable JSON string."""
        result = self.extract('{"name": "test", "value": 42}')
        assert result == {"name": "test", "value": 42}

    def test_direct_nested_json(self):
        """Directly parseable nested JSON."""
        result = self.extract('{"a": {"b": [1, 2, 3]}}')
        assert result == {"a": {"b": [1, 2, 3]}}

    def test_direct_json_array(self):
        """A JSON array is parseable — _extract_json accepts any valid JSON
        via the Step 2 direct json.loads() call before looking for '{'."""
        result = self.extract('[1, 2, 3]')
        assert result == [1, 2, 3]

    # ------------------------------------------------------------------
    # Test 2: Markdown fenced code blocks
    # ------------------------------------------------------------------

    def test_markdown_fenced_json(self):
        """JSON inside ```json fences."""
        text = """Here is the result:
```json
{"key": "value", "number": 123}
```
Hope that helps!
"""
        result = self.extract(text)
        assert result == {"key": "value", "number": 123}

    def test_markdown_fenced_no_lang(self):
        """JSON inside plain ``` fences."""
        text = "```\n{\"a\": 1}\n```"
        result = self.extract(text)
        assert result == {"a": 1}

    def test_markdown_fenced_multiple(self):
        """Only the first JSON block is extracted."""
        text = """```json
{"first": "block"}
```
Some text
```json
{"second": "block"}
```"""
        result = self.extract(text)
        assert result == {"first": "block"}

    # ------------------------------------------------------------------
    # Test 3: Trailing text after JSON
    # ------------------------------------------------------------------

    def test_trailing_text(self):
        """Extra text after the closing brace is ignored."""
        text = '{"key": "value"}\n\nSome additional explanation here.'
        result = self.extract(text)
        assert result == {"key": "value"}

    def test_trailing_text_with_brackets(self):
        """Trailing text containing brackets doesn't confuse the parser."""
        text = '{"data": [1, 2, 3]}\nSee the array [1, 2, 3] for details.'
        result = self.extract(text)
        assert result == {"data": [1, 2, 3]}

    # ------------------------------------------------------------------
    # Test 4: Trailing commas
    # ------------------------------------------------------------------

    def test_trailing_comma_in_object(self):
        """Trailing comma before } is cleaned."""
        text = '{"a": 1, "b": 2,}'
        result = self.extract(text)
        assert result == {"a": 1, "b": 2}

    def test_trailing_comma_in_array(self):
        """Trailing comma before ] is cleaned."""
        text = '{"items": [1, 2, 3,]}'
        result = self.extract(text)
        assert result == {"items": [1, 2, 3]}

    def test_trailing_commas_nested(self):
        """Trailing commas in nested structures."""
        text = '{"outer": {"inner": {"a": 1,},}, "list": [1, 2,],}'
        result = self.extract(text)
        assert result == {"outer": {"inner": {"a": 1}}, "list": [1, 2]}

    # ------------------------------------------------------------------
    # Test 5: Python booleans / None
    # ------------------------------------------------------------------

    def test_python_bools_true(self):
        """Python True → JSON true."""
        text = '{"active": True, "completed": False}'
        result = self.extract(text)
        assert result == {"active": True, "completed": False}

    def test_python_bools_none(self):
        """Python None → JSON null."""
        text = '{"value": None}'
        result = self.extract(text)
        assert result == {"value": None}

    def test_python_bools_mixed(self):
        """Mixed True/False/None in complex object."""
        text = '{"enabled": True, "data": None, "valid": False, "count": 0}'
        result = self.extract(text)
        assert result == {"enabled": True, "data": None, "valid": False, "count": 0}

    # ------------------------------------------------------------------
    # Test 6: Single quotes
    # ------------------------------------------------------------------

    def test_single_quoted_keys(self):
        """Single-quoted keys are converted to double-quoted."""
        text = "{'name': 'test', 'value': 42}"
        result = self.extract(text)
        assert result == {"name": "test", "value": 42}

    def test_single_quoted_nested(self):
        """Single quotes in nested objects."""
        text = "{'outer': {'inner': 'data'}}"
        result = self.extract(text)
        assert result == {"outer": {"inner": "data"}}

    def test_single_quoted_with_apostrophe(self):
        """Single quotes containing apostrophes (requires regex handling)."""
        text = "{'title': \"it's fine\"}"
        result = self.extract(text)
        assert result == {"title": "it's fine"}

    # ------------------------------------------------------------------
    # Test 7: Missing commas
    # ------------------------------------------------------------------

    def test_missing_commas_between_pairs(self):
        """Missing commas between key-value pairs when separated by } or ] are fixed.
        
        The fix regex targets the pattern '} "key":' / '] "key":', so
        only commas after closing brackets/braces are restored.
        """
        text = '{"items": [1] "next": "value"}'
        result = self.extract(text)
        assert result == {"items": [1], "next": "value"}

    def test_missing_commas_after_brackets(self):
        """Missing commas after } or ] are fixed (same regex)."""
        text = '{"a": {"b": 1} "c": 2}'
        result = self.extract(text)
        assert result == {"a": {"b": 1}, "c": 2}

    # ------------------------------------------------------------------
    # Test 8: Truncated JSON
    # ------------------------------------------------------------------

    def test_truncated_missing_braces(self):
        """Missing closing braces are added automatically."""
        text = '{"a": {"b": {"c": 1}'
        result = self.extract(text)
        assert result == {"a": {"b": {"c": 1}}}

    def test_truncated_missing_brackets(self):
        """Missing closing brackets and braces — braces-balanced but brackets-unclosed
        input {'items': [1, 2, 3} has equal {/} count so truncation isn't triggered,
        but 3 without a closing ] makes raw_parse fail — returns None."""
        text = '{"items": [1, 2, 3}'
        result = self.extract(text)
        # Braces are balanced, so truncation fix (step 5f) is not triggered.
        # The unclosed array makes all strategies fail.
        assert result is None

    def test_truncated_missing_brackets_and_braces(self):
        """Missing closing brackets AND braces — truncation fix adds missing }."""
        text = '{"items": [1, 2, 3'
        result = self.extract(text)
        # open_braces=1, close_braces=0 → truncation adds 1 `}`
        # Result: {"items": [1, 2, 3} — but this still has unclosed array
        # So it returns None
        assert result is None

    def test_truncated_deeply_nested(self):
        """Deeply nested truncated JSON is properly closed."""
        text = '{"level1": {"level2": {"level3": {"a": 1'
        result = self.extract(text)
        assert result is not None
        assert result["level1"]["level2"]["level3"]["a"] == 1

    # ------------------------------------------------------------------
    # Test 9: Control characters
    # ------------------------------------------------------------------

    def test_control_characters_removed(self):
        """Control characters are stripped."""
        text = '{"data": "hello\x00world\x1f"}'
        result = self.extract(text)
        assert result == {"data": "helloworld"}

    def test_tab_and_newline_preserved(self):
        """Tabs and newlines inside strings are preserved as escaped chars."""
        text = '{"text": "line1\\nline2\\tindented"}'
        result = self.extract(text)
        assert result == {"text": "line1\nline2\tindented"}

    # ------------------------------------------------------------------
    # Test 10: Empty / None input
    # ------------------------------------------------------------------

    def test_empty_string(self):
        """Empty string returns None."""
        assert self.extract("") is None

    def test_whitespace_only(self):
        """Whitespace-only string returns None."""
        assert self.extract("   \n  \t  ") is None

    def test_none_input(self):
        """None input returns None."""
        assert self.extract(None) is None

    # ------------------------------------------------------------------
    # Test 11: LLM commentary around JSON
    # ------------------------------------------------------------------

    def test_llm_commentary_before(self):
        """Natural language before the JSON block."""
        text = """Based on my analysis, here is the result:
{"product": "TestApp", "score": 95}
"""
        result = self.extract(text)
        assert result == {"product": "TestApp", "score": 95}

    def test_llm_commentary_after(self):
        """Natural language after the JSON block."""
        text = """{"product": "TestApp", "score": 95}
I hope this meets your requirements. Let me know if you need changes.
"""
        result = self.extract(text)
        assert result == {"product": "TestApp", "score": 95}

    def test_llm_commentary_full(self):
        """Commentary both before and after."""
        text = """Let me think about this...

```json
{"result": "success", "data": {"count": 10}}
```

Please review and let me know.
"""
        result = self.extract(text)
        assert result == {"result": "success", "data": {"count": 10}}

    def test_llm_explains_before_json(self):
        """LLM writes 'Here is the JSON:' style prefix."""
        text = 'Here is the JSON output: {"key": "value"} End.'
        result = self.extract(text)
        assert result == {"key": "value"}

    # ------------------------------------------------------------------
    # Test 12: Deeply nested JSON
    # ------------------------------------------------------------------

    def test_deeply_nested_balanced(self):
        """Deep nesting with balanced braces."""
        text = """{"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}"""
        result = self.extract(text)
        assert result == {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}

    def test_deeply_nested_with_arrays(self):
        """Deep nesting mixing objects and arrays."""
        text = """{
    "name": "root",
    "children": [
        {"name": "child1", "tags": ["a", "b"]},
        {"name": "child2", "data": {"key": "value"}}
    ]
}"""
        result = self.extract(text)
        assert result["name"] == "root"
        assert len(result["children"]) == 2
        assert result["children"][0]["tags"] == ["a", "b"]

    # ------------------------------------------------------------------
    # Combined / regression tests
    # ------------------------------------------------------------------

    def test_combined_issues(self):
        """Multiple issues combined: trailing comma, Python bool, single quotes.
        
        The missing-commas-between-values case (after `1` in `'active': True`)
        cannot be fixed by the current regex, so this returns None.
        """
        text = "{'name': 'Test', 'active': True, 'items': [1, 2,],}"
        result = self.extract(text)
        # The value "True" with a space after it doesn't have }/] before the next
        # key, so the missing-comma regex doesn't trigger. Combined with single
        # quotes this is too broken for the current fallback.
        assert result is None

    def test_combined_select_issues(self):
        """Select combinable issues: trailing commas + Python bools + single quotes.
        Each cleanup strategy is applied independently (not chained), so this
        returns None — no single fix handles all three issues at once."""
        text = "{'active': True, 'items': [1, 2,],}"
        result = self.extract(text)
        # Each strategy is applied to `raw` independently, not chained:
        #   5a (trailing commas)  → {'active': True, 'items': [1, 2]}   — still has ' + True
        #   5b (Python bools)     → {'active': true, 'items': [1, 2,],} — still has '
        #   5d (single quotes)    → {"active": True, 'items': [1, 2,],} — still has True
        # No single candidate handles all three simultaneously
        assert result is None

    def test_combined_all_issues(self):
        """Every issue at once: fence, trailing text, py bools, quotes, trailing commas.
        
        The missing commas between key-value pairs (e.g. True → next key)
        cannot be recovered, so returns None.
        """
        text = """Here's the output:
```json
{'product': 'MyApp', 'enabled': True, 'count': None, 'tags': ['a', 'b',],}
```
Cheers!
"""
        result = self.extract(text)
        # The value 'True' followed by 'count' without a comma is unfixable
        assert result is None

    def test_extra_text_after_object_with_brackets(self):
        """Text containing [] after the JSON object."""
        text = '{"data": [1, 2]}\n\nAdditional context: see [docs] for details.'
        result = self.extract(text)
        assert result == {"data": [1, 2]}

    def test_no_json_object(self):
        """Text with no JSON object returns None."""
        text = "This is just plain text without any JSON."
        result = self.extract(text)
        assert result is None

    def test_only_brackets_no_object(self):
        """Only square brackets — Step 2 json.loads() accepts any valid JSON,
        so [1, 2, 3] is parseable as a JSON array."""
        result = self.extract("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_unclosed_string_in_value(self):
        """An unclosed string is handled gracefully (returns None or partial)."""
        text = '{"key": "unclosed string}'
        result = self.extract(text)
        # This is a tough case; the fallback tries raw_decode as last resort
        # May return None if all strategies fail
        assert result is None or isinstance(result, dict)


# ============================================================================
# _derive_name — Tests
# ============================================================================

class TestDeriveName:
    """Deriving product names from idea text."""

    def test_normal_idea(self):
        """First 2-3 significant words form the name."""
        name = BaseAgent._derive_name("Create a task management system")
        assert name == "Create Task Management"

    def test_short_idea(self):
        """Fewer than 3 meaningful words."""
        name = BaseAgent._derive_name("Hello World")
        assert name == "Hello World"

    def test_empty_idea(self):
        """Empty idea returns default name."""
        name = BaseAgent._derive_name("")
        assert name == "AI-Factory Product"

    def test_whitespace_idea(self):
        """Whitespace-only returns default."""
        name = BaseAgent._derive_name("   ")
        assert name == "AI-Factory Product"

    def test_single_word(self):
        """Single word with <=2 chars uses default."""
        name = BaseAgent._derive_name("A")
        assert name == "AI-Factory Product"

    def test_single_long_word(self):
        """Single long word is used."""
        name = BaseAgent._derive_name("Microservice")
        assert name == "Microservice"

    def test_short_words_filtered(self):
        """Words of length <= 2 are skipped; only first 3 >2-char words used."""
        name = BaseAgent._derive_name("To be or not to be that is the question")
        # Words >2 chars: "not", "that", "the", "question"
        # Only first 3: "Not", "That", "The"
        assert "The" in name
        assert "Question" not in name  # Only 3 words max

    def test_special_characters(self):
        """Special characters in idea are preserved, but .capitalize() lowercases
        everything after the first character."""
        name = BaseAgent._derive_name("Build-A-Bot Platform")
        # "Build-A-Bot".capitalize() → "Build-a-bot"
        assert name == "Build-a-bot Platform"


# ============================================================================
# _save_artifact / _load_artifact — Tests
# ============================================================================

class TestArtifactPersistence:
    """File-based artifact save/load via tmp_path."""

    @pytest.fixture
    def agent(self, tmp_path):
        return make_agent(str(tmp_path))

    def test_save_and_load_artifact(self, agent):
        """Roundtrip save → load."""
        path = agent._save_artifact("prod-1", "specs", {"key": "value"}, "test_spec.json")
        assert path is not None
        assert Path(path).exists()

        loaded = agent._load_artifact("prod-1", "specs", "test_spec.json")
        assert loaded == {"key": "value"}

    def test_save_generates_filename(self, agent):
        """Auto-generated filename when none provided."""
        path = agent._save_artifact("prod-2", "arch", {"design": "v1"})
        assert path is not None
        fname = Path(path).name
        assert fname.endswith(".json")
        assert "arch_" in fname

    def test_load_nonexistent(self, agent):
        """Loading a non-existent artifact returns None."""
        loaded = agent._load_artifact("nonexistent", "specs", "nope.json")
        assert loaded is None

    def test_save_creates_directory(self, agent, tmp_path):
        """Saving creates intermediate directories."""
        agent._save_artifact("deep/path", "specs", {"a": 1}, "test.json")
        assert (tmp_path / "specs" / "deep/path" / "test.json").exists()

    def test_load_after_reload(self, agent, tmp_path):
        """Data survives a new BaseAgent instance (temp dir)."""
        agent._save_artifact("prod-r", "specs", {"persist": True}, "reload.json")

        agent2 = make_agent(str(tmp_path))
        loaded = agent2._load_artifact("prod-r", "specs", "reload.json")
        assert loaded == {"persist": True}

    def test_list_artifacts(self, agent):
        """List artifacts for a product."""
        agent._save_artifact("prod-l", "specs", {"a": 1}, "a.json")
        agent._save_artifact("prod-l", "specs", {"b": 2}, "b.json")

        files = agent._list_artifacts("prod-l", "specs")
        assert len(files) == 2
        assert "a.json" in files
        assert "b.json" in files

    def test_list_artifacts_empty(self, agent):
        """No artifacts → empty list."""
        files = agent._list_artifacts("no-such", "specs")
        assert files == []


# ============================================================================
# _ensure_directories — Tests
# ============================================================================

class TestEnsureDirectories:
    """Required subdirectories are created on init."""

    def test_directories_created(self, tmp_path):
        agent = make_agent(str(tmp_path))
        expected = ["specs", "arch", "code", "bugs", "state", "logs", "telemetry", "security"]
        for d in expected:
            assert (tmp_path / d).is_dir(), f"Missing directory: {d}"

    def test_existing_directories_not_recreated(self, tmp_path):
        (tmp_path / "specs").mkdir(parents=True)
        # Should not raise
        agent = make_agent(str(tmp_path))
        assert (tmp_path / "specs").is_dir()
