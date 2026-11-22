"""Make evm_signature_fixtures.json: an EIP-191 personal_sign signature by a throwaway key.

    uv run --project ../hestia python tests/make_evm_signature_fixtures.py

The signature (r, s) comes from the `cryptography` library (secp256k1; its nonces are random, so a
rerun writes another signature that verifies alike). The agent's own keccak names the address and
its recovery picks v from the two candidates; if recovery were wrong, neither would match and this
script stops.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, decode_dss_signature

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from replay import load  # noqa: E402

N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def main() -> None:
    _, _, ns = load("evm-signature", {})
    key = ec.generate_private_key(ec.SECP256K1())
    numbers = key.public_key().public_numbers()
    address = ns["keccak256"](numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big"))[12:]
    message = "HESTIA fixture: sign in to example.com at 2026-11-21T20:00:00Z"
    digest = ns["personal_digest"](message.encode())
    r, s = decode_dss_signature(key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256()))))
    if s > N // 2:
        s = N - s  # low-s, as wallets produce
    for recid in (0, 1):
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27 + recid])
        if ns["recover_address"](digest, raw) == address:
            break
    else:
        raise SystemExit("no recovery id recovers the key")
    out = {
        "signer": ns["checksum"](address),
        "message": message,
        "signature": "0x" + raw.hex(),
        "digest": "0x" + digest.hex(),
    }
    (HERE / "evm_signature_fixtures.json").write_text(json.dumps(out, indent=1) + "\n")
    print(out)


if __name__ == "__main__":
    main()
