"""Single-source guard for the on-chain deployment registry.

`config/deployments/<network>-mainnet.json` is the ONE file a human edits. Every other
place that needs an address is GENERATED from it by
`scripts/sync_deployment_addresses.py`:

  - aimarket-hub/aimarket_hub/deployments/   (package data for the hub)
  - alien-monitor/backend/deployments/       (package data for the monitor)
  - argus/src/ecosystem/deployments.base.json (imported by networks.ts)

The previous model was *mirroring*: the same addresses were typed by hand into two
Python modules and one TypeScript object, and a test noticed divergence afterwards. A
redeploy was therefore a six-file edit where five files could be forgotten, and a green
test only meant nobody had drifted yet. These tests now enforce the stronger property:
regenerating changes nothing, and no consumer hard-codes an address at all.

docs/onchain-journal.md stays the human record and is checked against the registry too.
Addresses are public (on-chain); this is consistency, not secrecy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "deployments" / "base-mainnet.json"
JOURNAL = ROOT / "docs" / "onchain-journal.md"
CHAIN_NET = ROOT / "aimarket-hub" / "aimarket_hub" / "chain_net.py"
MONITOR_CHAIN_NET = ROOT / "alien-monitor" / "backend" / "chain_net.py"
ARGUS_NETWORKS = ROOT / "argus" / "src" / "ecosystem" / "networks.ts"
ARGUS_JSON = ROOT / "argus" / "src" / "ecosystem" / "deployments.base.json"
SYNC_SCRIPT = ROOT / "scripts" / "sync_deployment_addresses.py"
GENERATED = (
    ROOT / "aimarket-hub" / "aimarket_hub" / "deployments" / "base-mainnet.json",
    ROOT / "alien-monitor" / "backend" / "deployments" / "base-mainnet.json",
    ARGUS_JSON,
)


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


def test_no_consumer_hardcodes_an_address():
    """The whole point: a redeploy must not require editing any of these files.

    Only the registry and the files generated from it may contain an address.
    """
    reg_addrs = _addrs_in(REGISTRY.read_text(encoding="utf-8"))
    for path in (CHAIN_NET, MONITOR_CHAIN_NET, ARGUS_NETWORKS):
        found = _addrs_in(path.read_text(encoding="utf-8"))
        leaked = found & reg_addrs
        assert not leaked, (
            f"{path.relative_to(ROOT)} hard-codes deployed address(es) {sorted(leaked)} — "
            "read them from the registry instead (see scripts/sync_deployment_addresses.py)"
        )


#: Files that may legitimately contain a live address: the registry itself, the files
#: GENERATED from it, the human record, and the deploy journal/receipts.
_ADDRESS_ALLOWED = (
    "config/deployments/",
    "aimarket-hub/aimarket_hub/deployments/",
    "alien-monitor/backend/deployments/",
    "argus/src/ecosystem/deployments.base.json",
    "docs/onchain-journal.md",
    # Templates, fixtures and course content legitimately carry a literal — their whole
    # purpose is to SHOW an address. They are still worth updating on a redeploy (and were,
    # on 2026-09-04), but a literal there is not the drift this check is about: nothing reads
    # them to decide which contract to talk to. The `SUPERSEDED` check below is the one that
    # covers them, and it is the one that matters for a stale value.
    "deploy/hub-payment.env.example",
    "school/",
    "aimarket-hub/tests/",
    "escrow-signer/tests/",
    "tests/test_escrow_settlement_sweep.py",
    # HORKOS pins the escrow DELIBERATELY and must not read it from the registry: it holds
    # the only key in AIMarketEscrow.authorizedHubs, and `_verify_chain_identity` fails
    # closed when the domain separator (which binds the contract address) disagrees with
    # this constant. Reading the address from a file the hub also writes would remove
    # exactly the independent check that makes the signer a boundary. Moving it is a
    # deliberate, coordinated act — see the comment on that constant.
    "escrow-signer/escrow_signer/config.py",
)

#: Directories with no bearing on what the software talks to.
_ADDRESS_SKIP_DIRS = {
    ".git", "node_modules", "out", "cache", "broadcast", "dist", "coverage",
    "__pycache__", ".venv", "lib", ".pytest_cache", "site-packages",
    # Nested checkouts of this same repo (git worktrees, vendored upstream copies): their
    # generated files are theirs to keep in sync, not this tree's.
    ".claude", ".upstreams",
}


def test_no_source_file_anywhere_hardcodes_a_live_address():
    """The narrow test above scanned exactly the three files a previous audit had fixed.

    That is how `core/aimarket_participant.py` kept the Base escrow address as a hardcoded
    DEFAULT in three places through two audits and one redeploy: it was a consumer nobody
    had put on the list. The invariant is repo-wide — "a redeploy must not require editing
    any of these files" is only true if the check does not need a list of them.
    """
    import json as _json

    registry = _json.loads(REGISTRY.read_text(encoding="utf-8"))
    # Only the contracts WE deploy. USDC is Circle's and never moves for us, and the owner
    # wallet is an identity rather than a deployment — pinning either is not drift.
    reg_addrs = {
        str(addr).lower()
        for name, addr in (registry.get("contracts") or {}).items()
        if name != "USDC" and isinstance(addr, str) and addr.startswith("0x")
    }
    assert reg_addrs, "no deployed addresses parsed out of the registry — the check would pass vacuously"

    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".js", ".json", ".sh", ".yml", ".yaml", ".env", ".example"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in _ADDRESS_SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if rel.startswith(_ADDRESS_ALLOWED):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        leaked = _addrs_in(text) & reg_addrs
        if leaked:
            offenders.append(f"{rel}: {sorted(leaked)}")
    assert not offenders, (
        "these files hard-code a CURRENTLY-DEPLOYED address, so a redeploy silently leaves "
        "them stale — read the registry instead:\n  " + "\n  ".join(sorted(offenders))
    )


def test_generated_files_are_in_sync():
    """`--check` must pass, so a stale generated copy fails CI rather than production."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, (
        "generated address files are stale — run "
        f"`python scripts/sync_deployment_addresses.py`:\n{proc.stdout}{proc.stderr}"
    )


def test_every_generated_file_exists_and_matches_the_registry():
    """Compare the address-bearing OBJECT, not the whole blob: a generated copy also
    carries provenance fields like owner_wallet that are not contracts."""
    contracts = {v.lower() for v in _registry()["contracts"].values()}
    for path in GENERATED:
        assert path.exists(), f"{path.relative_to(ROOT)} missing — run the sync script"
        data = json.loads(path.read_text(encoding="utf-8"))
        block = data.get("contracts") or data.get("addresses")
        assert isinstance(block, dict) and block, (
            f"{path.relative_to(ROOT)} has no contracts/addresses object"
        )
        unknown = {str(v).lower() for v in block.values()} - contracts
        assert not unknown, f"{path.relative_to(ROOT)} has addresses not in the registry: {unknown}"
        assert "_generated" in data, f"{path.relative_to(ROOT)} must be marked generated"


def test_argus_reads_the_generated_json():
    ts = ARGUS_NETWORKS.read_text(encoding="utf-8")
    assert "deployments.base.json" in ts, "networks.ts must import the generated registry"
    assert "baseDeployment.addresses" in ts, "networks.ts must derive addresses from the import"


def test_hub_package_data_ships_the_registry():
    """chain_net has no inline table any more, so the wheel must carry the JSON."""
    pyproject = (ROOT / "aimarket-hub" / "pyproject.toml").read_text(encoding="utf-8")
    assert "deployments/*.json" in pyproject, (
        "aimarket_hub package-data must include deployments/*.json or an off-repo install "
        "resolves an empty address map"
    )


def test_no_source_file_still_points_at_a_SUPERSEDED_address():
    """The other half, and the half that is already broken rather than fragile.

    The check above catches a file pinning a CURRENT address — it will go stale at the next
    redeploy. This one catches a file still holding a REPLACED one, which is stale today.
    The 2026-09-04 escrow redeploy left two such files behind
    (`scripts/reopen_product_escrow_channel.py`, `tests/test_escrow_settlement_sweep.py`)
    and the first check could not see them, because the moment an address is superseded it
    leaves `registry["contracts"]` and stops being something the scan compares against.
    """
    import json as _json

    registry = _json.loads(REGISTRY.read_text(encoding="utf-8"))
    superseded: set[str] = set()
    for key, block in registry.items():
        if not isinstance(block, dict):
            continue
        for name, addr in (block.get("superseded") or {}).items():
            if isinstance(addr, str) and addr.startswith("0x"):
                superseded.add(addr.lower())
    if not superseded:
        pytest.skip("no superseded addresses recorded yet")

    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        # CODE AND CONFIG ONLY. Documentation, case studies and landing pages legitimately
        # quote the address that was live when they were written — that is the historical
        # record, and docs/onchain-journal.md is where the current one is kept. Rewriting
        # history on every redeploy would make the prose wrong instead of stale.
        if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".js", ".json", ".sh", ".yml", ".yaml", ".env", ".example"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in _ADDRESS_SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if rel.startswith(_ADDRESS_ALLOWED) or rel.startswith("config/deployments/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        leaked = _addrs_in(text) & superseded
        if leaked:
            offenders.append(f"{rel}: {sorted(leaked)}")
    assert not offenders, (
        "these files still name a SUPERSEDED contract — they are talking to the wrong "
        "address right now:\n  " + "\n  ".join(sorted(offenders))
    )
