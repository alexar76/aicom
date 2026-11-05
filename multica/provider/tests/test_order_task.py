"""order-task: reads and closes only the order agent's own tasks; refuses odd ids before calling Multica."""
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "order-task" / "order-task"
AGENT = "0ac4ba96-4066-4c8d-bfb9-690ee0c98d3e"
OTHER = "3001a515-2e3c-417d-861c-2b8a6f3f3941"
FAKE = """#!/bin/sh
echo "$*" >> "$LOG"
if [ "$1 $2" = "issue get" ]; then
  case "$3" in
    MY-1|0d3c3a7e-0000-4000-8000-000000000001) printf '{"identifier":"%s","assignee_type":"agent","assignee_id":"%s","description":"x"}' "$3" "$ORDER";;
    MY-2) printf '{"identifier":"MY-2","assignee_type":"agent","assignee_id":"%s"}' "$OTHERAGENT";;
    MY-3) printf '{"identifier":"MY-3","assignee_type":"member","assignee_id":"%s"}' "$ORDER";;
    *) echo "not found" >&2; exit 1;;
  esac
  exit 0
fi
[ "$1 $2" = "issue status" ] && exit 0
exit 9
"""


@pytest.fixture()
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "multica"
    fake.write_text(FAKE)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}", "LOG": str(log), "ORDER": AGENT, "OTHERAGENT": OTHER}, log


def run(env, *args):
    e, log = env
    p = subprocess.run([str(SCRIPT), *args], env=e, capture_output=True, text=True, timeout=10)
    calls = log.read_text().splitlines() if log.exists() else []
    return p.returncode, p.stdout, calls


def test_reads_its_own_task(env):
    code, out, calls = run(env, "get", "MY-1")
    assert code == 0 and json.loads(out)["identifier"] == "MY-1"
    assert calls == ["issue get MY-1 --output json"]


def test_uuid_ids_work(env):
    code, out, _ = run(env, "get", "0d3c3a7e-0000-4000-8000-000000000001")
    assert code == 0 and json.loads(out)["assignee_id"] == AGENT


def test_closes_its_own_task(env):
    code, out, calls = run(env, "done", "MY-1")
    assert code == 0 and out.strip() == "done: MY-1"
    assert calls == ["issue get MY-1 --output json", "issue status MY-1 done --no-start"]


@pytest.mark.parametrize("issue", ["MY-2", "MY-3"])
@pytest.mark.parametrize("action", ["get", "done"])
def test_refuses_other_tasks(env, action, issue):
    code, out, calls = run(env, action, issue)
    assert code == 3 and out == ""
    assert calls == [f"issue get {issue} --output json"], "never prints or changes another task"


@pytest.mark.parametrize("args", [
    [], ["get"], ["get", "MY-1", "MY-2"], ["list", "MY-1"], ["get", "MY-"], ["get", "MY-1a"], ["get", "MY-12345678"],
    ["get", "MY-1\nMY-2"], ["get", "--output"], ["get", "0D3C3A7E-0000-4000-8000-000000000001"],
    ["get", "0d3c3a7e-0000-4000-8000-00000000000"], ["get", "../MY-1"], ["done", "MY-1 --start"],
])
def test_refuses_odd_arguments_before_calling_multica(env, args):
    code, _, calls = run(env, *args)
    assert code == 2 and calls == []


def test_unknown_task(env):
    code, out, calls = run(env, "get", "MY-404")
    assert code == 1 and out == "" and calls == ["issue get MY-404 --output json"]
