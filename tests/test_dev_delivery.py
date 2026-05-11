"""Tests for developer delivery mode inference and validation."""
from __future__ import annotations

import json

import pytest

from agents.dev_delivery import DeliveryMode, infer_delivery_mode, validate_saved_files


def test_load_developer_investigation_brief(tmp_path):
    from agents.dev import _load_developer_investigation_brief

    pid = "prod-test-brief"
    state_dir = tmp_path / "state" / pid
    state_dir.mkdir(parents=True)
    payload = {
        "market_research": {
            "developer_investigation_brief": "1) Use relative paths.\n2) Hero + CTA.",
        }
    }
    (state_dir / "market_research.json").write_text(json.dumps(payload), encoding="utf-8")
    assert "relative" in _load_developer_investigation_brief(tmp_path, pid)


@pytest.mark.parametrize(
    "admin,expected",
    [
        ("Python CLI todo using argparse", DeliveryMode.PYTHON_CLI),
        ("Keep scope tiny; Python only; include README.", DeliveryMode.WEB_APP),
        ("E2E test: minimal CLI todo app for developers", DeliveryMode.PYTHON_CLI),
        ("Build a React SPA dashboard", DeliveryMode.WEB_APP),
        ("No browser — Python tool only with Typer", DeliveryMode.PYTHON_CLI),
        ("", DeliveryMode.WEB_APP),
    ],
)
def test_infer_mode(admin: str, expected: DeliveryMode):
    assert infer_delivery_mode(admin or None, {}) == expected


def test_infer_python_only_cli():
    assert infer_delivery_mode("Python only\nCLI with typer", {}) == DeliveryMode.PYTHON_CLI


def test_validate_python_cli_ok():
    ok, msg = validate_saved_files(
        DeliveryMode.PYTHON_CLI,
        ["main.py", "README.md", "tests/test_main.py"],
    )
    assert ok and msg == ""


def test_validate_python_cli_rejects_html():
    ok, msg = validate_saved_files(
        DeliveryMode.PYTHON_CLI,
        ["main.py", "index.html"],
    )
    assert not ok and "html" in msg.lower()


def test_validate_web_requires_html():
    ok, msg = validate_saved_files(DeliveryMode.WEB_APP, ["app.js"])
    assert not ok
    ok2, _ = validate_saved_files(DeliveryMode.WEB_APP, ["index.html", "styles.css"])
    assert ok2
