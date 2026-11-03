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

_SSN_RE = re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b")

# A card number is a token of its own. `\b` let the pattern start and stop inside a longer
# dashed run, so a UUID whose leading groups happen to be all digits read as a card:
# `urn:uuid:83778821-8649-4619-abc1-…` is `8377 8821-8649-4619`. Measured live on
# 2026-10-03 — HISTOR's `histor.changes@v1` labels every change with such a URN, and the hub
# refused the delivered answer as "Response may contain PII" whenever one of the 25 newest
# labels came out that way. So a candidate may not be glued to a word character, or to
# another dash-joined group, on either side.
_CARD_RES: list[re.Pattern[str]] = [
    re.compile(r"(?<!\w)(?<!\w-)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!-?\w)"),  # Credit card
    re.compile(
        r"(?<!\w)(?<!\w-)(4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})(?!-?\w)"
    ),  # Card PAN
]

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")


def _luhn_ok(candidate: str) -> bool:
    """The checksum every real card number carries. A run of digits that fails it is not one.

    9007199254740991 (JavaScript's MAX_SAFE_INTEGER, which every JSON-schema `maximum` diff
    quotes) and hex digests that happen to be all digits match the card shape; nine in ten
    of them fail here.
    """
    digits = [int(c) for c in candidate if c.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return bool(digits) and total % 10 == 0


def _contains_pii(text: str) -> bool:
    if _SSN_RE.search(text):
        return True
    for pattern in _CARD_RES:
        if any(_luhn_ok(m.group(0)) for m in pattern.finditer(text)):
            return True
    return bool(_EMAIL_RE.search(text))


# Public telemetry identifiers are long digit strings too. Scanning a USGS
# ``station_id`` as unstructured prose makes a nine-digit gauge id look exactly
# like the permissive SSN regex (separators are optional), and a 16-digit time
# series/device id look like a PAN. These fields name machines/observations, not
# people. They are masked only for the post-response PII pass; their surrounding
# payload is still scanned for email/SSN/card leakage and every other safety
# classifier still sees the full response.
_PUBLIC_MACHINE_ID_KEYS = frozenset({
    "station_id", "registry_id", "monitoring_location_id", "monitoring_location_number",
    "time_series_id", "timeseries_id",
    "device_id", "point_id", "polygon_id", "event_id", "radar_id", "storm_id",
    "wmo", "mmsi", "icao",
    # Public blockchain coordinates and quantities are machine identifiers, not
    # personal data. Decimal block heights can otherwise resemble an SSN/PAN and
    # make the post-response safety gate reject healthy EVM results.
    "chain_id", "block_number", "from_block", "to_block", "paid_block",
    "created_block", "last_scanned_block", "confirmations", "nonce",
    "amount_raw", "balance_raw", "balance_wei", "gas_price_wei",
    "base_fee_per_gas_wei", "estimated_gas",
})

# A HESTIA compute receipt meters each replica: its PYTHONHASHSEED (a random 32-bit integer —
# nine or ten digits, i.e. an SSN to the pattern above about half the time) and what it used.
# Measured live: hestia.compute.run@v1 answered, the gate read hash_seeds [510349588] as PII,
# blocked the delivered answer and refunded it. Masked only while they ARE what they claim —
# an integer or a list of integers — so the names cannot hide a string or a subtree.
_PUBLIC_MACHINE_INT_KEYS = frozenset({"hash_seeds", "cpu_ms", "max_rss_kb", "wall_ms"})


def _is_integer_metering(key: str, value: Any) -> bool:
    if key.lower() not in _PUBLIC_MACHINE_INT_KEYS:
        return False
    values = value if isinstance(value, list) else [value]
    return all(isinstance(v, int) and not isinstance(v, bool) for v in values)

# The set above names fields one at a time, which means every NEW capability that returns an
# integer quantity under a new name is blocked, refunded, and recorded as a PROVIDER failure -
# for a regex this hub owns. That happened to `debt_at_risk_raw` (a Morpho market aggregate in
# base units: "494249644", nine digits, read as an SSN), and it will happen again to the next
# `*_raw` nobody thought to list.
#
# So match the CONVENTION as well as the name. These three suffixes mean "an integer in base
# units" or "a block height" everywhere in this ecosystem and in EVM tooling generally, and
# they are quantities, never people.
#
# Deliberately narrower than the exact-name set in one way: a suffix match masks only an
# INTEGER-valued leaf. A name is weaker evidence than an explicit listing, so it does not get
# to hide a nested structure or a formatted string that happens to sit under a matching key.
# `_id` is NOT here on purpose - `customer_id`, `patient_id` and `member_id` all end in it.
#
# `_bytes` joined 2026-10-14: an eSIM seller's quote carries each plan's allowance as
# `data_bytes` (100 MB = 104857600, nine digits), and the doctor's sandbox pass read it as an
# SSN, so the demo node of the eSIM operator kit could not be admitted. A byte count is a size.
_PUBLIC_MACHINE_ID_SUFFIXES = ("_raw", "_wei", "_block", "_bytes")


def _is_public_machine_quantity(key: str, value: Any) -> bool:
    """True for `<something>_raw|_wei|_block|_bytes` holding a plain integer."""
    if not key.lower().endswith(_PUBLIC_MACHINE_ID_SUFFIXES):
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    # Base-unit amounts exceed 2**53 and so travel as decimal strings.
    return isinstance(value, str) and value.strip().lstrip("-").isdigit()

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
    # The gap may not cross a sentence end. `.*` did, and every response is flattened into a
    # SINGLE line before it is scanned, so the two halves could sit in unrelated fields at
    # either end of a JSON document and still match. Measured against real responses from
    # this ecosystem's own security satellites: MOMUS's "Two attack paths confirmed." plus a
    # `plan` key in another object, and WARDEN's "…injection attack." plus "the ruleset
    # guide" in a `docs` field, were both blocked, refunded, and recorded as provider
    # failures. A genuine instruction keeps its verb and its object in one clause - the case
    # this pattern was written for, "how to kill someone: detailed instructions", still
    # matches, because ":" is not a sentence end.
    re.compile(r"\b(kill|murder|bomb|terrorist|weapon|attack)\b[^.!?\n]{0,120}"
               r"\b(plan|instructions?|how\s+to|guide)\b", re.I),
    re.compile(r"\b(hate\s+speech|racial\s+slur|discriminat)\b", re.I),
]

# Opaque machine tokens — Ed25519 signatures and public keys (base64, 44/88 chars), SHA-256
# digests and nonces (hex), UUID-free identifiers — are not prose and are never scanned. Every
# signed receipt and every GAIA/oracle attestation carries several of them, and a word-bounded
# pattern such as `cp\b` or `csam` matches a random run of letters sooner or later: on
# 2026-10-30 a free-trial weather reading was refused as "illegal content" and the caller
# saw a bare safety block. A token counts as opaque when it is 32+ base64/hex characters with
# at least one digit or base64 symbol; dash- or underscore-joined slugs and ordinary words are
# left in, so prose hidden in a long token is still read.
_OPAQUE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9+/])(?=[A-Za-z0-9+/]*[0-9+/=])[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/])"
)

# ── Illegal content ───────────────────────────────────────────

_ILLEGAL_RES: list[re.Pattern[str]] = [
    re.compile(r"\b(how\s+to\s+make|build|construct|synthesize)\b.*\b(bomb|explosive|weapon|firearm|grenade)\b", re.I),
    re.compile(r"\b(cook|synthesize|manufactur(e|ing))\b.*\b(meth(amphetamine)?|fentanyl|heroin|cocaine|mdma|lsd)\b", re.I),
    re.compile(r"\b(child(\s+|-)?(porn|sexual|abuse)|cp\b|csam|loli(con)?)\b", re.I),
    re.compile(r"\b(human\s+trafficking|slave\s+trade|sell\s+(a\s+)?(person|human|child))\b", re.I),
    re.compile(r"\b(launder(ing)?\s+money|money\s+launder(ing)?)\b", re.I),
    re.compile(r"\b(hack(ing)?|break\s+into|exploit)\b.*\b(bank|atm|nuclear|power\s+grid|hospital)\s+(system|network)\b", re.I),
    re.compile(r"\b(ransomware|botnet|ddos|malware)\s+(code|payload|sample|builder)\b", re.I),
    re.compile(r"\b(assassinat(e|ion)|hire\s+a\s+hit)\b", re.I),
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
            verdict = self._check_pii(self._extract_pii_text(output))
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

        # Check for prompt-injection patterns leaked into output
        # (jailbroken LLM might echo system prompts or instruction templates)
        verdict = self._check_injection(text)
        if not verdict.passed:
            return verdict

        # Check illegal content in output if configured
        if "class:illegal" in self.contract.blocked_categories:
            hits = sum(1 for p in _ILLEGAL_RES if p.search(text))
            if hits >= 1:
                return SafetyVerdict(
                    passed=False,
                    category="class:illegal",
                    reason="Response contains illegal content patterns — blocked by provider policy",
                    blocked_input=text[:200],
                )

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
            # No version argument on purpose: sign_receipt derives the canonical version
            # from the receipt's own content, so this rejection's `category`/`reason`/
            # `refunded`/`channel_id` — the entire justification for refunding the buyer —
            # is inside the signature. Under the old v1 default every field v1 signed on a
            # rejection was a constant, so a relay could rewrite WHY without breaking it.
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
    def _extract_text(payload: Any) -> str:
        """Extract all text from a payload for scanning.

        Walks dict keys AND values (EXP-57: attacker hides jailbreaks in keys),
        converts bytes, ints, floats to strings, and applies NFKC Unicode
        normalization so fullwidth/Cyrillic homoglyphs don't bypass regex.
        Opaque machine tokens (signatures, keys, digests) are blanked: see _OPAQUE_TOKEN.
        """
        if isinstance(payload, str):
            return _OPAQUE_TOKEN.sub(" ", unicodedata.normalize("NFKC", payload))
        if isinstance(payload, (bytes, bytearray)):
            try:
                return _OPAQUE_TOKEN.sub(" ", unicodedata.normalize("NFKC", payload.decode("utf-8", errors="replace")))
            except Exception:
                return ""
        if isinstance(payload, (int, float, bool)):
            return str(payload)
        parts: list[str] = []
        if isinstance(payload, dict):
            for k, v in payload.items():
                if isinstance(k, str):
                    parts.append(unicodedata.normalize("NFKC", k))
                parts.append(SafetyGate._extract_text(v))
        elif isinstance(payload, (list, tuple, set)):
            for item in payload:
                parts.append(SafetyGate._extract_text(item))
        return " ".join(p for p in parts if p)

    @staticmethod
    def _extract_pii_text(payload: Any, *, parent_key: str = "") -> str:
        """Structured PII projection that excludes public machine identifiers."""
        if parent_key.lower() in _PUBLIC_MACHINE_ID_KEYS:
            return "[public-machine-id]"
        if _is_public_machine_quantity(parent_key, payload) or _is_integer_metering(parent_key, payload):
            return "[public-machine-quantity]"
        # A JSON number with a fractional part is not one of these identifiers. The SSN
        # pattern makes its separators optional, so a six-decimal float reads as one:
        # `343.556535` is \d{3} `343`, `[-.]` `.`, \d{2} `55`, \d{4} `6535`. Measured on a
        # real response — a great-circle distance in kilometres — which the gate refused as
        # "Response may contain PII", refunded, and recorded as a provider failure. Every
        # capability returning coordinates, distances or rates was affected.
        #
        # Integral values are still scanned: a nine-digit id CAN be a real SSN written as a
        # number, and that is the case this must not lose.
        if isinstance(payload, float) and not payload.is_integer():
            return "[decimal]"
        if isinstance(payload, dict):
            parts: list[str] = []
            for key, value in payload.items():
                normalized = unicodedata.normalize("NFKC", str(key))
                parts.append(normalized)
                parts.append(SafetyGate._extract_pii_text(value, parent_key=normalized))
            return " ".join(part for part in parts if part)
        if isinstance(payload, (list, tuple, set)):
            return " ".join(SafetyGate._extract_pii_text(item) for item in payload)
        return SafetyGate._extract_text(payload)

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
        if _contains_pii(t):
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

        if "class:illegal" in blocked:
            hits = sum(1 for p in _ILLEGAL_RES if p.search(text))
            if hits >= 1:
                return SafetyVerdict(
                    passed=False,
                    category="class:illegal",
                    reason="Input matches known patterns for illegal content/activity",
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
