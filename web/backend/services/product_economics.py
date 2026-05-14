"""
Per-Product Economics
=====================
Aggregate LLM call cost, token usage, call volume, and agent-breakdown
for each product from the shared ``llm_calls.jsonl`` log.

Used by the admin PipelineTab to show cost/quality/ROI badges without
reading the entire log file per product.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from llm.pricing_estimate import enrich_llm_log_entry

logger = logging.getLogger(__name__)

_LLM_LOG_PATH = Path("/app/data/logs/llm_calls.jsonl")


# ── Public API ────────────────────────────────────────────────────────────────


def get_product_llm_costs(
    product_ids: set[str],
    *,
    log_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Read ``llm_calls.jsonl`` once and aggregate cost/token/call stats per product.

    Returns a dict keyed by ``product_id``; each value contains::

        {
            "llm_cost_usd": float,       # total estimated USD (rounded to 6 decimals)
            "llm_call_count": int,       # total enriched calls for this product
            "llm_total_tokens": int,     # sum of prompt + completion tokens
            "llm_agent_breakdown": {     # per-agent-type subtotals
                "analyst": {"cost_usd": ..., "calls": ..., "tokens": ...},
                ...
            },
        }

    Products with zero matching calls are **not** included in the result.
    """
    if not product_ids:
        return {}

    path = log_path or _LLM_LOG_PATH
    if not path.exists():
        logger.debug("LLM log path %s does not exist — returning empty economics", path)
        return {}

    # Accumulators: product_id → {agent_type → {cost, calls, tokens}}
    accum: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"cost_usd": 0.0, "calls": 0, "tokens": 0})
    )

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue

                pid = entry.get("product_id")
                if not pid or pid not in product_ids:
                    continue

                # Enrich cost estimate if missing
                enrich_llm_log_entry(entry)

                cost = entry.get("estimated_cost_usd")
                if cost is None:
                    cost = 0.0
                else:
                    cost = float(cost)

                tokens = 0
                pt = entry.get("prompt_tokens")
                ct = entry.get("completion_tokens")
                if isinstance(pt, (int, float)) and isinstance(ct, (int, float)):
                    tokens = int(pt) + int(ct)
                elif isinstance(entry.get("tokens_used"), (int, float)):
                    tokens = int(entry["tokens_used"])

                agent = str(entry.get("agent_type", "unknown")) or "unknown"
                bucket = accum[pid][agent]
                bucket["cost_usd"] += cost
                bucket["calls"] += 1
                bucket["tokens"] += tokens

    except (OSError, IOError) as exc:
        logger.warning("Cannot read LLM log for product economics: %s", exc)
        return {}

    # Flatten nested accumulators into the public shape
    result: dict[str, dict[str, Any]] = {}
    for pid, agent_map in accum.items():
        total_cost = 0.0
        total_calls = 0
        total_tokens = 0
        breakdown: dict[str, dict[str, Any]] = {}

        for agent_type, stats in agent_map.items():
            c = round(stats["cost_usd"], 6)
            calls = stats["calls"]
            toks = stats["tokens"]
            total_cost += c
            total_calls += calls
            total_tokens += toks
            breakdown[agent_type] = {
                "cost_usd": c,
                "calls": calls,
                "tokens": toks,
            }

        result[pid] = {
            "llm_cost_usd": round(total_cost, 6),
            "llm_call_count": total_calls,
            "llm_total_tokens": total_tokens,
            "llm_agent_breakdown": breakdown,
        }

    return result


def compute_roi_band(
    llm_cost_usd: float | None,
    quality_score: float | None,
) -> str:
    """Return a traffic-light ROI band: ``"green"``, ``"amber"``, or ``"red"``.

    Heuristic (tunable later):
      - **green**: cost ≤ $1.00  OR  quality_score ≥ 4 (low cost or high quality)
      - **red**:   cost > $5.00  AND  quality_score < 3 (expensive + low quality)
      - **amber**: everything in between
    """
    if llm_cost_usd is None:
        llm_cost_usd = 0.0
    if quality_score is None:
        quality_score = 0.0

    if llm_cost_usd <= 1.0 or quality_score >= 4.0:
        return "green"
    if llm_cost_usd > 5.0 and quality_score < 3.0:
        return "red"
    return "amber"
