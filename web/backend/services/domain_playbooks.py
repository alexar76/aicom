"""
Domain playbooks
================
Per-vertical best practices and discovery prompts. This is the "domain brain"
that makes output resemble a real product team instead of generic templates.
"""

from __future__ import annotations

import re
from typing import Any


_PLAYBOOKS: dict[str, dict[str, Any]] = {
    "fintech": {
        "vertical": "fintech",
        "north_star": "Trust, compliance, and auditability beat flashy novelty.",
        "defaults": {
            "security": ["MFA/2FA optional", "audit log", "least privilege roles", "rate limits"],
            "compliance": ["data retention policy", "PII minimization", "export for audit"],
        },
        "discovery_questions": [
            "Who is the buyer vs day-to-day user (finance ops, controller, founder)?",
            "What systems must it integrate with (bank feeds, Stripe, ERP, accounting)?",
            "What is the risk tolerance: what errors are unacceptable (wrong numbers, access leaks)?",
            "What are the required audit artifacts (who changed what, when, why)?",
        ],
        "ux_patterns": ["clear states for pending/settled", "explainability tooltips", "export-first flows"],
        "anti_patterns": ["vague 'AI insights' with no audit trail", "no export / no data ownership"],
    },
    "education": {
        "vertical": "education",
        "north_star": "Clarity + progression. Teachers need control; learners need momentum.",
        "defaults": {"a11y": ["WCAG labels", "keyboard nav", "captions/alt text discipline"]},
        "discovery_questions": [
            "Who is the primary user: student, teacher, parent, or admin?",
            "How is progress tracked and verified (rubrics, mastery, grades)?",
            "What content model is needed (lessons, quizzes, assignments)?",
            "What offline/low-bandwidth constraints exist?",
        ],
        "ux_patterns": ["progress indicators", "resume where left off", "teacher moderation tools"],
        "anti_patterns": ["quiz-only without pedagogy", "no progress persistence"],
    },
    "ecommerce": {
        "vertical": "ecommerce",
        "north_star": "Conversion + fulfillment correctness.",
        "defaults": {"reliability": ["idempotent checkout", "inventory consistency", "refund flows"]},
        "discovery_questions": [
            "What is the catalog size and SKU complexity (variants, bundles)?",
            "Which payment/shipping providers are required?",
            "What is the core differentiator: price, speed, curation, personalization?",
            "What post-purchase flows matter (tracking, returns, support)?",
        ],
        "ux_patterns": ["fast product discovery", "trust badges", "clear error messages at checkout"],
        "anti_patterns": ["fake checkout", "no order history", "no returns path"],
    },
    "devtools": {
        "vertical": "devtools",
        "north_star": "Fast feedback loops, docs, and reliable automation.",
        "defaults": {"engineering": ["CLI/API parity", "config-as-code", "dry-run mode", "sane logs"]},
        "discovery_questions": [
            "Where does it run (local, CI, server) and how is auth handled?",
            "What is the minimal happy path (time-to-first-value)?",
            "What is the rollback story if automation misbehaves?",
            "What formats/contracts must be supported (OpenAPI, JSON schema, GitHub API)?",
        ],
        "ux_patterns": ["copy-pastable commands", "progress logs", "explicit failure modes"],
        "anti_patterns": ["no README", "no examples", "magic automation with no controls"],
    },
    "general": {
        "vertical": "general",
        "north_star": "Make the user's core job faster with fewer steps.",
        "defaults": {},
        "discovery_questions": [
            "Who is the user and what is the job-to-be-done?",
            "What is the core action and what does success look like?",
            "What is the main failure mode and recovery path?",
        ],
        "ux_patterns": ["onboarding -> core action -> results", "clear CTA", "recoverable errors"],
        "anti_patterns": ["generic SaaS filler copy", "placeholder flows", "no persistence"],
    },
}


def infer_vertical(idea: str, admin_instructions: str = "") -> str:
    text = f"{idea}\n{admin_instructions}".lower()
    if any(k in text for k in ("fintech", "invoice", "reconciliation", "payments", "bank", "stripe", "kyc", "aml")):
        return "fintech"
    if any(k in text for k in ("education", "teacher", "student", "course", "lesson", "quiz", "lms")):
        return "education"
    if any(k in text for k in ("e-commerce", "ecommerce", "checkout", "cart", "sku", "shop", "store")):
        return "ecommerce"
    if any(k in text for k in ("devtools", "developer tools", "ci", "git", "api", "sdk", "lint", "observability")):
        return "devtools"
    return "general"


def load_playbook(vertical: str) -> dict[str, Any]:
    v = (vertical or "general").strip().lower()
    return dict(_PLAYBOOKS.get(v, _PLAYBOOKS["general"]))


def build_discovery_pack(idea: str, admin_instructions: str = "") -> dict[str, Any]:
    """
    Lightweight product discovery "interview" pack:
    - assumptions
    - questions
    - risks
    """
    vertical = infer_vertical(idea, admin_instructions)
    pb = load_playbook(vertical)
    blob = f"{idea}\n{admin_instructions}".strip()
    assumptions = []
    if re.search(r"\b(saas|b2b)\b", blob.lower()):
        assumptions.append("Multi-tenant B2B SaaS by default (roles, org/workspace).")
    assumptions.append("Ship a usable core flow, not a placeholder UI.")
    return {
        "source": "discovery_pack_v1",
        "vertical": vertical,
        "north_star": pb.get("north_star"),
        "assumptions": assumptions,
        "questions": pb.get("discovery_questions", [])[:10],
        "ux_patterns": pb.get("ux_patterns", [])[:10],
        "anti_patterns": pb.get("anti_patterns", [])[:10],
        "defaults": pb.get("defaults", {}),
    }

