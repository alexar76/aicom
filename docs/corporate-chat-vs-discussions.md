# Corporate Chat vs Brainstorming & Discussions

<p align="center">
  <img src="./assets/icons/message-circle.svg" width="28" height="28" alt="Corporate Chat" />
  &nbsp;·&nbsp;
  <img src="./assets/icons/brain-circuit.svg" width="28" height="28" alt="Brainstorming" />
</p>

> Full UI walkthrough: [Admin Panel guide → Corporate Chat & Brainstorming](./admin-guide.md#corporate-chat) · [Screenshots](./assets/screenshots/README.md)

## At a glance

| | **Corporate Chat** | **Brainstorming & Discussions** |
|---|----------------------|--------------------------------|
| **Goal** | Persistent “office” channel: rituals (standup), status, clarifications from AI Director, messages from the human **Owner** | Time-boxed **sessions** by topic: brainstorm, feature discussion, strategy |
| **Flow** | Chronological feed; all messages in one place | Rounds; participants picked per session; output is ideas/decisions for the topic |
| **Director** | Runs **standup** on a schedule: plan, collects “employee” reports (agent roles), follow-up questions | Participates as one agent in the discussion orchestration (Discussion Engine), not as a scheduled facilitator |
| **Owner** | Explicit **platform owner** role: display name from settings; can post anytime | Admin creates a session and may post as a human within that session |
| **Artifact** | Message history (`chat_messages.json`), team operating mode | Session files under `/app/data/discussions/`, promoting ideas into the pipeline |
| **Pipeline** | **Worker posts** a line when an agent finishes a stage (`CORPORATE_CHAT_PIPELINE_EVENTS`, default on) | Not automatic — you **create** a session and **Start** rounds |

## Corporate Chat philosophy

- This is the **company kitchen**: short updates, questions to Director, answers from roles (PM, Dev, QA, etc.).
- With the **pipeline worker** running, **production-stage updates** appear here after each completed agent task (same filters as the pipeline; disable via env if noisy).
- **Standup** is a ritual: at the configured time Director posts the **plan**, then **role reports**, then **follow-ups** if needed.
- **Owner** is separate from agent-role logic: a human with owner privileges; in the UI messages are labeled Owner.

## Brainstorming & Discussions philosophy

- These are **project rooms**: topic, type (brainstorm / feature discussion), agent set, **rounds**.
- Focus is **quality of the outcome**, not daily status.
- Results can be **promoted** into a product / pipeline via a separate flow.

## Implementation

- Corporate Chat: `web/backend/api/admin/chat.py`, messages in `/app/data/state/chat_messages.json`, fields `role`, `kind`, optional `agent_type`.
- Pipeline → chat: `web/backend/services/pipeline_chat_notify.py`, called from `pipeline_worker.py` on successful task completion.
- Standup: `web/backend/services/corporate_standup.py`, schedule in `admin.json`, loop in FastAPI lifespan.
- Discussions: `web/backend/api/admin/discussions.py`, `web/backend/discussion/engine.py`, UI `BrainstormingTab.tsx`. First startup with no sessions seeds one **pending** discussion you can open and **Start**.
