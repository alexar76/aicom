"""Unparseable requirements.txt must fail QA and must not be copied into a Vercel bundle.

Sentinel shipped ``bcrypt==3.2.2==0.110.0``. The sandbox pip -r failed, the preview still
booted from extras, Vercel --prod died on parse, and the pipeline recorded COMPLETED.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import json

from web.backend.services.requirements_manifest import (
    drop_invalid_requirements,
    requirement_line_is_valid,
    run_requirements_manifest_check,
)
from web.backend.services.live_deployment_gate import vercel_publish_failure_as_live_gate
from web.backend.services.vercel_fullstack_adapter import build_vercel_bundle


def test_repair_batch_extracts_the_requirements_path():
    from core.repair_batches import _files_in

    assert "backend/requirements.txt" in _files_in(
        "invalid_requirement:backend/requirements.txt:2: bcrypt==3.2.2==0.110.0"
    )
    assert requirement_line_is_valid("bcrypt==3.2.2==0.110.0") is False
    assert requirement_line_is_valid("fastapi==0.110.0") is True
    assert requirement_line_is_valid("uvicorn[standard]==0.29.0") is True
    assert requirement_line_is_valid("passlib[bcrypt]") is True


def test_drop_invalid_keeps_the_real_pin():
    kept, invalid = drop_invalid_requirements(
        [
            "fastapi",
            "bcrypt==3.2.2==0.110.0",
            "bcrypt==4.1.2",
            "httpx==0.27.0",
        ]
    )
    assert "bcrypt==3.2.2==0.110.0" in invalid
    assert "bcrypt==4.1.2" in kept
    assert "bcrypt==3.2.2==0.110.0" not in kept


def test_qa_gate_names_the_requirements_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    code = tmp_path / "code" / "prod-x" / "backend"
    code.mkdir(parents=True)
    (code / "requirements.txt").write_text(
        "fastapi==0.110.0\nbcrypt==3.2.2==0.110.0\nbcrypt==4.1.2\n",
        encoding="utf-8",
    )
    report = run_requirements_manifest_check("prod-x", tmp_path)
    assert report["passed"] is False
    assert any("bcrypt==3.2.2==0.110.0" in i for i in report["issues"])
    assert any(p.endswith("requirements.txt") for p in report["files"])


def test_bundle_does_not_copy_the_double_pin(tmp_path: Path):
    root = tmp_path / "code" / "prod-x"
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "frontend" / "dist" / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (root / "frontend" / "dist" / "assets" / "x.js").write_text("//js", encoding="utf-8")
    (root / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (root / "backend" / "requirements.txt").write_text(
        "fastapi==0.110.0\nbcrypt==3.2.2==0.110.0\nbcrypt==4.1.2\n",
        encoding="utf-8",
    )
    out = tmp_path / "bundle"
    report = build_vercel_bundle(root, out, build_frontend=False)
    assert report["ok"] is True, report
    assert "bcrypt==3.2.2==0.110.0" in (report.get("invalid_requirements") or [])
    text = (out / "requirements.txt").read_text(encoding="utf-8")
    assert "bcrypt==3.2.2==0.110.0" not in text
    assert "bcrypt==4.1.2" in text


def test_vercel_cli_parse_error_is_a_live_gate_failure():
    gate = vercel_publish_failure_as_live_gate(
        product_id="prod-bdb1634806de",
        exit_code=1,
        stderr=(
            "Error: could not parse requirements.txt: Couldn't parse requirement in "
            "`/vercel/path1/requirements.txt` at position 8\n"
        ),
        bundle={"invalid_requirements": ["bcrypt==3.2.2==0.110.0"]},
    )
    assert gate["passed"] is False
    assert gate.get("skipped") is False
    assert any("invalid_requirement" in i for i in gate["issues"])
    assert any("vercel_build_failed" in i for i in gate["issues"])
    assert any("requirements.txt" in p for p in gate["repair_scope"])


def test_publish_and_executor_treat_cli_failure_as_live_gate():
    from pathlib import Path as P

    publish = (P("web") / "backend" / "services" / "auto_publish.py").read_text(encoding="utf-8")
    executor = (P("orchestrator") / "task_executor_agent.py").read_text(encoding="utf-8")
    assert "vercel_publish_failure_as_live_gate" in publish
    assert "invalid_requirements" in publish
    assert "live_gate_failed" in executor
    assert 'lg.get("passed") is False' in executor
    assert "live_gate_from_saved_vercel_record" in executor
    worker = (P("pipeline_worker.py").read_text(encoding="utf-8"))
    assert "_enforce_failed_vercel_publish" in worker


def test_preview_does_not_install_line_by_line_after_pip_r_fails(tmp_path: Path, monkeypatch):
    from web.backend.services import sandbox_preview_env as env

    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text("bcrypt==3.2.2==0.110.0\n", encoding="utf-8")
    python_bin = tmp_path / "python"
    python_bin.write_text("", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if "-r" in cmd:
            return MagicMock(returncode=1, stdout="", stderr="Couldn't parse requirement")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(env.subprocess, "run", fake_run)
    result = env._pip_install_requirements(backend, tmp_path, python_bin)
    assert result["ok"] is False
    assert any("-r" in c for c in calls)
    assert not any(
        cmd[:3] == [str(python_bin), "-m", "pip"] and "-r" not in cmd and "-e" not in cmd
        for cmd in calls
    )


def test_saved_vercel_parse_error_reopens_a_completed_product(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-bdb1634806de"
    rec = tmp_path / "state" / pid
    rec.mkdir(parents=True)
    (rec / "auto_publish.json").write_text(
        json.dumps(
            {
                "ok": True,
                "product_id": pid,
                "vercel": {
                    "ok": False,
                    "exit_code": 1,
                    "stderr_tail": (
                        "Error: could not parse requirements.txt: Couldn't parse requirement "
                        "in `/vercel/path1/requirements.txt` at position 8"
                    ),
                    "live_gate": {},
                },
            }
        ),
        encoding="utf-8",
    )
    from web.backend.services.live_deployment_gate import (
        apply_vercel_publish_failure_to_snapshot,
        live_gate_from_saved_vercel_record,
    )

    gate = live_gate_from_saved_vercel_record(pid)
    assert gate is not None
    assert gate["passed"] is False
    product = {"id": pid, "idea": "Sentinel", "state": "COMPLETED"}
    queue: list = []
    assert apply_vercel_publish_failure_to_snapshot(pid, product, queue) is True
    assert product["state"] == "BUG_FOUND"
    assert queue and queue[0]["state"] == "DEV_FIXING"
    assert queue[0]["input_data"]["live_gate_blocked"] is True


def test_missing_vercel_token_does_not_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-no-token"
    rec = tmp_path / "state" / pid
    rec.mkdir(parents=True)
    (rec / "auto_publish.json").write_text(
        json.dumps({"ok": True, "vercel": {"ok": False, "error": "VERCEL_TOKEN not set"}}),
        encoding="utf-8",
    )
    from web.backend.services.live_deployment_gate import live_gate_from_saved_vercel_record

    assert live_gate_from_saved_vercel_record(pid) is None


def test_complete_marker_is_ignored_when_vercel_prod_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-x"
    rec = tmp_path / "state" / pid
    rec.mkdir(parents=True)
    (rec / "auto_publish.json").write_text(
        json.dumps(
            {
                "ok": True,
                "vercel": {
                    "ok": False,
                    "exit_code": 1,
                    "stderr_tail": "Error: could not parse requirements.txt",
                },
            }
        ),
        encoding="utf-8",
    )
    from orchestrator.pipeline_state_sync import infer_product_state_from_tasks

    tasks = [
        {
            "product_id": pid,
            "agent_type": "__complete__",
            "state": "COMPLETED",
            "status": "completed",
        }
    ]
    assert infer_product_state_from_tasks(tasks) != "COMPLETED"
