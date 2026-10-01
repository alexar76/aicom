"""Surrogate calibration (L3) — does an AI "approve" actually pan out? (spec §8 L3)

Joins ``autonomy/surrogate_decisions.jsonl`` (what the surrogate decided + how confident)
with ``discovery/outcomes.jsonl`` (what actually happened) to answer: when the surrogate
approved at confidence C, how often was the build genuinely good (shipped / positive EV)?

Two products:
* **calibration_summary** — per-gate accuracy + calibration error, for the dashboard (§9).
* **calibrated_min_confidence** — raises the surrogate's approve threshold for a gate that
  has been historically over-confident. This is the machine substitute for "the operator
  learned not to trust that gate". Opt-in via ``AIFACTORY_AUTONOMY_CALIBRATION=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _surrogate_decisions_path(data_root: Path) -> Path:
    return Path(data_root) / "autonomy" / "surrogate_decisions.jsonl"


def _outcomes_path(data_root: Path) -> Path:
    return Path(data_root) / "discovery" / "outcomes.jsonl"


def _read_jsonl(fp: Path) -> list[dict[str, Any]]:
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


def _min_samples() -> int:
    try:
        return max(1, int(os.environ.get("AIFACTORY_CALIBRATION_MIN_SAMPLES", "5")))
    except ValueError:
        return 5


def _good(outcome: dict[str, Any]) -> bool:
    """A build was genuinely good if it shipped and ended EV-non-negative."""
    reached = str(outcome.get("reached") or "").upper() == "COMPLETED"
    try:
        ev_ok = float(outcome.get("ev") or 0.0) >= 0.0
    except (TypeError, ValueError):
        ev_ok = True
    return reached and ev_ok


def calibration_summary(data_root: Path) -> dict[str, Any]:
    """Per-gate approve accuracy + calibration error joined on product outcome."""
    decisions = _read_jsonl(_surrogate_decisions_path(Path(data_root)))
    outcomes = {str(o.get("product_id") or ""): o for o in _read_jsonl(_outcomes_path(Path(data_root)))}

    by_point: dict[str, dict[str, Any]] = {}
    for d in decisions:
        if str(d.get("decision") or "") != "approve":
            continue
        pid = str(d.get("product_id") or "")
        if pid not in outcomes:
            continue
        point = str(d.get("point") or "unknown")
        try:
            conf = max(0.0, min(1.0, float(d.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            conf = 0.0
        good = _good(outcomes[pid])
        b = by_point.setdefault(point, {"n": 0, "correct": 0, "conf_sum": 0.0, "brier": 0.0})
        b["n"] += 1
        b["correct"] += 1 if good else 0
        b["conf_sum"] += conf
        b["brier"] += (conf - (1.0 if good else 0.0)) ** 2

    per_point: dict[str, dict[str, float]] = {}
    overall_n = 0
    overall_brier = 0.0
    for point, b in by_point.items():
        n = b["n"]
        per_point[point] = {
            "n": n,
            "approve_accuracy": round(b["correct"] / n, 3) if n else 0.0,
            "mean_confidence": round(b["conf_sum"] / n, 3) if n else 0.0,
            "calibration_error": round(b["brier"] / n, 3) if n else 0.0,
        }
        overall_n += n
        overall_brier += b["brier"]
    return {
        "per_point": per_point,
        "overall_calibration_error": round(overall_brier / overall_n, 3) if overall_n else 0.0,
        "samples": overall_n,
    }


def calibration_enabled() -> bool:
    return (os.environ.get("AIFACTORY_AUTONOMY_CALIBRATION", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def calibrated_min_confidence(data_root: Path, point: str, base: float) -> float:
    """Raise the approve threshold for a gate that has been over-confident.

    new = base + max(0, mean_confidence − approve_accuracy), clamped to [base, 0.95].
    Returns ``base`` unchanged when disabled or evidence is thin.
    """
    if not calibration_enabled():
        return base
    summary = calibration_summary(Path(data_root)).get("per_point", {})
    stats = summary.get(point)
    if not stats or stats.get("n", 0) < _min_samples():
        return base
    overconfidence = float(stats["mean_confidence"]) - float(stats["approve_accuracy"])
    if overconfidence <= 0:
        return base
    return round(min(0.95, base + overconfidence), 3)
