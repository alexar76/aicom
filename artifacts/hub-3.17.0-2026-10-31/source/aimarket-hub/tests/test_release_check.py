"""A hub hears about a newer release when doctor or serve starts, and is never slowed by it."""
from __future__ import annotations

from aimarket_hub import release_check


def test_a_newer_release_is_announced():
    line = release_check.notice("3.15.25", "3.15.26")
    assert line and "3.15.26" in line and "3.15.25" in line and "pip install -U" in line


def test_same_older_or_unknown_says_nothing():
    assert release_check.notice("3.15.25", "3.15.25") is None
    assert release_check.notice("3.15.25", "3.15.9") is None
    assert release_check.notice("3.15.25", None) is None
    assert release_check.notice("3.15.25", "") is None


def test_numeric_not_lexical_order():
    assert release_check.notice("3.9.0", "3.15.0") is not None


def test_an_unreachable_index_is_none_not_an_error():
    assert release_check.latest(timeout=0.5, url="http://127.0.0.1:9/nothing") is None


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("AIMARKET_UPDATE_CHECK", "0")
    assert release_check.enabled() is False
    monkeypatch.setenv("AIMARKET_UPDATE_CHECK", "1")
    assert release_check.enabled() is True
