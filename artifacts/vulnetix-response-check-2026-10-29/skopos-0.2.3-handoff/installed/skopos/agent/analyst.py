from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig
from ..db import connect_for_config, init_db
from .config import AgentConfig, load_agent_config
from .context import build_server_context
from .providers import ChatMessage, chat_completion, chat_completion_stream


@dataclass(frozen=True)
class AnalysisResult:
    provider: str
    model: str
    report: str


ANALYSIS_PROMPT = """Perform a comprehensive security audit based on the server context below.

Structure your report with:
1. Executive summary (risk level: Critical/High/Medium/Low)
2. Open ports & exposure analysis
3. Resource health (CPU, memory, disk)
4. Docker containers — role, ports, CPU/RAM per container, stopped vs running
5. Authentication & SSH hardening
6. HTTP attack surface from traffic logs
7. Prioritized remediation checklist (numbered, actionable)

Be specific to the actual data. Reference server names and ports."""


def run_security_analysis(
    app_cfg: AppConfig,
    agent_cfg: AgentConfig,
    *,
    server_name: str | None = None,
    provider_id: str | None = None,
) -> AnalysisResult:
    con = connect_for_config(app_cfg)
    init_db(con)
    try:
        context = build_server_context(app_cfg, con, server_name=server_name)
        context = context[: agent_cfg.max_context_chars]
        prov_id = provider_id or agent_cfg.default_provider
        prov = agent_cfg.providers[prov_id]
        messages = [
            ChatMessage(role="system", content=agent_cfg.system_prompt),
            ChatMessage(
                role="user",
                content=f"{ANALYSIS_PROMPT}\n\n---\n\n{context}",
            ),
        ]
        report = chat_completion(agent_cfg, messages, provider_id=prov_id)
        return AnalysisResult(provider=prov_id, model=prov.model, report=report)
    finally:
        con.close()


def chat_with_agent(
    agent_cfg: AgentConfig,
    history: list[ChatMessage],
    user_message: str,
    *,
    context: str,
    provider_id: str | None = None,
) -> str:
    messages = [
        ChatMessage(role="system", content=agent_cfg.system_prompt),
        ChatMessage(
            role="user",
            content=f"Server context (for reference):\n\n{context[: agent_cfg.max_context_chars]}",
        ),
        ChatMessage(role="assistant", content="Understood. I have the server context. How can I help?"),
    ]
    messages.extend(history)
    messages.append(ChatMessage(role="user", content=user_message))
    return chat_completion(agent_cfg, messages, provider_id=provider_id)


def chat_with_agent_stream(
    agent_cfg: AgentConfig,
    history: list[ChatMessage],
    user_message: str,
    *,
    context: str,
    provider_id: str | None = None,
):
    messages = [
        ChatMessage(role="system", content=agent_cfg.system_prompt),
        ChatMessage(
            role="user",
            content=f"Server context (for reference):\n\n{context[: agent_cfg.max_context_chars]}",
        ),
    ]
    messages.extend(history)
    messages.append(ChatMessage(role="user", content=user_message))
    yield from chat_completion_stream(agent_cfg, messages, provider_id=provider_id)
