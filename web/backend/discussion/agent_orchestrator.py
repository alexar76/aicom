"""
Agent Orchestrator
==================
Calls the LLM router on behalf of discussion participants.

IMPORTANT: Agents in discussions are NOT invoked via their execute() method.
Instead, the AgentOrchestrator calls LLMRouter.generate() directly with
carefully crafted prompts that include:
  - The agent's role description (from context_provider)
  - The session context (topic, type, product context)
  - The conversation history
  - Session-type-specific guidance

This approach avoids:
  - Agent-specific tool calls (search, code gen) that are irrelevant to discussion
  - Long agent initialization overhead
  - Side effects (saving artifacts, logging agent cycles)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from llm.router import LLMRouter
from llm.provider import GenerationConfig

from .models import (
    Message,
    MessageMetadata,
    Session,
    SessionType,
)
from .context_provider import build_context, get_agent_role, get_session_type_prompt

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates LLM calls for discussion participants.

    For each agent in a discussion round:
    1. Build a prompt with role description, context, and history
    2. Call LLMRouter.generate() with task_type="discussion"
    3. Parse and return the response as a Message object
    """

    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def call_agent(
        self,
        session: Session,
        agent_type: str,
        round_number: int,
        conversation_history: list[str],
    ) -> Message:
        """
        Call a single agent and return its response as a Message.

        Args:
            session: The current discussion session.
            agent_type: Which agent to call (e.g. "pm", "architect").
            round_number: Current round number.
            conversation_history: Formatted history of previous messages.

        Returns:
            A Message object with the agent's response.
        """
        start_time = time.time()

        # Build the system prompt with role + context
        system_context = build_context(session, round_number, conversation_history)
        role_description = get_agent_role(agent_type)
        session_guidance = get_session_type_prompt(session.session_type)

        system_prompt = (
            f"{role_description}\n\n"
            f"{system_context}\n\n"
            f"Remember: {session_guidance}"
        )

        # Build the user message for this round
        user_prompt = self._build_agent_prompt(
            agent_type=agent_type,
            session=session,
            round_number=round_number,
            history=conversation_history,
        )

        # Prepare generation config
        generation_config = GenerationConfig(
            temperature=session.config.temperature,
            max_tokens=session.config.max_tokens_per_agent,
            timeout_sec=60.0,
        )

        # Build the full prompt (system + user)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            # Call LLM router
            llm_model = None  # Will be filled by router
            llm_provider = None
            prompt_tokens = None
            completion_tokens = None

            response_text = await self.llm_router.generate(
                prompt=full_prompt,
                task_type="discussion",
                config=generation_config,
            )

            latency_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Agent '{agent_type}' responded in round {round_number} "
                f"({latency_ms:.0f}ms)"
            )

        except Exception as e:
            logger.error(
                f"Failed to get response from agent '{agent_type}' "
                f"in round {round_number}: {e}"
            )
            response_text = (
                f"[{agent_type} agent unavailable — error: {str(e)[:100]}]"
            )
            latency_ms = (time.time() - start_time) * 1000

        # Build the message
        message = Message(
            session_id=session.session_id,
            round_number=round_number,
            agent_type=agent_type,
            sender_name=self._get_sender_name(agent_type),
            content=response_text,
            metadata=MessageMetadata(
                model=llm_model,
                provider=llm_provider,
                latency_ms=round(latency_ms, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )

        return message

    async def call_human(
        self,
        session: Session,
        text: str,
        username: str = "Human",
    ) -> Message:
        """
        Create a Message for human input (no LLM call).

        Args:
            session: The current discussion session.
            text: The human's message text.
            username: Display name for the human.

        Returns:
            A Message object with the human's input.
        """
        # Determine current round number
        round_number = session.round_count + 1 if session.rounds else 1

        return Message(
            session_id=session.session_id,
            round_number=round_number,
            agent_type="human",
            sender_name=username,
            content=text,
        )

    @staticmethod
    def _build_agent_prompt(
        agent_type: str,
        session: Session,
        round_number: int,
        history: list[str],
    ) -> str:
        """Build the agent-specific prompt for this round."""
        lines = [
            f"Your role: {agent_type}",
            f"Discussion topic: {session.topic}",
            "",
        ]

        if history:
            lines.append("Here is what has been said so far:")
            lines.extend(history)
            lines.append("")

        lines.append("Please provide your perspective on this topic.")
        lines.append(
            "Keep your response focused, concise, and actionable. "
            "If you agree or disagree with previous points, explain your reasoning. "
            "If you have new ideas or suggestions, present them clearly."
        )

        return "\n".join(lines)

    @staticmethod
    def _get_sender_name(agent_type: str) -> str:
        """Get a human-readable display name for an agent type."""
        names = {
            "pm": "PM Agent",
            "analyst": "Market Analyst",
            "architect": "Architect Agent",
            "dev": "Developer Agent",
            "qa": "QA Agent",
            "devops": "DevOps Agent",
            "security": "Security Agent",
            "marketing": "Marketing Agent",
            "sales": "Sales Agent",
            "evolution_analyst": "Evolution Analyst",
            "methodologist": "Methodologist",
            "human": "Human",
            "system": "System",
        }
        return names.get(agent_type, f"{agent_type.capitalize()} Agent")
