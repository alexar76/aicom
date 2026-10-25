"""A garbled answer to a per-idea enrichment leaves it empty instead of failing the cycle."""
from __future__ import annotations

import asyncio

from director import discovery_pipeline as dp


class _Router:
    def __init__(self, text: str):
        self.text = text

    async def generate(self, prompt, task_type=None, config=None):
        return self.text


def _pipeline(text: str):
    p = dp.DiscoveryPipeline.__new__(dp.DiscoveryPipeline)
    p.router = _Router(text)
    return p


def test_an_empty_answer_leaves_the_gap_analysis_empty():
    out = asyncio.run(_pipeline("")._competitive_gap_analysis(idea="x", category="tools", signals=[]))
    assert out == {"competitors": [], "gaps": [], "tam_sam_som": {}, "pain_to_feature_map": []}


def test_an_empty_answer_leaves_the_interviews_empty():
    assert asyncio.run(_pipeline("sorry, I cannot")._simulate_problem_interviews(idea="x", category="tools")) == []


def test_a_good_answer_still_parses():
    out = asyncio.run(_pipeline('```json\n{"competitors": ["a"], "gaps": []}\n```')._competitive_gap_analysis(
        idea="x", category="tools", signals=[]))
    assert out["competitors"] == ["a"]
