from __future__ import annotations

import json
import time
from pathlib import Path

from web.backend.services.feedback_digest import build_feedback_digest


def test_feedback_digest_empty_when_no_feedback(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_SUPPORT_SESSIONS_DIR", str(tmp_path / "support" / "sessions"))
    d = build_feedback_digest(window_hours=1)
    assert d["source"] == "feedback_digest_v1"
    assert "by_classification" in d


def test_feedback_digest_counts_recent_feedback(tmp_path: Path, monkeypatch):
    # feedback_digest reads feedback_dir() == data_root()/"feedback"; redirect the data
    # root into tmp instead of writing to a hardcoded /app/data/feedback.
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    fb_dir = tmp_path / "data" / "feedback"
    fb_dir.mkdir(parents=True, exist_ok=True)
    p = fb_dir / "fb-test.json"
    p.write_text(
        json.dumps(
            {
                "id": "fb-test",
                "product_id": "prod-x",
                "rating": 2,
                "comment": "Bug: sandbox crashes when clicking start",
                "classification": "bug",
                "usefulness_score": 0.8,
                "created_at": time.time(),
            }
        ),
        encoding="utf-8",
    )
    d = build_feedback_digest(window_hours=1)
    assert d["count"] >= 1
    assert d["by_classification"].get("bug", 0) >= 1

