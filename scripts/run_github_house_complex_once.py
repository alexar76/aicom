#!/usr/bin/env python3
"""Director discovery + Marketing/Analyst brainstorm → one on-demand full_software product.

Operator script for a single GitHub-house factory run. Writes
``/app/data/state/github_house_complex_run.json`` and focuses the pipeline on
the new product.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from pathlib import Path

OUT = Path("/app/data/state/github_house_complex_run.json")


def _existing_catalog() -> tuple[list[str], list[str]]:
    con = sqlite3.connect("/app/data/state/pipeline.db")
    try:
        rows = con.execute("SELECT idea, category FROM products").fetchall()
    finally:
        con.close()
    ideas = [str(r[0] or "").strip() for r in rows if str(r[0] or "").strip()]
    cats = [str(r[1] or "").strip() for r in rows if str(r[1] or "").strip()]
    return ideas, cats


def _dump(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT, flush=True)


async def _marketing_charter(router, ranked: list[dict]) -> dict:
    from llm import GenerationConfig

    slim = []
    for row in ranked[:8]:
        slim.append(
            {
                "idea": row.get("idea"),
                "category": row.get("category"),
                "score_total": row.get("score_total"),
                "balanced_score": row.get("balanced_score"),
                "research_summary": (row.get("research_summary") or "")[:800],
                "market_rationale": (row.get("market_rationale") or "")[:800],
            }
        )
    prompt = (
        "You are the factory Marketing Agent, pairing with the Director's discovery ranking.\n"
        "Pick ONE idea that must be built as **full_software** (real API + persistence + browser UI),\n"
        "NOT a marketing landing. Prefer the most ambitious but shippable vertical slice.\n"
        "Name it like a boutique brand (no ™/®, no enterprise SKU).\n"
        "Return a single JSON object with keys:\n"
        "product_name, tagline, idea (120-250 words, English), admin_instructions (engineering charter),\n"
        "category (marketplace slug), why_this_one (2-4 sentences).\n"
        "admin_instructions MUST require: FastAPI (or Nest) + Postgres/SQLite + browser UI,\n"
        "auth/session, seed demo user, tests (unit+behavior, coverage ≥70% / CI fail <60%),\n"
        "README with badges + hero/gallery, bilingual docs (en + product locale if not en),\n"
        "LICENSE, CHANGELOG 0.1.0, .github/workflows/ci.yml and release.yml (GitHub Release on v* tags).\n"
        "UI copy language: follow the idea's natural language; docs stay English + locale twin.\n\n"
        f"DIRECTOR_RANKED_IDEAS:\n{json.dumps(slim, ensure_ascii=False, indent=2)}\n"
    )
    raw = await router.generate(
        prompt,
        task_type="market_research",
        config=GenerationConfig(temperature=0.7, max_tokens=4000, timeout_sec=180, json_mode=True),
    )
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"marketing did not return JSON: {text[:400]!r}")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict) or not str(data.get("idea") or "").strip():
        raise RuntimeError(f"marketing JSON missing idea: {data!r}"[:500])
    return data


async def _brainstorm(router, ranked: list[dict]) -> str:
    """Optional 2-round marketing+analyst chat. Returns transcript text (may be empty)."""
    try:
        from web.backend.discussion.engine import DiscussionEngine
        from web.backend.discussion.models import CreateSessionRequest, SessionConfig, SessionType
        from web.backend.discussion import session_manager as sm

        slim = [{"idea": r.get("idea"), "category": r.get("category"), "score": r.get("balanced_score") or r.get("score_total")} for r in ranked[:6]]
        req = CreateSessionRequest(
            topic="Choose one ambitious full_software product from Director discovery — real app, not a landing",
            session_type=SessionType.product_idea,
            participants=["marketing", "analyst"],
            additional_instructions=(
                "Director already ranked opportunities. Marketing owns naming and positioning; "
                "Analyst stresses market evidence. Agree on ONE full_software MVP with API+DB+UI. "
                "Reject brochure landings. End with a concrete product brief.\n\n"
                + json.dumps(slim, ensure_ascii=False)
            ),
            config=SessionConfig(max_rounds=2, auto_conclude=True, temperature=0.8),
        )
        session = sm.create_session(req)
        engine = DiscussionEngine(router)
        session = await engine.start_session(session.session_id)
        if session.round_count < 2 and str(session.status.value) == "active":
            session = await engine.run_round(session.session_id)
        msgs, _total = sm.get_session_messages(session.session_id, limit=40)
        lines = []
        for m in reversed(msgs):
            agent = getattr(m, "agent_type", None) or getattr(m, "author_agent", "")
            content = getattr(m, "content", "") or ""
            lines.append(f"{agent}: {content}")
        print("brainstorm session", session.session_id, "rounds", session.round_count, "msgs", len(lines), flush=True)
        return "\n\n".join(lines)[:12000]
    except Exception as exc:
        print("brainstorm skipped", type(exc).__name__, exc, flush=True)
        return ""


def _create_product(charter: dict, ranked: list[dict], transcript: str) -> str:
    from core.pipeline_state_writer import append_product_to_pipeline_state
    from web.backend.core.config import AppConfig
    from web.backend.services.pipeline_focus import apply_pipeline_focus_mode
    from core.pipeline_worker_notify import notify_pipeline_worker_wake

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    idea = str(charter.get("idea") or "").strip()
    name = str(charter.get("product_name") or "").strip()
    if name and name.lower() not in idea.lower():
        idea = f"{name} — {idea}"
    instructions = str(charter.get("admin_instructions") or "").strip()
    extra = (
        "\n\nEngineering charter (binding):\n"
        "- delivery_profile: full_software\n"
        "- Follow GITHUB_HOUSE_CONTRACT: README hero+gallery+badges, bilingual docs, "
        "CI coverage ≥70% (fail <60%), CHANGELOG 0.1.0, LICENSE, "
        ".github/workflows/ci.yml + release.yml (GitHub Release on v* tags).\n"
        "- Relative URLs only in shipped HTML (sandbox iframe).\n"
        "- Seed demo login via SANDBOX_DEMO_* env when auth exists.\n"
    )
    ts = time.time()
    product = {
        "id": product_id,
        "idea": idea,
        "admin_instructions": (instructions + extra).strip(),
        "delivery_profile": "full_software",
        "production_mode": False,
        "on_demand": True,
        "category": str(charter.get("category") or "saas"),
        "tags": ["github-house", "director-marketing"],
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
        "metadata": {
            "delivery_profile": "full_software",
            "source": "director_discovery+marketing",
            "product_name": name,
            "tagline": charter.get("tagline"),
            "why_this_one": charter.get("why_this_one"),
        },
        "market_research": {
            "research_summary": (ranked[0].get("research_summary") if ranked else "") or "",
            "director_top_idea": (ranked[0].get("idea") if ranked else "") or "",
        },
        "discovery": {
            "score_total": ranked[0].get("score_total") if ranked else None,
            "brainstorm_excerpt": transcript[:2000] if transcript else "",
        },
    }
    if not append_product_to_pipeline_state(product):
        raise RuntimeError("append_product_to_pipeline_state failed")

    cfg = AppConfig()
    apply_pipeline_focus_mode(cfg, focus_product_id=product_id, resume_factory=True)
    notify_pipeline_worker_wake()
    print("CREATED", product_id, "focus+resume", flush=True)
    return product_id


async def main() -> int:
    from llm import LLMRouter
    from director.discovery_pipeline import DiscoveryPipeline
    import director.discovery_pipeline as discovery_mod

    def _tolerant_json(text: str) -> dict:
        raw = (text or "").strip()
        fence = __import__("re").search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence:
            raw = fence.group(1).strip()
        for candidate in (raw, raw[raw.find("{") : raw.rfind("}") + 1] if "{" in raw else ""):
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        print("WARN tolerant_json fallback empty", flush=True)
        return {}

    discovery_mod._safe_json = _tolerant_json  # type: ignore[attr-defined]

    payload: dict = {"started_at": time.time(), "phase": "discovery"}
    _dump(payload)

    ideas, cats = _existing_catalog()
    router = LLMRouter()
    discovery = DiscoveryPipeline(router=router)
    try:
        result = await discovery.run(existing_ideas=ideas, existing_categories=cats)
    except Exception as exc:
        print("DISCOVERY_FAILED", type(exc).__name__, exc, flush=True)
        fb = discovery._fallback_candidate([], cats)
        result = {"ranked_ideas": [fb], "signals_collected_now": 0, "signals_total": 0, "error": str(exc)[:400]}
    ranked = result.get("ranked_ideas") if isinstance(result.get("ranked_ideas"), list) else []
    payload.update(
        {
            "phase": "brainstorm",
            "signals_collected_now": result.get("signals_collected_now"),
            "signals_total": result.get("signals_total"),
            "ranked_preview": [
                {
                    "idea": (r.get("idea") or "")[:240],
                    "category": r.get("category"),
                    "score_total": r.get("score_total"),
                    "balanced_score": r.get("balanced_score"),
                }
                for r in ranked[:8]
            ],
        }
    )
    _dump(payload)
    print("DISCOVERY ranked", len(ranked), flush=True)
    for row in payload["ranked_preview"]:
        print(" -", row.get("balanced_score"), row.get("category"), (row.get("idea") or "")[:120], flush=True)

    transcript = await _brainstorm(router, ranked)
    payload["phase"] = "marketing_charter"
    payload["brainstorm_chars"] = len(transcript)
    _dump(payload)

    charter = await _marketing_charter(router, ranked)
    if transcript:
        charter["brainstorm_used"] = True
    payload["charter"] = {
        "product_name": charter.get("product_name"),
        "tagline": charter.get("tagline"),
        "category": charter.get("category"),
        "why_this_one": charter.get("why_this_one"),
        "idea_excerpt": str(charter.get("idea") or "")[:400],
    }
    payload["phase"] = "enqueue"
    _dump(payload)

    pid = _create_product(charter, ranked, transcript)
    payload.update(
        {
            "phase": "running",
            "product_id": pid,
            "finished_invent_at": time.time(),
        }
    )
    _dump(payload)
    print("OK", pid, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
