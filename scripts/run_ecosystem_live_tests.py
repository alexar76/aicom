#!/usr/bin/env python3
"""Run live contracts through SSH forwards without payments or LLM work."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    "FACTORY_URL": 9081, "FRONTEND_URL": 9080, "HUB_URL": 9083, "MESH_URL": 8090,
    "ARGUS_URL": 8787, "ARGUS_UNI_URL": 8788, "MONITOR_URL": 9100,
    "PULSE_URL": 5199, "LOTTERY_RELAYER_URL": 9195,
}
# Read just the two credentials needed for GET endpoints. Never print or persist their values.
TOKEN_READER = """
import json,subprocess
out={}
for container,key in [('aicom-mesh-api','MESH_API_TOKEN'),('alien-monitor','ALIEN_API_TOKEN')]:
    data=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
    values=dict(entry.split('=',1) for entry in data['Config']['Env'] if '=' in entry)
    if values.get(key): out[key]=values[key]
print(json.dumps(out))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", default="factory-vps")
    parser.add_argument("--skopos-ssh-host", default="skopos-vps")
    args, pytest_args = parser.parse_known_args()
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    env = dict(os.environ, ECOSYSTEM_INTEGRATION="1", ENV_FILE=os.devnull)
    env["SKOPOS_URL"] = "https://skopos.modelmarket.dev"
    credentials = subprocess.run(
        [*ssh, args.ssh_host, "python3 -c " + shlex.quote(TOKEN_READER)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    env.update(json.loads(credentials.stdout))
    skopos_reader = TOKEN_READER.replace(
        "[('aicom-mesh-api','MESH_API_TOKEN'),('alien-monitor','ALIEN_API_TOKEN')]",
        "[('metis-skopos','SKOPOS_AIMARKET_API_KEY')]",
    )
    skopos_credentials = subprocess.run(
        [*ssh, args.skopos_ssh_host, "python3 -c " + shlex.quote(skopos_reader)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    env.update(json.loads(skopos_credentials.stdout))
    forwards = []
    for name, remote in SERVICES.items():
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            local = reserve.getsockname()[1]
        env[name] = f"http://127.0.0.1:{local}"
        forwards += ["-L", f"127.0.0.1:{local}:127.0.0.1:{remote}"]
    with tempfile.TemporaryFile() as errors:
        tunnel = subprocess.Popen(
            [*ssh, "-N", "-o", "ExitOnForwardFailure=yes", *forwards, args.ssh_host],
            stdout=subprocess.DEVNULL, stderr=errors,
        )
        try:
            deadline = time.monotonic() + 30
            port = int(env["FACTORY_URL"].rsplit(":", 1)[1])
            while True:
                if tunnel.poll() is not None:
                    raise RuntimeError("SSH tunnel exited before readiness")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("SSH tunnel did not become ready") from None
                    time.sleep(.1)
            return subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "tests/test_ecosystem_connectivity.py",
                 "--timeout=90", *pytest_args], cwd=ROOT, env=env, check=False,
            ).returncode
        finally:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()


if __name__ == "__main__":
    raise SystemExit(main())
