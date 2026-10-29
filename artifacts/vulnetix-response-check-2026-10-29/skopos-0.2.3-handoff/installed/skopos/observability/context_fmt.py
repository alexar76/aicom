"""Markdown formatters so the LLM agent can consume APM / Prometheus data."""

from __future__ import annotations

from typing import Any

from skopos.observability.charts import targets_table_rows
from skopos.observability.prom import (
    collect_overview_kpis,
    parse_instant_vector,
    prometheus_base_url,
    query_instant,
)


def _up_label(v: float | None) -> str:
    if v is None:
        return "unknown"
    return "UP" if v >= 0.5 else "DOWN"


def _fmt_num(v: float | None, *, digits: int = 3) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):.{digits}g}"


def format_observability_context(*, include_hub_breakdown: bool = True) -> str:
    """Build a compact ``## Observability`` markdown block for LLM context.

    When Prometheus is unreachable, do **not** invent demo KPIs for the model —
    only state that live APM is unavailable (UI may still show demo charts).
    """
    lines: list[str] = [
        "\n## Observability (Prometheus APM)\n",
        f"- Prometheus URL: `{prometheus_base_url()}`\n",
    ]
    try:
        kpis, live = collect_overview_kpis()
    except Exception as exc:  # defensive — never break agent context
        lines.append(f"- Status: unreachable ({exc})\n")
        lines.append(
            "- No live Hub/Factory/Metis metrics in this turn. "
            "Do not invent APM numbers; rely on nginx/security sections instead.\n"
        )
        return "".join(lines)

    if not live:
        lines.append("- Status: **unreachable** (no live scrape data this turn)\n")
        lines.append(
            "- Observability UI may show demo charts locally; "
            "do **not** treat demo numbers as production truth.\n"
        )
        lines.append(
            "- Hint: set `SKOPOS_PROMETHEUS_URL` to a reachable Prometheus "
            "(VPN / SSH tunnel / authenticated path) for live KPIs.\n"
        )
        return "".join(lines)

    lines.append("- Status: **live**\n")
    lines.append(f"- Hub: {_up_label(kpis.get('hub_up'))}\n")
    lines.append(f"- Factory (`job=aicom`): {_up_label(kpis.get('factory_up'))}\n")
    lines.append(f"- Metis: {_up_label(kpis.get('metis_up'))}\n")
    lines.append(f"- Hub invoke RPS (5m): {_fmt_num(kpis.get('invoke_rps'))}\n")
    lines.append(f"- Hub 402 / payment_required RPS (5m): {_fmt_num(kpis.get('payment_required_rps'))}\n")
    lines.append(f"- Hub invoke p99 seconds (5m): {_fmt_num(kpis.get('p99_s'))}\n")

    lines.append("\n### Scrape targets\n")
    for row in targets_table_rows(True, kpis):
        lines.append(
            f"- {row['target']} (job={row['job']}): {row['status']} [{row['source']}]\n"
        )

    if include_hub_breakdown:
        lines.extend(_hub_capability_breakdown())

    lines.append(
        "\nUse these APM figures together with nginx traffic and security findings. "
        "If Hub is DOWN or 402 RPS spikes, prefer payment/federation checks over nginx-only advice.\n"
    )
    return "".join(lines)


def _hub_capability_breakdown(limit: int = 12) -> list[str]:
    """Top Hub invoke rates by capability × result (live PromQL)."""
    rows = parse_instant_vector(
        query_instant("topk(12, sum by (capability, result) (rate(aimarket_hub_invokes_total[15m])))")
    )
    if not rows:
        return []
    out: list[str] = ["\n### Hub invokes by capability × result (15m rate)\n"]
    # Sort by value desc when present
    ranked: list[dict[str, Any]] = sorted(
        rows,
        key=lambda r: float(r.get("value") or 0.0),
        reverse=True,
    )
    for row in ranked[:limit]:
        metric = row.get("metric") or {}
        cap = str(metric.get("capability") or "unknown")[:48]
        res = str(metric.get("result") or "n/a")[:24]
        out.append(f"- {cap} / {res}: {_fmt_num(row.get('value'))}/s\n")
    return out
