#!/usr/bin/env python3
"""Fail if any production Solana graph reintroduces the retired codec."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "bincode-next": ("2.1.0", "dbe9e7e6d14aeb39557f226bff158a30e367fac279d0e69b8b42fb41999f9a86"),
    "unty-next": ("0.1.2", "16062d030850f35054e37746427b9febb74a2f24c9c6dd6fa2d0c13c5f53221e"),
}
for relative in ("contracts/solana", "acex/contracts/solana", "security/solana-wire"):
    lock = tomllib.loads((ROOT / relative / "Cargo.lock").read_text())
    packages = lock["package"]
    assert not any(p["name"] == "bincode" for p in packages), f"{relative}: retired bincode dependency"
    for name, (version, checksum) in EXPECTED.items():
        found = [p for p in packages if p["name"] == name]
        assert len(found) == 1 and (found[0]["version"], found[0].get("checksum")) == (version, checksum), f"{relative}: unreviewed {name}"
    print(f"{relative}: retired bincode absent; maintained codec/checksums pinned")

for name in ("anchor-lang", "solana-instruction", "solana-sysvar", "solana-zk-sdk"):
    for relative in ("contracts/solana", "acex/contracts/solana"):
        if name == "solana-zk-sdk" and relative == "contracts/solana":
            continue
        workspace = ROOT / relative
        manifest = tomllib.loads((workspace / "Cargo.toml").read_text())
        actual = (workspace / manifest["patch"]["crates-io"][name]["path"]).resolve()
        assert actual == ROOT / "security/vendor-rust" / name, f"{relative}: missing reviewed {name} patch"
        entry = next(p for p in tomllib.loads((workspace / "Cargo.lock").read_text())["package"] if p["name"] == name and p["version"] == tomllib.loads((actual / "Cargo.toml").read_text())["package"]["version"])
        assert "source" not in entry, f"{relative}: patch {name} is not selected"
