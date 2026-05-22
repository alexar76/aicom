"""aimarket-zk plugin — Zero-knowledge proofs for privacy-preserving AI invocation."""

from aimarket_hub.plugin import HubPlugin
from aimarket_zk.zk_proofs import ZKProver


class ZKPlugin(HubPlugin):
    name = "aimarket-zk"
    version = "2.0.0"
    description = "Zero-knowledge proofs for privacy-preserving AI invocation"
    homepage = "https://github.com/ai-factory/aimarket-zk"
    category = "security"

    def __init__(self):
        super().__init__()
        self._prover = ZKProver()

    def register_routes(self, router):
        
        from pydantic import BaseModel, Field
        from fastapi.responses import JSONResponse

        class ProveInputRequest(BaseModel):
            capability_id: str = Field(..., min_length=2)
            input_schema: dict = Field(default_factory=dict)
            input_payload: dict = Field(default_factory=dict)

        @router.post("/zk/prove-input")
        async def prove_input(body: ProveInputRequest):
            proof = self._prover.prove_input(body.capability_id, body.input_schema, body.input_payload)
            return {"proof_id": proof.proof_id, "input_commitment": proof.input_commitment[:16] + "...",
                    "nullifier": proof.nullifier[:16] + "...", "schema_hash": proof.schema_hash[:16] + "..."}

        @router.get("/zk/stats")
        async def zk_stats():
            return self._prover.stats()

    def get_manifest_extension(self):
        return {"zk": {"scheme": "Groth16 (simulated)", "production": "circom + bn254 via bellman/gnark"}}
