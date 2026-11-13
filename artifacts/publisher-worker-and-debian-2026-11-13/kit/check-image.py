"""Capture package parity, Hub source parity, and runtime checks without a database."""

import gzip
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import subprocess
import sys
import zlib

from aimarket_hub.publisher_withdrawal_chain import PublisherWithdrawalChain, USDC_ADDRESS
from eth_account import Account


package_root = Path("/app/aimarket_hub")
digest = hashlib.sha256()
for path in sorted(package_root.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
        digest.update(str(path.relative_to(package_root)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())

packages = {}
rows = subprocess.check_output(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Abbrev}\n"],
                               text=True)
for row in rows.splitlines():
    name, version, status = row.split("\t")
    if status.startswith("ii"):
        packages[name] = version
assert not subprocess.check_output(["dpkg", "--audit"], text=True).strip()
subprocess.run(["apt-get", "check"], check=True, stdout=sys.stderr)

message = bytes(range(256)) * 8
assert zlib.decompress(zlib.compress(message)) == message
assert gzip.decompress(gzip.compress(message)) == message
account = Account.create()
assert PublisherWithdrawalChain(account.address).sender == account.address.lower()

print(json.dumps({"apt_version": subprocess.check_output(["apt-get", "--version"], text=True).splitlines()[0],
                  "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION, "zlib_gzip_roundtrip": True,
                  "base_usdc_contract": USDC_ADDRESS, "hub_source_sha256": digest.hexdigest(),
                  "python": sorted([dist.metadata["Name"], dist.version] for dist in distributions()),
                  "debian": packages}, sort_keys=True))
