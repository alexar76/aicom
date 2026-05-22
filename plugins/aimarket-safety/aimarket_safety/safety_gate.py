"""Built-in safety gate for capability invocations.

Every request/response passes through safety classifiers.
Flagged → atomic abort + refund + signed rejection reason.

This is a liability shield for both sides:
- Provider: "I rejected this because it was flagged as {category}"
- Consumer: "I got a signed receipt proving my invoke was rejected for safety, not for lack of payment"

Categories align with constitutional contracts:
    class:PII, class:medical, class:children, class:illegal, class:injection, class:harassment

Architecture:
    pre_invoke_check(input, capability_constraints) → (ok, reason|None)
    post_response_check(output, capability_constraints) → (ok, reason|None)
    build_rejection_receipt(invoke_context, reason) → signed receipt
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

SafetyCategory = Literal[
    "class:PII",
    "class:medical",
    "class:children",
    "class:illegal",
    "class:injection",
    "class:harassment",
    "class:constitutional",
]

SAFETY_CATEGORIES: list[SafetyCategory] = [
    "class:PII",
    "class:medical",
    "class:children",
    "class:illegal",
    "class:injection",
    "class:harassment",
    "class:constitutional",
]


@dataclass
class SafetyVerdict:
    """Result of a safety check."""

    passed: bool
    category: SafetyCategory | None = None
    reason: str = ""
    blocked_input: str = ""  # truncated snippet of what was blocked
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class ConstitutionalContract:
    """Provider-declared constraints on what they process."""

    blocked_categories: list[SafetyCategory] = field(default_factory=list)
    required_categories: list[SafetyCategory] = field(default_factory=list)
    max_input_length: int = 100_000
    allowed_content_patterns: list[str] = field(default_factory=list)
    blocked_content_patterns: list[str] = field(default_factory=list)


# ── Injection patterns (from existing prompt_safety.py) ───────

_CRITICAL_RES: list[re.Pattern[str]] = [
    re.compile(r"\[\s*INST\s*\]", re.I),
    re.compile(r"\[/\s*INST\s*\]", re.I),
    re.compile(r"<\s*\|\s*im_(start|end)\s*\|>", re.I),
    re.compile(r"<\s*/\s*system\s*>", re.I),
    re.compile(r"<\s*system\s*>", re.I),
    re.compile(r"override\s+(the\s+)?(above|prior|previous)\s+instructions?", re.I),
    re.compile(r"ignore\s+all\s+(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+all\s+(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"forget\s+(everything|all)\s+(you|above|prior|previous)", re.I),
    re.compile(r"\bdeveloper\s+mode\b.*\b(enabled|on)\b", re.I | re.S),
    re.compile(r"\bDAN\s+mode\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"сброс(ь)?\s+контекст", re.I),
    re.compile(r"игнорируй\s+(все\s+)?(предыдущ|вышеуказан)", re.I),
    re.compile(r"забудь\s+(все\s+)?(инструкц|правил)", re.I),
    re.compile(r"новые?\s+системн(ые|ая)\s+инструкц", re.I),
    re.compile(r"ты\s+теперь\s+(не\s+)?бот\s+поддерж", re.I),
    re.compile(r"раскрой\s+системн", re.I),
]

_STRONG_RES: list[re.Pattern[str]] = [
    re.compile(r"\bact\s+as\s+(if\s+you\s+are|a|an)\b", re.I),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.I),
    re.compile(r"\byou\s+are\s+now\s+(a|an|the)\b", re.I),
    re.compile(r"\bsimulate\s+being\b", re.I),
    re.compile(r"role\s*play\s+as\b", re.I),
    re.compile(r"###\s*assistant\s*:", re.I),
    re.compile(r"###\s*system\s*:", re.I),
    re.compile(r"^\s*(system|assistant|developer)\s*:\s*$", re.I | re.M),
    re.compile(r"end\s+of\s+system\s+prompt", re.I),
    re.compile(r"base64\s*[-–—]\s*decode", re.I),
    re.compile(r"прикинься\s+что\s+ты", re.I),
    re.compile(r"выполни\s+команду\s+shell", re.I),
    re.compile(r"выполни\s+python", re.I),
    re.compile(r"ignore\s+the\s+above", re.I),
    re.compile(r"disregard\s+the\s+above", re.I),
]

# ── PII patterns ──────────────────────────────────────────────

_PII_RES: list[re.Pattern[str]] = [
    re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"),  # SSN
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # Credit card
    re.compile(r"\b(4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b"),  # Card PAN
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # Email
]

# ── Medical / PHI patterns ────────────────────────────────────

_MEDICAL_RES: list[re.Pattern[str]] = [
    re.compile(r"\b(patient|diagnosis|prognosis|symptoms?|treatment|prescription|dose|medication)\b", re.I),
    re.compile(r"\b(ICD-?\d{2}|HIPAA|PHI|EMR|EHR)\b", re.I),
    re.compile(r"\b(medical\s+record|health\s+record|clinical\s+data)\b", re.I),
]

# ── Children's data ───────────────────────────────────────────

_CHILDREN_RES: list[re.Pattern[str]] = [
    re.compile(r"\b(child|children|minor|under\s*18|underage|COPPA)\b", re.I),
    re.compile(r"\b(infant|toddler|preschool|kindergarten|adolescent|teenager)\b", re.I),
]

# ── Harassment / toxic content ────────────────────────────────

_HARASSMENT_RES: list[re.Pattern[str]] = [
    re.compile(r"\b(kill|murder|bomb|terrorist|weapon|attack)\b.*\b(plan|instructions?|how\s+to|guide)\b", re.I),
    re.compile(r"\b(hate\s+speech|racial\s+slur|discriminat)\b", re.I),
]


class SafetyGate:
    """Pre-invoke and post-response safety classifier.

    Integrates with the hub to provide liability-shielded rejections:
    - Flagged calls get atomic abort (no execution)
    - Channel refunded automatically
    - Signed rejection receipt issued with specific category + reason
    """

    def __init__(self, constitutional_contract: ConstitutionalContract | None = None):
        self.contract = constitutional_contract or ConstitutionalContract()

    # ── Public API ─────────────────────────────────────────────

    def pre_invoke_check(self, input_payload: dict[str, Any]) -> SafetyVerdict:
        """Check input BEFORE invocation. Returns SafetyVerdict."""
        text = self._extract_text(input_payload)

        # Check length
        if self.contract.max_input_length and len(text) > self.contract.max_input_length:
            return SafetyVerdict(
                passed=False,
                category="class:constitutional",
                reason=f"Input exceeds max length ({len(text)} > {self.contract.max_input_length})",
                blocked_input=text[:200],
            )

        # Check injection
        verdict = self._check_injection(text)
        if not verdict.passed:
            return verdict

        # Check constitutional blocked categories
        verdict = self._check_blocked_categories(text)
        if not verdict.passed:
            return verdict

        # Check blocked content patterns
        verdict = self._check_content_patterns(text, self.contract.blocked_content_patterns)
        if not verdict.passed:
            return verdict

        # Check required allowed patterns
        if self.contract.allowed_content_patterns:
            verdict = self._check_allowed_patterns(text, self.contract.allowed_content_patterns)
            if not verdict.passed:
                return verdict

        return SafetyVerdict(passed=True)

    def post_response_check(self, output: dict[str, Any]) -> SafetyVerdict:
        """Check response AFTER execution but before returning to consumer."""
        text = self._extract_text(output)

        # Check PII leakage in output
        if "class:PII" in self.contract.blocked_categories:
            verdict = self._check_pii(text)
            if not verdict.passed:
                return SafetyVerdict(
                    passed=False,
                    category="class:PII",
                    reason="Response may contain PII — blocked by provider policy",
                    blocked_input=text[:200],
                )

        # Check harassment/toxic output
        verdict = self._check_harassment(text)
        if not verdict.passed:
            return verdict

        return SafetyVerdict(passed=True)

    def build_rejection_receipt(
        self,
        product_id: str,
        capability_id: str,
        channel_id: str | None,
        verdict: SafetyVerdict,
        signer=None,  # Signer instance
    ) -> dict[str, Any]:
        """Build a signed rejection receipt for audit trail."""
        receipt = {
            "type": "safety_rejection",
            "product_id": product_id,
            "capability_id": capability_id,
            "channel_id": channel_id,
            "category": verdict.category,
            "reason": verdict.reason,
            "timestamp": verdict.timestamp,
            "refunded": True,
            "nonce": f"safety_{int(time.time())}_{product_id[:8]}",
        }
        if signer:
            receipt["signature"] = signer.sign_receipt(receipt)
        return receipt

    def refund_channel(
        self, channel_id: str | None, refund_amount_usd: float = 0.0
    ) -> dict[str, Any]:
        """Issue a refund for the aborted invocation."""
        return {
            "channel_id": channel_id,
            "refunded": True,
            "amount_usd": refund_amount_usd,
            "reason": "safety_abort",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # ── Internal checks ────────────────────────────────────────

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        """Extract all text from a payload for scanning."""
        if isinstance(payload, str):
            return payload
        parts: list[str] = []
        for v in payload.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, dict):
                parts.append(SafetyGate._extract_text(v))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.append(SafetyGate._extract_text(item))
        return " ".join(parts)

    @staticmethod
    def _check_injection(text: str) -> SafetyVerdict:
        t = text or ""
        if not t:
            return SafetyVerdict(passed=True)

        critical_hits = sum(1 for p in _CRITICAL_RES if p.search(t))
        if critical_hits >= 1:
            return SafetyVerdict(
                passed=False,
                category="class:injection",
                reason="Input contains instruction-injection patterns",
                blocked_input=t[:200],
            )

        strong_hits = sum(1 for p in _STRONG_RES if p.search(t))
        if strong_hits >= 2:
            return SafetyVerdict(
                passed=False,
                category="class:injection",
                reason="Input contains layered instruction-injection patterns",
                blocked_input=t[:200],
            )

        role_lines = len(re.findall(r"(?im)^\s*(user|assistant|system|developer)\s*:\s*\S", t))
        if role_lines >= 4 and len(t) > 400:
            return SafetyVerdict(
                passed=False,
                category="class:injection",
                reason="Input appears to be a simulated system dialog",
                blocked_input=t[:200],
            )

        return SafetyVerdict(passed=True)

    @staticmethod
    def _check_pii(text: str) -> SafetyVerdict:
        t = text or ""
        pii_count = sum(1 for p in _PII_RES if p.search(t))
        if pii_count >= 1:
            return SafetyVerdict(
                passed=False,
                category="class:PII",
                reason="Input contains personally identifiable information (PII)",
                blocked_input=t[:200],
            )
        return SafetyVerdict(passed=True)

    @staticmethod
    def _check_harassment(text: str) -> SafetyVerdict:
        t = text or ""
        hits = sum(1 for p in _HARASSMENT_RES if p.search(t))
        if hits >= 1:
            return SafetyVerdict(
                passed=False,
                category="class:harassment",
                reason="Response contains potentially harmful content",
                blocked_input=t[:200],
            )
        return SafetyVerdict(passed=True)

    def _check_blocked_categories(self, text: str) -> SafetyVerdict:
        """Check against provider's blocked category declarations."""
        blocked = set(self.contract.blocked_categories)

        if "class:PII" in blocked:
            v = self._check_pii(text)
            if not v.passed:
                return v

        if "class:medical" in blocked:
            hits = sum(1 for p in _MEDICAL_RES if p.search(text))
            if hits >= 2:
                return SafetyVerdict(
                    passed=False,
                    category="class:medical",
                    reason="Input contains medical/health information — blocked by provider policy",
                    blocked_input=text[:200],
                )

        if "class:children" in blocked:
            hits = sum(1 for p in _CHILDREN_RES if p.search(text))
            if hits >= 1:
                return SafetyVerdict(
                    passed=False,
                    category="class:children",
                    reason="Input references children's data — blocked by provider policy",
                    blocked_input=text[:200],
                )

        return SafetyVerdict(passed=True)

    @staticmethod
    def _check_content_patterns(text: str, blocked_patterns: list[str]) -> SafetyVerdict:
        for pattern in blocked_patterns:
            if re.search(pattern, text, re.I):
                return SafetyVerdict(
                    passed=False,
                    category="class:constitutional",
                    reason=f"Input matches blocked pattern: {pattern}",
                    blocked_input=text[:200],
                )
        return SafetyVerdict(passed=True)

    @staticmethod
    def _check_allowed_patterns(text: str, allowed_patterns: list[str]) -> SafetyVerdict:
        if not any(re.search(p, text, re.I) for p in allowed_patterns):
            return SafetyVerdict(
                passed=False,
                category="class:constitutional",
                reason="Input does not match any required content pattern",
                blocked_input=text[:200],
            )
        return SafetyVerdict(passed=True)


# ── Factory helpers ────────────────────────────────────────────


def make_constitutional_contract(
    *,
    block_pii: bool = True,
    block_medical: bool = False,
    block_children: bool = True,
    block_illegal: bool = True,
    max_input_length: int = 100_000,
    allowed_patterns: list[str] | None = None,
    blocked_patterns: list[str] | None = None,
) -> ConstitutionalContract:
    """Create a constitutional contract with common defaults."""
    blocked: list[SafetyCategory] = ["class:injection", "class:harassment"]
    if block_pii:
        blocked.append("class:PII")
    if block_medical:
        blocked.append("class:medical")
    if block_children:
        blocked.append("class:children")
    if block_illegal:
        blocked.append("class:illegal")

    return ConstitutionalContract(
        blocked_categories=blocked,
        max_input_length=max_input_length,
        allowed_content_patterns=allowed_patterns or [],
        blocked_content_patterns=blocked_patterns or [],
    )


def default_safety_gate() -> SafetyGate:
    """Create a safety gate with sensible defaults for production."""
    return SafetyGate(constitutional_contract=make_constitutional_contract())
