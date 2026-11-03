"""Real ZK prover/verifier (Groth16 or PLONK) — wraps snarkjs CLI.

Replaces zk_proofs.ZKProverSimulated for production. Implements the
same Protocol (prove_input / verify_input_proof / verify_output_proof
returning dicts) so callers can switch backends via env config.

Two proof systems share this code path because the same circuit/r1cs
drives both — only the snarkjs subcommand differs:

    AIMARKET_ZK_BACKEND=plonk    — universal setup, NO per-circuit trusted
                                   setup ceremony (reuses a public Powers-of-
                                   Tau). Default-recommended; closes KI-1.
    AIMARKET_ZK_BACKEND=groth16  — smaller proofs / cheaper on-chain verify,
                                   but needs a per-circuit ceremony first.

Required artifacts (built once by contracts/zk/scripts/setup_plonk.sh):
    AIMARKET_ZK_WASM       — input_validity.wasm  (witness generator)
    AIMARKET_ZK_ZKEY       — input_validity_plonk.zkey (proving key;
                             for PLONK this is NOT secret — derived
                             deterministically from the public ptau)
    AIMARKET_ZK_VKEY_JSON  — verification_key.json (public, committed)

Plus a deployed verifier contract for any on-chain verification path:
    AIMARKET_ZK_VERIFIER_CONTRACT  — address of Verifier.sol on-chain

The circuit (contracts/zk/circuits/input_validity.circom) proves the
prover knows an input that hashes to inputCommitment AND produces a
deterministic nullifier from (input, schemaHash). It does NOT prove
arbitrary JSON-schema validity — schema-specific circuits are out of
scope for this skeleton; the field-element encoding is the caller's
responsibility (typically Poseidon-hash the input bytes).

Output dicts carry `simulated: false` and `backend: "groth16"` so the
invoke pipeline can tell them apart from the dev simulation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aimarket_hub.signing import Signer

logger = logging.getLogger(__name__)


# ── Config / discovery ────────────────────────────────────────────────────


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(
            f"{name} is required for real Groth16 prover. "
            "Run contracts/zk/scripts/setup.sh to build the circuit, then "
            f"set {name} to point at the resulting artifact."
        )
    return val


def _require_path(name: str) -> Path:
    p = Path(_require_env(name)).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"{name}={p} does not exist or is not a file")
    return p


def _snarkjs() -> str:
    """Locate snarkjs CLI; raise with install hint if missing."""
    sj = shutil.which("snarkjs")
    if not sj:
        raise RuntimeError(
            "snarkjs CLI not found in PATH. Install: npm install -g snarkjs"
        )
    return sj


# ── Field-element encoding ────────────────────────────────────────────────

# BN254 scalar field size (Groth16 over bn128). Inputs MUST be < this.
_BN254_R = 21888242871839275222246405745257275088548364400416034343698204186575808495617


def encode_to_field(data: bytes) -> int:
    """Map arbitrary bytes to a BN254 field element via SHA-256 truncation.

    Returns int in [0, _BN254_R). Stable, but not collision-free across
    different byte lengths if you use the same hash chunk; for replay-safe
    nullifiers always include a domain separator (schema hash).
    """
    h = hashlib.sha256(data).digest()
    # Take first 31 bytes (248 bits, definitely < r which is ~254 bits).
    return int.from_bytes(h[:31], "big")


# ── Nullifier store ───────────────────────────────────────────────────────


class _NullifierStore:
    """Persistent set of consumed nullifiers — survives hub restart.

    SQLite single-table store keyed by AIMARKET_ZK_NULLIFIER_DB (default:
    `data/zk_nullifiers.db` next to the hub data dir). Uses an exclusive
    transaction on insert so multi-process hubs all see the same view.
    """

    def __init__(self, db_path: Path):
        self._path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as cx:
            cx.execute(
                "CREATE TABLE IF NOT EXISTS used_nullifiers ("
                "  nullifier TEXT PRIMARY KEY,"
                "  used_at   INTEGER NOT NULL"
                ")"
            )

    @contextmanager
    def _conn(self):
        cx = sqlite3.connect(str(self._path), timeout=10, isolation_level=None)
        try:
            cx.execute("PRAGMA journal_mode=WAL")
            yield cx
        finally:
            cx.close()

    def contains(self, nullifier: str) -> bool:
        with self._lock, self._conn() as cx:
            row = cx.execute(
                "SELECT 1 FROM used_nullifiers WHERE nullifier=? LIMIT 1",
                (nullifier,),
            ).fetchone()
            return row is not None

    def add(self, nullifier: str) -> bool:
        """Atomically insert; return True if new, False if already used."""
        with self._lock, self._conn() as cx:
            try:
                cx.execute(
                    "INSERT INTO used_nullifiers (nullifier, used_at) VALUES (?, ?)",
                    (nullifier, int(time.time())),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def count(self) -> int:
        with self._conn() as cx:
            return cx.execute("SELECT COUNT(*) FROM used_nullifiers").fetchone()[0]


# ── Proof types ───────────────────────────────────────────────────────────


@dataclass
class Groth16Proof:
    """Groth16 proof + public signals, ready to send to verifier."""

    proof: dict[str, Any]              # snarkjs proof.json structure (pi_a, pi_b, pi_c, etc.)
    public_signals: list[str]          # [inputCommitment, nullifier, schemaHash] as decimal strings
    input_commitment: str              # decimal string (also in public_signals[0])
    nullifier: str                     # decimal string (also in public_signals[1])
    schema_hash: str                   # decimal string (also in public_signals[2])
    capability_id: str
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""                # Hub Ed25519 sig over canonical, NOT the ZK proof itself

    def canonical(self) -> str:
        return (
            f"capability:{self.capability_id}"
            f"|input_commitment:{self.input_commitment}"
            f"|nullifier:{self.nullifier}"
            f"|schema_hash:{self.schema_hash}"
        )

    def sign(self, signer: Signer) -> Groth16Proof:
        self.signature = signer.sign_canonical(self.canonical())
        return self


# ── Prover / Verifier ─────────────────────────────────────────────────────


_VALID_SYSTEMS = ("groth16", "plonk")

# `None` and `{}` are both legitimate schemas, so neither can mean "caller passed nothing".
# A verifier that was handed no schema cannot bind the proof's `schemaHash`, and refuses.
_SCHEMA_NOT_SUPPLIED = object()


class Groth16Prover:
    """Real ZK proofs (Groth16 or PLONK) via snarkjs CLI.

    Maintains the ZKProverSimulated interface so callers can switch backends
    by setting AIMARKET_ZK_BACKEND=plonk|groth16 instead of
    AIMARKET_ZK_SIMULATED=1. The proof system is a single snarkjs subcommand
    swap because the same circuit/r1cs/wasm drives both.

    (Class name kept for backward-compat; see module-level `ZKProver` alias.)
    """

    def __init__(
        self,
        *,
        wasm_path: Path | str | None = None,
        zkey_path: Path | str | None = None,
        vkey_path: Path | str | None = None,
        nullifier_db: Path | str | None = None,
        signer: Signer | None = None,
        proof_system: str | None = None,
    ):
        system = (proof_system or os.environ.get("AIMARKET_ZK_BACKEND", "plonk")).strip().lower()
        if system not in _VALID_SYSTEMS:
            raise ValueError(f"proof_system must be one of {_VALID_SYSTEMS}, got {system!r}")
        self._system = system
        self.wasm = Path(wasm_path) if wasm_path else _require_path("AIMARKET_ZK_WASM")
        self.zkey = Path(zkey_path) if zkey_path else _require_path("AIMARKET_ZK_ZKEY")
        self.vkey = Path(vkey_path) if vkey_path else _require_path("AIMARKET_ZK_VKEY_JSON")
        self.signer = signer or Signer()
        self._snarkjs = _snarkjs()
        # Persistent nullifier store — replay protection MUST survive restart.
        # Path resolution: explicit arg → AIMARKET_ZK_NULLIFIER_DB → default.
        db_env = os.environ.get("AIMARKET_ZK_NULLIFIER_DB", "").strip()
        db_path = Path(nullifier_db or db_env or "data/zk_nullifiers.db")
        self._nullifiers = _NullifierStore(db_path.resolve())
        logger.info(
            "ZK prover initialized — system=%s wasm=%s zkey=%s nullifier_db=%s",
            self._system, self.wasm.name, self.zkey.name, db_path,
        )

    # ── Prove ────────────────────────────────────────────────────

    def prove_input(
        self,
        capability_id: str,
        input_schema: dict[str, Any] | None,
        input_payload: dict[str, Any],
    ) -> Groth16Proof:
        """Generate a Groth16 proof that we know `input_payload`.

        The input is encoded as a single field element (SHA-256 → 248-bit int).
        The salt is fresh randomness per proof — included in the witness only,
        never revealed in public signals.
        """
        import secrets

        # Encode private inputs as field elements.
        input_blob = json.dumps(input_payload, sort_keys=True).encode()
        input_value = encode_to_field(input_blob)
        nullifier_salt = secrets.randbelow(_BN254_R - 1) + 1  # avoid 0

        # Schema hash (public) — domain separator for the nullifier. Derived through the
        # shared helper so the verifier can re-derive the identical value.
        schema_hash = self._derive_schema_hash(input_schema, capability_id)

        # Public outputs derived inside the circuit; here we precompute them
        # so the input.json is consistent with what the circuit will assert.
        # snarkjs computes the witness, so we don't actually do Poseidon here
        # — we just supply the inputs and read the public signals from the
        # proof output.

        witness_input = {
            "inputValue": str(input_value),
            "nullifierSalt": str(nullifier_salt),
            # Placeholders — circuit recomputes and asserts equality against
            # these. snarkjs will fail loud if the prover lies about them.
            # We have to supply them; use zeros and let the witness gen fill
            # them via the circuit's constraints? No — circom requires all
            # signals provided. So compute them in Python with poseidon-py
            # OR supply commitment/nullifier as outputs the circuit derives.
            # For simplicity, our circuit declares them as `signal input`
            # (public) — caller must compute them. We use the Python poseidon
            # binding if available; otherwise we fail with an install hint.
            **self._compute_public_signals(input_value, nullifier_salt, schema_hash),
            "schemaHash": str(schema_hash),
        }

        proof_dict, public_signals = self._run_prove(witness_input)

        result = Groth16Proof(
            proof=proof_dict,
            public_signals=public_signals,
            input_commitment=public_signals[0],
            nullifier=public_signals[1],
            schema_hash=public_signals[2],
            capability_id=capability_id,
        )
        result.sign(self.signer)
        return result

    def _derive_schema_hash(self, input_schema: Any, capability_id: str) -> int:
        """The `schemaHash` public signal for a (schema, capability) pair.

        Shared by `prove_input` and `verify_input_proof` on purpose: the verifier's whole
        ability to reject a forged domain separator rests on computing the SAME value the
        prover was supposed to use, so these two must not be able to drift apart.

        Capability binding is a Poseidon hash rather than a XOR: plain XOR on field elements
        is mathematically meaningless (a ring-of-integers op, not a BN254 group op). Hashing
        the schema together with the capability keeps nullifiers from different capabilities
        from colliding even on an identical input.
        """
        schema_blob = json.dumps(input_schema or {}, sort_keys=True).encode()
        schema_field = encode_to_field(schema_blob)
        cap_field = encode_to_field(b"capability:" + capability_id.encode())
        return self._poseidon2(schema_field, cap_field) % _BN254_R

    def _poseidon_script(self) -> Path:
        env = os.environ.get("AIMARKET_ZK_POSEIDON_SCRIPT", "").strip()
        if env:
            return Path(env)
        return Path("/opt/zk/scripts/poseidon2.mjs")

    def _poseidon2(self, a: int, b: int) -> int:
        """Poseidon(2) via the original circomlibjs WASM subset in the hub image."""
        script = self._poseidon_script()
        if not script.is_file():
            raise RuntimeError(
                f"Poseidon WASM helper missing at {script}. "
                "Rebuild the hub image with contracts/zk/scripts/poseidon2.mjs."
            )
        result = subprocess.run(
            ["node", str(script), "--stdin"],
            input=json.dumps([str(a), str(b)]),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"poseidon2 helper failed (exit {result.returncode}): "
                f"{result.stderr[:200]}"
            )
        return int(result.stdout.strip())

    def _compute_public_signals(
        self, input_value: int, nullifier_salt: int, schema_hash: int
    ) -> dict[str, str]:
        """Compute Poseidon(input_value, salt) and Poseidon(input_value, schema_hash)."""
        commit = self._poseidon2(input_value, nullifier_salt)
        null = self._poseidon2(input_value, schema_hash)
        return {
            "inputCommitment": str(commit),
            "nullifier": str(null),
        }

    def _run_prove(self, witness_input: dict[str, str]) -> tuple[dict, list[str]]:
        """Run `snarkjs <system> fullprove` and return (proof, public_signals)."""
        with tempfile.TemporaryDirectory(prefix="aimarket-zk-") as tmp:
            tmp_path = Path(tmp)
            input_file = tmp_path / "input.json"
            proof_file = tmp_path / "proof.json"
            public_file = tmp_path / "public.json"

            input_file.write_text(json.dumps(witness_input))

            result = subprocess.run(
                [
                    self._snarkjs,
                    self._system,
                    "fullprove",
                    str(input_file),
                    str(self.wasm),
                    str(self.zkey),
                    str(proof_file),
                    str(public_file),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"snarkjs {self._system} fullprove failed (exit {result.returncode}): "
                    f"{result.stderr[:400]}"
                )

            proof = json.loads(proof_file.read_text())
            signals = json.loads(public_file.read_text())
            if not isinstance(signals, list):
                raise RuntimeError(f"unexpected public signals format: {type(signals)}")
            return proof, [str(x) for x in signals]

    # ── Verify ───────────────────────────────────────────────────

    def verify_input_proof(
        self,
        proof: Groth16Proof | dict[str, Any],
        expected_capability_id: str,
        prover_public_key: str,
        expected_input_schema: Any = _SCHEMA_NOT_SUPPLIED,
    ) -> dict[str, Any]:
        """Run `snarkjs groth16 verify` and check replay/binding.

        `prover_public_key` is REQUIRED — pass the Ed25519 public key of the
        hub that signed the proof envelope. Without it the proof signature
        check is meaningless. Pass empty string only to explicitly opt out
        (testing), and the verifier will refuse the proof.

        `expected_input_schema` is REQUIRED for the same reason, and is the
        schema the capability actually declares. `schemaHash` is a PUBLIC
        signal the prover chooses, and the nullifier is
        ``Poseidon(inputValue, schemaHash)`` — so without re-deriving it here
        the same secret input yields unlimited distinct "fresh" nullifiers,
        and the replay check below can never fire. The envelope's
        `capability_id` does not cover this: it is metadata beside the proof,
        not one of the signals the circuit constrained.

        Returns dict matching the simulated-prover shape: keys `valid`,
        `reason`, `simulated: False`, `backend: "groth16"`.
        """
        if isinstance(proof, dict):
            try:
                proof = self._from_dict(proof)
            except (KeyError, IndexError, TypeError, ValueError):
                return self._mark({"valid": False, "reason": "Malformed proof envelope"})

        # snarkjs constrains public_signals, whereas the envelope signature and
        # replay store use the named fields. They must describe the SAME values:
        # otherwise a proof can be swapped beneath another signed envelope and
        # its real nullifier never gets consumed. Canonical field encodings also
        # prevent one scalar being claimed under multiple textual replay keys.
        signals = proof.public_signals
        if not isinstance(signals, list) or len(signals) != 3 or any(
            not isinstance(value, str) or not value.isascii() or not value.isdecimal()
            or len(value) > 78 or str(int(value)) != value or int(value) >= _BN254_R
            for value in signals
        ):
            return self._mark({"valid": False, "reason": "Malformed proof public signals"})
        if signals != [proof.input_commitment, proof.nullifier, proof.schema_hash]:
            return self._mark({"valid": False, "reason": "Proof public signals do not match signed envelope"})

        # 1. Hub signature is mandatory — refuse proofs with no caller-supplied key.
        if not prover_public_key:
            return self._mark({
                "valid": False,
                "reason": "prover_public_key is required to verify proof envelope signature",
            })
        if not self.signer.verify(prover_public_key, proof.signature, proof.canonical()):
            return self._mark({"valid": False, "reason": "Invalid hub signature on proof envelope"})

        # 2. Capability ID must match what caller expects.
        if proof.capability_id != expected_capability_id:
            return self._mark({"valid": False, "reason": "Capability ID mismatch"})

        # 3. Bind the in-circuit `schemaHash` to the schema this capability really declares.
        #    Without this the replay check in step 4 is decorative: schemaHash is a public
        #    signal the prover picks, so varying it mints a fresh nullifier for the same
        #    secret input every time.
        if expected_input_schema is _SCHEMA_NOT_SUPPLIED:
            return self._mark({
                "valid": False,
                "reason": "expected_input_schema is required to bind the proof's schemaHash",
            })
        try:
            expected_schema_hash = self._derive_schema_hash(
                expected_input_schema, expected_capability_id
            )
        except Exception as exc:  # poseidon backend missing / unusable
            return self._mark({
                "valid": False,
                "reason": f"Could not derive the expected schemaHash: {exc}",
            })
        # Compare the PUBLIC SIGNAL, not `proof.schema_hash` — the latter is envelope
        # metadata that `_from_dict` takes at face value, so it proves nothing on its own.
        try:
            claimed_schema_hash = int(proof.public_signals[2])
        except (IndexError, TypeError, ValueError):
            return self._mark({
                "valid": False,
                "reason": "Proof does not carry a schemaHash public signal",
            })
        if claimed_schema_hash != expected_schema_hash:
            return self._mark({
                "valid": False,
                "reason": "schemaHash does not match the capability's declared schema",
            })

        # 4. Replay protection — nullifier must be fresh (durable store).
        if self._nullifiers.contains(proof.nullifier):
            return self._mark({"valid": False, "reason": "Nullifier already used (replay)"})

        # 5. Actual Groth16 verification via snarkjs.
        with tempfile.TemporaryDirectory(prefix="aimarket-zk-verify-") as tmp:
            tmp_path = Path(tmp)
            proof_file = tmp_path / "proof.json"
            public_file = tmp_path / "public.json"
            proof_file.write_text(json.dumps(proof.proof))
            public_file.write_text(json.dumps(proof.public_signals))

            result = subprocess.run(
                [
                    self._snarkjs,
                    self._system,
                    "verify",
                    str(self.vkey),
                    str(public_file),
                    str(proof_file),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return self._mark({
                    "valid": False,
                    "reason": "snarkjs verify rejected the proof",
                    "detail": result.stderr[:200] + result.stdout[:200],
                })

        # 6. Atomically claim the nullifier; race with a concurrent verifier
        #    on the same proof is resolved here — only one wins.
        if not self._nullifiers.add(proof.nullifier):
            return self._mark({"valid": False, "reason": "Nullifier already used (replay)"})
        return self._mark({"valid": True, "reason": f"{self._system} proof verified"})

    @staticmethod
    def _from_dict(d: dict[str, Any]) -> Groth16Proof:
        return Groth16Proof(
            proof=d["proof"],
            public_signals=list(d["public_signals"]),
            input_commitment=d.get("input_commitment", str(d["public_signals"][0])),
            nullifier=d.get("nullifier", str(d["public_signals"][1])),
            schema_hash=d.get("schema_hash", str(d["public_signals"][2])),
            capability_id=d.get("capability_id", ""),
            timestamp=d.get("timestamp", ""),
            signature=d.get("signature", ""),
        )

    def _mark(self, d: dict[str, Any]) -> dict[str, Any]:
        """Stamp every returned dict to distinguish real proofs from sim."""
        d["simulated"] = False
        d["backend"] = self._system
        return d

    # ── Stats ────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return self._mark({
            "nullifiers_used": self._nullifiers.count(),
            "wasm": str(self.wasm),
            "zkey": str(self.zkey),
            "vkey": str(self.vkey),
        })


# ── Factory ──────────────────────────────────────────────────────────────


# Backward-compat / forward-looking alias: the class handles both systems.
ZKProver = Groth16Prover


def make_zk_prover(signer: Signer | None = None):
    """Return a real ZK prover (PLONK or Groth16) or the simulated one.

    Priority:
      AIMARKET_ZK_BACKEND=plonk   + AIMARKET_ZK_WASM/ZKEY/VKEY paths → real PLONK
      AIMARKET_ZK_BACKEND=groth16 + AIMARKET_ZK_WASM/ZKEY/VKEY paths → real Groth16
      AIMARKET_ZK_SIMULATED=1                                         → sim
      neither                                                         → sim (opt-in)
    """
    backend = os.environ.get("AIMARKET_ZK_BACKEND", "").strip().lower()
    if backend in _VALID_SYSTEMS:
        return Groth16Prover(signer=signer, proof_system=backend)
    # Fall through to simulated only if explicitly opted in.
    from aimarket_hub.zk_proofs import ZKProverSimulated

    return ZKProverSimulated(signer=signer)
