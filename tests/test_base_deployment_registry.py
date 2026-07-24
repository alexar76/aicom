"""Anti-divergence guard for the Base-mainnet deployment registry.

config/deployments/base-mainnet.json is the single canonical source of the
deployed Base contract addresses. Three other places hold the same addresses:
  - docs/onchain-journal.md       (the human record, with every deploy tx)
  - aimarket-hub chain_net.py      (_BASE_ADDRESSES_FALLBACK, Python bundled copy)
  - argus/src/ecosystem/networks.ts (BASE_MAINNET_ADDRESSES, the TS client)

These tests fail if any of them drifts from the registry, so "docs ↔ code" can
never silently diverge. Addresses are public (on-chain); this is consistency,
not secrecy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "deployments" / "base-mainnet.json"
JOURNAL = ROOT / "docs" / "onchain-journal.md"
CHAIN_NET = ROOT / "aimarket-hub" / "aimarket_hub" / "chain_net.py"
ARGUS_NETWORKS = ROOT / "argus" / "src" / "ecosystem" / "networks.ts"


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _addrs_in(text: str) -> set[str]:
    """All 0x EVM addresses (40 hex) in a blob, lowercased."""
    return {m.lower() for m in re.findall(r"0x[0-9a-fA-F]{40}", text)}


def test_registry_is_wellformed():
    reg = _registry()
    assert reg["network"] == "base" and reg["chain_id"] == 8453
    contracts = reg["contracts"]
    assert contracts, "registry has no contracts"
    for name, addr in contracts.items():
        assert re.fullmatch(r"0x[0-9a-fA-F]{40}", addr), f"{name} is not a valid address: {addr}"


def test_every_registry_address_is_documented_in_the_journal():
    """Each deployed address must appear in the on-chain journal (docs ↔ config)."""
    journal_addrs = _addrs_in(JOURNAL.read_text(encoding="utf-8"))
    for name, addr in _registry()["contracts"].items():
        assert addr.lower() in journal_addrs, f"{name} {addr} is missing from docs/onchain-journal.md"
    assert _registry()["owner_wallet"].lower() in journal_addrs, "owner_wallet missing from the journal"


def test_python_fallback_matches_registry():
    """chain_net._BASE_ADDRESSES_FALLBACK must equal the registry (bundled copy in sync)."""
    import sys

    sys.path.insert(0, str(ROOT / "aimarket-hub"))
    from aimarket_hub import chain_net  # noqa: E402

    reg = {k: v.lower() for k, v in _registry()["contracts"].items()}
    fallback = {k: v.lower() for k, v in chain_net._BASE_ADDRESSES_FALLBACK.items()}
    assert fallback == reg, "chain_net._BASE_ADDRESSES_FALLBACK drifted from the registry"
    # And the live-loaded dict resolves to the same values.
    loaded = {k: v.lower() for k, v in chain_net._BASE_ADDRESSES.items()}
    assert loaded == reg, "chain_net loaded addresses differ from the registry"


def test_argus_typescript_constant_matches_registry():
    """Every address ARGUS hard-codes in BASE_MAINNET_ADDRESSES must be in the registry."""
    ts = ARGUS_NETWORKS.read_text(encoding="utf-8")
    block = re.search(r"BASE_MAINNET_ADDRESSES[^{]*\{(.*?)\}", ts, re.DOTALL)
    assert block, "could not find BASE_MAINNET_ADDRESSES in networks.ts"
    ts_addrs = _addrs_in(block.group(1))
    assert ts_addrs, "no addresses parsed from the ARGUS constant"
    reg_addrs = {v.lower() for v in _registry()["contracts"].values()}
    missing = ts_addrs - reg_addrs
    assert not missing, f"ARGUS networks.ts has addresses absent from the registry: {missing}"
