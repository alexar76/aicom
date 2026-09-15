"""Outcome memory — ship-rate prior for discovery (closed demand loop MVP)."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

NEUTRAL_PRIOR = 5.0

_EV_METRICS: dict[str, Any] | None = None


def _ev_metrics():
    global _EV_METRICS
    if _EV_METRICS is not None:
        return _EV_METRICS
    try:
        from prometheus_client import Counter, Histogram

        _EV_METRICS = {
            "ev": Histogram(
                "factory_ev_per_build",
                "Realized Expected Value per shipped/failed build",
                ["cohort", "shipped"],
                buckets=(-5.0, -1.0, -0.1, 0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
            ),
            "builds": Counter(
                "factory_builds_total",
                "Terminal builds recorded by the learning loop",
                ["cohort", "shipped"],
            ),
        }
    except Exception:
        _EV_METRICS = {}
    return _EV_METRICS


def _record_ev_metric(ev: float, *, shipped: bool, frozen: bool) -> None:
    m = _ev_metrics()
    if not m:
        return
    cohort = "frozen" if frozen else "live"
    sh = "true" if shipped else "false"
    try:
        m["ev"].labels(cohort=cohort, shipped=sh).observe(ev)
        m["builds"].labels(cohort=cohort, shipped=sh).inc()
    except Exception:
        pass


def outcome_min_samples() -> int:
    raw = os.environ.get("AIFACTORY_OUTCOME_MIN_SAMPLES", "5")
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


def outcome_prior_weight() -> float:
    raw = os.environ.get("AIFACTORY_OUTCOME_PRIOR_WEIGHT", "0.12")
    try:
        return max(0.0, min(0.5, float(raw)))
    except ValueError:
        return 0.12


def outcomes_path(data_root: Path) -> Path:
    return data_root / "discovery" / "outcomes.jsonl"


def episodes_path(data_root: Path) -> Path:
    return data_root / "state" / "episodes.jsonl"


def append_outcome(data_root: Path, row: dict[str, Any]) -> None:
    fp = outcomes_path(data_root)
    fp.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("ts", time.time())
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_episode(data_root: Path, row: dict[str, Any]) -> None:
    fp = episodes_path(data_root)
    fp.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("ts", time.time())
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_outcomes(data_root: Path) -> list[dict[str, Any]]:
    fp = outcomes_path(data_root)
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
    return rows


def outcome_prior(
    data_root: Path,
    *,
    category: str,
    delivery_profile: str = "",
) -> dict[str, float]:
    """
    Learned ship/demand prior for idea scoring. Returns neutral 5.0 until min samples.
    """
    cat = (category or "general").strip().lower()
    profile = (delivery_profile or "").strip().lower()
    rows = _load_outcomes(data_root)
    matched = [
        r
        for r in rows
        if str(r.get("category") or "").strip().lower() == cat
        and (not profile or str(r.get("delivery_profile") or "").strip().lower() == profile)
    ]
    if len(matched) < outcome_min_samples():
        return {"ship_rate": NEUTRAL_PRIOR, "demand_rate": NEUTRAL_PRIOR, "samples": float(len(matched))}
    completed = sum(1 for r in matched if str(r.get("reached") or "").upper() == "COMPLETED")
    ship_rate = 10.0 * completed / len(matched)
    demand_scores: list[float] = []
    for r in matched:
        tel = r.get("telemetry") if isinstance(r.get("telemetry"), dict) else {}
        inv = float(tel.get("aimarket_invokes") or 0)
        views = float(tel.get("views") or 0)
        demand_scores.append(min(10.0, inv * 2.0 + views / 100.0))
    demand_rate = sum(demand_scores) / len(demand_scores) if demand_scores else NEUTRAL_PRIOR
    return {
        "ship_rate": round(ship_rate, 3),
        "demand_rate": round(demand_rate, 3),
        "samples": float(len(matched)),
    }


def _explore_bonus(samples: float) -> float:
    """UCB-style exploration bonus (spec §8.7): keeps under-explored categories from
    collapsing out of the ranking. Shrinks as evidence accumulates, so proven winners
    keep their earned score while thin-history options stay reachable."""
    import math

    try:
        c = float(os.environ.get("AIFACTORY_LEARNING_EXPLORE_C", "1.5"))
    except ValueError:
        c = 1.5
    return c * math.sqrt(1.0 / (1.0 + max(0.0, samples)))


def outcome_fit_score(data_root: Path, *, category: str, delivery_profile: str = "") -> float:
    prior = outcome_prior(data_root, category=category, delivery_profile=delivery_profile)
    samples = float(prior.get("samples") or 0.0)
    if samples < outcome_min_samples():
        # Cold start: stay neutral — no data, inject no noise.
        return NEUTRAL_PRIOR
    # Exploit measured ship/demand, plus a UCB exploration bonus that keeps
    # under-sampled (but past-threshold) categories reachable instead of collapsing
    # to one niche (spec §8.7). The bonus shrinks toward 0 as evidence accumulates.
    exploit = 0.6 * prior["ship_rate"] + 0.4 * prior["demand_rate"]
    return round(min(10.0, exploit + _explore_bonus(samples)), 3)


def _extract_root_cause(product: dict[str, Any]) -> dict[str, Any]:
    """Best-effort credit assignment (spec §8.3): which stage/gate caused the outcome,
    derived from the task history rather than a single coarse field. Also records a
    compact per-stage decision trail for deeper attribution later."""
    gate = str(product.get("last_gate") or product.get("last_failed_gate") or "")
    signal = str(product.get("human_review_reason") or product.get("failure_reason") or "")
    stage = ""
    decisions: list[dict[str, Any]] = []
    tasks = product.get("tasks")
    if isinstance(tasks, list):
        for t in tasks[-8:]:
            if isinstance(t, dict):
                decisions.append(
                    {
                        "stage": str(t.get("agent_type") or t.get("agent") or t.get("type") or ""),
                        "status": str(t.get("status") or t.get("state") or ""),
                    }
                )
        for t in reversed(tasks):
            if not isinstance(t, dict):
                continue
            st = str(t.get("status") or t.get("state") or "").lower()
            if st in ("failed", "error", "bug_found") or t.get("error"):
                stage = str(t.get("agent_type") or t.get("agent") or t.get("type") or "")
                if not signal:
                    signal = str(t.get("error") or "")
                break
    if not stage:
        stage = str(product.get("human_review_kind") or product.get("failure_reason") or "")
    return {"stage": stage[:120], "gate": gate[:120], "signal": signal[:500], "decisions": decisions}


def _outcome_marker_path(data_root: Path, pid: str, state: str) -> Path:
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in f"{pid}_{state}")
    return data_root / "outcomes" / "_recorded" / f"{safe}.json"


def record_terminal_outcome(data_root: Path, product: dict[str, Any]) -> None:
    """Emit outcome + episode rows when a product reaches a terminal state.

    Idempotent per (product, terminal state): monitoring cycles re-invoke this for
    products that remain COMPLETED, which would otherwise append duplicate
    outcome/episode rows and re-reward the process bandit for the same build,
    skewing the learning curve. A marker file records that a given terminal
    outcome was already booked so repeats are no-ops.
    """
    pid = str(product.get("id") or "")
    if not pid:
        return
    state = str(product.get("state") or "").upper()
    if state not in ("COMPLETED", "FAILED"):
        return
    marker = _outcome_marker_path(data_root, pid, state)
    if marker.exists():
        return  # this terminal outcome was already recorded
    meta = product.get("metadata") if isinstance(product.get("metadata"), dict) else {}
    category = str(product.get("category") or meta.get("category") or "general")
    profile = str(product.get("delivery_profile") or meta.get("delivery_profile") or "")
    tel_dir = data_root / "telemetry" / pid
    telemetry: dict[str, Any] = {}
    if tel_dir.is_dir():
        for name in ("summary.json", "metrics.json"):
            fp = tel_dir / name
            if fp.is_file():
                with contextlib.suppress(Exception):
                    telemetry.update(json.loads(fp.read_text(encoding="utf-8")))

    shipped = state == "COMPLETED"
    repair_rounds = int(product.get("quality_repair_round") or 0)
    try:
        cost_usd = float(
            product.get("cost_usd")
            or product.get("estimated_cost_usd")
            or meta.get("cost_usd")
            or telemetry.get("cost_usd")
            or 0.0
        )
    except (TypeError, ValueError):
        cost_usd = 0.0
    demand = {
        "views": telemetry.get("views", 0),
        "checkout_starts": telemetry.get("checkout_starts", 0),
        "aimarket_invokes": telemetry.get("aimarket_invokes", 0),
    }
    # Realized Expected Value — the single objective the learning curve plots (§8.1).
    from core.learning_objective import expected_value, learning_frozen

    ev = expected_value(shipped=shipped, cost_usd=cost_usd, repair_rounds=repair_rounds, demand=demand)
    frozen = learning_frozen(product)

    append_outcome(
        data_root,
        {
            "product_id": pid,
            "category": category,
            "delivery_profile": profile,
            "keywords": product.get("tags") or [],
            "reached": state,
            "repair_rounds": repair_rounds,
            "cost_usd": cost_usd,
            "ev": ev,
            "surrogate_decisions": product.get("surrogate_decisions") or [],
            "telemetry": telemetry,
        },
    )
    append_episode(
        data_root,
        {
            "product_id": pid,
            "category": category,
            "stack": product.get("stack") or meta.get("stack") or "",
            "delivery_profile": profile,
            "learning_frozen": frozen,
            "objective": {
                "shipped": shipped,
                "ev": ev,
                "cost_usd": cost_usd,
                "repair_rounds": repair_rounds,
                "demand": demand,
            },
            "root_cause": _extract_root_cause(product),
        },
    )
    _record_ev_metric(ev, shipped=shipped, frozen=frozen)

    # L4: feed realized EV back to the process bandit for the arm this build ran under.
    arm = product.get("config_arm")
    if arm:
        try:
            from core.process_bandit import update as bandit_update

            bandit_update(data_root, category=category, arm=str(arm), reward=ev)
        except Exception as exc:
            logger.debug("process bandit update skipped: %s", exc)

    # Close the loop: re-distill the playbook on a cadence so learning actually compounds.
    try:
        from core.playbook import distill_if_due

        distill_if_due(data_root)
    except Exception as exc:
        logger.debug("playbook distill skipped: %s", exc)

    # Mark this terminal outcome recorded so later monitoring cycles skip it.
    with contextlib.suppress(OSError):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"product_id": pid, "state": state}), encoding="utf-8")
