"""Run existing adversarial suites for all first-party Vulnetix advisory families."""
import concurrent.futures
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PYTHON = str(ROOT / ".venv-quality/bin/python")
SUITES = {
    "helios": ("helios", ["tests"]),
    "mcp": ("aimarket-mcp", ["tests/test_hosted.py", "tests/test_ssrf_pinning.py"]),
    "metis": ("metis", ["tests/test_security.py", "tests/test_ssrf_pinning.py"]),
    "hestia": ("hestia", ["tests/test_owners.py", "tests/test_isolation.py", "tests/test_domains.py", "tests/test_ssrf.py"]),
    "platon": ("platon/backend", ["tests/test_api.py"]),
    "logos": ("logos", ["tests/test_app.py"]),
    "oracle-core": ("oracles/core", ["tests/test_tiers.py", "tests/test_calls.py"]),
    "skopos": ("skopos", ["tests/test_security_hardening.py", "tests/test_dashboard_peer_trust.py", "tests/test_remediation_git_push_hostkeys.py", "tests/test_auth_store.py"]),
    "signal-hunt": ("signal-hunt", ["tests/test_federation.py"]),
    "treasury": ("treasury", ["tests/test_treasury_service.py"]),
    "atlas": ("atlas", ["tests/test_watchbox_delivery.py"]),
    "histor": ("histor", ["tests/test_observer.py", "tests/test_security_events.py"]),
    "hub": ("aimarket-hub", ["tests/test_federated_invoke.py", "tests/test_outbound_pinning.py"]),
}


def run(item):
    name, (directory, files) = item
    env = dict(os.environ)
    source_paths = [ROOT / directory, ROOT / "oracles/core", ROOT / "momus", ROOT / "awr/reference/python"]
    if name == "skopos":
        prepared = Path("/private/tmp/claude-501/-Users-alex-Desktop-ai-tests-aicompany-aicom--claude-worktrees-platon-randomness-import-cedda0/658812e0-06b0-407e-a45a-636fae96bbfc/scratchpad/wheelsmoke/skopos/lib/python3.12/site-packages")
        if prepared.is_dir():
            source_paths.append(prepared)
    if name == "hub":
        source_paths.append(ROOT)
    env["PYTHONPATH"] = os.pathsep.join(map(str, source_paths))
    interpreter = "/private/tmp/aicom-vulnetix-hestia-testenv-20261107/bin/python" if name == "hestia" else PYTHON
    command = [interpreter, "-m", "pytest", *files, "-q"]
    if name == "hestia":
        # These are targeted trust-boundary regressions, not the full coverage gate.
        command.extend(["-o", "addopts="])
    result = subprocess.run(command, cwd=ROOT / directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    log = OUT / (name + "-tests.log")
    if log.exists():
        log.rename(OUT / (name + "-tests-initial.log"))
    log.write_text(result.stdout)
    row = {"suite": name, "cwd": directory, "command": command, "exit_code": result.returncode,
           "result": result.stdout.strip().splitlines()[-1] if result.stdout else "no output"}
    print(json.dumps(row), flush=True)
    return row


if __name__ == "__main__":
    chosen = {name: value for name, value in SUITES.items() if not sys.argv[1:] or name in sys.argv[1:]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(run, chosen.items()))
    dest = OUT / "regressions.json"
    previous = json.loads(dest.read_text())["suites"] if dest.exists() else []
    rows = [row for row in previous if row["suite"] not in chosen] + rows
    dest.write_text(json.dumps({"ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "suites": rows}, indent=2) + "\n")
