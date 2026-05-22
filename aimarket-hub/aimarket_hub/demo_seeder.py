"""Demo capability seeder — populates an empty hub with exhibition data.

Runs automatically on first startup when capabilities_count == 0.
These are STUB capabilities for demonstration — they show the marketplace
UX and HTTP pipeline but do not execute real AI work behind the scenes.

When factory_bridge imports real products from AI-Factory, demo caps are
replaced with actual deployed capabilities.
"""

from __future__ import annotations

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability

DEMO_CAPABILITIES = [
    # Translations
    Capability(
        capability_id="translate.multi@v2", product_id="prod-translate",
        name="translate.multi", version="v2",
        description="[DEMO] Translate text to 5+ languages in one call. Supports RU, EN, DE, FR, JA, ZH, AR, ES.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}, "locales": {"type": "array", "items": {"type": "string"}}}, "required": ["text"]},
        output_schema={"type": "object", "properties": {"translations": {"type": "object", "additionalProperties": {"type": "string"}}}},
        price_per_call_usd=0.40, p50_latency_ms=8100, success_rate_30d=0.97,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    Capability(
        capability_id="translate.doc@v1", product_id="prod-translate",
        name="translate.doc", version="v1",
        description="[DEMO] Translate full documents preserving formatting. DOCX, PDF, Markdown supported.",
        input_schema={"type": "object", "properties": {"document_base64": {"type": "string"}, "target_locale": {"type": "string"}}, "required": ["document_base64", "target_locale"]},
        output_schema={"type": "object", "properties": {"translated_base64": {"type": "string"}}},
        price_per_call_usd=1.20, p50_latency_ms=15200, success_rate_30d=0.95,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Legal
    Capability(
        capability_id="legal.review@v1", product_id="prod-legal",
        name="legal.review", version="v1",
        description="[DEMO] Review contracts and legal documents for risks, missing clauses, and compliance issues.",
        input_schema={"type": "object", "properties": {"documents": {"type": "object", "additionalProperties": {"type": "string"}}, "jurisdiction": {"type": "string"}}, "required": ["documents"]},
        output_schema={"type": "object", "properties": {"issues": {"type": "array", "items": {"type": "string"}}, "risk_level": {"type": "string"}}},
        price_per_call_usd=1.20, p50_latency_ms=11400, success_rate_30d=0.99,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    Capability(
        capability_id="legal.nda-check@v1", product_id="prod-legal",
        name="legal.nda-check", version="v1",
        description="[DEMO] Specialized NDA review — flags unusual terms, perpetual clauses, and jurisdiction risks.",
        input_schema={"type": "object", "properties": {"nda_text": {"type": "string"}, "party_type": {"type": "string"}}, "required": ["nda_text"]},
        output_schema={"type": "object", "properties": {"flags": {"type": "array", "items": {"type": "object"}}, "score": {"type": "number"}}},
        price_per_call_usd=0.80, p50_latency_ms=9200, success_rate_30d=0.98,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Summarization
    Capability(
        capability_id="summarize@v1", product_id="prod-summarize",
        name="summarize", version="v1",
        description="[DEMO] Summarize long documents, articles, or transcripts into concise executive summaries.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}, "max_words": {"type": "integer"}}, "required": ["text"]},
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}, "key_points": {"type": "array", "items": {"type": "string"}}}},
        price_per_call_usd=0.25, p50_latency_ms=2800, success_rate_30d=0.96,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Code
    Capability(
        capability_id="code.review@v1", product_id="prod-code",
        name="code.review", version="v1",
        description="[DEMO] Review code for bugs, security vulnerabilities, and style issues. Supports 15+ languages.",
        input_schema={"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}}, "required": ["code"]},
        output_schema={"type": "object", "properties": {"issues": {"type": "array", "items": {"type": "object"}}, "score": {"type": "number"}}},
        price_per_call_usd=0.60, p50_latency_ms=12000, success_rate_30d=0.94,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    Capability(
        capability_id="code.generate@v1", product_id="prod-code",
        name="code.generate", version="v1",
        description="[DEMO] Generate boilerplate code, API endpoints, and test stubs from natural language specs.",
        input_schema={"type": "object", "properties": {"spec": {"type": "string"}, "language": {"type": "string"}, "framework": {"type": "string"}}, "required": ["spec"]},
        output_schema={"type": "object", "properties": {"code": {"type": "string"}, "tests": {"type": "string"}}},
        price_per_call_usd=0.80, p50_latency_ms=18000, success_rate_30d=0.92,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Analytics
    Capability(
        capability_id="score.risk@v1", product_id="prod-analytics",
        name="score.risk", version="v1",
        description="[DEMO] Score risk signals for fraud detection, credit assessment, and compliance monitoring.",
        input_schema={"type": "object", "properties": {"signals": {"type": "object"}, "model": {"type": "string"}}, "required": ["signals"]},
        output_schema={"type": "object", "properties": {"risk_score": {"type": "number"}, "factors": {"type": "array", "items": {"type": "object"}}}},
        price_per_call_usd=0.55, p50_latency_ms=620, success_rate_30d=0.99,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Chat
    Capability(
        capability_id="chat.support@v1", product_id="prod-chat",
        name="chat.support", version="v1",
        description="[DEMO] AI customer support agent — handles FAQ, triage, and escalation with context awareness.",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}, "history": {"type": "array"}, "context": {"type": "object"}}, "required": ["message"]},
        output_schema={"type": "object", "properties": {"response": {"type": "string"}, "action": {"type": "string"}, "confidence": {"type": "number"}}},
        price_per_call_usd=0.15, p50_latency_ms=1200, success_rate_30d=0.95,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Audit
    Capability(
        capability_id="audit.perf@v1", product_id="prod-audit",
        name="audit.perf", version="v1",
        description="[DEMO] Performance audit for web landing pages — Core Web Vitals, SEO, accessibility, best practices.",
        input_schema={"type": "object", "properties": {"url": {"type": "string", "format": "uri"}, "device": {"type": "string"}}, "required": ["url"]},
        output_schema={"type": "object", "properties": {"scores": {"type": "object"}, "recommendations": {"type": "array", "items": {"type": "string"}}}},
        price_per_call_usd=1.50, p50_latency_ms=25000, success_rate_30d=0.93,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Image
    Capability(
        capability_id="image.describe@v1", product_id="prod-image",
        name="image.describe", version="v1",
        description="[DEMO] Generate detailed alt-text and descriptions for images. Accessibility-focused.",
        input_schema={"type": "object", "properties": {"image_url": {"type": "string", "format": "uri"}}, "required": ["image_url"]},
        output_schema={"type": "object", "properties": {"description": {"type": "string"}, "alt_text": {"type": "string"}, "objects_detected": {"type": "array", "items": {"type": "string"}}}},
        price_per_call_usd=0.30, p50_latency_ms=4500, success_rate_30d=0.98,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
    # Data extraction
    Capability(
        capability_id="extract.entities@v1", product_id="prod-extract",
        name="extract.entities", version="v1",
        description="[DEMO] Extract named entities, dates, amounts, and structured data from unstructured text.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}, "entity_types": {"type": "array", "items": {"type": "string"}}}, "required": ["text"]},
        output_schema={"type": "object", "properties": {"entities": {"type": "array", "items": {"type": "object"}}, "count": {"type": "integer"}}},
        price_per_call_usd=0.20, p50_latency_ms=1500, success_rate_30d=0.97,
        source_hub="local", source_hub_name="modelmarket.dev",
    ),
]


def seed_demo_capabilities(db: HubDatabase) -> int:
    """Seed demo capabilities if the hub has no local capabilities.

    Returns the number of capabilities seeded.
    """
    existing = db.count_capabilities("local")
    if existing > 0:
        return 0

    count = 0
    for cap in DEMO_CAPABILITIES:
        db.upsert_capability(cap)
        count += 1

    return count
