"""Tests for the factory-side Metis confidence-gate (llm/metis_gate.py).

The gate must be auto-detecting and fail-open: with no Metis reachable the
factory proceeds unchanged and nothing raises. These tests monkeypatch
``urllib.request.urlopen`` so they never touch the network.
"""

from __future__ import annotations

import io
import json

import pytest

from llm import metis_gate


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Start from a known-clean env and a fresh detection cache every test.
    for var in (
        "AIFACTORY_METIS_GATE",
        "AIFACTORY_METIS_GATE_BLOCK",
        "AIFACTORY_METIS_URL",
        "METIS_URL",
        "AIFACTORY_METIS_API_KEY",
        "METIS_API_KEY",
        "AIFACTORY_METIS_GATE_ROUTE",
        "AIFACTORY_METIS_GATE_MIN_SCORE",
    ):
        monkeypatch.delenv(var, raising=False)
    metis_gate.reset_probe_cache()
    yield
    metis_gate.reset_probe_cache()


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._data = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._data

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _router(health_ok=True, verify_payload=None, verify_raises=None):
    """Build a fake urlopen that answers /health and /v1/verify."""

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/health"):
            if health_ok:
                return _FakeResp({"status": "ok", "service": "metis"})
            raise OSError("connection refused")
        if url.endswith("/v1/verify"):
            if verify_raises is not None:
                raise verify_raises
            return _FakeResp(verify_payload or {})
        raise AssertionError(f"unexpected url: {url}")

    return fake_urlopen


# ── mode resolution ──────────────────────────────────────────────────────────

def test_default_mode_is_auto():
    assert metis_gate.metis_gate_mode() == "auto"
    assert metis_gate.metis_gate_enabled() is True


def test_off_disables_without_network(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "off")

    def _boom(*a, **k):
        raise AssertionError("must not touch the network when off")

    monkeypatch.setattr(metis_gate.urllib.request, "urlopen", _boom)
    v = metis_gate.verify("anything")
    assert v.ok is True and v.available is False and v.status == "disabled"


# ── auto-detect + fail-open ──────────────────────────────────────────────────

def test_auto_not_detected_proceeds(monkeypatch):
    # /health refuses => not detected => fail-open proceed, /v1/verify never hit.
    monkeypatch.setattr(metis_gate.urllib.request, "urlopen", _router(health_ok=False))
    v = metis_gate.verify("build X")
    assert v.ok is True
    assert v.available is False
    assert v.status == "unavailable"


def test_verify_network_error_is_failopen(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE", "on")  # skip probe, call directly
    monkeypatch.setattr(
        metis_gate.urllib.request,
        "urlopen",
        _router(verify_raises=OSError("boom")),
    )
    v = metis_gate.verify("build X")
    assert v.ok is True and v.available is False and v.status == "unavailable"


# ── verdict mapping ──────────────────────────────────────────────────────────

def test_success_verified(monkeypatch):
    monkeypatch.setattr(
        metis_gate.urllib.request,
        "urlopen",
        _router(verify_payload={"status": "success", "verified": True, "verify_score": 0.91,
                                "route": "council", "answer": "ok"}),
    )
    v = metis_gate.verify("clear task", route="council")
    assert v.available is True
    assert v.ok is True and v.verified is True
    assert v.verify_score == 0.91 and v.status == "success"


def test_needs_clarification_flags(monkeypatch):
    monkeypatch.setattr(
        metis_gate.urllib.request,
        "urlopen",
        _router(verify_payload={"status": "needs_clarification", "verify_score": 0.0,
                                "clarifications": ["What platform?", "Which users?"]}),
    )
    v = metis_gate.verify("vague idea")
    assert v.available is True
    assert v.ok is False
    assert v.status == "needs_clarification"
    assert v.clarifications == ["What platform?", "Which users?"]


def test_low_score_flags(monkeypatch):
    monkeypatch.setenv("AIFACTORY_METIS_GATE_MIN_SCORE", "0.8")
    monkeypatch.setattr(
        metis_gate.urllib.request,
        "urlopen",
        _router(verify_payload={"status": "success", "verified": False, "verify_score": 0.5}),
    )
    v = metis_gate.verify("meh")
    assert v.ok is False and v.reason == "low_confidence"


def test_engine_error_is_failopen(monkeypatch):
    monkeypatch.setattr(
        metis_gate.urllib.request,
        "urlopen",
        _router(verify_payload={"status": "error", "verify_score": 0.0}),
    )
    v = metis_gate.verify("x")
    assert v.available is True and v.ok is True and v.status == "error"


# ── helpers ──────────────────────────────────────────────────────────────────

def test_build_understanding_query_includes_idea_and_spec():
    q = metis_gate.build_understanding_query("A todo app", spec="Must sync offline")
    assert "A todo app" in q and "Must sync offline" in q
    assert "clarification" in q.lower()


def test_verify_product_understanding(monkeypatch):
    monkeypatch.setattr(
        metis_gate.urllib.request,
        "urlopen",
        _router(verify_payload={"status": "success", "verified": True, "verify_score": 0.75}),
    )
    v = metis_gate.verify_product_understanding("An app", spec="clear spec")
    assert v.ok is True and v.verified is True


def test_probe_cache_reused(monkeypatch):
    calls = {"n": 0}
    fake = _router(verify_payload={"status": "success", "verified": True, "verify_score": 0.9})

    def counting(req, timeout=None):
        if (req.full_url).endswith("/health"):
            calls["n"] += 1
        return fake(req, timeout=timeout)

    monkeypatch.setattr(metis_gate.urllib.request, "urlopen", counting)
    metis_gate.verify("one")
    metis_gate.verify("two")
    assert calls["n"] == 1  # health probed once, then cached
