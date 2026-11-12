"""Scratch repro: the sandbox per-IP hourly cap is check-then-record, so concurrent free
trials from one address (each with a fresh self-chosen visitor id) all pass the check."""
from __future__ import annotations

import sys
import threading

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

from aimarket_hub import sandbox_trials  # noqa: E402


def test_ip_cap_overshoot(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_SANDBOX_MAX_PER_IP_HOUR", "3")
    monkeypatch.setattr(sandbox_trials, "_MAX_PER_IP_HOUR", 3)
    ledger = sandbox_trials.SandboxTrialLedger(db_path=str(tmp_path / "trials.db"))
    n = 20
    barrier = threading.Barrier(n)
    original = ledger._ip_within_limit

    def checked(ip):
        ok = original(ip)
        barrier.wait()  # every request has read the count before any recorded its hit
        return ok

    monkeypatch.setattr(ledger, "_ip_within_limit", checked)
    out = []

    def one(i):
        out.append(ledger.consume(f"visitor_{i:04d}x", client_ip="203.0.113.7"))

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    served = sum(1 for r in out if r.get("ok"))
    print("served", served, "of", n, "with a per-IP cap of 3")
    assert served == n
