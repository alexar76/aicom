"""ZK ceremony artifact validation for production startup."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path


def _path(env_name: str, default: str) -> Path:
    return Path(os.environ.get(env_name, default)).expanduser()


_VALID_BACKENDS = ("groth16", "plonk")

# BN128 (alt_bn128 / BN254) scalar field size r. snarkjs emits this as the `q`
# constant in the Solidity verifier; it is the modulus all public inputs and
# proof elements are reduced mod, so a verifier built for a different curve
# would carry a different value here.
_BN128_SCALAR_FIELD = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)

# Contract name snarkjs uses per proof system. Used to detect a verifier that
# was exported for a different backend than the verification key describes.
_PROTOCOL_CONTRACT = {
    "plonk": "PlonkVerifier",
    "groth16": "Groth16Verifier",
}


def _sol_uint_constant(source: str, name: str) -> int | None:
    """Return an integer ``uint*`` constant declared in a snarkjs Verifier.sol.

    Matches e.g. ``uint16 constant nPublic   = 3;`` and returns ``3``. Returns
    ``None`` when the constant is absent so callers can report a precise issue.
    """
    m = re.search(
        rf"uint\d*\s+constant\s+{re.escape(name)}\s*=\s*(\d+)\s*;",
        source,
    )
    return int(m.group(1)) if m else None


def _verifier_mismatch_issues(vkey: Path, verifier_sol: Path) -> list[str]:
    """Cross-check the deployed Verifier.sol against verification_key.json.

    A stale or swapped verifier (wrong proof system, wrong number of public
    inputs, wrong circuit size, or wrong curve) would silently accept or reject
    the wrong proofs, so we fail closed at startup. Returns one issue string per
    discrepancy; an empty list means the artifacts are consistent.
    """
    issues: list[str] = []

    try:
        vk = json.loads(vkey.read_text())
    except (OSError, ValueError) as exc:
        return [f"AIMARKET_ZK_VKEY_JSON at {vkey} is not readable JSON — {exc}"]

    try:
        source = verifier_sol.read_text()
    except OSError as exc:
        return [f"On-chain verifier at {verifier_sol} is not readable — {exc}"]

    hint = (
        "re-export it from the same verification key with "
        "`snarkjs zkey export solidityverifier`."
    )

    # Proof system: contract name must match the vkey protocol.
    protocol = str(vk.get("protocol", "")).strip().lower()
    expected_contract = _PROTOCOL_CONTRACT.get(protocol)
    if expected_contract is None:
        issues.append(
            f"verification key {vkey} declares unknown protocol {protocol!r} — "
            f"expected one of {sorted(_PROTOCOL_CONTRACT)}."
        )
    elif not re.search(rf"\bcontract\s+{expected_contract}\b", source):
        issues.append(
            f"On-chain verifier {verifier_sol} is not a {expected_contract} but the "
            f"verification key {vkey} declares protocol {protocol!r} — {hint}"
        )

    # Number of public inputs: a mismatch means the verifier hashes a different
    # transcript than the prover and would reject every honest proof (or, worse,
    # read attacker-controlled calldata for the missing signals).
    vk_npublic = vk.get("nPublic")
    sol_npublic = _sol_uint_constant(source, "nPublic")
    if not isinstance(vk_npublic, int):
        issues.append(f"verification key {vkey} is missing an integer nPublic field.")
    elif sol_npublic is None:
        issues.append(
            f"On-chain verifier {verifier_sol} has no nPublic constant to validate — {hint}"
        )
    elif sol_npublic != vk_npublic:
        issues.append(
            f"On-chain verifier nPublic={sol_npublic} but verification key {vkey} "
            f"declares nPublic={vk_npublic} — {hint}"
        )

    # Circuit size: snarkjs emits n = 2**power as the domain size.
    vk_power = vk.get("power")
    sol_n = _sol_uint_constant(source, "n")
    if not isinstance(vk_power, int):
        issues.append(f"verification key {vkey} is missing an integer power field.")
    elif sol_n is None:
        issues.append(
            f"On-chain verifier {verifier_sol} has no domain-size constant n to validate — {hint}"
        )
    elif sol_n != (1 << vk_power):
        issues.append(
            f"On-chain verifier n={sol_n} but verification key {vkey} declares "
            f"power={vk_power} (expected n=2**power={1 << vk_power}) — {hint}"
        )

    # Curve: the scalar field constant q pins the verifier to a curve.
    curve = str(vk.get("curve", "")).strip().lower()
    sol_q = _sol_uint_constant(source, "q")
    if curve in ("bn128", "bn254", "alt_bn128"):
        if sol_q is None:
            issues.append(
                f"On-chain verifier {verifier_sol} has no scalar-field constant q to validate — {hint}"
            )
        elif sol_q != _BN128_SCALAR_FIELD:
            issues.append(
                f"On-chain verifier scalar field q={sol_q} does not match the "
                f"{curve} scalar field — verifier was built for a different curve; {hint}"
            )
    else:
        issues.append(
            f"verification key {vkey} declares unsupported curve {curve!r} — "
            "only bn128 verifiers are validated."
        )

    return issues


def production_zk_issues() -> list[str]:
    """Return blocking issues when a real ZK backend is required but artifacts are missing.

    Supports both proof systems:
      - plonk:   universal setup (contracts/zk/scripts/setup_plonk.sh), no ceremony.
      - groth16: needs a per-circuit trusted-setup ceremony (ZK_CEREMONY.md) first.
    """
    backend = (os.environ.get("AIMARKET_ZK_BACKEND") or "").strip().lower()

    if backend not in _VALID_BACKENDS:
        # Production without an explicit real backend is already blocked
        # by prod_startup_guard (AIMARKET_ZK_SIMULATED=1). No extra artifact check.
        return []

    # PLONK needs no ceremony; Groth16 does. Reflect that in the default zkey
    # name and the remediation hint below.
    plonk = backend == "plonk"
    zkey_default = (
        "/app/data/secrets/zk/input_validity_plonk.zkey" if plonk
        else "/app/data/secrets/zk/input_validity_0001.zkey"
    )
    if plonk:
        remediation = (
            "run contracts/zk/scripts/setup_plonk.sh (universal setup — no ceremony), "
            "then copy artifacts to data/secrets/zk/."
        )
    else:
        remediation = (
            "run contracts/zk/scripts/setup.sh and the multi-party ceremony "
            "(contracts/zk/ZK_CEREMONY.md), then copy artifacts to data/secrets/zk/."
        )

    wasm = _path("AIMARKET_ZK_WASM", "/app/data/secrets/zk/input_validity.wasm")
    zkey = _path("AIMARKET_ZK_ZKEY", zkey_default)
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
            issues.append(f"{label} missing at {p} — {remediation}")

    if not verifier_sol.is_file():
        issues.append(
            f"On-chain verifier missing at {verifier_sol} — export with "
            "snarkjs zkey export solidityverifier."
        )
    elif vkey.is_file():
        # Both artifacts present: make sure the deployed verifier was generated
        # from this very verification key. Catches a stale/swapped Verifier.sol
        # (wrong proof system, public-input count, circuit size, or curve)
        # before it can silently mis-verify proofs in production.
        issues.extend(_verifier_mismatch_issues(vkey, verifier_sol))

    snarkjs = shutil.which("snarkjs") or os.environ.get("AIMARKET_ZK_SNARKJS", "")
    if not snarkjs:
        issues.append(
            f"snarkjs not found in PATH — install Node.js snarkjs for {backend} prove/verify "
            "(npm i -g snarkjs) or set AIMARKET_ZK_SNARKJS to the binary path."
        )

    return issues
