from __future__ import annotations

import asyncio

import pytest

from main import AIFactory


class _DummyCollector:
    def collect_all(self):
        return {}


class _SlowAnalyzer:
    def analyze(self, metrics):
        import time
        time.sleep(0.2)
        return {}


class _DummyInspector:
    def run_audit(self, window_hours=24):
        return {}


class _DummyDecisionEngine:
    def generate_decisions(self, analysis, metrics):
        return []


class _DummyDirectorIntegration:
    def apply_decision(self, decision):
        return None


class _DummyReportGenerator:
    def generate_report(self, analysis, metrics, decisions, inspector_report=None):
        return "ok"


@pytest.mark.asyncio
async def test_director_analysis_timeout(monkeypatch):
    monkeypatch.setenv("AIFACTORY_DIRECTOR_ANALYSIS_TIMEOUT_SEC", "0.05")
    factory = AIFactory()
    factory._components = {
        "metrics_collector": _DummyCollector(),
        "analyzer": _SlowAnalyzer(),
        "inspector": _DummyInspector(),
        "decision_engine": _DummyDecisionEngine(),
        "director_integration": _DummyDirectorIntegration(),
        "report_generator": _DummyReportGenerator(),
    }
    result = await factory._run_director_analysis()
    assert result["success"] is False
    assert "timeout" in str(result["error"]).lower()
