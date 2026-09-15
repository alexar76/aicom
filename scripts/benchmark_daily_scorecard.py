#!/usr/bin/env python3
"""
Build daily/weekly public scorecard from benchmark reports.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def _load_reports(reports_dir: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(reports_dir.glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(j, dict) and "pass_rate" in j:
                j["_file"] = p.name
                out.append(j)
        except Exception:
            continue
    return out


def _avg(vals: list[float]) -> float:
    return round(sum(vals) / max(1, len(vals)), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", default="data/reports/benchmarks")
    ap.add_argument("--output-json", default="data/reports/benchmark_scorecard.json")
    ap.add_argument("--output-md", default="data/reports/benchmark_scorecard.md")
    ap.add_argument("--alerts-json", default="data/reports/benchmark_alerts.json")
    ap.add_argument("--min-pass-rate-24h", type=float, default=0.7)
    ap.add_argument("--min-pass-rate-7d", type=float, default=0.75)
    args = ap.parse_args()

    reports = _load_reports(Path(args.reports_dir))
    if not reports:
        now = time.time()
        scorecard = {
            "generated_at": now,
            "runs_total": 0,
            "runs_last_24h": 0,
            "runs_last_7d": 0,
            "pass_rate_last_24h_avg": None,
            "pass_rate_last_7d_avg": None,
            "latest": None,
            "status": "no_reports",
        }
        alerts = [
            {
                "type": "missing_data",
                "window": "all",
                "metric": "benchmark_reports",
                "value": 0,
                "threshold": 1,
                "message": "No benchmark reports found",
            }
        ]
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
        Path(args.alerts_json).write_text(json.dumps({"generated_at": now, "alerts": alerts}, indent=2), encoding="utf-8")
        Path(args.output_md).write_text(
            "# Benchmark Scorecard\n\n- status: no_reports\n- Total runs: 0\n\n## Alerts\n- No benchmark reports found\n",
            encoding="utf-8",
        )
        print(json.dumps({"scorecard": scorecard, "alerts": alerts}, indent=2))
        return 2

    now = time.time()
    day_cut = now - 86400
    week_cut = now - 7 * 86400
    day = [r for r in reports if float(r.get("generated_at", 0)) >= day_cut]
    week = [r for r in reports if float(r.get("generated_at", 0)) >= week_cut]

    day_rates = [float(r.get("pass_rate", 0)) for r in day]
    week_rates = [float(r.get("pass_rate", 0)) for r in week]

    scorecard = {
        "generated_at": now,
        "runs_total": len(reports),
        "runs_last_24h": len(day),
        "runs_last_7d": len(week),
        "pass_rate_last_24h_avg": _avg(day_rates) if day_rates else None,
        "pass_rate_last_7d_avg": _avg(week_rates) if week_rates else None,
        "latest": reports[-1],
    }
    alerts: list[dict] = []
    if scorecard["pass_rate_last_24h_avg"] is not None and float(scorecard["pass_rate_last_24h_avg"]) < float(args.min_pass_rate_24h):
        alerts.append(
            {
                "type": "degradation",
                "window": "24h",
                "metric": "pass_rate_avg",
                "value": scorecard["pass_rate_last_24h_avg"],
                "threshold": args.min_pass_rate_24h,
                "message": "24h pass-rate below threshold",
            }
        )
    if scorecard["pass_rate_last_7d_avg"] is not None and float(scorecard["pass_rate_last_7d_avg"]) < float(args.min_pass_rate_7d):
        alerts.append(
            {
                "type": "degradation",
                "window": "7d",
                "metric": "pass_rate_avg",
                "value": scorecard["pass_rate_last_7d_avg"],
                "threshold": args.min_pass_rate_7d,
                "message": "7d pass-rate below threshold",
            }
        )
    latest_rate = float(scorecard["latest"].get("pass_rate", 0))
    if scorecard["pass_rate_last_7d_avg"] is not None and latest_rate < float(scorecard["pass_rate_last_7d_avg"]) - 0.2:
        alerts.append(
            {
                "type": "degradation",
                "window": "latest_vs_7d",
                "metric": "pass_rate_drop",
                "value": round(float(scorecard["pass_rate_last_7d_avg"]) - latest_rate, 3),
                "threshold": 0.2,
                "message": "Latest run dropped >0.2 versus 7d average",
            }
        )

    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    Path(args.alerts_json).write_text(json.dumps({"generated_at": now, "alerts": alerts}, indent=2), encoding="utf-8")

    md = [
        "# Benchmark Scorecard",
        "",
        f"- Generated: {int(now)}",
        f"- Total runs: {scorecard['runs_total']}",
        f"- Last 24h runs: {scorecard['runs_last_24h']}",
        f"- Last 7d runs: {scorecard['runs_last_7d']}",
        f"- Avg pass-rate (24h): {scorecard['pass_rate_last_24h_avg']}",
        f"- Avg pass-rate (7d): {scorecard['pass_rate_last_7d_avg']}",
        "",
        "## Latest run",
        f"- report: {scorecard['latest'].get('_file')}",
        f"- count: {scorecard['latest'].get('count')}",
        f"- completed: {scorecard['latest'].get('completed')}",
        f"- failed: {scorecard['latest'].get('failed')}",
        f"- unresolved: {scorecard['latest'].get('unresolved')}",
        f"- pass_rate: {scorecard['latest'].get('pass_rate')}",
        "",
        "## Alerts",
    ]
    if alerts:
        md.extend([f"- {a['message']}: value={a['value']} threshold={a['threshold']} ({a['window']})" for a in alerts])
    else:
        md.append("- none")
    Path(args.output_md).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"scorecard": scorecard, "alerts": alerts}, indent=2))
    return 2 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
