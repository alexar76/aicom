"""Tests for Owner corporate chat → Director routing (no live LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.backend.services import owner_chat_routing as ocr


def test_extract_json_object_raw_and_fence():
    assert ocr._extract_json_object('{"intent": "general_directive", "directive": "x"}')["intent"] == "general_directive"
    assert ocr._extract_json_object("```json\n{\"a\": 1}\n```")["a"] == 1


def test_apply_routing_new_idea(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipe = tmp_path / "pipeline.json"
    pipe.write_text(json.dumps({"products": {}, "task_queue": []}), encoding="utf-8")
    monkeypatch.setattr(ocr, "PIPELINE_FILE", pipe)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_uses_sql_store", lambda: False)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_json_path", lambda: pipe)
    fb_base = tmp_path / "feedback"
    monkeypatch.setattr(ocr, "FEEDBACK_BASE", fb_base)
    dirs_f = tmp_path / "owner_general_directives.json"
    monkeypatch.setattr(ocr, "DIRECTIVES_FILE", dirs_f)

    ok = ocr.apply_routing_result(
        {"intent": "new_idea", "idea": "Dental CRM for clinics"},
        message_id="m1",
        owner_text="ignored",
        catalog={},
    )
    assert ok is True
    state = json.loads(pipe.read_text(encoding="utf-8"))
    assert len(state["products"]) == 1
    pid = next(iter(state["products"].keys()))
    assert state["products"][pid]["state"] == "IDEA_RECEIVED"
    assert "Dental" in state["products"][pid]["idea"]


def test_apply_routing_product_feedback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipe = tmp_path / "pipeline.json"
    pipe.write_text(
        json.dumps(
            {
                "products": {
                    "prod-x": {"id": "prod-x", "idea": "Restaurant widget", "state": "DEV_DONE"},
                },
                "task_queue": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "PIPELINE_FILE", pipe)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_uses_sql_store", lambda: False)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_json_path", lambda: pipe)
    fb_base = tmp_path / "feedback"
    monkeypatch.setattr(ocr, "FEEDBACK_BASE", fb_base)

    ok = ocr.apply_routing_result(
        {
            "intent": "product_feedback",
            "product_id": "prod-x",
            "feedback": "Show free tables in widget",
        },
        message_id="msg-1",
        owner_text="Show free tables",
        catalog={"prod-x": {"id": "prod-x"}},
    )
    assert ok is True
    fb_path = fb_base / "prod-x" / "feedback.json"
    assert fb_path.exists()
    data = json.loads(fb_path.read_text(encoding="utf-8"))
    assert data["product_id"] == "prod-x"
    assert len(data["owner_messages"]) == 1
    assert data["owner_messages"][0]["text"] == "Show free tables in widget"
    assert data["owner_messages"][0]["intent"] == "product_feedback"


def test_orphan_product_feedback_heuristic_new_idea(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Invalid product_id but text looks like a new offering → pipeline."""
    pipe = tmp_path / "pipeline.json"
    pipe.write_text(json.dumps({"products": {}, "task_queue": []}), encoding="utf-8")
    monkeypatch.setattr(ocr, "PIPELINE_FILE", pipe)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_uses_sql_store", lambda: False)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_json_path", lambda: pipe)
    dirs_f = tmp_path / "owner_general_directives.json"
    monkeypatch.setattr(ocr, "DIRECTIVES_FILE", dirs_f)

    ok = ocr.apply_routing_result(
        {
            "intent": "product_feedback",
            "product_id": "nonexistent-prod",
            "feedback": "Build a CRM for dental clinics with online appointment booking",
        },
        message_id="orphan-1",
        owner_text="",
        catalog={},
    )
    assert ok is True
    state = json.loads(pipe.read_text(encoding="utf-8"))
    assert len(state["products"]) == 1
    pid = next(iter(state["products"].keys()))
    assert "dental" in state["products"][pid]["idea"].lower()


def test_orphan_product_feedback_heuristic_directive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Invalid product_id and short bug-like text → directive, not pipeline."""
    pipe = tmp_path / "pipeline.json"
    pipe.write_text(json.dumps({"products": {}, "task_queue": []}), encoding="utf-8")
    monkeypatch.setattr(ocr, "PIPELINE_FILE", pipe)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_uses_sql_store", lambda: False)
    monkeypatch.setattr("core.pipeline_state_writer.pipeline_json_path", lambda: pipe)
    dirs_f = tmp_path / "owner_general_directives.json"
    dirs_f.write_text(json.dumps({"directives": []}), encoding="utf-8")
    monkeypatch.setattr(ocr, "DIRECTIVES_FILE", dirs_f)

    ok = ocr.apply_routing_result(
        {
            "intent": "product_feedback",
            "product_id": "bad-id",
            "feedback": "The submit button does not work",
        },
        message_id="orphan-2",
        owner_text="",
        catalog={},
    )
    assert ok is True
    state = json.loads(pipe.read_text(encoding="utf-8"))
    assert len(state["products"]) == 0
    d = json.loads(dirs_f.read_text(encoding="utf-8"))
    assert len(d["directives"]) == 1
    assert "button" in d["directives"][0]["text"].lower()


def test_apply_routing_general_directive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pipe = tmp_path / "pipeline.json"
    pipe.write_text(json.dumps({"products": {}, "task_queue": []}), encoding="utf-8")
    monkeypatch.setattr(ocr, "PIPELINE_FILE", pipe)
    dirs_f = tmp_path / "owner_general_directives.json"
    monkeypatch.setattr(ocr, "DIRECTIVES_FILE", dirs_f)

    ok = ocr.apply_routing_result(
        {"intent": "general_directive", "directive": "More polish and motion design"},
        message_id="m2",
        owner_text="",
        catalog={},
    )
    assert ok is True
    d = json.loads(dirs_f.read_text(encoding="utf-8"))
    assert len(d["directives"]) == 1
    assert "motion" in d["directives"][0]["text"]


def test_format_owner_product_feedback_for_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ocr, "FEEDBACK_BASE", tmp_path / "feedback")
    base = tmp_path / "feedback" / "prod-a"
    base.mkdir(parents=True)
    base.joinpath("feedback.json").write_text(
        json.dumps(
            {
                "product_id": "prod-a",
                "owner_messages": [
                    {"text": "Fix login", "processed": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    txt = ocr.format_owner_product_feedback_for_prompt("prod-a")
    assert "Fix login" in txt
    assert "Owner feedback" in txt


def test_format_standup_owner_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dirs_f = tmp_path / "owner_general_directives.json"
    dirs_f.write_text(
        json.dumps({"directives": [{"text": "Ship faster", "id": "1"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "DIRECTIVES_FILE", dirs_f)
    fb = tmp_path / "feedback" / "p1"
    fb.mkdir(parents=True)
    fb.joinpath("feedback.json").write_text(
        json.dumps(
            {
                "product_id": "p1",
                "owner_messages": [{"text": "Bug in checkout", "processed": False}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ocr, "FEEDBACK_BASE", tmp_path / "feedback")

    out = ocr.format_standup_owner_context()
    assert "Ship faster" in out
    assert "checkout" in out
