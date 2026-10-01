"""
Context Provider
================
Gathers relevant context for a discussion session:
- Product specifications (if product_id is provided)
- Previous discussion summaries
- Additional instructions from the human
- Agent role descriptions

Used by the DiscussionEngine to build enriched prompts
for each round of discussion.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .models import Session, SessionType

logger = logging.getLogger(__name__)


# ── Agent Role Descriptions ──────────────────────────────────────────────────

AGENT_ROLES: dict[str, str] = {
    "pm": (
        "You are the Product Manager. Your job is to define clear requirements, "
        "prioritise tasks based on business value, manage scope, and ensure "
        "alignment with product goals. Be structured and decisive."
    ),
    "analyst": (
        "You are the Market Research Analyst. Your job is to provide data-driven "
        "insights, market trends, competitor analysis, and validate assumptions "
        "with research. Be objective and cite evidence."
    ),
    "architect": (
        "You are the System Architect. Your job is to design scalable architecture, "
        "evaluate technology choices, identify technical risks, and ensure the "
        "solution is feasible and maintainable. Be thorough and precise."
    ),
    "dev": (
        "You are the Developer. Your job is to assess implementation complexity, "
        "estimate development effort, propose technical solutions, and identify "
        "potential coding challenges. Be practical and solution-oriented."
    ),
    "qa": (
        "You are the QA Engineer. Your job is to identify quality risks, propose "
        "testing strategies, suggest edge cases to consider, and ensure the "
        "solution meets quality standards. Be meticulous and thorough."
    ),
    "devops": (
        "You are the DevOps Engineer. Your job is to evaluate infrastructure needs, "
        "deployment complexity, CI/CD requirements, monitoring, and operational "
        "concerns. Be pragmatic and ops-aware."
    ),
    "security": (
        "You are the Security Analyst. Your job is to identify security risks, "
        "threat vectors, compliance requirements, and propose security best "
        "practices. Be vigilant and risk-aware."
    ),
    "marketing": (
        "You are the Marketing Specialist. Your job is to evaluate market appeal, "
        "positioning, messaging, audience targeting, and go-to-market strategy. "
        "Be creative and audience-focused."
    ),
    "sales": (
        "You are the Sales Strategist. Your job is to assess revenue potential, "
        "pricing models, sales channels, competitive differentiation, and "
        "business development opportunities. Be commercial and strategic."
    ),
    "evolution_analyst": (
        "You are the Evolution Analyst. Your job is to analyse product growth "
        "trajectories, identify evolution opportunities, suggest data-driven "
        "improvements, and track progress against goals. Be analytical and "
        "forward-looking."
    ),
    "methodologist": (
        "You are the Methodologist. Your job is to verify the product follows "
        "the accepted PROCESS for its domain (CRM, helpdesk, LMS, e-commerce, "
        "finance, healthcare, analytics, devtools, project management, HR/ATS): "
        "required entities, user roles, lifecycle states, and capabilities. "
        "Flag domain-shape gaps regardless of UI polish or bug counts."
    ),
}

SESSION_TYPE_PROMPTS: dict[SessionType, str] = {
    SessionType.brainstorming: (
        "This is a BRAINSTORMING session. Generate creative, diverse ideas. "
        "Build on others' suggestions. Think outside the box. Quantity and "
        "variety are valued at this stage."
    ),
    SessionType.feature_discussion: (
        "This is a FEATURE DISCUSSION session. Evaluate the proposed feature "
        "from your perspective. Consider feasibility, value, risks, and "
        "dependencies. Be constructive and specific."
    ),
    SessionType.strategy_session: (
        "This is a STRATEGY SESSION. Think strategically about long-term "
        "direction, competitive positioning, resource allocation, and "
        "roadmap priorities. Be visionary but grounded."
    ),
    SessionType.product_idea: (
        "This is a PRODUCT IDEA generation session. Propose concrete product "
        "ideas with clear value propositions, target audiences, and "
        "differentiators. Be innovative but realistic."
    ),
}


def get_agent_role(agent_type: str) -> str:
    """Get the role description for a given agent type."""
    return AGENT_ROLES.get(agent_type, f"You are a {agent_type} agent.")


def get_session_type_prompt(session_type: SessionType) -> str:
    """Get the session-type-specific prompt."""
    return SESSION_TYPE_PROMPTS.get(
        session_type, "Participate in this discussion."
    )


# ── Product Context Loader ───────────────────────────────────────────────────


def load_product_context(product_id: Optional[str]) -> str:
    """
    Load product specification and evolution data to provide context.
    Returns a formatted string or empty string if no product_id.
    """
    if not product_id:
        return ""

    parts: list[str] = []

    # Try to load specification
    from core.paths import specification_path

    spec_path = str(specification_path(product_id))
    if os.path.exists(spec_path):
        try:
            with open(spec_path, "r") as f:
                spec = json.load(f)
            title = spec.get("title", spec.get("product_name", "Unknown Product"))
            desc = spec.get("description", spec.get("problem_statement", ""))
            parts.append(f"Product: {title}")
            if desc:
                parts.append(f"Description: {desc}")
            features = spec.get("core_features", [])
            if features:
                parts.append("Core features:")
                for ft in features[:5]:
                    parts.append(f"  - {ft}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load spec for {product_id}: {e}")

    # Try to load evolution report
    from core.paths import product_state_dir

    evo_path = str(product_state_dir(product_id) / "evolution_report.json")
    if os.path.exists(evo_path):
        try:
            with open(evo_path, "r") as f:
                evo = json.load(f)
            analysis = evo.get("analysis", evo.get("summary", ""))
            if analysis:
                parts.append(f"Evolution context: {analysis[:500]}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load evolution for {product_id}: {e}")

    return "\n".join(parts) if parts else ""


# ── Context Builder ──────────────────────────────────────────────────────────


def build_context(
    session: Session,
    round_number: int,
    conversation_history: list[str],
) -> str:
    """
    Build the full context prompt for an agent in a discussion round.

    Args:
        session: The current discussion session.
        round_number: Current round number.
        conversation_history: Formatted history of previous messages.

    Returns:
        A formatted context string to be prepended to the agent prompt.
    """
    lines: list[str] = [
        "=== DISCUSSION CONTEXT ===",
        f"Topic: {session.topic}",
        f"Session type: {session.session_type.value}",
        f"Round: {round_number} / {session.config.max_rounds}",
        "",
    ]

    # Product context
    if session.context and session.context.product_id:
        product_context = load_product_context(session.context.product_id)
        if product_context:
            lines.append("--- Product Context ---")
            lines.append(product_context)
            lines.append("")

    # Additional instructions
    if session.context and session.context.additional_instructions:
        lines.append("--- Additional Instructions ---")
        lines.append(session.context.additional_instructions)
        lines.append("")

    # Session type guidance
    session_prompt = get_session_type_prompt(session.session_type)
    lines.append("--- Session Guidance ---")
    lines.append(session_prompt)
    lines.append("")

    # Conversation history
    if conversation_history:
        lines.append("--- Discussion History ---")
        lines.extend(conversation_history)
        lines.append("")

    # Response format
    lines.append("--- Response Format ---")
    lines.append(
        "Provide your thoughts on the topic from your perspective. "
        "Keep responses concise and actionable. "
        "If you agree or disagree with previous points, explain why."
    )

    return "\n".join(lines)
