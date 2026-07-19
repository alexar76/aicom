"""Declarative browser scenario helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.backend.services.browser_e2e_scenarios import (
    load_scenario_specs,
    substitute_env_values,
)


def test_substitute_env_values_nested(monkeypatch):
    monkeypatch.setenv("MYVAR", "hello")
    assert substitute_env_values({"x": "${MYVAR}", "y": [1, "${MYVAR}"]}) == {"x": "hello", "y": [1, "hello"]}


def test_load_scenario_specs_from_code_dir(tmp_path, monkeypatch):
    code = tmp_path / "code" / "prod-x"
    code.mkdir(parents=True)
    specs = [{"name": "a", "steps": [{"wait_ms": 1}]}]
    (code / "e2e-scenarios.json").write_text(json.dumps(specs), encoding="utf-8")
    monkeypatch.delenv("AIFACTORY_BROWSER_SCENARIO_FILE", raising=False)
    out = load_scenario_specs(code)
    assert len(out) == 1 and out[0]["name"] == "a"


def test_load_scenario_file_override(tmp_path, monkeypatch):
    p = tmp_path / "custom.json"
    p.write_text(json.dumps({"scenarios": [{"name": "b", "steps": []}]}), encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_BROWSER_SCENARIO_FILE", str(p))
    out = load_scenario_specs(Path("/dev/null"))
    assert out[0]["name"] == "b"
