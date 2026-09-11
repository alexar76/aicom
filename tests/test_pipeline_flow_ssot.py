"""SSOT: config/pipeline_flow.json must match orchestrator and frontend loaders."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW, pipeline_product_states, pipeline_stage_agents


def test_pipeline_flow_json_loads_agent_flow():
    path = Path(__file__).resolve().parents[1] / "config" / "pipeline_flow.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    for state, pair in doc["agent_flow"].items():
        assert PIPELINE_AGENT_FLOW[state] == tuple(pair)


def test_pipeline_flow_contains_design_and_hardening_stages():
    assert PIPELINE_AGENT_FLOW["ARCH_DESIGNED"] == ("design_critic", "DESIGN_CRITIQUED")
    assert PIPELINE_AGENT_FLOW["DESIGN_CRITIQUED"] == ("developer", "CODE_COMMITTED")
    assert PIPELINE_AGENT_FLOW["CODE_COMMITTED"] == ("__runtime_test__", "CODE_TESTING")
    assert PIPELINE_AGENT_FLOW["CODE_TESTING"] == ("hardening", "DEV_FIXING")


def test_product_states_include_terminal_and_branch_states():
    states = pipeline_product_states()
    assert "COMPLETED" in states
    assert "FAILED" in states
    assert "BUG_FOUND" in states
    assert "HUMAN_REVIEW_PENDING" in states
    assert "DEPLOYED_PRODUCTION" in states


def test_stage_agents_match_monitor_order():
    stages = pipeline_stage_agents()
    assert stages[0] == "analyst"
    assert "methodologist" in stages
    assert stages[-1] == "sales"
