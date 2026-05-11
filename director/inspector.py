"""
Independent inspector agent
===========================
Audits quality/profit/crypto and emits neutral reports for Director.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class InspectorAgent:
    """Independent inspector that does not mutate pipeline state."""

    def __init__(self, data_root: str = "/app/data", report_dir: str = "/app/data/reports/inspector"):
        self.data_root = Path(data_root)
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _collect_orders(self) -> list[dict[str, Any]]:
        candidates = [
            self.data_root / "store" / "orders.jsonl",
            self.data_root / "store" / "orders.json",
        ]
        rows: list[dict[str, Any]] = []
        for p in candidates:
            if not p.exists():
                continue
            try:
                if p.suffix == ".jsonl":
                    for line in p.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            rows.append(json.loads(line))
                else:
                    obj = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(obj, list):
                        rows.extend(x for x in obj if isinstance(x, dict))
            except Exception:
                continue
        return rows

    def _collect_feedback_recent(self, hours: int = 24) -> list[dict[str, Any]]:
        fb_dir = self.data_root / "feedback"
        if not fb_dir.exists():
            return []
        cutoff = time.time() - (hours * 3600)
        out: list[dict[str, Any]] = []
        for p in fb_dir.glob("fb-*.json"):
            row = self._read_json(p)
            if float(row.get("created_at") or 0) >= cutoff:
                out.append(row)
        return out

    def run_audit(self, window_hours: int = 24) -> dict[str, Any]:
        now = time.time()
        pipeline = self._read_json(self.data_root / "state" / "pipeline.json")
        products = pipeline.get("products") if isinstance(pipeline, dict) else {}
        if not isinstance(products, dict):
            products = {}

        scorecard = self._read_json(self.data_root / "reports" / "benchmark_scorecard.json")
        alerts = self._read_json(self.data_root / "reports" / "benchmark_alerts.json").get("alerts") or []
        feedback_rows = self._collect_feedback_recent(window_hours)
        orders = self._collect_orders()

        by_product_feedback: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in feedback_rows:
            pid = str(row.get("product_id") or "")
            if pid:
                by_product_feedback[pid].append(row)

        by_product_orders: dict[str, list[dict[str, Any]]] = defaultdict(list)
        chain_revenue: dict[str, float] = defaultdict(float)
        fiat_revenue = 0.0
        crypto_revenue = 0.0
        for row in orders:
            pid = str(row.get("product_id") or "")
            if pid:
                by_product_orders[pid].append(row)
            amount = float(row.get("amount") or 0.0)
            chain = str(row.get("chain") or "").lower().strip()
            currency = str(row.get("currency") or "").upper().strip()
            if chain:
                chain_revenue[chain] += amount
                crypto_revenue += amount
            else:
                fiat_revenue += amount
            if currency in {"USDT", "USDC", "ETH", "BTC"}:
                crypto_revenue += 0.0  # already counted; keep currency hook for future normalization

        product_audit: dict[str, Any] = {}
        problematic: list[str] = []

        for pid, prod in products.items():
            state = str((prod or {}).get("state") or "")
            frows = by_product_feedback.get(pid, [])
            orows = by_product_orders.get(pid, [])
            avg_rating = round(sum(float(x.get("rating") or 0) for x in frows) / max(1, len(frows)), 2) if frows else None
            bug_reports = sum(1 for x in frows if str(x.get("classification") or "") == "bug")
            negative_votes = sum(1 for x in frows if "journey_prompt" in (x.get("tags") or []) and "no" in (x.get("tags") or []))
            revenue_total = round(sum(float(x.get("amount") or 0.0) for x in orows), 2)
            order_count = len(orows)

            flags: list[str] = []
            if state.upper() in {"FAILED", "BUG_FOUND", "DEV_FIXING"}:
                flags.append("quality_state_not_terminal")
            if avg_rating is not None and avg_rating < 3.5:
                flags.append("low_feedback_rating")
            if bug_reports >= 2:
                flags.append("bug_reports_spike")
            if negative_votes >= 2:
                flags.append("negative_journey_feedback")
            if revenue_total <= 0:
                flags.append("no_recent_revenue")
            if flags:
                problematic.append(pid)

            product_audit[pid] = {
                "state": state,
                "feedback": {
                    "items": len(frows),
                    "avg_rating": avg_rating,
                    "bug_reports": bug_reports,
                    "negative_journey_votes": negative_votes,
                },
                "profit": {
                    "orders": order_count,
                    "revenue_total": revenue_total,
                },
                "risk_flags": flags,
            }

        top_chains = sorted(
            ({"chain": k, "revenue": round(v, 2)} for k, v in chain_revenue.items()),
            key=lambda x: x["revenue"],
            reverse=True,
        )[:10]

        recommendations: list[dict[str, Any]] = []
        if problematic:
            recommendations.append(
                {
                    "kind": "hardening_batch",
                    "reason": "inspector_found_problematic_products",
                    "targets": problematic[:20],
                }
            )
        if scorecard.get("status") == "no_reports":
            recommendations.append(
                {
                    "kind": "benchmark_required",
                    "reason": "no benchmark reports in scorecard",
                }
            )
        if alerts:
            recommendations.append(
                {
                    "kind": "benchmark_alerts_present",
                    "reason": "benchmark_alerts_non_empty",
                    "count": len(alerts),
                }
            )

        report = {
            "generated_at": now,
            "window_hours": window_hours,
            "source": "InspectorAgent-v1",
            "summary": {
                "products_total": len(products),
                "problematic_products": len(problematic),
                "benchmark_status": scorecard.get("status") or "ok",
                "benchmark_alerts_count": len(alerts),
            },
            "products": product_audit,
            "crypto_summary": {
                "fiat_revenue": round(fiat_revenue, 2),
                "crypto_revenue": round(crypto_revenue, 2),
                "top_chains": top_chains,
                "fiat_vs_crypto_share": {
                    "fiat": round(fiat_revenue / max(1e-6, fiat_revenue + crypto_revenue), 3),
                    "crypto": round(crypto_revenue / max(1e-6, fiat_revenue + crypto_revenue), 3),
                },
            },
            "recommendations": recommendations,
        }
        date_str = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now))
        out_json = self.report_dir / f"inspector-{date_str}.json"
        out_md = self.report_dir / f"inspector-{date_str}.md"
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        out_md.write_text(self._to_markdown(report), encoding="utf-8")
        return report

    def _to_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            "# Inspector Report",
            "",
            f"- generated_at: {int(report.get('generated_at') or 0)}",
            f"- products_total: {report.get('summary', {}).get('products_total')}",
            f"- problematic_products: {report.get('summary', {}).get('problematic_products')}",
            f"- benchmark_status: {report.get('summary', {}).get('benchmark_status')}",
            "",
            "## Crypto Summary",
            f"- fiat_revenue: {report.get('crypto_summary', {}).get('fiat_revenue')}",
            f"- crypto_revenue: {report.get('crypto_summary', {}).get('crypto_revenue')}",
            "",
            "## Recommendations",
        ]
        recs = report.get("recommendations") or []
        if not recs:
            lines.append("- none")
        else:
            for r in recs:
                lines.append(f"- {r.get('kind')}: {r.get('reason')}")
        return "\n".join(lines) + "\n"
