"""ZK ceremony artifact validation for production startup."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _path(env_name: str, default: str) -> Path:
    return Path(os.environ.get(env_name, default)).expanduser()


def production_zk_issues() -> list[str]:
    """Return blocking issues when groth16 backend is required but artifacts are missing."""
    backend = (os.environ.get("AIMARKET_ZK_BACKEND") or "").strip().lower()
    simulated = os.environ.get("AIMARKET_ZK_SIMULATED", "").strip() == "1"

    if backend != "groth16" and not simulated:
        # Production without explicit groth16 and without sim flag is already blocked
        # by prod_startup_guard (AIMARKET_ZK_SIMULATED=1). No extra artifact check.
        return []

    if backend != "groth16":
        return []

    wasm = _path("AIMARKET_ZK_WASM", "/app/data/secrets/zk/input_validity.wasm")
    zkey = _path("AIMARKET_ZK_ZKEY", "/app/data/secrets/zk/input_validity_0001.zkey")
    vkey_default = "/app/contracts/zk/verifier/verification_key.json"
    vkey_env = (
        os.environ.get("AIMARKET_ZK_VKEY_JSON")
        or os.environ.get("AIMARKET_ZK_VKEY")
        or vkey_default
    )
    vkey = Path(vkey_env).expanduser()
    verifier_sol = Path(
        os.environ.get(
            "AIMARKET_ZK_VERIFIER_SOL",
            "/app/contracts/zk/verifier/Verifier.sol",
        )
    )

    issues: list[str] = []
    for label, p in (
        ("AIMARKET_ZK_WASM", wasm),
        ("AIMARKET_ZK_ZKEY", zkey),
        ("AIMARKET_ZK_VKEY_JSON", vkey),
    ):
        if not p.is_file():
            issues.append(
                f"{label} missing at {p} — run contracts/zk/scripts/setup.sh and the "
                "multi-party ceremony (contracts/zk/ZK_CEREMONY.md), then copy artifacts "
                "to data/secrets/zk/."
            )

    if not verifier_sol.is_file():
        issues.append(
            f"On-chain verifier missing at {verifier_sol} — export with "
            "snarkjs zkey export solidityverifier after ceremony."
        )

    snarkjs = shutil.which("snarkjs") or os.environ.get("AIMARKET_ZK_SNARKJS", "")
    if not snarkjs:
        issues.append(
            "snarkjs not found in PATH — install Node.js snarkjs for Groth16 prove/verify "
            "(npm i -g snarkjs) or set AIMARKET_ZK_SNARKJS to the binary path."
        )

    return issues
