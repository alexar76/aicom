import json
from pathlib import Path

import pytest
import respx
import httpx
from typer.testing import CliRunner

from relay_scout.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("RELAY_SCOUT_DATA_DIR", str(data_dir))
    cfg = tmp_path / "relay-scout.yaml"
    cfg.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "test-service",
                        "url": "https://example.com/health",
                        "kind": "json",
                        "webhook_urls": ["https://hooks.example.com/alert"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    # YAML loader accepts JSON too via yaml - use actual yaml
    cfg.write_text(
        "targets:\n  - name: test-service\n    url: https://example.com/health\n    kind: json\n    webhook_urls:\n      - https://hooks.example.com/alert\n",
        encoding="utf-8",
    )
    return cfg


def test_cli_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.stdout


@respx.mock
def test_cli_check(runner: CliRunner, config_file: Path) -> None:
    respx.get("https://example.com/health").respond(200, json={"status": "ok"})
    respx.post("https://hooks.example.com/alert").respond(200, json={"ok": True})
    result = runner.invoke(app, ["check", "--config", str(config_file)])
    assert result.exit_code == 0
    assert "UP" in result.stdout


@respx.mock
def test_cli_diff(runner: CliRunner, config_file: Path) -> None:
    respx.get("https://example.com/health").respond(200, json={"status": "ok", "v": 1})
    runner.invoke(app, ["check", "--config", str(config_file)])
    respx.get("https://example.com/health").respond(200, json={"status": "ok", "v": 2})
    runner.invoke(app, ["check", "--config", str(config_file)])
    result = runner.invoke(app, ["diff", "test-service", "--config", str(config_file)])
    assert result.exit_code == 0
    assert "Diff" in result.stdout
