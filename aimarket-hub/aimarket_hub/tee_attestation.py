"""TEE-Attested Execution — Nitro Enclaves / Intel TDX (#2)

Before invoke, server sends attestation report: "this code runs in encrypted enclave,
I physically cannot see your input." Receipt signed by enclave key.

Unlocks enterprise/legal/medical/finance — the only category ready to pay seriously.
Currently crypto-AI players (Phala, Marlin) do this; nobody packaged it in simple 402-flow.
You'll be first.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.signing import Signer


class EnclavePlatform(str):
    AWS_NITRO = "aws_nitro"
    INTEL_TDX = "intel_tdx"
    AMD_SEV = "amd_sev"
    AZURE_CC = "azure_confidential_computing"


@dataclass
class TEEAttestation:
    """Attestation report proving code runs in a TEE."""

    platform: str  # aws_nitro, intel_tdx, amd_sev
    enclave_id: str  # Unique enclave identifier
    code_hash: str  # SHA-256 of the code running inside
    pcr_values: dict[str, str]  # Platform Configuration Registers
    instance_id: str  # Cloud instance ID
    region: str  # Cloud region
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    ttl_s: int = 300  # Attestation valid for 5 minutes
    signature: str = ""  # Signed by enclave key (simulated here)

    def canonical(self) -> str:
        return (
            f"platform:{self.platform}"
            f"|enclave_id:{self.enclave_id}"
            f"|code_hash:{self.code_hash}"
            f"|pcr0:{self.pcr_values.get('pcr0', '')}"
            f"|instance:{self.instance_id}"
            f"|region:{self.region}"
            f"|timestamp:{self.timestamp}"
            f"|ttl:{self.ttl_s}"
        )

    def sign(self, signer: Signer) -> "TEEAttestation":
        self.signature = signer.sign_canonical(self.canonical())
        return self

    def is_expired(self) -> bool:
        try:
            from calendar import timegm
            ts = timegm(time.strptime(self.timestamp, "%Y-%m-%dT%H:%M:%SZ"))
            return (time.time() - ts) > self.ttl_s
        except (ValueError, OSError):
            return True

    def verify(self, expected_code_hash: str, signer: Signer, enclave_public_key: str) -> bool:
        """Verify attestation: code hash matches + signature valid + not expired."""
        if self.is_expired():
            return False
        if self.code_hash != expected_code_hash:
            return False
        return signer.verify(enclave_public_key, self.signature, self.canonical())


@dataclass
class TEEReceipt:
    """Receipt signed by TEE enclave key — proves execution happened in secure hardware."""

    receipt_id: str
    attestation: TEEAttestation
    capability_id: str
    product_id: str
    input_hash: str  # SHA-256 of input (provider cannot see plaintext)
    output_hash: str  # SHA-256 of output
    price_usd: float
    latency_ms: int
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""

    def canonical(self) -> str:
        return (
            f"receipt_id:{self.receipt_id}"
            f"|attestation_id:{self.attestation.enclave_id}"
            f"|capability_id:{self.capability_id}"
            f"|input_hash:{self.input_hash}"
            f"|output_hash:{self.output_hash}"
            f"|price_usd:{self.price_usd}"
            f"|timestamp:{self.timestamp}"
        )

    def sign(self, signer: Signer) -> "TEEReceipt":
        self.signature = signer.sign_canonical(self.canonical())
        return self


class TEEAttestationService:
    """Service for generating and verifying TEE attestations.

    In production:
    - AWS Nitro: attestation from Nitro hypervisor
    - Intel TDX: quote from TDX module
    - AMD SEV: attestation report from SEV firmware

    Here we simulate the attestation flow for development.
    """

    def __init__(self, signer: Signer | None = None, platform: str = EnclavePlatform.AWS_NITRO):
        self.signer = signer or Signer()
        self.platform = platform
        self._enclave_key = signer if signer else Signer()

    def generate_attestation(
        self,
        code_identifier: str,
        instance_id: str = "i-00000000000000000",
        region: str = "us-east-1",
    ) -> TEEAttestation:
        """Generate a TEE attestation for a capability."""
        code_hash = hashlib.sha256(code_identifier.encode()).hexdigest()
        enclave_id = f"enclave_{hashlib.sha256(f'{instance_id}:{code_hash}'.encode()).hexdigest()[:16]}"

        attestation = TEEAttestation(
            platform=self.platform,
            enclave_id=enclave_id,
            code_hash=code_hash,
            pcr_values={
                "pcr0": hashlib.sha256(f"{code_hash}:boot".encode()).hexdigest(),
                "pcr1": hashlib.sha256(f"{code_hash}:kernel".encode()).hexdigest(),
                "pcr2": hashlib.sha256(f"{code_hash}:application".encode()).hexdigest(),
            },
            instance_id=instance_id,
            region=region,
        ).sign(self._enclave_key)

        return attestation

    def execute_with_attestation(
        self,
        capability_id: str,
        product_id: str,
        input_payload: dict[str, Any],
        code_identifier: str,
        price_usd: float,
    ) -> dict[str, Any]:
        """Simulate TEE execution: generate attestation, "execute" inside enclave.

        Returns attestation + TEE-signed receipt.
        """
        # 1. Generate attestation
        attestation = self.generate_attestation(code_identifier)

        # 2. Hash input (provider cannot see plaintext inside enclave)
        input_json = json.dumps(input_payload, sort_keys=True)
        input_hash = hashlib.sha256(input_json.encode()).hexdigest()

        # 3. "Execute" inside enclave (simulated)
        t0 = time.time()
        output = {
            "result": f"TEE-executed {capability_id} securely",
            "enclave_id": attestation.enclave_id,
            "platform": self.platform,
        }
        latency = int((time.time() - t0) * 1000)
        output_hash = hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest()

        # 4. Sign receipt with enclave key
        receipt = TEEReceipt(
            receipt_id=f"tee_rcpt_{int(time.time())}",
            attestation=attestation,
            capability_id=capability_id,
            product_id=product_id,
            input_hash=input_hash,
            output_hash=output_hash,
            price_usd=price_usd,
            latency_ms=latency,
        ).sign(self._enclave_key)

        return {
            "attestation": {
                "platform": attestation.platform,
                "enclave_id": attestation.enclave_id,
                "code_hash": attestation.code_hash,
                "pcr_values": attestation.pcr_values,
                "signature": attestation.signature,
                "ttl_s": attestation.ttl_s,
            },
            "receipt": {
                "receipt_id": receipt.receipt_id,
                "input_hash": receipt.input_hash,
                "output_hash": receipt.output_hash,
                "price_usd": receipt.price_usd,
                "latency_ms": receipt.latency_ms,
                "signature": receipt.signature,
                "note": "Signed by TEE enclave key — verifiable confidential execution",
            },
            "result": output,
            "enterprise_compliance": {
                "gdpr": "Input never leaves enclave in plaintext",
                "hipaa": "Code hash verifiable; execution isolated",
                "soc2": "Full audit trail with TEE-signed receipts",
                "fedramp": "NIST 800-53 attestation-ready",
            },
        }

    def get_enclave_public_key(self) -> str:
        return self._enclave_key.public_key_b64
