# aimarket-zk

## Value in plain words

Prove an AI ran correctly on secret input without revealing the input — for M&A, legal, and regulated workflows where showing the document is not an option.

**Простыми словами:** Доказываете, что AI корректно обработал секретный ввод, не раскрывая его — для M&A, права и регулируемых процессов, где показать документ нельзя.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Zero-knowledge proofs for private AI capability invocation.**
Consumer proves "I sent valid input matching the schema" without revealing the input. Provider proves "I executed correctly" without revealing model weights or computation trace. Neither party sees the other's private data.

## When to Use
- Consumer sends proprietary business data — wants proof it was processed correctly, but doesn't want provider to see it
- Provider runs proprietary model — wants to prove correct execution without revealing weights
- Regulatory compliance — prove invocation happened correctly without disclosing contents
- Double-spend protection — ZK nullifiers prevent replay attacks on paid invocations

## Installation
```bash
pip install aimarket-zk
```

## Example
```python
from aimarket_hub.signing import Signer
from aimarket_zk.zk_proofs import ZKProver

signer = Signer()
prover = ZKProver(signer)

schema = {"type": "object", "properties": {"text": {"type": "string"}}}
secret_input = {"text": "confidential merger terms between CorpA and CorpB"}

# Consumer: prove input is valid without revealing it
input_proof = prover.prove_input("legal.review@v1", schema, secret_input)
print(f"Input commitment: {input_proof.input_commitment[:16]}...")
# Provider sees only the hash — not "confidential merger terms"

# Provider: verify input proof → execute → prove output
import hashlib, json
schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
verification = prover.verify_input_proof(input_proof, schema_hash, "legal.review@v1",
                                         signer.public_key_b64)
print(f"Input proof valid: {verification['valid']}")  # True
print(f"Privacy: {verification['reason']}")  # "input is valid without being revealed"

# Full private invoke cycle (input + output proofs)
def executor(pid, cid, inp):
    return {"risk_assessment": "low", "issues_found": 0}

result = prover.private_invoke_flow(
    "legal.review@v1", "prod-legal",
    schema, secret_input, executor
)
print(f"Success: {result['success']}")
print(f"Privacy: {result['privacy_guarantees']}")
# {"input_hidden": true, "execution_trace_hidden": true,
#  "double_spend_protected": true, "zk_scheme": "Groth16 (simulated)"}
```

## ZK Scheme
Reference implementation uses **simulated Groth16** for development. Production: circom circuits compiled to bn254 curve via bellman/gnark. The interface is identical — swap the prover backend and proofs become cryptographically sound.

## License
MIT · Maintained by AI-Factory
