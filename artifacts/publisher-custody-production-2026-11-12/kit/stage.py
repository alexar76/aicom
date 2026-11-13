"""Stage the custody patch alone against the documented 3.21.0 source baseline."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

BASELINE = "ce215c70b"
EXISTING = (
    "api.py", "channel_ledger/opening.py", "channel_ledger/spending.py", "channel_ledger/sweeps.py",
    "channels.py", "credits.py", "deposit_verify.py", "deposit_watch.py", "hub_lifespan.py",
    "hub_routes/invoke_parts/federated_delivery.py", "hub_routes/invoke_parts/local_delivery.py",
    "hub_routes/payments.py", "idempotency.py", "migrations.py", "settlement_service/finalizing.py", "topup.py",
)
ADDED = (
    "hub_routes/publisher_withdrawals.py", "publisher_withdrawal_chain.py", "publisher_withdrawal_cli.py",
    "publisher_withdrawals.py",
)


def main() -> None:
    kit = Path(__file__).resolve().parent
    repo = kit.parents[2]
    destination = Path(sys.argv[1]).resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise SystemExit("staging directory must be empty")
    old_hashes, new_hashes = [], []
    for relative in EXISTING + ADDED:
        source = "aimarket-hub/aimarket_hub/" + relative
        data = (repo / source).read_bytes()
        if relative in EXISTING:
            old = subprocess.check_output(["git", "show", f"{BASELINE}:{source}"], cwd=repo)
            old_hashes.append(f"{hashlib.sha256(old).hexdigest()}  {relative}\n")
            if data == old:
                raise SystemExit(f"custody patch is missing for {relative}")
        target = destination / "overlay" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        new_hashes.append(f"{hashlib.sha256(data).hexdigest()}  {relative}\n")
    (destination / "preimage.sha256").write_text("".join(old_hashes))
    (destination / "overlay.sha256").write_text("".join(new_hashes))
    for name in ("Dockerfile", "deploy.sh", "snapshot.py", "smoke.py"):
        shutil.copyfile(kit / name, destination / name)
    print(f"staged {len(new_hashes)} custody files at {destination}")


if __name__ == "__main__":
    main()
