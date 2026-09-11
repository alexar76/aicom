"""Self-improving prompts loop — analyze failures and propose prompt patches."""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.paths import data_root

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "agents" / "prompts"
PROPOSALS_FILE = "state/prompt_improvement_proposals.jsonl"
AB_FILE = "state/prompt_improvement_ab.json"


def _proposals_path() -> Path:
    p = data_root() / PROPOSALS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _ab_path() -> Path:
    p = data_root() / AB_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _agent_prompt_file(agent_type: str) -> Path | None:
    mapping = {
        "pm": "pm_system_prompt_base.md",
        "analyst": "analyst_research_prompt.md",
        "developer": "developer_core_prompt.md",
        "qa": "qa_system_prompt.md",
        "architect": "architect_role_prompt.md",
        "marketing": "marketing_system_prompt.md",
        "devops": "devops_system_prompt.md",
        "security": "security_system_prompt.md",
    }
    name = mapping.get(agent_type)
    if not name:
        return None
    path = PROMPTS_DIR / name
    return path if path.is_file() else None


def analyze_failures_and_propose(sm: Any, *, limit: int = 40) -> list[dict[str, Any]]:
    """Scan recent failed tasks and emit improvement proposals."""
    try:
        rows = sm.conn.execute(
            """
            SELECT agent_type, error, state, product_id, completed_at
            FROM tasks
            WHERE workspace_id = ?
              AND lower(trim(status)) = 'failed'
              AND completed_at > ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (sm.workspace_id, time.time() - 7 * 86400, limit),
        ).fetchall()
    except Exception:
        logger.debug("prompt improvement query failed", exc_info=True)
        return []

    by_agent: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        d = dict(row)
        agent = str(d.get("agent_type") or "unknown")
        err = str(d.get("error") or "unknown failure")[:300]
        by_agent[agent].append(err)

    proposals: list[dict[str, Any]] = []
    for agent, errors in by_agent.items():
        if len(errors) < 2:
            continue
        top = Counter(errors).most_common(3)
        dominant = top[0][0] if top else ""
        hypothesis = (
            f"Repeated failures on {agent}: tighten acceptance criteria and add explicit "
            f"counter-example for «{dominant[:120]}»."
        )
        prompt_path = _agent_prompt_file(agent)
        patch_preview = ""
        if prompt_path:
            text = prompt_path.read_text(encoding="utf-8", errors="replace")
            addition = (
                f"\n\n<!-- auto-improvement {int(time.time())} -->\n"
                f"**Quality guard:** Avoid: {dominant[:200]}. "
                f"Verify output against spec gates before finishing.\n"
            )
            patch_preview = addition.strip()

        proposal = {
            "id": f"prop-{agent}-{int(time.time())}",
            "agent_type": agent,
            "failure_count_7d": len(errors),
            "top_errors": [{"text": t, "count": c} for t, c in top],
            "hypothesis": hypothesis,
            "prompt_file": str(prompt_path.relative_to(PROMPTS_DIR.parent.parent)) if prompt_path else None,
            "patch_preview": patch_preview,
            "status": "proposed",
            "created_at": time.time(),
        }
        proposals.append(proposal)
        with _proposals_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal, ensure_ascii=False) + "\n")

    return proposals


def apply_proposal(proposal_id: str) -> dict[str, Any]:
    """Append patch block to agent prompt file (A/B variant B)."""
    path = _proposals_path()
    if not path.is_file():
        raise ValueError("proposal_not_found")
    target: dict | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("id") == proposal_id:
            target = row
            break
    if not target:
        raise ValueError("proposal_not_found")
    agent = str(target.get("agent_type") or "")
    prompt_path = _agent_prompt_file(agent)
    if not prompt_path:
        raise ValueError("prompt_file_missing")
    patch = str(target.get("patch_preview") or "").strip()
    if not patch:
        raise ValueError("empty_patch")
    original = prompt_path.read_text(encoding="utf-8")
    if patch in original:
        return {"status": "already_applied", "proposal_id": proposal_id}
    prompt_path.write_text(original.rstrip() + "\n\n" + patch + "\n", encoding="utf-8")
    target["status"] = "applied"
    target["applied_at"] = time.time()
    ab = {}
    if _ab_path().is_file():
        try:
            ab = json.loads(_ab_path().read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ab = {}
    variants = ab.get("variants") if isinstance(ab.get("variants"), list) else []
    variants.append({"proposal_id": proposal_id, "agent_type": agent, "applied_at": target["applied_at"]})
    ab["variants"] = variants[-20:]
    _ab_path().write_text(json.dumps(ab, indent=2), encoding="utf-8")
    return {"status": "applied", "proposal_id": proposal_id, "prompt_file": str(prompt_path)}


def list_proposals(*, limit: int = 30) -> list[dict[str, Any]]:
    path = _proposals_path()
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out
