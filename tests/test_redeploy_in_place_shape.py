"""Capture/replay the live Hub's Docker shape without Docker or a network."""
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("port, published", [(9083, 9083), (9083, 9183)])
def test_redeploy_preserves_hub_command_claims_and_actual_probe(tmp_path, port, published):
    script = Path(__file__).resolve().parents[1] / "scripts/redeploy_in_place.sh"
    text = script.read_text()
    capture = text.split("docker inspect \"$NAME\" | python3 -c '\n", 1)[1].split("\n'\n# Anything", 1)[0]
    env_file = tmp_path / "runtime.env"
    spec = {
        "Config": {
            "Env": ["PORT=8080", "PRIVATE_TEST_VALUE=do-not-print"],
            "Entrypoint": ["python", "-m", "aimarket_hub", "serve"],
            "Cmd": ["--name", "Hub with spaces"],
            "Healthcheck": {"Test": ["CMD-SHELL", f"curl -f http://localhost:{port}/.well-known/ai-market.json"]},
        },
        "HostConfig": {"NetworkMode": "bridge", "PortBindings": {
            "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "9460"}],
            f"{port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(published)}],
        }},
        "Mounts": [
            {"Type": "volume", "Name": "modelmarket_hub_data", "Source": "/var/lib/docker/volumes/data/_data", "Destination": "/app/data"},
            {"Type": "bind", "Source": "/claims", "Destination": "/shared/deposit-claims"},
            {"Type": "bind", "Source": "/catalog", "Destination": "/factory_data"},
        ],
    }
    result = subprocess.run(
        ["python3", "-c", capture], input=json.dumps([spec]), text=True, capture_output=True,
        env={**os.environ, "ENV_FILE": str(env_file), "DROP_LIST": str(tmp_path / "no-drops")}, check=True,
    )
    assert "do-not-print" not in result.stdout + result.stderr
    shape = Path(str(env_file) + ".shape").read_text()
    assert f'PORT="{port}"' in shape
    assert f'PROBE_PORT="{published}"' in shape
    assert "modelmarket_hub_data:/app/data" in shape
    assert "/claims:/shared/deposit-claims:ro" not in shape
    assert "/catalog:/factory_data:ro" in shape
    # Exercise the actual shell replay block, including argument boundaries.
    replay = text.split("RUN_ARGS=()\nCOMMAND_ARGS=", 1)[1].split("# shellcheck disable=SC2086", 1)[0]
    command = 'source "$1"\nRUN_ARGS=()\nCOMMAND_ARGS=' + replay
    command += '\nprintf "%s\\0" "${RUN_ARGS[@]}" "${COMMAND_ARGS[@]}"'
    out = subprocess.check_output(["bash", "-c", command, "test", str(env_file) + ".shape"])
    assert out.split(b"\n", 1)[1].split(b"\0")[:-1] == [
        b"--entrypoint", b"python", b"-m", b"aimarket_hub", b"serve", b"--name", b"Hub with spaces",
    ]
