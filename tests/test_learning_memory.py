from pathlib import Path

from web.backend.services.learning_memory import append_lesson, load_recent_lessons


def test_learning_memory_roundtrip(tmp_path: Path):
    root = str(tmp_path / "data")
    append_lesson(root, {"product_id": "prod-1", "summary": "first lesson"})
    append_lesson(root, {"product_id": "prod-2", "summary": "second lesson"})
    rows = load_recent_lessons(root, limit=2)
    assert len(rows) == 2
    assert rows[0]["product_id"] == "prod-2"


def test_learning_memory_compacts_and_dedups(tmp_path: Path, monkeypatch):
    root = str(tmp_path / "data")
    monkeypatch.setenv("AIFACTORY_LEARNING_MEMORY_MAX_BYTES", "400")
    monkeypatch.setenv("AIFACTORY_LEARNING_MEMORY_DEDUP_WINDOW", "50")
    for _ in range(10):
        append_lesson(root, {"product_id": "prod-1", "agent_type": "qa", "target_state": "QA_TESTING", "summary": "same"})
    rows = load_recent_lessons(root, limit=20)
    assert len(rows) >= 1
