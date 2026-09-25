"""themis/deploy/deploy_prod.sh recreates the production hub; it must hand it what deploy_hub.sh does.

deploy_hub.sh and deploy_hub_rebuild.sh give the hub a service-filtered env and mount only
the read-only catalog export at /factory_data. The THEMIS deploy is a second door that
recreates the same container, and both its deploy and rollback paths still mounted the
Factory data tree (secrets/, signing keys) with the raw `docker inspect` env.

The script is run for real, with `ssh` replaced by a local shell and docker by a recorder,
so what is asserted is the `docker run` the server would have executed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "themis" / "deploy" / "deploy_prod.sh"
sys.path.insert(0, str(ROOT / "scripts" / "security"))
from service_env import filtered  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix", reason="bash deploy script")

# What `docker inspect modelmarket-hub` reports: hub settings plus shared ones it must not keep.
LIVE_HUB_ENV = [
    "AIFACTORY_PROD=1",
    "AIFACTORY_DATA_ROOT=/factory_data",
    "AIMARKET_PAYMENT_RECIPIENT=0x000000000000000000000000000000000000dEaD",
    "AIMARKET_SELLS_FOR=local",
    "AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE=off",
    "ACEX_AUTO_IPO=0",
    "JWT_SECRET_KEY=CANARY_JWT",
    "CUSTOMER_JWT_SECRET=CANARY_CUSTOMER_JWT",
    "POSTGRES_PASSWORD=CANARY_POSTGRES",
    "MESH_API_TOKEN=CANARY_MESH",
]

FAKES = {
    "ssh": """
import os, subprocess, sys
host, command = sys.argv[1], sys.argv[2]
command = command.replace("/tmp/themis.pubkey", os.environ["FAKE_PUBKEY_FILE"])
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"tool": "ssh", "host": host}) + "\\n")
sys.exit(subprocess.run(["bash", "-c", command]).returncode)
""",
    "rsync": """
import shutil, sys
args, excludes, paths = sys.argv[1:], [], []
it = iter(args)
for a in it:
    if a == "--exclude":
        excludes.append(next(it))
    elif not a.startswith("-"):
        paths.append(a)
src, dst = paths
dst = dst.split(":", 1)[1]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"tool": "rsync", "dst": dst}) + "\\n")
shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*excludes))
""",
    "docker": """
import sys
args = sys.argv[1:]
record = {"tool": "docker", "argv": args, "env_files": {}}
for i, a in enumerate(args):
    if a == "--env-file":
        record["env_files"][args[i + 1]] = open(args[i + 1]).read()
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(record) + "\\n")
fmt = args[args.index("--format") + 1] if "--format" in args else ""
if args[0] == "inspect" and ".Config.Env" in fmt:
    print(open(os.environ["FAKE_HUB_ENV"]).read(), end="")
elif args[0] == "inspect" and ".Config.Image" in fmt:
    print("modelmarket-hub:prod-previous")
elif args[0] == "run" and "python" in args:
    print("FAKEPUBKEY0123456789abcdef")
elif args[0] == "exec":
    sys.stdin.read()
    if os.environ.get("FAKE_EXPORT_FAILS"):
        sys.exit("factory container is down")
    print(json.dumps({"products": {"prod-a": {"name": "A", "state": "COMPLETED"}}}))
""",
    "curl": """
print(json.dumps({"summary": {"mode": "advisory", "configured": True}}))
""",
    "sleep": "",
}


@pytest.fixture
def server(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        tool = bin_dir / name
        tool.write_text(f"#!{sys.executable}\nimport json, os\n{body}")
        tool.chmod(0o755)
    remote = tmp_path / "server" / "aicom"
    remote.mkdir(parents=True)
    # What the old mount handed the hub, so a regression is visible as a real directory.
    (remote / "data" / "secrets").mkdir(parents=True)
    (remote / "data" / "hub_signing_key").write_text("CANARY_SIGNING_KEY")
    export = tmp_path / "server" / "hub-catalog"
    hub_env = tmp_path / "live_hub.env"
    hub_env.write_text("\n".join(["PATH=/usr/local/bin", *LIVE_HUB_ENV]) + "\n")
    log = tmp_path / "calls.jsonl"

    def deploy(mode, **extra):
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "THEMIS_PROD_HOST": "fake-host", "THEMIS_PROD_PATH": str(remote),
               "AIMARKET_FACTORY_EXPORT_ROOT": str(export), "FAKE_LOG": str(log),
               "FAKE_HUB_ENV": str(hub_env), "FAKE_PUBKEY_FILE": str(tmp_path / "pubkey"),
               **extra}
        return subprocess.run(["bash", str(SCRIPT), mode], env=env, capture_output=True,
                              text=True, timeout=300)

    def docker_calls():
        if not log.exists():
            return []
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        return [r for r in rows if r["tool"] == "docker"]

    return {"deploy": deploy, "calls": docker_calls, "remote": remote, "export": export}


def _hub_run(calls):
    runs = [c for c in calls if c["argv"][:2] == ["run", "-d"] and "modelmarket-hub" in c["argv"]]
    assert len(runs) == 1, [c["argv"] for c in calls]
    return runs[0]


def _mounts(argv):
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]


def _env(record):
    (content,) = record["env_files"].values()
    return content.splitlines()


def _index(calls, prefix):
    return next(i for i, c in enumerate(calls) if c["argv"][:len(prefix)] == prefix)


def test_deploy_gives_the_hub_the_export_and_the_filtered_env(server):
    result = server["deploy"]("advisory")
    assert result.returncode == 0, result.stdout + result.stderr

    calls = server["calls"]()
    run = _hub_run(calls)
    assert f"{server['export']}:/factory_data:ro" in _mounts(run["argv"])
    assert not any(m.startswith(str(server["remote"] / "data")) for m in _mounts(run["argv"]))

    base = [line for line in filtered("hub", LIVE_HUB_ENV)
            if not line.startswith("AIMARKET_SUPPLY_CHAIN_")]
    assert _env(run) == base + [
        "AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE=advisory",
        "AIMARKET_SUPPLY_CHAIN_AUDITOR_URL=http://127.0.0.1:8080/invoke",
        "AIMARKET_SUPPLY_CHAIN_AUDITOR_PUBKEY=FAKEPUBKEY0123456789abcdef",
    ]
    assert "CANARY_" not in "\n".join(_env(run))
    assert "AIFACTORY_DATA_ROOT=/factory_data" in _env(run)

    snapshot = json.loads((server["export"] / "state" / "pipeline.json").read_text())
    assert list(snapshot["products"]) == ["prod-a"]
    assert _index(calls, ["exec"]) < _index(calls, ["rm", "-f", "modelmarket-hub"])


def test_a_failed_export_leaves_the_running_hub_alone(server):
    result = server["deploy"]("advisory", FAKE_EXPORT_FAILS="1")
    assert result.returncode != 0
    calls = server["calls"]()
    assert any(c["argv"][0] == "exec" for c in calls)
    assert not any(c["argv"][:2] == ["rm", "-f"] and "modelmarket-hub" in c["argv"] for c in calls)
    assert not any(c["argv"][:2] == ["run", "-d"] for c in calls)


def _prepare_rollback(server):
    admission = server["remote"] / "deploy-admission"
    admission.mkdir()
    # Captured raw by an earlier run of this script, before anything filtered it.
    (admission / "hub.env.previous").write_text("\n".join(LIVE_HUB_ENV) + "\n")
    (admission / "previous-image.txt").write_text("modelmarket-hub:prod-previous\n")


def test_rollback_uses_the_export_and_the_filtered_env(server):
    _prepare_rollback(server)
    result = server["deploy"]("rollback")
    assert result.returncode == 0, result.stdout + result.stderr

    run = _hub_run(server["calls"]())
    assert run["argv"][-1] == "modelmarket-hub:prod-previous"
    assert f"{server['export']}:/factory_data:ro" in _mounts(run["argv"])
    assert not any(m.startswith(str(server["remote"] / "data")) for m in _mounts(run["argv"]))
    assert _env(run) == filtered("hub", LIVE_HUB_ENV)
    assert "CANARY_" not in "\n".join(_env(run))


def test_rollback_with_the_factory_down_uses_the_last_snapshot(server):
    _prepare_rollback(server)
    (server["export"] / "state").mkdir(parents=True)
    (server["export"] / "state" / "pipeline.json").write_text('{"products": {}}')

    result = server["deploy"]("rollback", FAKE_EXPORT_FAILS="1")
    assert result.returncode == 0, result.stdout + result.stderr
    run = _hub_run(server["calls"]())
    assert f"{server['export']}:/factory_data:ro" in _mounts(run["argv"])


def test_rollback_with_no_export_at_all_keeps_the_running_hub(server):
    _prepare_rollback(server)
    result = server["deploy"]("rollback", FAKE_EXPORT_FAILS="1")
    assert result.returncode != 0
    assert not any(c["argv"][0] in ("rm", "run") for c in server["calls"]())


def test_nothing_mounts_anything_but_the_export_at_factory_data():
    """Every door that starts a hub: a new script copying the old mount line fails here."""
    listed = subprocess.run(["git", "ls-files", "*.sh", "*.py", "*.yml", "*.yaml"], cwd=ROOT,
                            capture_output=True, text=True)
    if listed.returncode:
        pytest.skip("not a git checkout")
    offenders = []
    for rel in listed.stdout.splitlines():
        path = ROOT / rel
        if "tests" in Path(rel).parts or not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for source in re.findall(r"""([^\s'"=]+)["']?:/factory_data\b""", line):
                if "FACTORY_EXPORT" not in source:
                    offenders.append(f"{rel}:{lineno}: {source}")
    assert offenders == []
