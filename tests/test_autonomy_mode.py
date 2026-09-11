"""Tests for core/autonomy_mode.py."""

from __future__ import annotations

import os

import pytest

from core.autonomy_mode import get_autonomy_mode, is_full_autonomy


def test_default_supervised(monkeypatch):
    monkeypatch.delenv("AIFACTORY_AUTONOMY_MODE", raising=False)
    assert get_autonomy_mode(config={"general": {"autonomy_mode": "supervised"}}) == "supervised"
    assert is_full_autonomy(config={"general": {"autonomy_mode": "supervised"}}) is False


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTONOMY_MODE", "full")
    assert get_autonomy_mode(config={"general": {"autonomy_mode": "supervised"}}) == "full"
    assert is_full_autonomy(config={"general": {"autonomy_mode": "full", "auto_pipeline": True}}) is True
    assert is_full_autonomy(config={"general": {"autonomy_mode": "full", "auto_pipeline": False}}) is False


def test_full_autonomy_requires_auto_pipeline(monkeypatch):
    monkeypatch.delenv("AIFACTORY_FACTORY_ON_HOLD", raising=False)
    cfg = {"general": {"autonomy_mode": "full", "auto_pipeline": False}}
    assert is_full_autonomy(config=cfg) is False
    cfg["general"]["auto_pipeline"] = True
    assert is_full_autonomy(config=cfg) is True


def test_factory_hold_blocks_full_autonomy(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTONOMY_MODE", "full")
    monkeypatch.setenv("AIFACTORY_FACTORY_ON_HOLD", "1")
    assert is_full_autonomy() is False
