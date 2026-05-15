"""Agent-to-agent handoff audit (hash-chained pipeline transitions)."""

from __future__ import annotations

import json

import pytest

from security.agent_handoff_audit import fingerprint_payload, log_agent_handoff
from security.audit_logger import AuditLogger


def test_fingerprint_payload_omits_values():
    fp = fingerprint_payload({"api_key": "secret", "idea": "hello"})
    assert "secret" not in json.dumps(fp)
    assert "hello" not in json.dumps(fp)
    assert fp["key_count"] == 2
    assert "api_key" in fp["keys"]


def test_log_agent_handoff_writes_hash_chain(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs" / "audit"
    monkeypatch.setattr(
        "security.agent_handoff_audit.logs_dir",
        lambda: tmp_path / "logs",
    )
    monkeypatch.setattr(
        "security.agent_handoff_audit._AUDIT",
        AuditLogger(str(log_dir)),
    )

    ok = log_agent_handoff(
        product_id="prod-abc",
        from_agent="pm",
        to_agent="architect",
        from_state="SPEC_WRITTEN",
        to_state="ARCH_DESIGNED",
        task_id="task-1",
        next_task_id="task-2",
        reason="sequential",
        output_data={"spec_version": 2, "notes": "do not store"},
    )
    assert ok is True
    files = list(log_dir.glob("audit-*.jsonl"))
    assert files
    line = files[0].read_text(encoding="utf-8").strip().split("\n")[-1]
    entry = json.loads(line)
    assert entry["action"] == "agent_handoff"
    assert entry["actor"] == "agent:pm"
    assert entry["resource"] == "pipeline/prod-abc"
    assert entry["details"]["to_agent"] == "architect"
    assert "do not store" not in json.dumps(entry["details"])
