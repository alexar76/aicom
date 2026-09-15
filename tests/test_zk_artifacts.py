"""Tests for ZK ceremony artifact validation."""

from __future__ import annotations

from security import zk_artifacts as zk


def test_production_zk_issues_empty_when_not_groth16(monkeypatch):
    monkeypatch.delenv("AIMARKET_ZK_BACKEND", raising=False)
    monkeypatch.setenv("AIMARKET_ZK_SIMULATED", "1")
    assert zk.production_zk_issues() == []


def test_production_zk_issues_reports_missing_artifacts(monkeypatch):
    monkeypatch.setenv("AIMARKET_ZK_BACKEND", "groth16")
    monkeypatch.setenv("AIMARKET_ZK_WASM", "/tmp/missing-zk.wasm")
    monkeypatch.setenv("AIMARKET_ZK_ZKEY", "/tmp/missing-zk.zkey")
    monkeypatch.setenv("AIMARKET_ZK_VKEY_JSON", "/tmp/missing-vkey.json")
    monkeypatch.setenv("AIMARKET_ZK_VERIFIER_SOL", "/tmp/MissingVerifier.sol")
    monkeypatch.delenv("AIMARKET_ZK_SNARKJS", raising=False)
    issues = zk.production_zk_issues()
    assert len(issues) >= 4
    assert any("AIMARKET_ZK_WASM" in i for i in issues)
    assert any("snarkjs" in i for i in issues)
