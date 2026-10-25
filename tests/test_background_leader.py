"""KI-3: with several uvicorn workers, the background loops run in exactly one of them."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_WORKER = textwrap.dedent("""
    import asyncio, os, sys
    sys.path.insert(0, {root!r})
    from web.backend.services import background_leader

    async def loop():
        with open({ran!r}, "a") as f:
            f.write(str(os.getpid()) + "\\n")
        await asyncio.sleep({hold})

    asyncio.run(background_leader.leader_only("test", loop, poll_s=0.1))
""")


def _start(tmp_path: Path, ran: Path, hold: float) -> subprocess.Popen:
    env = {**os.environ, "AIFACTORY_BACKGROUND_LEADER_LOCK": str(tmp_path / "leader.lock")}
    script = _WORKER.format(root=str(ROOT), ran=str(ran), hold=hold)
    return subprocess.Popen([sys.executable, "-c", script], env=env)


def _wait_for(pred, timeout: float = 20.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError("condition not reached")


def test_four_workers_run_the_loops_once_and_hand_them_over_when_the_leader_dies(tmp_path):
    ran = tmp_path / "ran.txt"
    workers = [_start(tmp_path, ran, hold=60) for _ in range(4)]
    try:
        _wait_for(lambda: ran.exists() and ran.read_text().strip())
        time.sleep(1.0)
        pids = ran.read_text().split()
        assert len(pids) == 1                       # one worker runs the loops ...
        leader = next(w for w in workers if str(w.pid) == pids[0])
        leader.kill()
        leader.wait(timeout=10)
        _wait_for(lambda: len(ran.read_text().split()) == 2)
        time.sleep(1.0)
        pids = ran.read_text().split()
        assert len(pids) == 2 and pids[1] != pids[0]  # ... and another takes over when it dies
    finally:
        for w in workers:
            w.kill()
            w.wait(timeout=10)
