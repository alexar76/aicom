"""Distilled playbook — turns raw episodes into validated, retrievable rules (spec §8.4–§8.6).

This is what converts *memory* into *learning*:

* **distill** — recompute rules from ``episodes.jsonl``. Each rule's ``lift_ev`` is
  *measured* against realized per-build EV (§8.1), so a rule is only ``active`` when
  avoiding its failure signal demonstrably raised EV with enough support. Negative or
  thin evidence → ``retired``/``provisional``. That measurement *is* the validation
  (§8.6) — not a hand-wave.
* **retrieve_rules** — top-k rules whose scope (category/stage) matches the current
  build, ranked by ``lift_ev × confidence`` (§8.5). Replaces "inject last N raw rows".

Deterministic and offline-capable: the heuristic distiller needs no LLM, so the loop
runs (and is testable) without a provider. An optional LLM pass may later refine claim
text, but correctness never depends on it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.learning_objective import expected_value

logger = logging.getLogger(__name__)


def playbook_path(data_root: Path) -> Path:
    return Path(data_root) / "state" / "playbook.jsonl"


def _episodes_path(data_root: Path) -> Path:
    return Path(data_root) / "state" / "episodes.jsonl"


def _envi(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def playbook_topk() -> int:
    return max(1, _envi("AIFACTORY_PLAYBOOK_TOPK", 6))


def _min_support() -> int:
    return max(1, _envi("AIFACTORY_PLAYBOOK_MIN_SUPPORT", 3))


def _conf_k() -> int:
    return max(1, _envi("AIFACTORY_PLAYBOOK_CONF_K", 4))


def _episode_window() -> int:
    return max(10, _envi("AIFACTORY_PLAYBOOK_EPISODE_WINDOW", 500))


def _rule_id(category: str, stage: str, claim: str) -> str:
    return "pb-" + hashlib.sha256(f"{category}|{stage}|{claim}".encode()).hexdigest()[:12]


def _episode_ev(ep: dict[str, Any]) -> float:
    obj = ep.get("objective") if isinstance(ep.get("objective"), dict) else {}
    if "ev" in obj:
        try:
            return float(obj["ev"])
        except (TypeError, ValueError):
            pass
    return expected_value(
        shipped=bool(obj.get("shipped")),
        cost_usd=float(obj.get("cost_usd") or 0.0),
        repair_rounds=int(obj.get("repair_rounds") or 0),
        demand=obj.get("demand") if isinstance(obj.get("demand"), dict) else {},
    )


def load_episodes(data_root: Path) -> list[dict[str, Any]]:
    fp = _episodes_path(data_root)
    if not fp.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in fp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-_episode_window() :]


def load_rules(data_root: Path) -> list[dict[str, Any]]:
    fp = playbook_path(data_root)
    if not fp.is_file():
        return []
    rules: list[dict[str, Any]] = []
    for line in fp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rules.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rules


def _scope_matches(rule: dict[str, Any], *, category: str, stage: str) -> bool:
    scope = rule.get("scope") if isinstance(rule.get("scope"), dict) else {}
    rc = str(scope.get("category") or "").strip().lower()
    rs = str(scope.get("stage") or "").strip().lower()
    cat_ok = (not rc) or rc == (category or "").strip().lower()
    stage_ok = (not rs) or rs == (stage or "").strip().lower()
    return cat_ok and stage_ok


def retrieve_rules(
    data_root: Path,
    *,
    category: str = "",
    stage: str = "",
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Active, scope-matched rules ranked by measured lift × confidence (§8.5)."""
    k = top_k if top_k is not None else playbook_topk()
    active = [
        r
        for r in load_rules(data_root)
        if str(r.get("status") or "") == "active" and _scope_matches(r, category=category, stage=stage)
    ]
    active.sort(
        key=lambda r: float(r.get("lift_ev") or 0.0) * float(r.get("confidence") or 0.0),
        reverse=True,
    )
    # Dedup by claim, keeping the highest-scoring (already first) — prefers the more
    # specific category rule over its global twin.
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in active:
        claim = str(r.get("claim") or "")
        if claim in seen:
            continue
        seen.add(claim)
        deduped.append(r)
    return deduped[: max(1, k)]


def _confidence(support: int) -> float:
    return round(support / (support + _conf_k()), 3)


def distill(data_root: Path, *, llm_router: Any = None) -> int:
    """Recompute the playbook from episodes. Returns the number of active rules.

    Heuristic, measurement-based: for each (category, stage) the dominant failure
    ``signal`` becomes a candidate "avoid: <signal>" rule whose ``lift_ev`` is the EV
    gap between builds that avoided it and builds that hit it. ``llm_router`` is an
    optional hook for prettier claim text — never required for correctness.
    """
    episodes = load_episodes(Path(data_root))
    if not episodes:
        return 0

    # Group EVs by category and by the failure signal within each group. Rules are
    # category-scoped (stage left wildcard) for MVP: the defect is named in the claim,
    # and category is the one tag that is consistent between write-time and retrieval.
    groups: dict[str, dict[str, Any]] = {}
    signal_categories: dict[str, set[str]] = {}
    for ep in episodes:
        category = str(ep.get("category") or "general").strip().lower()
        rc = ep.get("root_cause") if isinstance(ep.get("root_cause"), dict) else {}
        signal = str(rc.get("signal") or "").strip()
        shipped = bool((ep.get("objective") or {}).get("shipped"))
        ev = _episode_ev(ep)
        g = groups.setdefault(category, {"evs": [], "by_signal": {}})
        g["evs"].append(ev)
        # A failure signal only counts on builds that did NOT ship (it's a defect marker).
        if signal and not shipped:
            g["by_signal"].setdefault(signal, []).append(ev)
            signal_categories.setdefault(signal, set()).add(category)
    # Cross-category bucket ("" scope, matches any retrieval): only for signals that recur
    # in >= 2 categories — a genuinely general defect, not a per-category quirk.
    cross = {sig for sig, cats in signal_categories.items() if len(cats) >= 2}
    if cross:
        gall = groups.setdefault("", {"evs": [], "by_signal": {}})
        for ep in episodes:
            rc = ep.get("root_cause") if isinstance(ep.get("root_cause"), dict) else {}
            signal = str(rc.get("signal") or "").strip()
            shipped = bool((ep.get("objective") or {}).get("shipped"))
            ev = _episode_ev(ep)
            gall["evs"].append(ev)
            if signal in cross and not shipped:
                gall["by_signal"].setdefault(signal, []).append(ev)

    min_support = _min_support()
    rules: list[dict[str, Any]] = []
    now = time.time()
    stage = ""
    for category, g in groups.items():
        evs: list[float] = g["evs"]
        if len(evs) < min_support:
            continue
        base_mean = sum(evs) / len(evs)
        for signal, hit_evs in g["by_signal"].items():
            without = [e for e in evs if e not in hit_evs] or evs
            mean_without = sum(without) / len(without)
            mean_with = sum(hit_evs) / len(hit_evs)
            lift = round(mean_without - mean_with, 4)
            support = len(evs)
            beats = sum(1 for e in without if e >= base_mean)
            win_rate = round(beats / len(without), 3) if without else 0.0
            if support >= min_support and lift > 0:
                status = "active"
            elif support >= min_support and lift <= 0:
                status = "retired"
            else:
                status = "provisional"
            claim = f"avoid: {signal}"[:300]
            rules.append(
                {
                    "id": _rule_id(category, stage, claim),
                    "scope": {"category": category, "stage": stage},
                    "claim": claim,
                    "support": support,
                    "lift_ev": lift,
                    "confidence": _confidence(support),
                    "win_rate": win_rate,
                    "status": status,
                    "created_at": now,
                    "last_validated_at": now,
                }
            )

    fp = playbook_path(Path(data_root))
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rules) + ("\n" if rules else ""),
        encoding="utf-8",
    )
    active = sum(1 for r in rules if r["status"] == "active")
    logger.info("playbook distilled: %d rules (%d active) from %d episodes", len(rules), active, len(episodes))
    return active


def llm_refine_enabled() -> bool:
    return (os.environ.get("AIFACTORY_PLAYBOOK_LLM_REFINE", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def refine_playbook_claims(data_root: Path, *, llm_router: Any) -> int:
    """Optional LLM polish (spec §10): rewrite active rules' heuristic ``avoid: <signal>``
    claims into crisp, actionable guidance. Measurement fields (lift/confidence/status)
    are untouched — only wording changes. No-op unless ``AIFACTORY_PLAYBOOK_LLM_REFINE=1``
    and a router is supplied. Safe to schedule from an async worker (e.g. Director)."""
    if not llm_refine_enabled() or llm_router is None:
        return 0
    rules = load_rules(Path(data_root))
    active = [r for r in rules if r.get("status") == "active"]
    if not active:
        return 0
    refined = 0
    for r in active:
        if r.get("claim_refined"):
            continue  # already polished this playbook version — don't re-spend / drift
        claim = str(r.get("claim") or "")
        if not claim:
            continue
        scope = r.get("scope") or {}
        prompt = (
            "Rewrite this build-quality lesson as one crisp imperative rule for an engineering "
            f"agent (max 140 chars, no preamble). Category: {scope.get('category') or 'any'}. "
            f"Lesson: {claim}"
        )
        try:
            out = await llm_router.generate(prompt=prompt, task_type="quality_gate")
            text = (out or "").strip().strip('"').splitlines()[0][:300]
            if text:
                r["claim"] = text
                r["claim_refined"] = True
                refined += 1
        except Exception as exc:
            logger.debug("playbook claim refine failed: %s", exc)
    if refined:
        fp = playbook_path(Path(data_root))
        fp.write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in rules) + "\n",
            encoding="utf-8",
        )
    return refined


def distill_if_due(data_root: Path, *, llm_router: Any = None) -> int:
    """Run distillation on a cadence (every N episodes). Cheap; safe to call often."""
    cadence = max(1, _envi("AIFACTORY_PLAYBOOK_DISTILL_EVERY", 5))
    n = len(load_episodes(Path(data_root)))
    if n == 0 or n % cadence != 0:
        return -1
    try:
        return distill(Path(data_root), llm_router=llm_router)
    except Exception as exc:  # never let learning break the pipeline
        logger.warning("playbook distill_if_due failed: %s", exc)
        return -1
