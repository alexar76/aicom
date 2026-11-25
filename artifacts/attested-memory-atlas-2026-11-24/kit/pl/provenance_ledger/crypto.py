from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

try:
    from dilithium_py.ml_dsa import ML_DSA_65
except Exception:  # pragma: no cover
    ML_DSA_65 = None


def _enabled(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


class Signer:
    def __init__(self, key_file: str):
        self.path = Path(key_file)
        self.private_key = self._load_or_create()
        if _enabled("ATTESTED_PQC_REQUIRE") and not _enabled("ATTESTED_PQC_ENABLED"):
            raise RuntimeError("ATTESTED_PQC_REQUIRE=1 requires ATTESTED_PQC_ENABLED=1")
        self.pq = self._load_or_create_pq() if _enabled("ATTESTED_PQC_ENABLED") else None

    def _load_or_create(self) -> Ed25519PrivateKey:
        if self.path.exists():
            return serialization.load_pem_private_key(self.path.read_bytes(), password=None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        encoded = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
        return key

    def _load_or_create_pq(self) -> tuple[bytes, bytes]:
        if ML_DSA_65 is None:
            raise RuntimeError("ATTESTED_PQC_ENABLED=1 requires dilithium-py")
        path = Path(f"{self.path}.mldsa")
        if path.exists():
            public_hex, secret_hex = path.read_text().splitlines()[:2]
            return bytes.fromhex(public_hex), bytes.fromhex(secret_hex)
        public, secret = ML_DSA_65.keygen()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(f"{public.hex()}\n{secret.hex()}\n")
        return public, secret

    @property
    def public_key(self) -> str:
        raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @property
    def pq_public_key(self) -> str | None:
        return base64.b64encode(self.pq[0]).decode() if self.pq else None

    def sign(self, value: str) -> str:
        signature = self.private_key.sign(value.encode("ascii"))
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def sign_block(self, value: str) -> dict[str, str | None]:
        block: dict[str, str | None] = {
            "algorithm": "ed25519", "public_key": self.public_key,
            "value": self.sign(value), "pq_algorithm": None,
            "pq_public_key": None, "pq_value": None,
        }
        if self.pq:
            public, secret = self.pq
            block.update({
                "pq_algorithm": "ml-dsa-65",
                "pq_public_key": base64.b64encode(public).decode(),
                "pq_value": base64.b64encode(ML_DSA_65.sign(secret, value.encode())).decode(),
            })
        return block

    def response_headers(self, capability_id: str, product_id: str, payload: dict, result: object) -> dict[str, str]:
        input_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        canonical = json.dumps({
            "capability_id": capability_id, "product_id": product_id,
            "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(), "result": result,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        signature = self.sign_block(canonical)
        headers = {"X-Provider-Signature": str(signature["value"])}
        if signature["pq_value"]:
            headers.update({
                "X-Provider-PQ-Algorithm": str(signature["pq_algorithm"]),
                "X-Provider-PQ-Public-Key": str(signature["pq_public_key"]),
                "X-Provider-PQ-Signature": str(signature["pq_value"]),
            })
        return headers

    @staticmethod
    def verify(public_key: str, value: str, signature: str) -> bool:
        def decode(item: str) -> bytes:
            return base64.urlsafe_b64decode(item + "=" * (-len(item) % 4))

        try:
            Ed25519PublicKey.from_public_bytes(decode(public_key)).verify(
                decode(signature), value.encode("ascii")
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    @staticmethod
    def verify_pq(public_key: str | None, value: str, signature: str | None) -> bool:
        if not public_key or not signature:
            return not _enabled("ATTESTED_PQC_REQUIRE")
        if ML_DSA_65 is None:
            return False
        try:
            return bool(ML_DSA_65.verify(base64.b64decode(public_key), value.encode(), base64.b64decode(signature)))
        except Exception:
            return False
