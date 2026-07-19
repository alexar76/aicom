"""Domain service boundary (business/product logic)."""

from ..commerce import CommerceService
from ..feedback_guardrail import apply_feedback_guardrail
from ..spec_compiler import compile_product_brief

__all__ = [
    "CommerceService",
    "apply_feedback_guardrail",
    "compile_product_brief",
]
