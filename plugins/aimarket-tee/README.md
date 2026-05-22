# aimarket-tee

**TEE-attested execution for AI capabilities. AWS Nitro Enclaves / Intel TDX.**
Before invoke, the server sends a cryptographic attestation report: "this code runs in an encrypted hardware enclave. I physically cannot see your input." Receipts are signed by the enclave key. Unlocks enterprise, legal, medical, and finance verticals.

## When to Use
- **Confidential AI processing** — consumer sends sensitive data (PII, legal docs, medical records), provider can't see it
- **Enterprise compliance (GDPR/HIPAA/FedRAMP)** — attestation report proves code integrity and data isolation
- **Third-party model hosting** — model owner deploys to enclave, hub operator can't extract weights
- **Regulated industries** — prove to auditors that execution happened in certified hardware

## Installation
```bash
pip install aimarket-tee
```

## API Endpoints
No additional API endpoints. Activated automatically via invoke flow — attestation is attached to every invocation response.

## End-to-End Example
```python
from aimarket_tee.tee_attestation import TEEAttestationService, EnclavePlatform

service = TEEAttestationService(platform=EnclavePlatform.AWS_NITRO)

# Execute capability inside enclave — provider sees only hashes
result = service.execute_with_attestation(
    capability_id="legal.review@v1",
    product_id="prod-legal",
    input_payload={"documents": {"nda": "CONFIDENTIAL: review this NDA..."}},
    code_identifier="legal-review-v2.0.0-githash-abc123",
    price_usd=5.00
)

print(result["attestation"]["platform"])  # aws_nitro
print(result["attestation"]["code_hash"])  # sha256 of code
print(result["receipt"]["input_hash"])     # sha256 of input (provider never sees plaintext)
print(result["enterprise_compliance"]["gdpr"])  # "Input never leaves enclave in plaintext"
```

## Security
- **Code hash verification** — consumer verifies the exact code running in enclave
- **Input confidentiality** — provider sees only SHA-256(input), never plaintext
- **Output signed by enclave key** — verifiable proof of correct execution
- **Attestation TTL** — 5 minutes by default, prevents replay attacks

## License
MIT · Maintained by AI-Factory
