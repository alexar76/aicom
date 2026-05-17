"""
Classify Owner corporate-chat messages and route to pipeline / product feedback / directives.

Used from admin chat (background) and Director worker (batch).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.paths import (
    chat_messages_path,
    feedback_state_dir,
    owner_general_directives_path,
    pipeline_json_path,
)

CHAT_FILE = chat_messages_path()
PIPELINE_FILE = pipeline_json_path()
FEEDBACK_BASE = feedback_state_dir()
DIRECTIVES_FILE = owner_general_directives_path()

MAX_PRODUCTS_IN_PROMPT = 80


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
        if m:
            t = m.group(1).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    i = t.find("{")
    j = t.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(t[i : j + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def _catalog_prompt_lines() -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Return prompt lines and id -> product from pipeline."""
    state = _load_json(PIPELINE_FILE, {})
    products = state.get("products") or {}
    lines: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for pid, p in products.items():
        if not isinstance(p, dict):
            continue
        idea = str(p.get("idea") or "").strip()
        st = str(p.get("state") or "")
        lines.append(f'- {pid}: "{idea}" (state: {st})')
        by_id[str(pid)] = p
    lines = lines[:MAX_PRODUCTS_IN_PROMPT]
    return lines, by_id


def build_classification_prompt(owner_text: str) -> str:
    catalog_lines, _ = _catalog_prompt_lines()
    catalog_block = "\n".join(catalog_lines) if catalog_lines else "(no products yet)"
    return f"""You route messages from the company Owner (business stakeholder) to our AI factory.

Current products (id, idea, state):
{catalog_block}

Owner message:
\"\"\"{owner_text}\"\"\"

Respond with ONLY a JSON object (no markdown), using exactly one of these shapes:

1) New product idea (they want to launch something new that is not clearly about fixing an existing listed product):
{{"intent": "new_idea", "idea": "concise product idea in English", "reason": "short"}}

2) Feedback about an existing product (bugs, UX, copy for a product we already have — match by semantic meaning to one id above):
{{"intent": "product_feedback", "product_id": "<exact id from list or empty>", "feedback": "what to change", "matched_product_reason": "why"}}

If the message clearly refers to one product but you are unsure of the id, pick the best matching id from the list. If none match, use intent "general_directive" below.

3) General strategy / policy (quality bar, animations, tone, priorities — not tied to one product):
{{"intent": "general_directive", "directive": "concise directive in English", "reason": "short"}}

Rules:
- Prefer product_feedback when they complain about or improve something that fits an existing product idea.
- Prefer new_idea when they describe a new offering/market/product line not represented above.
- Use general_directive for company-wide guidance.

JSON only:"""


async def classify_owner_message(router: Any, owner_text: str) -> dict[str, Any] | None:
    from llm import GenerationConfig

    prompt = build_classification_prompt(owner_text)
    cfg = GenerationConfig(temperature=0.2, max_tokens=1024, timeout_sec=90.0)
    text = await router.generate(prompt, task_type="pm_analysis", config=cfg)
    return _extract_json_object(text or "")


def _validate_product_id(pid: str | None, catalog: dict[str, dict[str, Any]]) -> str | None:
    if not pid or not isinstance(pid, str):
        return None
    pid = pid.strip()
    if pid in catalog:
        return pid
    return None


def _orphan_feedback_routes_to_new_idea(text: str) -> bool:
    """
    When LLM said product_feedback but product_id is missing/invalid, decide:
    - new_idea: message reads like a new offering (queue pipeline)
    - else: store as general_directive
    """
    t = (text or "").strip().lower()
    if len(t) < 12:
        return False
    markers = (
        "сделай ",
        "создай ",
        "запусти ",
        "новый продукт",
        "новое прилож",
        "new product",
        "build a ",
        "build an ",
        "create a ",
        "create an ",
        "launch a ",
        "develop a ",
        "mvp",
        "saas for",
        "app for",
        "crm for",
        "сервис для",
        "приложен",
        "платформ для",
        "идея:",
        "product for",
    )
    if any(m in t for m in markers):
        return True
    if len(t) > 100 and any(x in t for x in (" for ", " для ", "для клиник", "для ресторан", "for dental", "for restaurants")):
        return True
    return False


def _merge_pipeline_metadata(product_id: str, snippet: dict[str, Any]) -> None:
    state = _load_json(PIPELINE_FILE, {})
    products = state.get("products") or {}
    p = products.get(product_id)
    if not isinstance(p, dict):
        return
    meta = p.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    tail = meta.get("owner_chat_tail")
    if not isinstance(tail, list):
        tail = []
    tail.append(snippet)
    tail = tail[-20:]
    meta["owner_chat_tail"] = tail
    p["metadata"] = meta
    products[product_id] = p
    state["products"] = products
    PIPELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_feedback_file(product_id: str, entry: dict[str, Any]) -> None:
    base = FEEDBACK_BASE / product_id
    base.mkdir(parents=True, exist_ok=True)
    path = base / "feedback.json"
    data = _load_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data["product_id"] = product_id
    msgs = data.get("owner_messages")
    if not isinstance(msgs, list):
        msgs = []
    msgs.append(entry)
    data["owner_messages"] = msgs
    _save_json(path, data)


def _append_general_directive(text: str, message_id: str) -> None:
    data = _load_json(DIRECTIVES_FILE, {"directives": []})
    directives = data.get("directives")
    if not isinstance(directives, list):
        directives = []
    directives.append(
        {
            "id": str(uuid.uuid4()),
            "text": text.strip(),
            "source_message_id": message_id,
            "timestamp": _utc_iso(),
        }
    )
    data["directives"] = directives[-200:]
    _save_json(DIRECTIVES_FILE, data)


def apply_routing_result(
    raw: dict[str, Any],
    *,
    message_id: str,
    owner_text: str,
    catalog: dict[str, dict[str, Any]],
) -> bool:
    """Persist routing outcome. Returns True if applied."""
    intent = str(raw.get("intent") or "").strip()

    if intent == "new_idea":
        idea = str(raw.get("idea") or owner_text).strip()
        if not idea:
            return False
        from web.backend.services.pipeline_enqueue import (
            append_product_to_pipeline_state,
            build_minimal_product_from_idea,
        )

        product = build_minimal_product_from_idea(
            idea,
            admin_instructions="Queued from Owner corporate chat (new_idea).",
        )
        append_product_to_pipeline_state(product)
        meta_snippet = {
            "kind": "owner_new_idea",
            "message_id": message_id,
            "idea": idea,
            "at": _utc_iso(),
        }
        _merge_pipeline_metadata(product["id"], meta_snippet)
        return True

    if intent == "product_feedback":
        feedback = str(raw.get("feedback") or owner_text).strip()
        pid = _validate_product_id(raw.get("product_id"), catalog)
        if not pid:
            body = feedback or owner_text
            if body and _orphan_feedback_routes_to_new_idea(body):
                logger.info(
                    "product_feedback without valid product_id; heuristic → new_idea",
                )
                return apply_routing_result(
                    {"intent": "new_idea", "idea": body},
                    message_id=message_id,
                    owner_text=owner_text,
                    catalog=catalog,
                )
            logger.info("product_feedback without valid product_id; treating as directive")
            _append_general_directive(body or owner_text, message_id)
            return True
        entry = {
            "id": message_id,
            "text": feedback or owner_text,
            "timestamp": _utc_iso(),
            "intent": "product_feedback",
            "processed": False,
        }
        _append_feedback_file(pid, entry)
        _merge_pipeline_metadata(
            pid,
            {
                "kind": "owner_feedback",
                "message_id": message_id,
                "summary": (feedback or owner_text)[:500],
                "at": _utc_iso(),
            },
        )
        return True

    if intent == "general_directive":
        directive = str(raw.get("directive") or owner_text).strip()
        if not directive:
            return False
        _append_general_directive(directive, message_id)
        return True

    logger.warning("Unknown owner routing intent: %s", intent)
    return False


def _iter_owner_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("kind") != "owner_message":
            continue
        if m.get("role") != "owner":
            continue
        out.append(m)
    return out


def _mark_message_processed(messages: list[Any], msg_id: str, extra: dict[str, Any]) -> None:
    for m in messages:
        if isinstance(m, dict) and m.get("id") == msg_id:
            m["director_processed_at"] = _utc_iso()
            for k, v in extra.items():
                m[k] = v
            break


async def process_owner_message_by_id(router: Any, message_id: str) -> bool:
    """Load chat file, classify message id, route, mark processed."""
    data = _load_json(CHAT_FILE, [])
    if not isinstance(data, list):
        return False
    target = None
    for m in data:
        if isinstance(m, dict) and m.get("id") == message_id:
            target = m
            break
    if not target:
        return False
    if target.get("director_processed_at"):
        return True
    text = str(target.get("text") or "").strip()
    if not text:
        _mark_message_processed(data, message_id, {"director_error": "empty"})
        _save_json(CHAT_FILE, data)
        return False

    _, catalog = _catalog_prompt_lines()
    try:
        raw = await classify_owner_message(router, text)
    except Exception as e:
        logger.exception("Owner classify failed: %s", e)
        return False

    if not raw:
        logger.warning("Owner classify returned no JSON for %s", message_id)
        return False

    # Re-load after slow LLM call so parallel workers do not double-apply.
    data = _load_json(CHAT_FILE, [])
    if not isinstance(data, list):
        return False
    target = None
    for m in data:
        if isinstance(m, dict) and m.get("id") == message_id:
            target = m
            break
    if not target:
        return False
    if target.get("director_processed_at"):
        return True
    text = str(target.get("text") or "").strip()

    intent = str(raw.get("intent") or "")
    _, catalog = _catalog_prompt_lines()
    try:
        ok = apply_routing_result(raw, message_id=message_id, owner_text=text, catalog=catalog)
    except Exception as e:
        logger.exception("Owner route apply failed: %s", e)
        return False

    if ok:
        _mark_message_processed(
            data,
            message_id,
            {"director_intent": intent, "director_routing": raw},
        )
        _save_json(CHAT_FILE, data)
    return ok


async def process_pending_owner_messages(router: Any, *, limit: int = 50) -> int:
    """Process owner messages without director_processed_at (batch). Returns count applied."""
    data = _load_json(CHAT_FILE, [])
    if not isinstance(data, list):
        return 0
    owners = _iter_owner_messages(data)
    n = 0
    for m in owners:
        if m.get("director_processed_at"):
            continue
        mid = str(m.get("id") or "")
        if not mid:
            continue
        if await process_owner_message_by_id(router, mid):
            n += 1
        if n >= limit:
            break
    return n


def format_standup_owner_context(max_directives: int = 8, max_feedback_lines: int = 12) -> str:
    """Compact text for standup LLM: recent directives + recent product feedback."""
    blocks: list[str] = []

    ddata = _load_json(DIRECTIVES_FILE, {})
    dirs = ddata.get("directives") if isinstance(ddata, dict) else []
    dir_lines: list[str] = []
    if isinstance(dirs, list) and dirs:
        for item in dirs[-max_directives:]:
            if isinstance(item, dict):
                t = str(item.get("text") or "").strip()
                if t:
                    dir_lines.append(f"  - {t}")
    if dir_lines:
        blocks.append("General directives (Owner, recent):\n" + "\n".join(dir_lines))

    fb_lines: list[str] = []
    fb_count = 0
    if FEEDBACK_BASE.is_dir():
        for sub in sorted(FEEDBACK_BASE.iterdir()):
            if not sub.is_dir():
                continue
            path = sub / "feedback.json"
            if not path.exists():
                continue
            raw = _load_json(path, {})
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("product_id") or sub.name)
            msgs = raw.get("owner_messages")
            if not isinstance(msgs, list):
                continue
            for om in msgs[-3:]:
                if not isinstance(om, dict):
                    continue
                if om.get("processed"):
                    continue
                tx = str(om.get("text") or "").strip()
                if tx:
                    fb_lines.append(f"  - [{pid}] {tx[:200]}")
                    fb_count += 1
                    if fb_count >= max_feedback_lines:
                        break
            if fb_count >= max_feedback_lines:
                break
    if fb_lines:
        blocks.append("Open product feedback (Owner):\n" + "\n".join(fb_lines))

    if not blocks:
        return "(No Owner directives or open product feedback yet.)"
    return "\n\n".join(blocks)


def format_owner_product_feedback_for_prompt(product_id: str, max_items: int = 15) -> str:
    """Unread Owner feedback lines for injection into Evolution / QA prompts."""
    path = FEEDBACK_BASE / product_id / "feedback.json"
    if not path.exists():
        return ""
    raw = _load_json(path, {})
    if not isinstance(raw, dict):
        return ""
    msgs = raw.get("owner_messages")
    if not isinstance(msgs, list):
        return ""
    lines: list[str] = []
    for om in msgs:
        if not isinstance(om, dict):
            continue
        if om.get("processed"):
            continue
        tx = str(om.get("text") or "").strip()
        if tx:
            lines.append(f"- {tx[:600]}")
        if len(lines) >= max_items:
            break
    if not lines:
        return ""
    return "Owner feedback (prioritize when relevant):\n" + "\n".join(lines)
