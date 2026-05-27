"""Tests for factory on-hold (pause) helper."""

from __future__ import annotations

import os

import pytest

from core.factory_hold import is_factory_on_hold


def test_factory_on_hold_from_config_dict():
    assert is_factory_on_hold(config={"general": {"factory_on_hold": True}}) is True
    assert is_factory_on_hold(config={"general": {"factory_on_hold": False}}) is False


def test_factory_on_hold_env_override(monkeypatch):
    monkeypatch.setenv("AIFACTORY_FACTORY_ON_HOLD", "1")
    assert is_factory_on_hold(config={"general": {"factory_on_hold": False}}) is True
