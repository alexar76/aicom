"""A config file that exists but cannot be used stops the orchestrator at startup.

Before 2026-10-23 a broken overlay (invalid YAML, a list at the top level) was skipped
silently by the merge and `AIFactory._load_config` swallowed anything else into `{}`, so the
process ran on defaults the operator never chose, with Director auto actions defaulting on.
"""

from __future__ import annotations

import logging

import pytest

from core.config_merge import ConfigLoadError, load_merged_config
from director.decision_engine import DecisionEngine, director_settings
from main import AIFactory


@pytest.fixture
def no_fragments(tmp_path, monkeypatch):
    empty = tmp_path / "no-fragments"
    empty.mkdir()
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(empty))
    return tmp_path


def test_lenient_load_skips_a_broken_overlay_and_logs_it(no_fragments, caplog):
    primary = no_fragments / "config.yaml"
    primary.write_text("director: [unclosed\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="core.config_merge"):
        assert load_merged_config(primary) == {}
    assert "config file skipped" in caplog.text
    assert str(primary) in caplog.text


def test_strict_load_raises_on_invalid_yaml(no_fragments):
    primary = no_fragments / "config.yaml"
    primary.write_text("director: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="config.yaml"):
        load_merged_config(primary, strict=True)


def test_strict_load_raises_on_a_non_mapping_and_a_broken_fragment(tmp_path, monkeypatch):
    frags = tmp_path / "fragments"
    frags.mkdir()
    (frags / "00-a.yaml").write_text("general: {ok: true}\n", encoding="utf-8")
    (frags / "10-b.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(frags))
    primary = tmp_path / "config.yaml"
    primary.write_text("general: {name: x}\n", encoding="utf-8")
    assert load_merged_config(primary)["general"] == {"ok": True, "name": "x"}
    with pytest.raises(ConfigLoadError, match="10-b.yaml: top level is list"):
        load_merged_config(primary, strict=True)


def test_strict_load_accepts_missing_and_empty_files(no_fragments):
    assert load_merged_config(no_fragments / "absent.yaml", strict=True) == {}
    empty = no_fragments / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_merged_config(empty, strict=True) == {}


def test_strict_is_checked_on_a_cache_hit_too(no_fragments):
    primary = no_fragments / "config.yaml"
    primary.write_text("general: [\n", encoding="utf-8")
    load_merged_config(primary)  # lenient call fills the cache
    with pytest.raises(ConfigLoadError):
        load_merged_config(primary, strict=True)


def test_factory_refuses_to_start_on_a_broken_overlay(no_fragments):
    primary = no_fragments / "config.yaml"
    primary.write_text("director:\n  auto_actions_enabled: true\n bad-indent: 1\n", encoding="utf-8")
    with pytest.raises(ConfigLoadError):
        AIFactory(str(primary))


def test_factory_refuses_a_quoted_boolean_for_auto_actions(no_fragments):
    primary = no_fragments / "config.yaml"
    primary.write_text('director:\n  auto_actions_enabled: "false"\n', encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="auto_actions_enabled must be true or false"):
        AIFactory(str(primary))


def test_factory_without_a_director_section_keeps_auto_actions_off(no_fragments):
    primary = no_fragments / "config.yaml"
    primary.write_text("general: {}\n", encoding="utf-8")
    factory = AIFactory(str(primary))
    assert factory.director_settings == {
        "auto_actions_enabled": False,
        "allowed_auto_actions": [],
        "analysis_interval_hours": 4,
    }
    assert factory.get_status()["config"]["auto_actions"] is False


def test_factory_reads_the_shipped_fragments(monkeypatch, tmp_path):
    from pathlib import Path

    frags = Path(__file__).resolve().parent.parent / "config" / "fragments"
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(frags))
    factory = AIFactory(str(tmp_path / "absent.yaml"))
    assert factory.director_settings["auto_actions_enabled"] is True
    assert "increase_agent_timeout" in factory.director_settings["allowed_auto_actions"]


@pytest.mark.parametrize(
    "section, message",
    [
        ([], "expected a mapping"),
        ({"auto_actions_enabled": "yes"}, "auto_actions_enabled"),
        ({"auto_actions_enabled": 1}, "auto_actions_enabled"),
        ({"allowed_auto_actions": "increase_agent_timeout"}, "allowed_auto_actions"),
        ({"allowed_auto_actions": [1]}, "allowed_auto_actions"),
        ({"analysis_interval_hours": 0}, "analysis_interval_hours"),
        ({"analysis_interval_hours": "4"}, "analysis_interval_hours"),
    ],
)
def test_director_settings_rejects_wrong_types(section, message):
    with pytest.raises(ConfigLoadError, match=message):
        director_settings(section)


def test_rules_file_with_a_quoted_false_turns_auto_actions_off(tmp_path):
    rules = tmp_path / "director_rules.yaml"
    rules.write_text('auto_actions_enabled: "false"\nallowed_auto_actions: [increase_agent_timeout]\n')
    engine = DecisionEngine(auto_actions_enabled=True, config_path=str(rules))
    assert engine.auto_actions_enabled is False
    assert engine._is_action_allowed("increase_agent_timeout") is False


def test_unreadable_rules_file_turns_auto_actions_off(tmp_path):
    rules = tmp_path / "director_rules.yaml"
    rules.write_text("auto_actions_enabled: [\n")
    engine = DecisionEngine(
        auto_actions_enabled=True, allowed_actions=["increase_agent_timeout"], config_path=str(rules)
    )
    assert engine._is_action_allowed("increase_agent_timeout") is False


def test_rules_file_without_the_keys_keeps_constructor_values(tmp_path):
    rules = tmp_path / "director_rules.yaml"
    rules.write_text("report_retention_days: 30\n")
    engine = DecisionEngine(
        auto_actions_enabled=True, allowed_actions=["increase_agent_timeout"], config_path=str(rules)
    )
    assert engine._is_action_allowed("increase_agent_timeout") is True
