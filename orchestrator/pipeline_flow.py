from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_FLOW_JSON = Path(__file__).resolve().parents[1] / "config" / "pipeline_flow.json"


@lru_cache(maxsize=1)
def _load_flow_document() -> dict[str, Any]:
    raw = json.loads(_FLOW_JSON.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid pipeline flow document: {_FLOW_JSON}")
    return raw


def _parse_agent_flow(doc: dict[str, Any]) -> dict[str, tuple[str, str]]:
    flow_raw = doc.get("agent_flow")
    if not isinstance(flow_raw, dict):
        raise ValueError("pipeline_flow.json: missing agent_flow object")
    out: dict[str, tuple[str, str]] = {}
    for state, pair in flow_raw.items():
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"pipeline_flow.json: agent_flow[{state!r}] must be [agent, next_state]")
        out[str(state)] = (str(pair[0]), str(pair[1]))
    return out


# Canonical state -> (agent, next_state) map used across orchestrator + worker.
PIPELINE_AGENT_FLOW: dict[str, tuple[str, str]] = _parse_agent_flow(_load_flow_document())


def pipeline_product_states() -> list[str]:
    doc = _load_flow_document()
    states = doc.get("product_states")
    if not isinstance(states, list):
        return []
    return [str(s) for s in states]


def pipeline_stage_agents() -> list[str]:
    doc = _load_flow_document()
    stages = doc.get("stage_agents")
    if not isinstance(stages, list):
        return []
    return [str(s) for s in stages]
