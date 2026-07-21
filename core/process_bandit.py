"""Process bandit (L4) — learn which run-config wins per category (spec §8 L4 / §8.7).

The factory can run a build under different *config arms* (e.g. model tier, repair
budget, gate strictness). This module learns, per category, which arm yields the best
realized EV — exploring on purpose so it never collapses onto one arm prematurely.

* **update** — record (category, arm, reward=EV) after a terminal build. Wired into
  ``record_terminal_outcome`` whenever a product carries ``config_arm``.
* **select_arm** — Thompson sampling over per-arm EV (Gaussian), with an ε-greedy floor.
  Opt-in via ``AIFACTORY_PROCESS_BANDIT=1``; the caller applies the chosen arm to the
  run config and tags the product with ``config_arm`` so the loop closes.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


def bandit_path(data_root: Path) -> Path:
    return Path(data_root) / "state" / "bandit.jsonl"


def default_arms() -> list[str]:
    raw = (os.environ.get("AIFACTORY_PROCESS_BANDIT_ARMS", "") or "").strip()
    if raw:
        arms = [a.strip() for a in raw.split(",") if a.strip()]
        if arms:
            return arms
    return ["balanced", "heavy", "light"]


def bandit_enabled() -> bool:
    return (os.environ.get("AIFACTORY_PROCESS_BANDIT", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _explore_frac() -> float:
    try:
        return max(0.0, min(1.0, float(os.environ.get("AIFACTORY_LEARNING_EXPLORE_FRAC", "0.15"))))
    except ValueError:
        return 0.15


def update(data_root: Path, *, category: str, arm: str, reward: float) -> None:
    fp = bandit_path(Path(data_root))
    fp.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "category": (category or "general").strip().lower(),
        "arm": arm,
        "reward": round(float(reward), 4),
        "ts": time.time(),
    }
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewards_by_arm(data_root: Path, category: str) -> dict[str, list[float]]:
    fp = bandit_path(Path(data_root))
    if not fp.is_file():
        return {}
    cat = (category or "general").strip().lower()
    out: dict[str, list[float]] = {}
    for line in fp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("category") or "").strip().lower() != cat:
            continue
        try:
            out.setdefault(str(row.get("arm")), []).append(float(row.get("reward") or 0.0))
        except (TypeError, ValueError):
            continue
    return out


def select_arm(data_root: Path, *, category: str, arms: list[str] | None = None) -> str:
    """Thompson sampling over per-arm EV with an ε-greedy exploration floor."""
    options = arms or default_arms()
    if not options:
        return "balanced"
    if random.random() < _explore_frac():
        return random.choice(options)
    history = _rewards_by_arm(Path(data_root), category)
    best_arm, best_sample = options[0], float("-inf")
    for arm in options:
        rewards = history.get(arm, [])
        if not rewards:
            # Optimistic prior so untried arms get explored.
            sample = 1.0 + random.gauss(0.0, 1.0)
        else:
            mu = mean(rewards)
            sigma = pstdev(rewards) if len(rewards) > 1 else 1.0
            sample = random.gauss(mu, max(0.05, sigma) / (len(rewards) ** 0.5))
        if sample > best_sample:
            best_arm, best_sample = arm, sample
    return best_arm


def arm_stats(data_root: Path, category: str) -> dict[str, dict[str, Any]]:
    """Per-arm mean EV + sample count for the dashboard."""
    history = _rewards_by_arm(Path(data_root), category)
    return {
        arm: {"n": len(rewards), "mean_ev": round(mean(rewards), 4) if rewards else 0.0}
        for arm, rewards in history.items()
    }


def select_process_arm(data_root: Path, category: str) -> str | None:
    """Worker entry point: chosen arm when the bandit is enabled, else None (no change)."""
    if not bandit_enabled():
        return None
    return select_arm(Path(data_root), category=category)


def arm_config(arm: str) -> dict[str, Any]:
    """Run-config a config arm maps to. The bandit learns which trade-off wins per
    category: ``light`` ships cheap but gives up on hard repairs sooner; ``heavy``
    spends more repair rounds chasing a ship; ``balanced`` uses pipeline defaults."""
    presets: dict[str, dict[str, Any]] = {
        "light": {"max_quality_loops": 3},
        "balanced": {"max_quality_loops": None},  # None → pipeline default
        "heavy": {"max_quality_loops": 10},
    }
    return presets.get(arm, {"max_quality_loops": None})


def assign_build_arm(data_root: Path, product: dict[str, Any]) -> str | None:
    """Pick + apply a config arm for a build at creation. No-op unless the bandit is on
    or the product already carries an arm. Tags ``config_arm`` so the realized EV is
    later fed back to the right arm by ``record_terminal_outcome`` (closing L4)."""
    if product.get("config_arm"):
        return str(product["config_arm"])
    arm = select_process_arm(Path(data_root), str(product.get("category") or "general"))
    if not arm:
        return None
    cfg = arm_config(arm)
    product["config_arm"] = arm
    loops = cfg.get("max_quality_loops")
    if isinstance(loops, int) and loops >= 1:
        product["max_quality_loops_override"] = loops
    return arm
