"""AuditLogger.verify_integrity — hash chain across files and tamper cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from security.audit_logger import AuditLogger, GENESIS_HASH


def test_verify_integrity_true_after_log_rotation(tmp_path) -> None:
    log_dir = tmp_path / "audit_chain"
    audit = AuditLogger(str(log_dir), max_file_size_mb=100, max_log_files=10)
    audit.max_file_size = 400
    for i in range(30):
        audit.log(f"evt_{i}", "actor", "res", {"i": i})
    files = sorted(log_dir.glob("audit-*.jsonl"))
    assert len(files) >= 2, "expected rotation into multiple jsonl files"
    r = audit.verify_integrity()
    assert r["verified"] is True, r
    assert r["entries_checked"] >= 30
    assert r["files_checked"] >= 2


def test_verify_integrity_detects_hash_chain_break(tmp_path) -> None:
    log_dir = tmp_path / "audit_break"
    audit = AuditLogger(str(log_dir), max_file_size_mb=100, max_log_files=10)
    audit.log("a1", "u", "r", {})
    audit.log("a2", "u", "r", {})
    log_file = sorted(log_dir.glob("audit-*.jsonl"))[0]
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    row = json.loads(lines[1])
    row["previous_hash"] = GENESIS_HASH
    lines[1] = json.dumps(row)
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = audit.verify_integrity()
    assert r["verified"] is False
    assert any(x.get("reason") == "hash_chain_break" for x in r["tampered_entries"])
