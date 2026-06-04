"""Policy audit: re-verify completed products when marketplace rules apply."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.backend.services.policy_audit import apply_policy_audit


def _write_manifest(code_dir: Path, files: list[str]) -> None:
    code_dir.mkdir(parents=True, exist_ok=True)
    payload = {"files": [{"path": f} for f in files]}
    (code_dir / "code_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    for f in files:
        p = code_dir / f
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("", encoding="utf-8")


def test_policy_audit_failing_product_gets_dev_task(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MAX_QUALITY_LOOPS", "10")

    root = tmp_path
    pid = "prod-audit-bad"
    _write_manifest(root / "data" / "code" / pid, ["index.html"])
    (root / "data" / "code" / pid / "index.html").write_text(
        "<!DOCTYPE html><html><body>Full application deployed.</body></html>",
        encoding="utf-8",
    )
    spec_path = root / "data" / "specs" / pid
    spec_path.mkdir(parents=True)
    spec_inner = {
        "product_name": "X",
        "description": "Hello world",
        "core_features": [{"name": "Feature A", "description": "Does something"}],
    }
    (spec_path / "specification.json").write_text(
        json.dumps({"specification": spec_inner}), encoding="utf-8"
    )

    products = {
        pid: {
            "id": pid,
            "idea": "idea",
            "state": "COMPLETED",
            "created_at": 0,
        }
    }
    task_queue: list = []

    changed = apply_policy_audit(products, task_queue, 1_700_000_000.0, data_root=str(root / "data"))
    assert changed is True
    assert products[pid]["state"] == "BUG_FOUND"
    assert len(task_queue) == 1
    assert task_queue[0]["agent_type"] == "developer"
    assert task_queue[0]["input_data"].get("policy_audit_trigger") is True


def test_policy_audit_passing_product_no_task(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    # Isolate from repo ``quality:`` YAML (defaults can require methodology / novelty, etc.).
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_QA_REALISM", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_RELEASE_SCORE", "0")
    root = tmp_path
    pid = "prod-audit-good"
    code_dir = root / "data" / "code" / pid
    _write_manifest(code_dir, ["index.html", "style.css", "main.py"])
    html = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>G</title><link href="./style.css" rel="stylesheet"/></head>
<body><main><h1>Hello world Feature A</h1>
<p>Does something useful for teams every day. Task management for teams who need reliability.</p>
<section><h2>Dashboard</h2><p>Analytics dashboard with live metrics for Feature A workflows.</p></section>
<footer><p>Contact and onboarding for new users.</p></footer>
<button type="button">Get started</button></main></body></html>"""
    (code_dir / "index.html").write_text(html, encoding="utf-8")
    (code_dir / "style.css").write_text(
        """:root{--bg:#020617;--fg:#e2e8f0;--accent:#38bdf8}
        body{background:var(--bg);color:var(--fg);font-family:system-ui,sans-serif}
        button:focus-visible{outline:3px solid var(--accent)}@media(max-width:720px){main{padding:16px}}""",
        encoding="utf-8",
    )
    (code_dir / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )

    spec_inner = {
        "product_name": "Good",
        "description": "Hello world product for teams",
        "core_features": [{"name": "Feature A", "description": "Does something useful"}],
    }
    spec_path = root / "data" / "specs" / pid
    spec_path.mkdir(parents=True)
    (spec_path / "specification.json").write_text(
        json.dumps({"specification": spec_inner}), encoding="utf-8"
    )

    products = {
        pid: {
            "id": pid,
            "idea": "idea",
            "state": "COMPLETED",
            "created_at": 0,
        }
    }
    task_queue: list = []

    apply_policy_audit(products, task_queue, 1_700_000_000.0, data_root=str(root / "data"))
    # A passing product must never be sent to rework: no dev task, stays terminal,
    # and is marked compliant. (It may flip `changed` the first time only because the
    # storefront listing gets marked "established" — not because of a quality regression.)
    assert len(task_queue) == 0
    assert products[pid]["state"] == "COMPLETED"
    assert products[pid].get("policy_audit_eligible") is True
    assert int(products[pid].get("quality_repair_round") or 0) == 0
