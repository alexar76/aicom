"""Expose Factory IQ / surrogate learning metrics from JSONL into the API /metrics registry.

Pipeline worker emits these counters into the default Prometheus registry, but
Prometheus scrapes the uvicorn process. This collector replays episodes and
surrogate audit rows so Grafana dashboards stay in sync with on-disk learning data.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import CollectorRegistry

from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

_REGISTERED = False


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


class FactoryIQPrometheusCollector:
    """Replay learning-loop JSONL as Prometheus metrics on each scrape."""

    def collect(self):
        data_root = factory_data_root()
        episodes = _read_jsonl(data_root / "state" / "episodes.jsonl")
        surrogates = _read_jsonl(data_root / "autonomy" / "surrogate_decisions.jsonl")

        builds = CounterMetricFamily(
            "factory_builds_total",
            "Terminal builds recorded by the learning loop",
            labels=["cohort", "shipped"],
        )
        ev_sum = GaugeMetricFamily(
            "factory_ev_per_build_sum",
            "Sum of realized EV per build (synced from episodes.jsonl)",
            labels=["cohort", "shipped"],
        )
        ev_count = GaugeMetricFamily(
            "factory_ev_per_build_count",
            "Count of realized EV samples (synced from episodes.jsonl)",
            labels=["cohort", "shipped"],
        )
        build_counts: dict[tuple[str, str], int] = defaultdict(int)
        ev_values: dict[tuple[str, str], list[float]] = defaultdict(list)

        for ep in episodes:
            cohort = "frozen" if ep.get("learning_frozen") else "live"
            obj = ep.get("objective") if isinstance(ep.get("objective"), dict) else {}
            shipped = "true" if obj.get("shipped") else "false"
            try:
                ev = float(obj.get("ev") or 0.0)
            except (TypeError, ValueError):
                ev = 0.0
            key = (cohort, shipped)
            build_counts[key] += 1
            ev_values[key].append(ev)

        for (cohort, shipped), count in sorted(build_counts.items()):
            builds.add_metric([cohort, shipped], count)
            values = ev_values[(cohort, shipped)]
            ev_sum.add_metric([cohort, shipped], sum(values))
            ev_count.add_metric([cohort, shipped], len(values))

        yield builds
        yield ev_sum
        yield ev_count

        decisions = CounterMetricFamily(
            "surrogate_decisions_total",
            "Surrogate gate decisions",
            labels=["point", "decision"],
        )
        escalations = CounterMetricFamily(
            "surrogate_escalations_total",
            "Surrogate judge escalations",
            labels=["point"],
        )
        conf_sum = GaugeMetricFamily(
            "surrogate_confidence_sum",
            "Sum of surrogate confidence scores (synced from audit log)",
            labels=["point"],
        )
        conf_count = GaugeMetricFamily(
            "surrogate_confidence_count",
            "Count of surrogate confidence samples (synced from audit log)",
            labels=["point"],
        )
        decision_counts: dict[tuple[str, str], int] = defaultdict(int)
        escalation_counts: dict[str, int] = defaultdict(int)
        conf_values: dict[str, list[float]] = defaultdict(list)

        for row in surrogates:
            point = str(row.get("point") or "unknown")
            decision = str(row.get("decision") or "unknown")
            decision_counts[(point, decision)] += 1
            if row.get("escalated"):
                escalation_counts[point] += 1
            try:
                conf = float(row.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            conf_values[point].append(max(0.0, min(1.0, conf)))

        for (point, decision), count in sorted(decision_counts.items()):
            decisions.add_metric([point, decision], count)
        for point, count in sorted(escalation_counts.items()):
            escalations.add_metric([point], count)
        for point, values in sorted(conf_values.items()):
            conf_sum.add_metric([point], sum(values))
            conf_count.add_metric([point], len(values))

        yield decisions
        yield escalations
        yield conf_sum
        yield conf_count

        try:
            from core.factory_iq import factory_iq_snapshot

            snap = factory_iq_snapshot(data_root)
            iq = GaugeMetricFamily("factory_iq_score", "Factory IQ composite score (0-100)")
            iq.add_metric([], float(snap.get("factory_iq") or 0.0))
            yield iq
        except Exception as exc:
            logger.debug("factory_iq_score gauge skipped: %s", exc)


def register_factory_iq_collector(registry: CollectorRegistry) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    registry.register(FactoryIQPrometheusCollector())
    _REGISTERED = True
