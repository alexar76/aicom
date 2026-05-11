"""
Brainstorming Session Manager
==============================
Specialised logic for brainstorming and product-idea sessions.

Handles:
- Idea scoring (feasibility, innovation, market potential)
- Support/oppose tracking
- Promoting ideas to pipeline products
- Aggregating brainstorming results
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from .models import (
    Idea,
    IdeaScore,
    Message,
    Session,
    SessionType,
)
from . import session_manager as sm

logger = logging.getLogger(__name__)


class BrainstormingSessionManager:
    """
    Manages brainstorming-specific logic on top of the base discussion engine.

    Provides methods for:
    - Extracting and scoring ideas from discussion messages
    - Recording support/opposition from agents
    - Promoting top ideas to pipeline products
    - Aggregating scores across multiple ideas
    """

    # ── Idea Extraction ─────────────────────────────────────────────────────

    async def extract_ideas_from_session(
        self, session: Session
    ) -> list[Idea]:
        """
        Extract structured ideas from all messages in a brainstorming session.

        This is more sophisticated than the basic extraction in DiscussionEngine.
        It:
        - Groups related statements by topic
        - Assigns scores based on agent feedback
        - Deduplicates similar ideas
        """
        if session.session_type not in (
            SessionType.brainstorming,
            SessionType.product_idea,
        ):
            logger.info(
                f"Session {session.session_id} is not brainstorming type, "
                f"skipping idea extraction"
            )
            return []

        messages, total = sm.get_session_messages(
            session.session_id, limit=200
        )
        messages.reverse()

        if not messages:
            return []

        # Simple extraction: group by agent and extract key proposals
        ideas = []
        seen_titles = set()

        for msg in messages:
            if msg.agent_type in ("human", "system"):
                continue

            content = msg.content.strip()
            if not content or len(content) < 30:
                continue

            # Extract title from first sentence or line
            title = self._extract_title(content)

            # Deduplicate by title similarity
            title_key = title.lower().strip()[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            # Score the idea
            score = self._calculate_initial_score(
                content, msg.agent_type
            )

            idea = Idea(
                session_id=session.session_id,
                title=title,
                description=content[:1000],
                author_agent=msg.agent_type,
                supporters=[msg.agent_type],
                score=score,
                tags=self._extract_tags(content),
            )

            ideas.append(idea)
            sm.save_idea(idea)

        # Update session with extracted ideas
        if session.results:
            session.results.ideas = ideas
            sm.update_session(session)

        logger.info(
            f"Extracted {len(ideas)} ideas from session {session.session_id}"
        )

        return ideas

    # ── Support / Oppose ─────────────────────────────────────────────────────

    async def record_support(
        self, idea_id: str, agent_type: str
    ) -> Optional[Idea]:
        """Record an agent's support for an idea."""
        # Need to find the idea in session
        # Since ideas are tied to sessions, we search through sessions
        stats = sm.get_discussion_stats()
        # For now, load ideas from the session directly
        # This is a simplified approach
        return None  # Will be enhanced with direct idea lookup

    async def record_oppose(
        self, idea_id: str, agent_type: str
    ) -> Optional[Idea]:
        """Record an agent's opposition to an idea."""
        return None

    # ── Idea Scoring ─────────────────────────────────────────────────────────

    def _calculate_initial_score(
        self, content: str, agent_type: str
    ) -> IdeaScore:
        """
        Calculate an initial score for an idea based on content heuristics.

        Args:
            content: The idea text.
            agent_type: Which agent proposed it.

        Returns:
            An IdeaScore with estimated ratings.
        """
        content_lower = content.lower()
        words = content.split()
        word_count = len(words)

        # Feasibility: based on concrete language and technical detail
        feasibility = 0.5
        concrete_indicators = [
            "implement", "build", "using", "architecture",
            "api", "database", "frontend", "backend",
            "microservice", "docker", "cloud", "scale",
        ]
        concrete_count = sum(
            1 for w in concrete_indicators if w in content_lower
        )
        feasibility = min(0.5 + concrete_count * 0.08, 1.0)

        # Innovation: based on novel concepts and creativity
        innovation = 0.5
        innovation_indicators = [
            "innovative", "novel", "new", "groundbreaking",
            "revolutionary", "unique", "different",
            "cutting-edge", "next-gen", "disruptive",
        ]
        innovation_count = sum(
            1 for w in innovation_indicators if w in content_lower
        )
        innovation = min(0.5 + innovation_count * 0.1, 1.0)

        # Market potential: based on market-aware language
        market_potential = 0.5
        market_indicators = [
            "market", "user", "customer", "revenue",
            "growth", "audience", "demand", "opportunity",
            "competitive", "differentiation", "value prop",
        ]
        market_count = sum(
            1 for w in market_indicators if w in content_lower
        )
        market_potential = min(
            0.5 + market_count * 0.08, 1.0
        )

        # Effort estimate based on content length and complexity
        if word_count < 30:
            effort = "S"
        elif word_count < 60:
            effort = "M"
        elif word_count < 100:
            effort = "L"
        else:
            effort = "XL"

        # Overall is average of dimensions
        overall = round(
            (feasibility + innovation + market_potential) / 3, 2
        )

        return IdeaScore(
            overall=overall,
            feasibility=round(feasibility, 2),
            innovation=round(innovation, 2),
            market_potential=round(market_potential, 2),
            effort_estimate=effort,
        )

    # ── Promote to Pipeline ─────────────────────────────────────────────────

    async def promote_idea_to_product(
        self, idea: Idea, session: Session
    ) -> Optional[str]:
        """
        Promote a brainstorming idea to a pipeline product.

        This creates a minimal product entry by writing to the pipeline state
        and updating the idea record.

        Args:
            idea: The idea to promote.
            session: The originating session.

        Returns:
            The new product_id if successful, None otherwise.
        """
        product_id = f"brainstorm-{idea.idea_id[:12]}"

        # Create a minimal product spec
        product_data = {
            "product_id": product_id,
            "title": idea.title,
            "description": idea.description,
            "source": "brainstorming",
            "source_session_id": session.session_id,
            "source_idea_id": idea.idea_id,
            "author_agent": idea.author_agent,
            "score": idea.score.model_dump() if idea.score else None,
            "tags": idea.tags,
            "created_at": time.time(),
            "status": "pending",
            "state": "new",
        }

        # Write to pipeline state
        pipeline_dir = "/app/data/state"
        os.makedirs(pipeline_dir, exist_ok=True)

        pipeline_path = f"{pipeline_dir}/pipeline.json"
        try:
            if os.path.exists(pipeline_path):
                with open(pipeline_path, "r") as f:
                    pipeline = json.load(f)
            else:
                pipeline = {"products": []}

            pipeline["products"].append(product_data)
            pipeline["total"] = len(pipeline["products"])

            with open(pipeline_path, "w") as f:
                json.dump(pipeline, f, indent=2, ensure_ascii=False)

            # Update the idea
            idea.converted_to_product = True
            idea.product_id = product_id
            sm.update_idea(idea)

            logger.info(
                f"Promoted idea '{idea.title[:50]}' to product {product_id}"
            )

            return product_id

        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to promote idea to product: {e}")
            return None

    # ── Helper Methods ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_title(content: str) -> str:
        """
        Extract a meaningful title from idea content.
        Uses the first sentence or first line.
        """
        # Try to find a line that looks like a title (short, no period end)
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip very long lines
            if len(line) > 200:
                # Use first sentence
                sentences = line.split(".")
                for s in sentences:
                    s = s.strip()
                    if 10 <= len(s) <= 120:
                        return s
                return line[:100]
            if 10 <= len(line) <= 150:
                return line

        # Fallback: first 100 chars
        return content[:100].rstrip(".,!? ")

    @staticmethod
    def _extract_tags(content: str) -> list[str]:
        """
        Extract relevant tags from content.
        Looks for key technology, domain, and concept mentions.
        """
        content_lower = content.lower()
        tag_candidates = {
            "ai": ["ai", "artificial intelligence", "machine learning", "ml", "deep learning"],
            "automation": ["automation", "automated", "auto"],
            "cloud": ["cloud", "aws", "azure", "gcp"],
            "security": ["security", "secure", "encryption", "auth"],
            "mobile": ["mobile", "ios", "android", "app"],
            "web": ["web", "frontend", "backend", "api", "rest"],
            "data": ["data", "analytics", "big data", "database"],
            "devops": ["devops", "ci/cd", "deployment", "infrastructure"],
            "ux": ["ux", "user experience", "usability", "interface"],
            "performance": ["performance", "optimization", "speed", "scalability"],
        }

        tags = []
        for tag, keywords in tag_candidates.items():
            if any(kw in content_lower for kw in keywords):
                tags.append(tag)

        return tags[:5]  # Limit to 5 tags

    @staticmethod
    def get_top_ideas(
        ideas: list[Idea], top_n: int = 5
    ) -> list[Idea]:
        """
        Return the top N ideas sorted by overall score.
        """
        scored = [
            idea for idea in ideas if idea.score is not None
        ]
        scored.sort(
            key=lambda i: i.score.overall if i.score else 0,
            reverse=True,
        )
        return scored[:top_n]

    @staticmethod
    def get_ideas_summary(ideas: list[Idea]) -> dict:
        """
        Get a summary of all ideas in a session.
        """
        if not ideas:
            return {"count": 0, "average_score": 0, "top_ideas": []}

        scores = [
            idea.score.overall
            for idea in ideas
            if idea.score is not None
        ]
        avg_score = sum(scores) / len(scores) if scores else 0

        top = BrainstormingSessionManager.get_top_ideas(ideas, 3)

        return {
            "count": len(ideas),
            "average_score": round(avg_score, 2),
            "top_ideas": [
                {
                    "title": idea.title[:80],
                    "author": idea.author_agent,
                    "score": idea.score.overall if idea.score else 0,
                }
                for idea in top
            ],
        }
