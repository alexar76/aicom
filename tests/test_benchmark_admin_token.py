"""Tests for optional benchmark admin JWT resolution."""

from __future__ import annotations

from pathlib import Path

from core.benchmark_admin_token import read_benchmark_admin_token


def test_no_token_when_unset(monkeypatch):
    monkeypatch.delenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE", raising=False)
    assert read_benchmark_admin_token() is None


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN", "  jwt-here  ")
    monkeypatch.delenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE", raising=False)
    assert read_benchmark_admin_token() == "jwt-here"


def test_token_from_file(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN", raising=False)
    p = tmp_path / "tok.txt"
    p.write_text(" from-file \n", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE", str(p))
    assert read_benchmark_admin_token() == "from-file"


def test_env_wins_over_file(monkeypatch, tmp_path: Path):
    p = tmp_path / "tok.txt"
    p.write_text("file", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE", str(p))
    monkeypatch.setenv("AIFACTORY_BENCHMARK_ADMIN_TOKEN", "env-wins")
    assert read_benchmark_admin_token() == "env-wins"
