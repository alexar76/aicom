"""Surrogate review — eligibility, verdict schema, human-channel writers (pure helpers)."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

SurrogateDecision = Literal["approve", "block", "fill"]

# Human-judgment gates the surrogate may resolve (never objective pass/fail gates).
SURROGATE_ELIGIBLE_POINTS = frozenset(
    {
        "post_devops_gate",
        "human_review_stream",
        "qa_repair_exhausted",
        "security_repair_exhausted",
        "director_decision",
        "owner_feedback",
        "worker_review",
    }
)

# Objective gates — surrogate must not approve past these.
HARD_POLICY_BLOCKERS = frozenset(
    {
        "benchmark_gate",
        "demo_quality_gate",
        "browser_smoke_gate",
        "security_critical_unresolved",
    }
)


@dataclass
class SurrogateVerdict:
    point: str
    decision: SurrogateDecision
    confidence: float
    rationale: str
    judge_model: str = ""
    escalated: bool = False
    fill: dict[str, Any] = field(default_factory=dict)
    product_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_point_surrogate_eligible(point: str) -> bool:
    return point in SURROGATE_ELIGIBLE_POINTS


def autonomy_min_confidence() -> float:
    raw = os.environ.get("AIFACTORY_AUTONOMY_MIN_CONFIDENCE", "0.55")
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.55


def autonomy_max_judge_calls() -> int:
    raw = os.environ.get("AIFACTORY_AUTONOMY_MAX_JUDGE_CALLS", "6")
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def judge_calls_path(data_root: Path) -> Path:
    return data_root / "autonomy" / "judge_calls.json"


def get_judge_call_count(data_root: Path, product_id: str) -> int:
    fp = judge_calls_path(data_root)
    if not fp.is_file():
        return 0
    try:
        row = json.loads(fp.read_text(encoding="utf-8"))
        return int(row.get(product_id) or 0)
    except Exception:
        return 0


def increment_judge_call_count(data_root: Path, product_id: str) -> int:
    fp = judge_calls_path(data_root)
    fp.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, int] = {}
    if fp.is_file():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[product_id] = int(data.get(product_id) or 0) + 1
    fp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data[product_id]


def fail_safe_verdict(point: str, product_id: str, reason: str) -> SurrogateVerdict:
    return SurrogateVerdict(
        point=point,
        decision="block",
        confidence=0.0,
        rationale=reason,
        judge_model="fail_safe",
        product_id=product_id,
    )


def apply_confidence_policy(
    verdict: SurrogateVerdict, *, point: str, min_confidence: float | None = None
) -> SurrogateVerdict:
    """Sub-threshold confidence on eligible gates → block (fail closed).

    ``min_confidence`` lets the caller pass a calibrated threshold (L3); when ``None``
    the env default (``AIFACTORY_AUTONOMY_MIN_CONFIDENCE``) is used.
    """
    if not is_point_surrogate_eligible(point):
        return verdict
    if verdict.decision == "fill":
        return verdict
    threshold = autonomy_min_confidence() if min_confidence is None else min_confidence
    if verdict.confidence >= threshold:
        return verdict
    return SurrogateVerdict(
        point=verdict.point,
        decision="block",
        confidence=verdict.confidence,
        rationale=f"confidence below threshold ({verdict.confidence:.2f}): {verdict.rationale}",
        judge_model=verdict.judge_model,
        escalated=verdict.escalated,
        fill=verdict.fill,
        product_id=verdict.product_id,
    )


def append_surrogate_audit(data_root: Path, verdict: SurrogateVerdict) -> None:
    fp = data_root / "autonomy" / "surrogate_decisions.jsonl"
    fp.parent.mkdir(parents=True, exist_ok=True)
    row = verdict.to_dict()
    row["ts"] = time.time()
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _record_prometheus(verdict)


def write_ai_review_feedback(
    data_root: Path,
    *,
    product_id: str,
    review_decision: Literal["approve", "block"],
    rationale: str,
    point: str,
    confidence: float,
) -> Path:
    """Write fb-*.json using the same channel humans use (source=ai_review)."""
    fb_dir = data_root / "feedback"
    fb_dir.mkdir(parents=True, exist_ok=True)
    ts = time.time()
    fb_id = f"fb-{uuid.uuid4().hex[:12]}"
    row = {
        "id": fb_id,
        "product_id": product_id,
        "source": "ai_review",
        "review_decision": review_decision,
        "tags": ["ai_review", review_decision, point],
        "message": rationale[:4000],
        "confidence": confidence,
        "created_at": ts,
    }
    fp = fb_dir / f"{fb_id}.json"
    fp.write_text(json.dumps(row, indent=2), encoding="utf-8")
    return fp


def parse_verdict_json(raw: str, *, point: str, product_id: str, judge_model: str) -> SurrogateVerdict:
    text = (raw or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return fail_safe_verdict(point, product_id, "judge returned non-JSON")
    decision = str(data.get("decision") or "block").strip().lower()
    if decision not in ("approve", "block", "fill"):
        decision = "block"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    fill = data.get("fill") if isinstance(data.get("fill"), dict) else {}
    rationale = str(data.get("rationale") or "")[:4000]
    return SurrogateVerdict(
        point=point,
        decision=decision,  # type: ignore[arg-type]
        confidence=confidence,
        rationale=rationale or decision,
        judge_model=judge_model,
        escalated=bool(data.get("escalated")),
        fill=fill,
        product_id=product_id,
    )


_PROM_COUNTERS: dict[str, Any] | None = None


def _prometheus_counters():
    global _PROM_COUNTERS
    if _PROM_COUNTERS is not None:
        return _PROM_COUNTERS
    try:
        from prometheus_client import Counter, Histogram

        _PROM_COUNTERS = {
            "decisions": Counter(
                "surrogate_decisions_total",
                "Surrogate gate decisions",
                ["point", "decision"],
            ),
            "escalations": Counter(
                "surrogate_escalations_total",
                "Surrogate judge escalations",
                ["point"],
            ),
            "confidence": Histogram(
                "surrogate_confidence",
                "Surrogate verdict confidence",
                ["point"],
                buckets=(0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0),
            ),
        }
    except Exception:
        _PROM_COUNTERS = {}
    return _PROM_COUNTERS


def _record_prometheus(verdict: SurrogateVerdict) -> None:
    counters = _prometheus_counters()
    if not counters:
        return
    try:
        counters["decisions"].labels(point=verdict.point, decision=verdict.decision).inc()
        if verdict.escalated:
            counters["escalations"].labels(point=verdict.point).inc()
        counters["confidence"].labels(point=verdict.point).observe(verdict.confidence)
    except Exception:
        pass
