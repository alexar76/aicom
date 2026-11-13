#!/usr/bin/env python3
"""Stage a CMC-only ARGUS signer from stdin on Attested without restarting a service."""

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path("/root/argus")
ROSTER = ROOT / "docker-compose.roster.yml"
ENV_FILE = ROOT / ".env.external-x402"
ENV_NAME = "ARGUS_EXTERNAL_X402_WALLET_KEY"
PAYEE_NAME = "ARGUS_CMC_PAY_TO"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", ROSTER.name, "config", "--format", "json"]


def config():
    result = subprocess.run(COMPOSE, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("Compose validation failed")
    return json.loads(result.stdout)["services"]


def replace(path, data, mode):
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=ROOT)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


if os.geteuid() != 0 or len(sys.argv) != 2 or not re.fullmatch(r"0x[0-9a-fA-F]{40}", sys.argv[1]):
    raise SystemExit("Run as root with the confirmed CMC recipient argument and send the signer key on stdin")
key = sys.stdin.buffer.read(256).strip()
if not re.fullmatch(rb"0x[0-9a-fA-F]{64}", key):
    raise SystemExit("Expected one 32-byte 0x-prefixed signer key on stdin")
if ENV_FILE.exists() or ENV_FILE.is_symlink() or ROSTER.is_symlink():
    raise SystemExit("Dedicated signer file already exists or roster path is a symlink")

previous = config()
if any(name in service.get("environment", {}) for service in previous.values() for name in (ENV_NAME, PAYEE_NAME)):
    raise SystemExit("Unexpected existing signer or recipient in Compose")
original = ROSTER.read_bytes()
mode = stat.S_IMODE(ROSTER.stat().st_mode)
anchor = b"services:\n  argus:\n"
if original.count(anchor) != 1 or b"env_file:" in original:
    raise SystemExit("Unexpected ARGUS roster shape")
new = original.replace(anchor, anchor + b"    env_file:\n      - .env.external-x402\n", 1)
payee = sys.argv[1].lower()
backup = ROSTER.with_name(f"{ROSTER.name}.pre-cmc-env-20261113")
if backup.exists() or backup.is_symlink():
    raise SystemExit("Roster backup already exists")
replace(backup, original, mode)
try:
    replace(ENV_FILE, ENV_NAME.encode() + b"=" + key + b"\n" + PAYEE_NAME.encode() + b"=" + payee.encode() + b"\n", 0o600)
    replace(ROSTER, new, mode)
    current = config()
    live = current["argus"].get("environment", {})
    if live.pop(ENV_NAME, None) != key.decode() or live.pop(PAYEE_NAME, None) != payee:
        raise SystemExit("Dedicated signer and recipient did not resolve into the live service")
    if current != previous:
        raise SystemExit("Unexpected Compose changes beyond the two live ARGUS fields")
except BaseException:
    replace(ROSTER, original, mode)
    ENV_FILE.unlink(missing_ok=True)
    backup.unlink(missing_ok=True)
    raise

print("CMC-only signer staged in the live service. Compose resolves unchanged configuration for UNI. Restart pending.")
