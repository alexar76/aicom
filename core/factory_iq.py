"""Factory IQ — analytics snapshot that makes "the factory is getting smarter" visible.

Pure read-only rollup over ``episodes.jsonl`` + ``playbook.jsonl`` (spec §9). The
dashboard / ``GET /api/analytics/factory-iq`` is a thin wrapper over this. Nothing here
mutates state, so it is safe to call from a public surface (only whitelisted scalars).

Hero signals:
* **learning curve** — rolling EV/build for the live cohort vs the frozen control;
  the gap is the literal value of learning (§9.2).
* **Factory IQ** — one 0–100 number designed to climb as learning works (§9.1).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from core.playbook import load_episodes, load_rules


def _ev(ep: dict[str, Any]) -> float:
    obj = ep.get("objective") if isinstance(ep.get("objective"), dict) else {}
    try:
        return float(obj.get("ev") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _slope(xs: list[float]) -> float:
    """Improvement signal: mean(second half) − mean(first half)."""
    if len(xs) < 2:
        return 0.0
    mid = len(xs) // 2
    return _mean(xs[mid:]) - _mean(xs[:mid])


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def factory_iq_snapshot(data_root: Path, *, series_limit: int = 100) -> dict[str, Any]:
    episodes = load_episodes(Path(data_root))
    live = [e for e in episodes if not e.get("learning_frozen")]
    frozen = [e for e in episodes if e.get("learning_frozen")]

    live_evs = [_ev(e) for e in live]
    frozen_evs = [_ev(e) for e in frozen]

    live_mean = round(_mean(live_evs), 4)
    frozen_mean = round(_mean(frozen_evs), 4)
    gap = round(live_mean - frozen_mean, 4) if frozen_evs else None

    shipped = sum(1 for e in live if (e.get("objective") or {}).get("shipped"))
    ship_rate = round(shipped / len(live), 4) if live else 0.0
    costs = [float((e.get("objective") or {}).get("cost_usd") or 0.0) for e in live]
    cost_per_ship = round(sum(costs) / shipped, 4) if shipped else 0.0
    ev_slope = round(_slope(live_evs), 4)

    rules = load_rules(Path(data_root))
    active = [r for r in rules if r.get("status") == "active"]
    rule_mean_lift = round(_mean([float(r.get("lift_ev") or 0.0) for r in active]), 4) if active else 0.0

    # Factory IQ (§9.1) — MVP scaling (no long history for z-scores yet). Honest, bounded.
    iq = round(
        100.0
        * _sigmoid(
            1.2 * ev_slope
            + 1.0 * (ship_rate - 0.5)
            + 0.8 * rule_mean_lift
            - 0.3 * cost_per_ship
        ),
        1,
    )

    try:
        from core.calibration import calibration_summary

        calibration = calibration_summary(Path(data_root))
    except Exception:
        calibration = {"per_point": {}, "overall_calibration_error": 0.0, "samples": 0}

    recent_rules = sorted(
        active,
        key=lambda r: float(r.get("lift_ev") or 0.0) * float(r.get("confidence") or 0.0),
        reverse=True,
    )[:10]

    return {
        "factory_iq": iq,
        "learning_curve": {
            "live_ev_mean": live_mean,
            "frozen_ev_mean": frozen_mean if frozen_evs else None,
            "gap": gap,
            "paying_off": (gap is not None and gap > 0),
            "ev_series": [round(x, 4) for x in live_evs[-series_limit:]],
        },
        "ship_rate": ship_rate,
        "cost_per_ship": cost_per_ship,
        "ev_slope": ev_slope,
        "builds": {"live": len(live), "frozen": len(frozen)},
        "playbook": {
            "active_rules": len(active),
            "total_rules": len(rules),
            "rule_mean_lift": rule_mean_lift,
        },
        "calibration": calibration,
        "recent_rules": [
            {
                "claim": r.get("claim"),
                "category": (r.get("scope") or {}).get("category"),
                "lift_ev": r.get("lift_ev"),
                "confidence": r.get("confidence"),
                "win_rate": r.get("win_rate"),
                "support": r.get("support"),
            }
            for r in recent_rules
        ],
    }
