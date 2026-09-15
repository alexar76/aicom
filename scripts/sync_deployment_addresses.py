#!/usr/bin/env python3
"""Regenerate every derived copy of the on-chain address registry.

`config/deployments/<network>-mainnet.json` is the ONE file a human edits (or that a
deploy script writes). Everything else that needs an address is generated from it:

    config/deployments/base-mainnet.json          ← the only hand-edited source
      ├─ aimarket-hub/aimarket_hub/deployments/   ← package data, so a standalone
      ├─ alien-monitor/backend/deployments/          pip install still resolves
      └─ argus/src/ecosystem/deployments.base.json ← TS import (resolveJsonModule)

Before this existed the addresses were *mirrored*: typed by hand into two Python
modules and one TypeScript object, with a test that noticed divergence after the fact.
That made a redeploy a six-file edit where five of the files could be forgotten, and
"the test is green" only meant nobody had drifted yet.

Usage:
    python scripts/sync_deployment_addresses.py            # write
    python scripts/sync_deployment_addresses.py --check    # fail if anything is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "config" / "deployments"

#: Python consumers get the registry verbatim as package data, so
#: ``chain_net._load_deployment_contracts`` resolves it even off-repo.
PACKAGE_DATA_DIRS = (
    ROOT / "aimarket-hub" / "aimarket_hub" / "deployments",
    ROOT / "alien-monitor" / "backend" / "deployments",
)

#: ARGUS maps registry names onto its own field names. Keeping the mapping HERE (not in
#: TypeScript) is what stops an address from being typed by hand on that side.
ARGUS_JSON = ROOT / "argus" / "src" / "ecosystem" / "deployments.base.json"
ARGUS_FIELD_MAP = {
    "lottery": "AIAgentLottery",
    "usdc": "USDC",
    "escrow": "AIMarketEscrow",
    "acexAmm": "PulseAMM",
    "acexRegistry": "AgentListingRegistry",
    "lendingPool": "AgentLendingPool",
    "capabilityNft": "AIMarketCapabilityNFT",
}

GENERATED_BANNER = (
    "GENERATED FILE — do not edit. Source: config/deployments/{name}. "
    "Regenerate with: python scripts/sync_deployment_addresses.py"
)


def load_registry(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    contracts = data.get("contracts")
    if not isinstance(contracts, dict) or not contracts:
        raise SystemExit(f"{path}: no 'contracts' object")
    return data


def _write(path: Path, text: str, *, check: bool, stale: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == text:
        return
    if check:
        stale.append(str(path.relative_to(ROOT)))
        return
    path.write_text(text, encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def sync_network(registry_path: Path, *, check: bool, stale: list[str]) -> dict:
    data = load_registry(registry_path)
    contracts: dict[str, str] = data["contracts"]
    name = registry_path.name

    # 1. Python package data: the registry, verbatim, plus a provenance banner.
    payload = dict(data)
    payload["_generated"] = GENERATED_BANNER.format(name=name)
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    for pkg_dir in PACKAGE_DATA_DIRS:
        _write(pkg_dir / name, body, check=check, stale=stale)

    # 2. ARGUS: only the fields it declares, under its own field names.
    if registry_path.stem == "base-mainnet":
        missing = [v for v in ARGUS_FIELD_MAP.values() if v not in contracts]
        if missing:
            raise SystemExit(f"registry is missing contracts ARGUS needs: {missing}")
        argus = {
            "_generated": GENERATED_BANNER.format(name=name),
            "chainId": data.get("chain_id"),
            "addresses": {k: contracts[v] for k, v in ARGUS_FIELD_MAP.items()},
        }
        _write(
            ARGUS_JSON,
            json.dumps(argus, indent=2, ensure_ascii=False) + "\n",
            check=check,
            stale=stale,
        )
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report staleness, write nothing")
    args = ap.parse_args()

    registries = sorted(REGISTRY_DIR.glob("*-mainnet.json"))
    if not registries:
        raise SystemExit(f"no registries found in {REGISTRY_DIR}")

    stale: list[str] = []
    for reg in registries:
        if not args.check:
            print(f"{reg.relative_to(ROOT)}:")
        sync_network(reg, check=args.check, stale=stale)

    if args.check and stale:
        print("stale generated files (run scripts/sync_deployment_addresses.py):")
        for path in stale:
            print(f"  - {path}")
        return 1
    if args.check:
        print("all generated address files are in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
