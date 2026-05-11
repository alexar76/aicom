"""
Discussion Engine
=================
Main orchestrator for multi-agent discussions.

Lifecycle:
1. Create session via SessionManager
2. Start discussion → run rounds
3. Each round:
   a. ContextProvider gathers relevant context
   b. AgentOrchestrator calls each participant agent via LLM
   c. Collect responses → store as Messages
   d. Check termination conditions (max_rounds, consensus, boredom, timeout)
4. ConsensusBuilder aggregates results
5. Save results to session
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from llm.router import LLMRouter

from .models import (
    CreateSessionRequest,
    Idea,
    Message,
    Round,
    Session,
    SessionResults,
    SessionStatus,
    UpdateSessionRequest,
)
from . import session_manager as sm
from .agent_orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


class DiscussionEngine:
    """
    Orchestrates the full lifecycle of a multi-agent discussion session.

    Handles session creation, round execution, termination checking,
    and result aggregation.
    """

    def __init__(self, llm_router: LLMRouter):
        self.orchestrator = AgentOrchestrator(llm_router)
        # Track active sessions to prevent concurrent execution conflicts
        self._active_sessions: set[str] = set()

    # ── Session Lifecycle ────────────────────────────────────────────────────

    async def create_session(self, request: CreateSessionRequest) -> Session:
        """Create and persist a new discussion session."""
        return sm.create_session(request)

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Load a session by ID."""
        return sm.get_session(session_id)

    async def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        session_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        """List sessions with optional filters."""
        response = sm.list_sessions(
            status=status,
            session_type=session_type,
            limit=limit,
            offset=offset,
        )
        return response

    async def update_session(
        self, session_id: str, request: UpdateSessionRequest
    ) -> Optional[Session]:
        """Update session configuration."""
        session = sm.get_session(session_id)
        if session is None:
            return None

        if request.topic is not None:
            session.topic = request.topic
        if request.config is not None:
            session.config = request.config
        if request.additional_instructions is not None:
            if session.context:
                session.context.additional_instructions = (
                    request.additional_instructions
                )

        return sm.update_session(session)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its data."""
        return sm.delete_session(session_id)

    # ── Discussion Execution ─────────────────────────────────────────────────

    async def start_session(self, session_id: str) -> Session:
        """
        Start a discussion session.

        Sets status to 'active' and begins round execution.
        Returns the session object after starting the first round.
        """
        session = sm.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if session.status != SessionStatus.pending:
            raise ValueError(
                f"Cannot start session in status '{session.status.value}'. "
                "Must be 'pending'."
            )

        session.status = SessionStatus.active
        session = sm.update_session(session)

        # Run the first round immediately
        session = await self.run_round(session_id)

        return session

    async def run_round(self, session_id: str) -> Session:
        """
        Execute a single discussion round.

        In each round, every participant agent is called in sequence.
        After all agents respond, termination conditions are checked.
        """
        session = sm.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if session.status != SessionStatus.active:
            logger.warning(
                f"Session {session_id} is {session.status.value}, "
                "cannot run round"
            )
            return session

        # Prevent concurrent execution on the same session
        if session_id in self._active_sessions:
            logger.warning(f"Session {session_id} already has an active round")
            return session
        self._active_sessions.add(session_id)

        try:
            round_number = session.round_count + 1

            # Create new round
            discussion_round = Round(round_number=round_number)
            session.rounds.append(discussion_round)
            session = sm.update_session(session)

            # Build conversation history from previous messages
            history = await self._build_conversation_history(session)

            # Call each participant agent
            for agent_type in session.participants:
                # Skip human/system in automated rounds
                if agent_type in ("human", "system"):
                    continue

                message = await self.orchestrator.call_agent(
                    session=session,
                    agent_type=agent_type,
                    round_number=round_number,
                    conversation_history=history,
                )

                # Save message
                sm.save_message(message)

                # Add message ID to the round
                discussion_round.message_ids.append(message.message_id)

                # Add to history for subsequent agents in this round
                history.append(
                    f"[{message.sender_name}]: {message.content[:200]}"
                )

                # Update session after each message
                sm.update_session(session)

            # Mark round as completed
            discussion_round.completed_at = time.time()
            session = sm.update_session(session)

            # Check termination conditions
            should_conclude, reason = self._check_termination(session)
            if should_conclude:
                session = await self._conclude_session(
                    session, reason
                )

        except Exception as e:
            logger.error(
                f"Error running round {session.round_count} "
                f"for session {session_id}: {e}"
            )
            raise
        finally:
            self._active_sessions.discard(session_id)

        return session

    async def add_human_input(
        self, session_id: str, text: str, username: str = "Human"
    ) -> Message:
        """
        Add a human message to the discussion.

        If the session is 'pending', it will be started.
        If 'active', the message is added and a new round may be triggered.
        """
        session = sm.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Auto-start if pending
        if session.status == SessionStatus.pending:
            session.status = SessionStatus.active
            sm.update_session(session)

        if session.status != SessionStatus.active:
            raise ValueError(
                f"Cannot add message to session in "
                f"'{session.status.value}' status"
            )

        # Create the human message
        message = await self.orchestrator.call_human(session, text, username)
        sm.save_message(message)

        # Find or create current round
        round_number = session.round_count
        if round_number == 0:
            # No rounds yet — create first round
            discussion_round = Round(round_number=1)
            session.rounds.append(discussion_round)
            round_number = 1
        else:
            discussion_round = session.rounds[-1]

        discussion_round.message_ids.append(message.message_id)
        sm.update_session(session)

        return message

    async def pause_session(self, session_id: str) -> Optional[Session]:
        """Pause an active session."""
        session = sm.get_session(session_id)
        if session is None:
            return None

        if session.status != SessionStatus.active:
            return session

        session.status = SessionStatus.paused
        return sm.update_session(session)

    async def resume_session(self, session_id: str) -> Optional[Session]:
        """Resume a paused session."""
        session = sm.get_session(session_id)
        if session is None:
            return None

        if session.status != SessionStatus.paused:
            return session

        session.status = SessionStatus.active
        session = sm.update_session(session)

        # Run next round
        session = await self.run_round(session_id)

        return session

    async def conclude_session(
        self, session_id: str
    ) -> Optional[Session]:
        """Manually conclude a session."""
        session = sm.get_session(session_id)
        if session is None:
            return None

        return await self._conclude_session(
            session, "Manually concluded by user"
        )

    # ── Internal Methods ─────────────────────────────────────────────────────

    async def _build_conversation_history(
        self, session: Session, max_messages: int = 30
    ) -> list[str]:
        """
        Build a formatted conversation history from recent messages.

        Args:
            session: The current session.
            max_messages: Maximum number of recent messages to include.

        Returns:
            A list of formatted message strings.
        """
        messages, total = sm.get_session_messages(
            session.session_id, limit=max_messages
        )

        # Reverse back to chronological order
        messages.reverse()

        history = []
        for msg in messages:
            prefix = f"[{msg.sender_name}]"
            content = msg.content[:300]  # Truncate long messages
            history.append(f"{prefix}: {content}")

        return history

    def _check_termination(
        self, session: Session
    ) -> tuple[bool, str]:
        """
        Check if the session should be concluded.

        Checks:
        1. max_rounds reached
        2. Inactivity timeout
        3. Auto-conclude (always check after max_rounds)

        Returns:
            Tuple of (should_conclude, reason_string).
        """
        # Check 1: Max rounds reached
        if session.round_count >= session.config.max_rounds:
            return True, f"Max rounds ({session.config.max_rounds}) reached"

        # Check 2: Inactivity timeout
        if session.config.inactivity_timeout_minutes > 0:
            last_activity = session.updated_at
            elapsed = time.time() - last_activity
            timeout_sec = session.config.inactivity_timeout_minutes * 60
            if elapsed > timeout_sec:
                return True, f"Inactivity timeout ({session.config.inactivity_timeout_minutes}min)"

        return False, ""

    async def _conclude_session(
        self, session: Session, reason: str
    ) -> Session:
        """
        Conclude a session: generate summary, save results, update status.
        """
        logger.info(
            f"Concluding session {session.session_id}: {reason}"
        )

        # Build a simple summary from the last few messages
        summary = await self._generate_summary(session)

        # Collect ideas from messages
        ideas = await self._extract_ideas(session)

        # Build results
        session.results = SessionResults(
            summary=summary,
            ideas=ideas,
            action_items=[],  # Will be populated by ConsensusBuilder
        )

        session.status = SessionStatus.completed
        session.completed_at = time.time()
        session = sm.update_session(session)

        logger.info(
            f"Session {session.session_id} concluded. "
            f"Messages: {session.message_count}, Ideas: {len(ideas)}"
        )

        return session

    async def _generate_summary(self, session: Session) -> str:
        """Generate a simple summary of the discussion."""
        if not session.rounds:
            return "No discussion occurred."

        messages, _ = sm.get_session_messages(
            session.session_id, limit=50
        )
        messages.reverse()  # Chronological

        if not messages:
            return "No messages in session."

        # Extract key points from each participant
        participants = set()
        key_points = []

        for msg in messages:
            participants.add(msg.sender_name)
            content_preview = msg.content[:150].strip()
            if content_preview:
                key_points.append(f"• {msg.sender_name}: {content_preview}")

        summary_parts = [
            f"Discussion on: {session.topic}",
            f"Participants: {', '.join(sorted(participants))}",
            f"Rounds completed: {session.round_count}",
            "",
            "Key contributions:",
            *key_points[:10],
        ]

        return "\n".join(summary_parts)

    async def _extract_ideas(self, session: Session) -> list[Idea]:
        """
        Extract structured ideas from discussion messages.
        Currently creates simple ideas from messages.
        Enhanced extraction will be in BrainstormingSessionManager.
        """
        messages, _ = sm.get_session_messages(
            session.session_id, limit=100
        )
        messages.reverse()

        ideas = []
        seen_content = set()

        for msg in messages:
            if msg.agent_type in ("human", "system"):
                continue

            # Simple idea extraction: use first sentence as idea title
            content = msg.content.strip()
            if not content or len(content) < 20:
                continue

            # Deduplicate
            content_key = content[:50].lower()
            if content_key in seen_content:
                continue
            seen_content.add(content_key)

            # Use first line/first sentence as title
            title = content.split("\n")[0][:100]
            if content.endswith(("?", "!", ".")):
                title = title.rstrip("?!")

            idea = Idea(
                session_id=session.session_id,
                title=title,
                description=content[:500],
                author_agent=msg.agent_type,
                supporters=[msg.agent_type],
            )
            ideas.append(idea)
            sm.save_idea(idea)

        return ideas
