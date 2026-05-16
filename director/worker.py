"""
Director AI Worker
==================
Background process that runs Director AI analysis cycles.
Wires together: MetricsCollector → DirectorAnalyzer → DecisionEngine → ReportGenerator

Started by entrypoint.sh alongside the pipeline worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import signal
import sys
import time
from pathlib import Path

# Ensure we can import from the project root
sys.path.insert(0, "/app")

from core.paths import config_path
from core.config_merge import load_merged_config
from core.benchmark_admin_token import read_benchmark_admin_token
from director.metrics_collector import MetricsCollector
from director.analyzer import DirectorAnalyzer
from director.decision_engine import DecisionEngine
from director.report_generator import ReportGenerator
from director.scheduler import DirectorScheduler
from director.inspector import InspectorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("director-worker")


# ── Signal file for on-demand analysis trigger ──────────────────────────────
TRIGGER_SIGNAL_FILE = "/app/data/state/director_trigger.signal"
DECISIONS_FILE = "/app/data/state/director_decisions.json"
BENCHMARK_STATUS_FILE = "/app/data/state/benchmark_status.json"


class DirectorWorker:
    """
    Background worker that runs Director AI analysis cycles.

    The analysis cycle:
    1. Collect metrics from all sources (MetricsCollector)
    2. Analyze metrics for trends/anomalies (DirectorAnalyzer)
    3. Generate decisions + recommendations (DecisionEngine)
    4. Save decisions to file (for admin panel)
    5. Generate markdown report (ReportGenerator)
    """

    def __init__(self):
        self._running = False
        self._scheduler: DirectorScheduler | None = None
        self._signal_check_task: asyncio.Task | None = None
        self._auto_pipeline_task: asyncio.Task | None = None
        self._benchmark_league_task: asyncio.Task | None = None

        # Initialize Director components
        self.metrics_collector = MetricsCollector()
        self.analyzer = DirectorAnalyzer()
        self.decision_engine = DecisionEngine(
            auto_actions_enabled=True,
            allowed_actions=None,
        )
        self.report_generator = ReportGenerator()
        self.inspector = InspectorAgent()

        # Load config for auto-pipeline settings
        self._auto_pipeline_enabled = False
        self._auto_pipeline_interval_minutes = 60
        self._last_auto_product_time = 0
        self._analysis_interval_hours = 4
        self._llm_router = None
        self._benchmark_enabled = False
        self._benchmark_interval_hours = 24
        self._benchmark_count = 20
        self._benchmark_timeout_min = 60
        self._discovery_interval_hours = 6
        self._discovery_auto_enqueue = True
        self._discovery_auto_enqueue_cooldown_min = 120
        self._last_discovery_enqueue_time = 0.0
        self._autopipeline_backlog_pause_idea_received = 250
        self._autopipeline_backlog_resume_idea_received = 120
        self._last_benchmark_scorecard_refresh = 0.0

    def _load_config(self):
        """Load settings from merged platform config (fragments + overlay)."""
        try:
            config = load_merged_config(config_path())
            general = config.get("general", {})
            if not isinstance(general, dict):
                general = {}
            self._auto_pipeline_enabled = general.get("auto_pipeline", False)
            try:
                raw_iv = int(general.get("auto_pipeline_interval_minutes", 60))
            except (TypeError, ValueError):
                raw_iv = 60
            self._auto_pipeline_interval_minutes = max(15, min(10080, raw_iv))
            director_cfg = config.get("director", {})
            if not isinstance(director_cfg, dict):
                director_cfg = {}
            self._analysis_interval_hours = int(director_cfg.get("analysis_interval_hours", 4))
            self._benchmark_enabled = str(os.environ.get("AIFACTORY_BENCHMARK_AUTORUN_ENABLED", "0")).strip().lower() in ("1", "true", "yes")
            self._benchmark_interval_hours = int(os.environ.get("AIFACTORY_BENCHMARK_INTERVAL_HOURS", "24"))
            self._benchmark_count = int(os.environ.get("AIFACTORY_BENCHMARK_COUNT", "20"))
            self._benchmark_timeout_min = int(os.environ.get("AIFACTORY_BENCHMARK_TIMEOUT_MIN", "60"))
            self._discovery_interval_hours = int(os.environ.get("AIFACTORY_DISCOVERY_INTERVAL_HOURS", "6"))
            self._discovery_auto_enqueue = str(os.environ.get("AIFACTORY_DISCOVERY_AUTO_ENQUEUE", "1")).strip().lower() in (
                "1",
                "true",
                "yes",
            )
            self._discovery_auto_enqueue_cooldown_min = int(
                os.environ.get("AIFACTORY_DISCOVERY_AUTO_ENQUEUE_COOLDOWN_MIN", "120")
            )
            self._autopipeline_backlog_pause_idea_received = int(
                os.environ.get("AIFACTORY_AUTOPIPELINE_BACKLOG_PAUSE_IDEA_RECEIVED", "250")
            )
            self._autopipeline_backlog_resume_idea_received = int(
                os.environ.get("AIFACTORY_AUTOPIPELINE_BACKLOG_RESUME_IDEA_RECEIVED", "120")
            )
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")

    def _autopipeline_backpressure_allows_create(self, state: dict) -> bool:
        """
        Gate auto-create when IDEA_RECEIVED backlog is too large.
        Uses hysteresis (pause threshold > resume threshold) to avoid flapping.
        """
        products = state.get("products") if isinstance(state.get("products"), dict) else {}
        idea_received = 0
        for product in products.values():
            if str((product or {}).get("state") or "") == "IDEA_RECEIVED":
                idea_received += 1

        pause_thr = max(1, int(self._autopipeline_backlog_pause_idea_received))
        resume_thr = max(0, int(self._autopipeline_backlog_resume_idea_received))
        if resume_thr >= pause_thr:
            resume_thr = max(0, pause_thr - 1)

        if idea_received >= pause_thr:
            logger.warning(
                "Auto-pipeline paused by backlog guard: IDEA_RECEIVED=%s (pause>=%s, resume<=%s)",
                idea_received,
                pause_thr,
                resume_thr,
            )
            return False
        if idea_received > resume_thr:
            logger.info(
                "Auto-pipeline backlog still elevated: IDEA_RECEIVED=%s (resume<=%s)",
                idea_received,
                resume_thr,
            )
            return False
        return True

    async def _refresh_benchmark_scorecard(self) -> None:
        """Always refresh scorecard from existing benchmark reports."""
        cmd = [
            "/app/venv/bin/python",
            "/app/scripts/benchmark_daily_scorecard.py",
            "--reports-dir",
            "/app/data/reports/benchmarks",
            "--output-json",
            "/app/data/reports/benchmark_scorecard.json",
            "--output-md",
            "/app/data/reports/benchmark_scorecard.md",
            "--alerts-json",
            "/app/data/reports/benchmark_alerts.json",
        ]
        try:
            proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, check=False)
            if proc.returncode not in (0, 2):
                logger.warning("Benchmark scorecard refresh failed: %s", proc.stderr[-300:])
        except Exception as e:
            logger.warning("Benchmark scorecard refresh error: %s", e)

    async def _run_benchmark_league_once(self) -> None:
        """Optional autonomous benchmark run + scorecard regeneration."""
        token = read_benchmark_admin_token()
        if not token:
            logger.warning(
                "Benchmark league skipped: set AIFACTORY_BENCHMARK_ADMIN_TOKEN or "
                "AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE so admin API calls are authenticated"
            )
            status_path = Path(BENCHMARK_STATUS_FILE)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(
                    {
                        "status": "skipped_no_token",
                        "ended_at": time.time(),
                        "hint": "Set AIFACTORY_BENCHMARK_ADMIN_TOKEN or AIFACTORY_BENCHMARK_ADMIN_TOKEN_FILE",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return

        status_path = Path(BENCHMARK_STATUS_FILE)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        # Avoid stacking runs if a previous benchmark left "running" (crash/kill) or one is in flight.
        try:
            if status_path.exists():
                prev = json.loads(status_path.read_text(encoding="utf-8"))
                if prev.get("status") == "running":
                    started = float(prev.get("started_at") or 0)
                    stale_sec = (max(10, int(self._benchmark_timeout_min)) + 20) * 60
                    if started and (time.time() - started) < stale_sec:
                        logger.info("Benchmark league skipped: a run is already in progress")
                        return
                    logger.warning("Benchmark league: clearing stale running status before start")
        except Exception as exc:
            logger.debug("Benchmark status precheck: %s", exc)

        status_path.write_text(
            json.dumps(
                {
                    "status": "running",
                    "started_at": time.time(),
                    "count": self._benchmark_count,
                    "timeout_min": self._benchmark_timeout_min,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        ideas_file = Path("/app/scripts/benchmark_ideas.example.txt")
        if not ideas_file.exists():
            logger.warning("Benchmark autorun skipped: ideas file missing")
            status_path.write_text(
                json.dumps({"status": "failed", "error": "ideas_file_missing", "ended_at": time.time()}, indent=2),
                encoding="utf-8",
            )
            return
        ts = int(time.time())
        out = Path(f"/app/data/reports/benchmarks/run-{ts}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "/app/venv/bin/python",
            "/app/scripts/benchmark_pass_rate.py",
            "--ideas-file",
            str(ideas_file),
            "--base-url",
            "http://127.0.0.1:8081",
            "--count",
            str(max(1, self._benchmark_count)),
            "--timeout-min",
            str(max(10, self._benchmark_timeout_min)),
            "--production-mode",
            "--output",
            str(out),
        ]
        logger.info("Starting benchmark league run: count=%s timeout_min=%s", self._benchmark_count, self._benchmark_timeout_min)
        child_env = {**os.environ, "AIFACTORY_BENCHMARK_ADMIN_TOKEN": token}
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=child_env,
        )
        if proc.returncode != 0:
            logger.warning("Benchmark league run failed: %s", proc.stderr[-400:])
            status_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "returncode": proc.returncode,
                        "error": (proc.stderr or proc.stdout)[-1000:],
                        "ended_at": time.time(),
                        "output_report": str(out),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            status_path.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "returncode": 0,
                        "ended_at": time.time(),
                        "output_report": str(out),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        await self._refresh_benchmark_scorecard()

    async def _benchmark_league_loop(self):
        """Periodic autonomous benchmark league (opt-in via env)."""
        last_run = 0.0
        while self._running:
            try:
                self._load_config()
                now = time.time()
                if now - self._last_benchmark_scorecard_refresh >= 900:
                    await self._refresh_benchmark_scorecard()
                    self._last_benchmark_scorecard_refresh = now
                if self._benchmark_enabled:
                    now = time.time()
                    interval = max(1, self._benchmark_interval_hours) * 3600
                    if now - last_run >= interval:
                        await self._run_benchmark_league_once()
                        last_run = now
            except Exception as e:
                logger.error("Benchmark league loop error: %s", e)
            await asyncio.sleep(300)

    def _get_llm_router(self):
        if self._llm_router is None:
            from llm.router import LLMRouter

            self._llm_router = LLMRouter()
        return self._llm_router

    def _save_decisions(self, decisions: list[dict], analysis: dict, metrics: dict):
        """Save decisions to the shared decisions file for the admin panel."""
        try:
            # Load existing decisions
            existing = {"pending": [], "applied": []}
            if os.path.exists(DECISIONS_FILE):
                with open(DECISIONS_FILE, "r") as f:
                    existing = json.load(f)

            # Separate new decisions
            pending = [d for d in decisions if d.get("requires_approval", True)]
            applied = [d for d in decisions if not d.get("requires_approval", True)]

            # Merge: keep existing pending + applied, add new ones
            existing_pending_ids = {d.get("id") for d in existing.get("pending", [])}
            existing_pending_by_action = {d.get("action"): d for d in existing.get("pending", [])}
            existing_applied_ids = {d.get("id") for d in existing.get("applied", [])}

            for d in pending:
                if d.get("id") not in existing_pending_ids:
                    action = d.get("action")
                    if action and action in existing_pending_by_action:
                        # Dedup: refresh timestamp on existing decision so it does not go stale or pile up
                        existing_pending_by_action[action]["created_at"] = time.time()
                        existing_pending_by_action[action]["message"] = d.get("message", existing_pending_by_action[action].get("message", ""))
                        logger.debug(f"Refreshed existing pending decision: {action}")
                        continue
                    d["status"] = "pending"
                    d["created_at"] = time.time()
                    existing["pending"].append(d)

            for d in applied:
                if d.get("id") not in existing_applied_ids:
                    d["status"] = "applied"
                    d["applied_at"] = time.time()
                    existing["applied"].append(d)

            # Limit storage size
            existing["pending"] = existing["pending"][-50:]
            existing["applied"] = existing["applied"][-100:]

            with open(DECISIONS_FILE, "w") as f:
                json.dump(existing, f, indent=2)

            logger.info(f"Saved {len(pending)} pending + {len(applied)} auto decisions")
        except Exception as e:
            logger.error(f"Failed to save decisions: {e}")

    def _apply_non_bypassable_auto_actions(self, decisions: list[dict]) -> None:
        """Apply mandatory auto-governance actions immediately."""
        actions = {str(d.get("action") or "") for d in decisions if not d.get("requires_approval", True)}
        if "trigger_benchmark_and_rework_cycle" in actions:
            if not read_benchmark_admin_token():
                logger.warning(
                    "Auto-action: benchmark_now skipped (no AIFACTORY_BENCHMARK_ADMIN_TOKEN / _FILE); "
                    "SLO breach will not spawn unauthenticated benchmark traffic"
                )
            else:
                trigger_path = Path(TRIGGER_SIGNAL_FILE)
                trigger_path.parent.mkdir(parents=True, exist_ok=True)
                trigger_path.write_text(json.dumps({"timestamp": time.time(), "benchmark_now": True}), encoding="utf-8")
                logger.warning("Auto-action: benchmark_now signal emitted due to pipeline SLO breach")
        if "run_catalog_compliance_remediation" in actions:
            try:
                from web.backend.services.catalog_hardening import harden_catalog_products
                from web.backend.services.policy_audit import sync_sqlite_from_pipeline_json

                p = Path("/app/data/state/pipeline.json")
                state = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"products": {}, "task_queue": []}
                products = state.get("products") if isinstance(state.get("products"), dict) else {}
                task_queue = state.get("task_queue") if isinstance(state.get("task_queue"), list) else []
                harden_catalog_products(products=products, task_queue=task_queue, data_root="/app/data", now=time.time())
                state["products"] = products
                state["task_queue"] = task_queue
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                sync_sqlite_from_pipeline_json()
                logger.warning("Auto-action: catalog hardening remediation applied")
            except Exception as exc:
                logger.error("Auto-action remediation failed: %s", exc)

    async def run_full_analysis(self) -> dict:
        """
        Run a complete Director AI analysis cycle.

        Returns:
            Status dict with results
        """
        logger.info("=== Director AI: Starting analysis cycle ===")
        start_time = time.time()

        try:
            # 0. Owner Corporate Chat → classify & route pending messages (pipeline / feedback / directives)
            logger.info("Phase 0/6: Routing Owner corporate chat messages...")
            try:
                router = self._get_llm_router()
                from web.backend.services.owner_chat_routing import process_pending_owner_messages

                n_owner = await process_pending_owner_messages(router, limit=50)
                if n_owner:
                    logger.info("Owner chat routing: applied %s message(s)", n_owner)
            except Exception as exc:
                logger.warning("Owner chat routing skipped: %s", exc)

            # 1. Collect metrics
            logger.info("Phase 1/6: Collecting metrics...")
            metrics = self.metrics_collector.collect_all()
            logger.info(f"Metrics collected: pipeline={bool(metrics.get('pipeline_metrics'))}, "
                        f"agents={len(metrics.get('agent_metrics', {}))}, "
                        f"resources={bool(metrics.get('resource_metrics'))}")

            # 2. Analyze metrics
            logger.info("Phase 2/6: Analyzing metrics...")
            analysis = self.analyzer.analyze(metrics)
            logger.info(f"Analysis complete: health={analysis.get('overall_health')}, "
                        f"alerts={len(analysis.get('alerts', []))}")
            inspector_report = self.inspector.run_audit(window_hours=24)
            analysis["inspector_report"] = inspector_report

            # 3. Generate decisions
            logger.info("Phase 3/6: Generating decisions...")
            decisions = self.decision_engine.generate_decisions(analysis, metrics)
            logger.info(f"Generated {len(decisions)} decisions")

            # 4. Save decisions
            logger.info("Phase 4/6: Saving decisions...")
            self._save_decisions(decisions, analysis, metrics)
            self._apply_non_bypassable_auto_actions(decisions)

            # 5. Generate report
            logger.info("Phase 5/6: Generating report...")
            report_content = self.report_generator.generate_report(analysis, metrics, decisions)
            logger.info(f"Report generated ({len(report_content)} chars)")

            duration = time.time() - start_time
            logger.info(f"=== Director AI: Analysis cycle completed in {duration:.1f}s ===")

            return {
                "success": True,
                "duration_seconds": duration,
                "overall_health": analysis.get("overall_health"),
                "alerts_count": len(analysis.get("alerts", [])),
                "decisions_count": len(decisions),
                "report_size": len(report_content),
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.error(f"Director AI analysis failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timestamp": time.time(),
            }

    async def run_discovery_cycle(self) -> dict:
        """Periodic discovery refresh without forcing product creation."""
        try:
            from director.discovery_pipeline import DiscoveryPipeline

            pipeline_file = Path("/app/data/state/pipeline.json")
            state: dict = {"products": {}, "task_queue": []}
            if pipeline_file.exists():
                with open(pipeline_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            products = state.get("products") if isinstance(state.get("products"), dict) else {}
            existing_ideas = [str(p.get("idea") or "").strip() for p in products.values() if str(p.get("idea") or "").strip()]
            existing_categories = [str(p.get("category") or "").strip() for p in products.values() if str(p.get("category") or "").strip()]

            result = await DiscoveryPipeline(router=self._get_llm_router()).run(
                existing_ideas=existing_ideas,
                existing_categories=existing_categories,
            )
            top = (result.get("ranked_ideas") or [{}])[0]
            logger.info(
                "Discovery cycle complete: signals_total=%s top_score=%s",
                result.get("signals_total", 0),
                top.get("score_total"),
            )
            now = time.time()
            if self._discovery_auto_enqueue:
                elapsed_min = (now - self._last_discovery_enqueue_time) / 60.0
                if elapsed_min >= max(1, self._discovery_auto_enqueue_cooldown_min):
                    await self._auto_create_product()
                    self._last_discovery_enqueue_time = time.time()
                    logger.info("Discovery auto-enqueue completed (top-ranked idea sent to pipeline)")
            return {"success": True, "timestamp": time.time(), "result": result}
        except Exception as e:
            logger.error("Discovery cycle failed: %s", e, exc_info=True)
            return {"success": False, "timestamp": time.time(), "error": str(e)}

    async def _on_analysis_complete(self) -> dict:
        """Callback for DirectorScheduler - runs full analysis cycle."""
        return await self.run_full_analysis()

    async def _check_trigger_signal(self):
        """Monitor for on-demand trigger signal file from the web backend."""
        signal_path = Path(TRIGGER_SIGNAL_FILE)
        while self._running:
            if signal_path.exists():
                try:
                    # Read trigger data (optional: product idea to auto-create)
                    trigger_data = {}
                    try:
                        trigger_data = json.loads(signal_path.read_text())
                    except (json.JSONDecodeError, IOError):
                        pass

                    signal_path.unlink(missing_ok=True)
                    logger.info("On-demand Director analysis triggered via signal file")

                    # Run analysis
                    result = await self.run_full_analysis()

                    # If trigger had auto_pipeline flag, create product
                    if trigger_data.get("auto_pipeline") or self._auto_pipeline_enabled:
                        await self._auto_create_product()
                    if trigger_data.get("benchmark_now") is True:
                        await self._run_benchmark_league_once()

                except Exception as e:
                    logger.error(f"Signal handling error: {e}")
                    signal_path.unlink(missing_ok=True)

            await asyncio.sleep(2)  # Check every 2 seconds

    async def _auto_pipeline_loop(self):
        """Periodically create new products when auto-pipeline is enabled."""
        while self._running:
            try:
                self._load_config()  # Reload config to get latest settings

                if self._auto_pipeline_enabled:
                    now = time.time()
                    elapsed = (now - self._last_auto_product_time) / 60
                    if elapsed >= self._auto_pipeline_interval_minutes:
                        await self._auto_create_product()
                        self._last_auto_product_time = now
                else:
                    self._last_auto_product_time = 0

            except Exception as e:
                logger.error(f"Auto-pipeline loop error: {e}")

            await asyncio.sleep(30)  # Check every 30 seconds

    async def _auto_create_product(self):
        """Create a new product from discovery-ranked opportunities."""
        try:
            from director.discovery_pipeline import DiscoveryPipeline

            pipeline_file = Path("/app/data/state/pipeline.json")
            state: dict = {"products": {}, "task_queue": []}
            if pipeline_file.exists():
                with open(pipeline_file) as f:
                    state = json.load(f)

            if not self._autopipeline_backpressure_allows_create(state):
                return

            existing_ideas: list[str] = []
            existing_categories: list[str] = []
            for p in state.get("products", {}).values():
                idea = str(p.get("idea") or "").strip()
                if idea:
                    existing_ideas.append(idea)
                c = p.get("category")
                if c is not None and str(c).strip():
                    existing_categories.append(str(c).strip())

            router = self._get_llm_router()
            discovery = DiscoveryPipeline(router=router)
            discovery_result = await discovery.run(
                existing_ideas=existing_ideas,
                existing_categories=existing_categories,
            )
            ranked = discovery_result.get("ranked_ideas") if isinstance(discovery_result, dict) else None
            if not isinstance(ranked, list) or not ranked:
                raise RuntimeError("Discovery returned no ranked ideas")
            brief = ranked[0]

            import uuid

            product_id = f"prod-{uuid.uuid4().hex[:12]}"
            timestamp = time.time()
            idea = brief["idea"]

            admin_instructions = (
                "PRIMARY DELIVERABLE: **ship-ready browser software** (HTML/CSS/JS) that feels like a real product slice, not a thin template.\n"
                "- **Art direction / wow:** this build must feel **visually unmistakable** — not another dark-glass-cyan twin of generic AI landings. "
                "Architect must encode a bold, product-specific `ui_experience` (palette + typography + signature moment + **`svg_creative_brief`**); Developer must **ship that vision**, not swap in default tokens.\n"
                "- **SVG is unlimited:** generate rich inline or file-based SVG — hero backgrounds, patterns, masks, illustrated metaphors, faux-3D, charts — full vector toolkit (filters, defs, paths); use raster only sparingly if truly needed.\n"
                "- Differentiation: one clear audience + promise; visible copy and UI must match the idea and research below (no generic SaaS filler).\n"
                "- Scope: multi-file front-end (e.g. index.html, styles, modular JS), README with how to open/run locally, and a short manual test checklist or tiny self-check script.\n"
                "- Depth: implement **core user flows** from the PM spec (forms, tabs, filters, or a credible interactive demo) with empty/loading/error states where appropriate.\n"
                "- Polish: responsive layout, cohesive typography (e.g. Google Fonts), CSS variables, motion with `prefers-reduced-motion` respect.\n"
                "- Pass sandbox/demo gates: relative asset paths, no fake «deployed» placeholders, no broken console on load.\n\n"
                "Market research (autonomous pipeline — Director-generated phrase).\n\n"
                f"Research summary:\n{brief['research_summary']}\n\n"
                f"Market rationale:\n{brief['market_rationale']}\n\n"
                "QA: treat this as a product preview — structure, interactions, and copy quality matter as much as visuals."
            )

            product = {
                "id": product_id,
                "idea": idea,
                "category": brief["category"],
                "tags": brief["tags"],
                "delivery_profile": "full_software",
                "admin_instructions": admin_instructions,
                "state": "IDEA_RECEIVED",
                "created_at": timestamp,
                "updated_at": timestamp,
                "tasks": [],
                "spec": None,
                "architecture": None,
                "code": None,
                "marketing": None,
                "pricing": None,
                "evolution_history": [],
                "market_research": {
                    "research_summary": brief["research_summary"],
                    "market_rationale": brief["market_rationale"],
                },
                "discovery": {
                    "score_total": brief.get("score_total"),
                    "score_confidence": brief.get("score_confidence"),
                    "validation_notes": brief.get("validation_notes", []),
                    "signals_collected_now": discovery_result.get("signals_collected_now", 0),
                    "signals_total": discovery_result.get("signals_total", 0),
                    "anomaly": discovery_result.get("anomaly"),
                },
            }

            state.setdefault("products", {})[product_id] = product
            pipeline_file.parent.mkdir(parents=True, exist_ok=True)
            with open(pipeline_file, "w") as f:
                json.dump(state, f, indent=2)

            # Keep SQLite storefront/API in sync when JSON is source of truth
            try:
                if os.environ.get("USE_SQLITE", "").strip().lower() in ("1", "true", "yes"):
                    from orchestrator.migrate import migrate

                    migrate(
                        json_path=str(pipeline_file),
                        db_path=os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db"),
                    )
            except Exception as sync_exc:
                logger.warning("SQLite migrate after auto product failed: %s", sync_exc)

            logger.info("Auto-created product %s from market research: %s...", product_id, idea[:80])
            logger.info("Pipeline worker will pick this up and start processing")

            DirectorScheduler._log(
                "INFO",
                f"Auto-created product {product_id}",
                action="auto_create_product",
                product_id=product_id,
                idea=idea[:200],
            )

        except Exception as e:
            logger.error(f"Failed to auto-create product (market research): {e}", exc_info=True)

    async def run(self):
        """Main worker loop."""
        self._running = True
        logger.info("=== Director AI Worker started ===")

        # Load config
        self._load_config()

        # Create scheduler with the analysis callback (interval from config.yaml director.analysis_interval_hours)
        interval_hours = self._analysis_interval_hours
        self._scheduler = DirectorScheduler(
            analysis_interval_hours=interval_hours,
            on_analysis_complete=self._on_analysis_complete,
            discovery_interval_hours=max(1, self._discovery_interval_hours),
            on_discovery_complete=self.run_discovery_cycle,
        )

        # Start the scheduler
        await self._scheduler.start()
        logger.info(f"Director scheduler started (interval: {interval_hours}h)")

        # Start trigger signal monitor
        self._signal_check_task = asyncio.create_task(self._check_trigger_signal())
        logger.info("Trigger signal monitor started")

        # Start auto-pipeline loop
        self._auto_pipeline_task = asyncio.create_task(self._auto_pipeline_loop())
        logger.info(f"Auto-pipeline loop started (enabled={self._auto_pipeline_enabled}, "
                    f"interval={self._auto_pipeline_interval_minutes}min)")

        # Start benchmark league loop
        self._benchmark_league_task = asyncio.create_task(self._benchmark_league_loop())
        logger.info(
            "Benchmark league loop started (enabled=%s interval=%sh count=%s)",
            self._benchmark_enabled,
            self._benchmark_interval_hours,
            self._benchmark_count,
        )

        # Run an initial analysis upon startup
        logger.info("Running initial Director analysis on startup...")
        result = await self.run_full_analysis()
        if result.get("success"):
            logger.info(f"Initial analysis complete: health={result.get('overall_health')}")
        else:
            logger.warning(f"Initial analysis had issues: {result.get('error')}")

        # Keep running - scheduler and monitors are doing work
        try:
            while self._running:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

        logger.info("Director AI Worker shutting down")

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        if self._scheduler:
            await self._scheduler.stop()
        if self._signal_check_task:
            self._signal_check_task.cancel()
            try:
                await self._signal_check_task
            except asyncio.CancelledError:
                pass
        if self._auto_pipeline_task:
            self._auto_pipeline_task.cancel()
            try:
                await self._auto_pipeline_task
            except asyncio.CancelledError:
                pass
        if self._benchmark_league_task:
            self._benchmark_league_task.cancel()
            try:
                await self._benchmark_league_task
            except asyncio.CancelledError:
                pass
        logger.info("Director AI Worker stopped")


async def main():
    """Entry point for the Director AI worker."""
    worker = DirectorWorker()
    try:
        await worker.run()
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        logger.info("Shutting down Director AI worker...")
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
