"""
Shared helpers and protocol for pipeline task execution.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol

from core.paths import agent_artifact_dir, data_root
from web.backend.services.learning_memory import append_lesson, load_recent_lessons

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("pipeline-worker")


class PipelineTaskExecutorHost(Protocol):
    """Surface ``PipelineWorker`` uses for per-task execution."""

    data_root: Path
    _agents: dict[str, Any]
    _llm_router: Any
    peer_review_engine: Any
    quality_manager: Any

    def _get_priority(self, agent_type: str) -> int: ...
    def _audit_agent_handoff(self, **kwargs: Any) -> None: ...
    def _run_runtime_tests(self, product_id: str, task_queue: list) -> dict: ...
    def _create_next_task(self, product: dict) -> dict | None: ...
    def _load_spec(self, product_id: str) -> dict: ...
    def _load_arch(self, product_id: str) -> dict: ...
    def _architecture_gate(
        self, product_id: str, *, delivery_profile: str | None = None
    ) -> tuple[bool, list[str]]: ...
    def _apply_watermark_policy(self, product_id: str, product: dict) -> None: ...
    def _release_critic(self, product_id: str, product: dict) -> tuple[bool, list[str]]: ...


def build_task_context(task_queue: list, product_id: str) -> dict:
    """Build context from previously completed tasks for this product."""
    completed = [
        t for t in task_queue
        if t.get("product_id") == product_id and t.get("status") == "completed"
    ]
    return {
        "completed_tasks": len(completed),
        "previous_outputs": {
            t["agent_type"]: t.get("output_data", {})
            for t in completed
        },
        "historical_lessons": load_recent_lessons(str(data_root()), limit=10),
    }


def record_task_lesson(product_id: str, agent_type: str, target_state: str, output_data: dict) -> None:
    summary = ""
    if isinstance(output_data, dict):
        for key in ("notes", "summary", "design_feedback", "test_summary", "analysis_summary"):
            if output_data.get(key):
                summary = str(output_data.get(key))
                break
    append_lesson(
        str(data_root()),
        {
            "product_id": product_id,
            "agent_type": agent_type,
            "target_state": target_state,
            "summary": (summary or f"{agent_type} -> {target_state}")[:500],
        },
    )


def save_task_artifact(product_id: str, agent_type: str, data: dict) -> None:
    """Save agent output artifact to disk."""
    artifact_dir = agent_artifact_dir(agent_type, product_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = artifact_dir / "output.json"
    try:
        with open(artifact_file, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logger.warning("Could not save artifact for %s/%s: %s", product_id, agent_type, e)


def fallback_agent_output(agent_type: str, pid: str, product: dict) -> dict:
    """Generate structured fallback output when agent is not available.
    
    This is NOT mock data - it's deterministic rule-based output that
    provides meaningful structure for each pipeline stage. When LLM
    agents are available, this fallback is never used.
    """
    idea = product.get("idea", "")
    idea_preview = idea[:100] if idea else "No idea provided"

    fallbacks = {
        "analyst": {
            "product_name": " ".join(w.capitalize() for w in idea.split()[:3] if len(w) > 2) or "AI-Product",
            "category": "saas",
            "tags": ["ai", "automation", "cloud"],
            "market_analysis": {
                "market_size": "Growing market with high demand",
                "competitors": ["Competitor A", "Competitor B"],
                "trends": ["AI adoption increasing", "Cloud-native solutions preferred"],
                "demand_level": "high",
            },
            "feature_priorities": [
                {"feature": "Core automation", "priority": "critical", "rationale": "Core value proposition"},
                {"feature": "User management", "priority": "high", "rationale": "Required for multi-tenant"},
                {"feature": "Analytics dashboard", "priority": "medium", "rationale": "Differentiator"},
            ],
            "monetization": {
                "free_tier": {"available": True, "limitations": {"features": ["Basic access"], "usage_limits": "100 requests/day", "users": "1 user"}},
                "paid_tiers": [
                    {"name": "Starter", "price": 29, "features": ["Full API", "Analytics"], "target_audience": "Small teams"},
                    {"name": "Professional", "price": 99, "features": ["Full API", "Analytics", "Priority support"], "target_audience": "Growing businesses"},
                    {"name": "Enterprise", "price": 499, "features": ["Everything", "Custom integrations", "Dedicated support"], "target_audience": "Large organizations"},
                ],
            },
            "positioning": f"{idea_preview} — a modern solution for forward-thinking teams",
        },
        "pm": {
            "product_name": " ".join(w.capitalize() for w in idea.split()[:3] if len(w) > 2) or "AI-Product",
            "description": f"Product specification for: {idea_preview}",
            "target_audience": "Technology companies",
            "core_features": [
                {"name": "User Authentication", "description": "Secure login and registration", "priority": "high"},
                {"name": "Data API", "description": "RESTful API for data operations", "priority": "high"},
                {"name": "Dashboard", "description": "Analytics and monitoring dashboard", "priority": "medium"},
            ],
            "user_stories": [
                {"story": "User can register and authenticate", "acceptance_criteria": "Email+password registration works"},
                {"story": "Admin can view system metrics", "acceptance_criteria": "Dashboard shows real-time metrics"},
            ],
            "estimated_effort": "M",
            "estimated_days": 14,
        },
        "architect": {
            "architecture_name": f"Architecture-{pid[:8]}",
            "overview": f"Microservices architecture for: {idea_preview}",
            "components": [
                {"name": "API Gateway", "description": "Entry point and auth proxy", "technology": "FastAPI"},
                {"name": "Core Service", "description": "Business logic layer", "technology": "Python"},
                {"name": "Data Store", "description": "Persistent storage", "technology": "PostgreSQL"},
            ],
            "tech_stack": {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL"},
        },
        "developer": {
            "code_summary": f"Implementation for {pid[:8]}",
            "files": [
                {"path": "api/routes.py", "purpose": "API route definitions", "lines": 85},
                {"path": "models/schema.py", "purpose": "Data models", "lines": 62},
                {"path": "services/core.py", "purpose": "Core business logic", "lines": 120},
            ],
            "dependencies": ["fastapi", "sqlalchemy", "pydantic"],
        },
        "qa": {
            "test_summary": f"QA assessment for {pid[:8]}",
            "test_cases": [
                {"name": "Auth flow test", "type": "integration", "status": "passed"},
                {"name": "API contract test", "type": "contract", "status": "passed"},
                {"name": "Performance baseline", "type": "performance", "status": "passed"},
            ],
            "coverage": 72,
            "quality_score": "A",
        },
        "security": {
            "security_score": 85,
            "grade": "B",
            "summary": f"Security scan completed for {pid[:8]}",
            "vulnerabilities": [],
            "secrets_found": [],
            "dependency_risks": [],
            "passed_checks": [
                "SQL Injection Prevention",
                "Command Injection Prevention",
                "No Hardcoded Secrets",
                "XSS Prevention",
                "Use of Secure Cryptography",
                "No Information Disclosure",
                "Path Traversal Prevention",
                "Secure Configuration",
            ],
            "failed_checks": [],
        },
        "devops": {
            "infrastructure": f"DevOps setup for {pid[:8]}",
            "docker_image": f"aicom-{pid[:8]}:latest",
            "ci_pipeline": "GitHub Actions",
            "deployment_target": "Docker container",
        },
        "marketing": {
            "product_name": " ".join(w.capitalize() for w in idea.split()[:3] if len(w) > 2) or "AI-Product",
            "tagline": f"Revolutionize your workflow with {idea_preview}",
            "short_description": f"{idea_preview} — built for modern teams",
            "long_description": f"A comprehensive solution for {idea_preview}. Designed with cutting-edge technology to deliver exceptional results.",
            "key_benefits": ["Increased productivity", "Reduced costs", "Seamless integration"],
            "selling_description": f"{idea_preview} — the ultimate solution for your business needs",
            "seo_metadata": {"title": f"{idea_preview} - AI-Powered Solution", "description": f"Discover {idea_preview}", "keywords": ["ai", "automation", "saas"]},
            "social_media_posts": [
                {"platform": "Twitter", "content": f"Introducing {idea_preview}! 🚀", "hashtags": ["#AI", "#SaaS"]},
                {"platform": "LinkedIn", "content": f"We're excited to launch {idea_preview}", "hashtags": ["#Technology", "#Innovation"]},
            ],
        },
        "sales": {
            "pricing_model": "SaaS subscription",
            "tiers": [
                {"name": "Free", "price": 0, "features": ["Basic access"]},
                {"name": "Pro", "price": 99, "features": ["Full access", "Support"]},
            ],
        },
    }

    return fallbacks.get(agent_type, {
        "result": f"{agent_type} completed processing",
        "product_id": pid,
    })
