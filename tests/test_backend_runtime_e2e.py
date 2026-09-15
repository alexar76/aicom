"""Tests for backend runtime E2E gate helpers."""

from __future__ import annotations

from web.backend.services.backend_runtime_e2e import run_backend_runtime_e2e


def test_backend_runtime_e2e_disabled(monkeypatch):
    monkeypatch.setenv("AIFACTORY_BACKEND_RUNTIME_E2E", "0")
    rep = run_backend_runtime_e2e("any", data_root="/nonexistent")
    assert rep.get("skipped") is True
    assert rep.get("passed") is True


def test_backend_runtime_e2e_no_code_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_BACKEND_RUNTIME_E2E", "1")
    rep = run_backend_runtime_e2e("missing", data_root=str(tmp_path))
    assert rep.get("passed") is False
    assert "no_code_dir" in (rep.get("issues") or [rep.get("error")])
