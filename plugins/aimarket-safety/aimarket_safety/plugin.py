"""Safety Gate Plugin — pre/post-invoke safety classifier.

Implements HubPlugin interface. Auto-discovered by hub via entry point.
"""

from __future__ import annotations

from aimarket_hub.plugin import HubPlugin

from aimarket_safety.safety_gate import SafetyGate, default_safety_gate, make_constitutional_contract


class SafetyPlugin(HubPlugin):
    name = "aimarket-safety"
    version = "2.0.0"
    description = "Pre/post-invoke safety classifier with constitutional contracts. Blocks injection, PII, medical data, harassment. Issues signed rejection receipts with automatic refund."
    homepage = "https://github.com/ai-factory/aimarket-safety"
    category = "security"

    def __init__(self):
        self._gate = default_safety_gate()

    def register_routes(self, router):
        """Register constitutional contract endpoints."""
        from fastapi import HTTPException

        @router.get("/safety/constitutional")
        async def list_constitutional_contracts(limit: int = 50):
            return {
                "contracts": [
                    {
                        "blocked_categories": self._gate.contract.blocked_categories,
                        "max_input_length": self._gate.contract.max_input_length,
                        "allowed_patterns": self._gate.contract.allowed_content_patterns,
                        "blocked_patterns": self._gate.contract.blocked_content_patterns,
                        "safety_gate_enabled": True,
                        "compliance": {
                            "gdpr": "class:PII blocked by default",
                            "hipaa": "class:medical blocked per provider config",
                            "coppa": "class:children blocked by default",
                            "soc2": "Full audit trail with signed rejection receipts",
                        },
                    }
                ],
                "count": 1,
            }

    def on_invoke_pre_check(self, input_payload: dict, context: dict) -> dict | None:
        verdict = self._gate.pre_invoke_check(input_payload)
        if not verdict.passed:
            return {
                "blocked": True,
                "category": verdict.category,
                "reason": verdict.reason,
                "refund": True,
            }
        return None

    def on_invoke_post_check(self, output: dict, context: dict) -> dict | None:
        verdict = self._gate.post_response_check(output)
        if not verdict.passed:
            return {
                "blocked": True,
                "category": verdict.category,
                "reason": verdict.reason,
                "refund": True,
            }
        return None

    def get_manifest_extension(self) -> dict:
        return {
            "safety_gate": {
                "enabled": True,
                "pre_invoke": True,
                "post_response": True,
                "on_block": "atomic_abort + refund + signed_rejection_receipt",
                "categories_blocked": self._gate.contract.blocked_categories,
            }
        }
