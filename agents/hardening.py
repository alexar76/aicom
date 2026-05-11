"""
Hardening Agent
===============
Mandatory stabilization pass after initial code generation and before QA.
"""

from __future__ import annotations

import time

from .base_agent import AgentInput, AgentOutput
from .dev import DeveloperAgent
from .product_profile import FULL_SOFTWARE, normalize_delivery_profile
from llm import LLMRouter


_FULL_SOFTWARE_AUTH_BLOCK = """
FULL_SOFTWARE — AUTH & ACCESS (mandatory when the product has accounts or protected data):
- Implement password hashing (bcrypt or argon2); never store plaintext passwords.
- JWT access (short TTL) + refresh **or** signed HTTP-only session cookies; document env vars.
- Endpoints at minimum: POST /api/auth/register, POST /api/auth/login, GET /api/auth/me (or equivalent).
- RBAC: at least **admin** vs **user** (claims or roles table); guard admin routes.
- CORS + CSRF posture documented for cookie sessions.
"""


class HardeningAgent(DeveloperAgent):
    """Second-pass developer focused on production hardening."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)
        self.agent_type = "hardening"

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        feedback_digest_note = ""
        try:
            from web.backend.services.feedback_digest import build_feedback_digest

            digest = build_feedback_digest(window_hours=168)
            feedback_digest_note = (
                "\n\nRECENT USER FEEDBACK DIGEST (last 7d):\n"
                f"{digest}\n"
                "Use this as reality-check: tighten UX, fix recurring bugs, and avoid repeated mistakes.\n"
            )
        except Exception:
            feedback_digest_note = ""
        owner_fb_note = ""
        try:
            from web.backend.services.owner_chat_routing import format_owner_product_feedback_for_prompt

            ob = format_owner_product_feedback_for_prompt(agent_input.product_id)
            if ob:
                owner_fb_note = "\n\n" + ob + "\n"
        except Exception:
            owner_fb_note = ""
        hardening_brief = (
            "MANDATORY HARDENING PASS before QA. Refactor for maintainability, "
            "add/strengthen tests, close security gaps, improve UX polish and a11y labels/alt/h1, "
            "remove placeholders/stubs, verify realistic stateful behavior."
        ) + feedback_digest_note + owner_fb_note
        data = dict(agent_input.data or {})
        admin = str(data.get("admin_instructions") or "").strip()
        inject_fs_auth = False
        raw_dp = data.get("delivery_profile")
        if raw_dp is not None:
            inject_fs_auth = normalize_delivery_profile(str(raw_dp).strip()) == FULL_SOFTWARE
        elif isinstance(data.get("specification"), dict):
            sdp = data["specification"].get("delivery_profile")
            if sdp is not None:
                inject_fs_auth = normalize_delivery_profile(str(sdp).strip()) == FULL_SOFTWARE
        if inject_fs_auth:
            hardening_brief = f"{hardening_brief}\n{_FULL_SOFTWARE_AUTH_BLOCK}"
        data["admin_instructions"] = f"{admin}\n\n{hardening_brief}".strip()
        data["hardening_pass"] = True
        wrapped = AgentInput(
            task_id=agent_input.task_id,
            product_id=agent_input.product_id,
            agent_type="hardening",
            data=data,
            context=agent_input.context,
            timestamp=time.time(),
        )
        out = await super().execute(wrapped)
        out.agent_type = "hardening"
        return out
