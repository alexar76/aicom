"""
Consensus Builder
=================
Analyses discussion messages to find:
- Consensus topics (agreement across agents)
- Divergence points (disagreements)
- Action items
- Aggregated ratings

Used at the end of a discussion session to produce structured results.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .models import Idea, Message, Session, SessionResults
from . import session_manager as sm

logger = logging.getLogger(__name__)

# Keywords suggesting agreement
AGREEMENT_PATTERNS = [
    r"\b(agree|support|+1|good idea|great point|i like|makes sense)\b",
    r"\b(second|endorse|approved|aligned|on the same page)\b",
    r"\b(definitely|absolutely|exactly|correct|right)\b",
]

# Keywords suggesting disagreement
DISAGREEMENT_PATTERNS = [
    r"\b(disagree|concern|issue|problem|worried|however|but)\b",
    r"\b(not sure|unclear|risky|difficult|challenging|unlikely)\b",
    r"\b(against|oppose|counter|object|negative|drawback)\b",
]

# Keywords suggesting action items
ACTION_PATTERNS = [
    r"\b(should|need to|must|action item|todo|next step)\b",
    r"\b(follow.up|implement|create|build|develop|setup)\b",
    r"\b(schedule|assign|deadline|milestone|deliverable)\b",
]


class ConsensusBuilder:
    """
    Analyses discussion messages to extract consensus, divergence,
    action items, and overall ratings.
    """

    def __init__(self):
        self._agreement_count = 0
        self._disagreement_count = 0

    async def build_results(self, session: Session) -> SessionResults:
        """
        Analyse all messages in a session and produce structured results.

        Args:
            session: The completed (or completing) discussion session.

        Returns:
            A SessionResults object with analysis.
        """
        messages, total = sm.get_session_messages(
            session.session_id, limit=200
        )
        messages.reverse()  # Chronological order

        if not messages:
            return SessionResults(summary="No messages to analyse.")

        # 1. Find consensus topics
        consensus_topics = self._find_consensus_topics(messages)

        # 2. Find divergence points
        divergence_points = self._find_divergence_points(messages)

        # 3. Extract action items
        action_items = self._extract_action_items(messages)

        # 4. Calculate aggregated rating
        rating = self._calculate_rating(
            consensus_topics, divergence_points, messages
        )

        return SessionResults(
            summary=self._generate_summary(
                session, messages, consensus_topics, action_items
            ),
            ideas=[],  # Ideas are managed by DiscussionEngine
            consensus_topics=consensus_topics,
            divergence_points=divergence_points,
            action_items=action_items,
            aggregated_rating=rating,
        )

    def _find_consensus_topics(
        self, messages: list[Message]
    ) -> list[str]:
        """
        Identify topics where agents expressed agreement.
        Looks for agreement keywords and supporting statements.
        """
        topics = set()
        agent_opinions: dict[str, list[str]] = {}

        for msg in messages:
            if msg.agent_type in ("human", "system"):
                continue

            content_lower = msg.content.lower()

            # Check for agreement
            if self._matches_pattern(content_lower, AGREEMENT_PATTERNS):
                # Extract the topic being agreed upon (simple heuristic)
                topic = self._extract_topic(msg.content)
                if topic:
                    topics.add(topic)

            # Track what each agent said about key topics
            for topic_word in self._find_topic_words(msg.content):
                if topic_word not in agent_opinions:
                    agent_opinions[topic_word] = []
                agent_opinions[topic_word].append(msg.agent_type)

        # Find topics mentioned by multiple agents with agreement
        validated_topics = []
        for topic in topics:
            validated_topics.append(topic)

        # Limit to top 10
        return validated_topics[:10]

    def _find_divergence_points(
        self, messages: list[Message]
    ) -> list[str]:
        """
        Identify topics where agents expressed disagreement.
        """
        divergences = []
        disagreement_messages = []

        for msg in messages:
            if msg.agent_type in ("human", "system"):
                continue

            content_lower = msg.content.lower()

            if self._matches_pattern(content_lower, DISAGREEMENT_PATTERNS):
                # Extract what they disagreed about
                topic = self._extract_topic(msg.content)
                if topic and topic not in divergences:
                    divergences.append(topic)
                    disagreement_messages.append(
                        f"{msg.sender_name} raised concerns about: {topic}"
                    )

        # Limit to top 5
        return disagreement_messages[:5]

    def _extract_action_items(
        self, messages: list[Message]
    ) -> list[str]:
        """
        Extract actionable statements from messages.
        """
        actions = []
        seen = set()

        for msg in messages:
            content_lower = msg.content.lower()
            if self._matches_pattern(content_lower, ACTION_PATTERNS):
                # Extract sentences containing action keywords
                sentences = re.split(r'[.!?\n]', msg.content)
                for sentence in sentences:
                    sentence_lower = sentence.lower().strip()
                    if any(
                        re.search(pattern, sentence_lower)
                        for pattern in ACTION_PATTERNS
                    ):
                        clean = sentence.strip()
                        if clean and clean not in seen and len(clean) > 10:
                            actions.append(f"• {clean}")
                            seen.add(clean)

        return actions[:10]

    def _calculate_rating(
        self,
        consensus_topics: list[str],
        divergence_points: list[str],
        messages: list[Message],
    ) -> Optional[float]:
        """
        Calculate an aggregated rating for the discussion outcome.

        Rating is based on:
        - Ratio of agreement to disagreement
        - Number of consensus topics found
        - Number of participants who contributed
        """
        agent_count = len(
            set(
                m.agent_type
                for m in messages
                if m.agent_type not in ("human", "system")
            )
        )

        if agent_count == 0:
            return None

        # Base score
        base_score = 0.5

        # Bonus for consensus topics
        consensus_bonus = min(len(consensus_topics) * 0.05, 0.2)

        # Penalty for strong disagreements
        divergence_penalty = min(len(divergence_points) * 0.05, 0.2)

        # Participation bonus
        participation_bonus = min(agent_count * 0.03, 0.15)

        rating = base_score + consensus_bonus - divergence_penalty + participation_bonus
        rating = max(0.0, min(1.0, rating))

        return round(rating, 2)

    def _generate_summary(
        self,
        session: Session,
        messages: list[Message],
        consensus_topics: list[str],
        action_items: list[str],
    ) -> str:
        """Generate a human-readable summary of the discussion."""
        participants = set()
        for m in messages:
            if m.agent_type not in ("human", "system"):
                participants.add(m.sender_name)

        lines = [
            f"Discussion Summary: {session.topic}",
            f"Type: {session.session_type.value}",
            f"Status: {session.status.value}",
            f"Rounds completed: {session.round_count}",
            f"Total messages: {len(messages)}",
            f"Participants: {', '.join(sorted(participants)) if participants else 'None'}",
            "",
        ]

        if consensus_topics:
            lines.append("Consensus Topics:")
            for topic in consensus_topics[:5]:
                lines.append(f"  ✓ {topic}")

        if action_items:
            lines.append("\nAction Items:")
            for item in action_items[:5]:
                lines.append(f"  {item}")

        return "\n".join(lines)

    # ── Helper Methods ──────────────────────────────────────────────────────

    @staticmethod
    def _matches_pattern(
        text: str, patterns: list[str]
    ) -> bool:
        """Check if text matches any of the regex patterns."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _extract_topic(text: str) -> Optional[str]:
        """
        Extract a topic from text by finding the main subject.
        Uses simple heuristics: looks for phrases after
        'about', 'regarding', 'topic of', etc.
        """
        patterns = [
            r"(?:about|regarding|concerning|on the topic of)\s+([^,.!?]{5,60})",
            r"(?:the idea of|the concept of|the proposal for)\s+([^,.!?]{5,60})",
            r"(?:focus on|deals with|covers)\s+([^,.!?]{5,60})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                topic = match.group(1).strip()
                if len(topic) > 5:
                    return topic

        # Fallback: return first meaningful sentence fragment
        sentences = re.split(r'[.!?\n]', text)
        for sentence in sentences:
            words = sentence.strip().split()
            if 3 <= len(words) <= 20:
                return sentence.strip()[:80]

        return None

    @staticmethod
    def _find_topic_words(text: str) -> list[str]:
        """
        Find potential topic words in text.
        Returns important capitalized terms or quoted phrases.
        """
        topics = []

        # Find quoted phrases
        quoted = re.findall(r'"([^"]{5,60})"', text)
        topics.extend(quoted)

        # Find capitalized multi-word terms
        caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
        topics.extend(caps)

        return topics
