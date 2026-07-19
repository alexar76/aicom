"""Tests for QA repair budget policy — factory ships products, not FAILED."""

from __future__ import annotations

import os

import pytest

from orchestrator.qa_repair_policy import (
    resolve_qa_repair_after_failure,
    resolve_security_repair_after_failure,
)


def test_resolve_qa_repair_within_budget():
    product = {"id": "p1", "quality_repair_round": 0}
    exhausted, rnd, state = resolve_qa_repair_after_failure(
        product, new_repair_round=3, max_quality_loops=25
    )
    assert not exhausted
    assert rnd == 3
    assert state == "BUG_FOUND"


def test_resolve_qa_repair_auto_extends(monkeypatch):
    monkeypatch.setenv("AIFACTORY_QA_REPAIR_EXTENSIONS", "2")
    product = {"id": "p1", "quality_repair_round": 8}
    exhausted, rnd, state = resolve_qa_repair_after_failure(
        product, new_repair_round=9, max_quality_loops=8
    )
    assert not exhausted
    assert rnd == 0
    assert state == "BUG_FOUND"
    assert product["qa_repair_extensions"] == 1
    assert product.get("quality_repair_round") == 0


def test_resolve_qa_repair_human_review_not_failed(monkeypatch):
    monkeypatch.setenv("AIFACTORY_QA_REPAIR_EXTENSIONS", "0")
    product = {"id": "p1", "quality_repair_round": 7}
    exhausted, rnd, state = resolve_qa_repair_after_failure(
        product, new_repair_round=9, max_quality_loops=8
    )
    assert exhausted
    assert rnd == 9
    assert state == "HUMAN_REVIEW_PENDING"
    assert product.get("human_review_kind") == "qa_repair_exhausted"
    assert "failure_reason" not in product


def test_resolve_security_repair_human_review(monkeypatch):
    monkeypatch.setenv("AIFACTORY_QA_REPAIR_EXTENSIONS", "0")
    product = {"id": "p2", "security_repair_round": 4}
    exhausted, state = resolve_security_repair_after_failure(
        product, new_sec_round=6, max_security_loops=5
    )
    assert exhausted
    assert state == "HUMAN_REVIEW_PENDING"
    assert product.get("human_review_kind") == "security_repair_exhausted"


def test_max_pipeline_repair_rounds_for_landing_respects_yaml_cap(monkeypatch):
    monkeypatch.delenv("AIFACTORY_MAX_QUALITY_LOOPS", raising=False)
    monkeypatch.delenv("AIFACTORY_LANDING_MAX_QUALITY_LOOPS", raising=False)
    from core.quality_settings import (
        OPTIMIZED_QUALITY_PRESETS,
        max_pipeline_repair_rounds_for_delivery_profile,
    )

    assert (
        max_pipeline_repair_rounds_for_delivery_profile("marketing_landing")
        == OPTIMIZED_QUALITY_PRESETS["max_pipeline_repair_rounds_landing"]
    )
