from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    from dilithium_py.ml_dsa import ML_DSA_65
except Exception:  # pragma: no cover
    ML_DSA_65 = None


def _enabled(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


class ProviderSigner:
    def __init__(self, key_file: str):
        self.path = Path(key_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.ed = serialization.load_pem_private_key(self.path.read_bytes(), password=None)
        else:
            self.ed = Ed25519PrivateKey.generate()
            pem = self.ed.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(pem)
        self.pq = None
        if _enabled("ATTESTED_PQC_REQUIRE") and not _enabled("ATTESTED_PQC_ENABLED"):
            raise RuntimeError("ATTESTED_PQC_REQUIRE=1 requires ATTESTED_PQC_ENABLED=1")
        if _enabled("ATTESTED_PQC_ENABLED"):
            if ML_DSA_65 is None:
                raise RuntimeError("ATTESTED_PQC_ENABLED=1 requires dilithium-py")
            pq_path = Path(f"{self.path}.mldsa")
            if pq_path.exists():
                public_hex, secret_hex = pq_path.read_text().splitlines()[:2]
                self.pq = (bytes.fromhex(public_hex), bytes.fromhex(secret_hex))
            else:
                self.pq = ML_DSA_65.keygen()
                fd = os.open(pq_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(f"{self.pq[0].hex()}\n{self.pq[1].hex()}\n")

    @property
    def public_key(self) -> str:
        raw = self.ed.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode()

    @property
    def pq_public_key(self) -> str | None:
        return base64.b64encode(self.pq[0]).decode() if self.pq else None

    def sign(self, canonical: str) -> dict[str, str]:
        block = {"algorithm": "ed25519", "public_key": self.public_key, "value": base64.b64encode(self.ed.sign(canonical.encode())).decode()}
        if self.pq:
            public, secret = self.pq
            block.update({"pq_algorithm": "ml-dsa-65", "pq_public_key": base64.b64encode(public).decode(), "pq_value": base64.b64encode(ML_DSA_65.sign(secret, canonical.encode())).decode()})
        return block

    def response_headers(self, capability_id: str, product_id: str, payload: dict, result: object) -> dict[str, str]:
        input_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        canonical = json.dumps({
            "capability_id": capability_id, "product_id": product_id,
            "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(), "result": result,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        signature = self.sign(canonical)
        headers = {"X-Provider-Signature": signature["value"]}
        if "pq_value" in signature:
            headers.update({"X-Provider-PQ-Algorithm": signature["pq_algorithm"], "X-Provider-PQ-Public-Key": signature["pq_public_key"], "X-Provider-PQ-Signature": signature["pq_value"]})
        return headers
