"""
AUTONOMOUS AI-FACTORY v2.1
==========================
Main entry point for the AI-Factory platform.
Starts the Orchestrator, Web Server, and Director Scheduler.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from core.paths import config_path, data_root, git_repos_dir, logs_dir, pipeline_db_path, pipeline_json_path
from core.config_merge import load_merged_config
from web.backend.api.metrics import PrometheusMetrics
from core.logging_utils import log_suppressed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(logs_dir() / "platform.log")),
    ],
)

logger = logging.getLogger("ai-factory")


class AIFactory:
    """
    Main application class for the AI-Factory platform.
    
    Manages the lifecycle of all components:
    - Orchestrator (pipeline state machine + agents)
    - LLM Router (provider abstraction)
    - Director AI (scheduler + analysis)
    - Web Server (FastAPI backend)
    """

    def __init__(self, config_path_value: str | None = None):
        self.config_path = config_path_value or str(config_path())
        self.config: dict = {}
        self._running = False
        self._components: dict[str, any] = {}
        self._load_config()

    def _load_config(self):
        """Load configuration (fragments + primary overlay)."""
        try:
            self.config = load_merged_config(self.config_path)
            logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = {}

    async def initialize(self):
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info("AUTONOMOUS AI-FACTORY v2.1")
        logger.info("Initializing components...")
        logger.info("=" * 60)

        # Ensure data directories exist
        self._ensure_directories()

        # Initialize LLM Router
        from llm import LLMRouter
        self._components["llm_router"] = LLMRouter(
            config_path=str(data_root() / "config" / "model_providers.yaml")
        )
        await self._components["llm_router"].start_health_checks()
        logger.info("✓ LLM Router initialized")

        # Initialize Pipeline State Machine
        # USE_SQLITE env var controls backend: "true" → SQLite, anything else → JSON
        use_sqlite = os.environ.get("USE_SQLITE", "true").lower() == "true"
        db_path = str(pipeline_db_path())

        from orchestrator import PipelineStateMachine
        self._components["state_machine"] = PipelineStateMachine(
            state_file=str(pipeline_json_path()),
            use_sqlite=use_sqlite,
            db_path=db_path,
        )

        backend_name = "SQLite" if use_sqlite else "JSON"
        sm_path = db_path if use_sqlite else str(pipeline_json_path())
        logger.info(f"✓ Pipeline State Machine initialized (backend: {backend_name}, path: {sm_path})")

        # Initialize Timeout Manager
        from orchestrator import TimeoutManager
        self._components["timeout_manager"] = TimeoutManager()
        await self._components["timeout_manager"].start_monitoring()
        logger.info("✓ Timeout Manager initialized")

        # Initialize Escalation Handler
        from orchestrator import EscalationHandler
        self._components["escalation"] = EscalationHandler(
            self._components["state_machine"]
        )
        logger.info("✓ Escalation Handler initialized")

        # Initialize Director Integration
        from orchestrator import DirectorIntegration
        self._components["director_integration"] = DirectorIntegration(
            self._components["state_machine"],
            self._components["timeout_manager"],
        )
        logger.info("✓ Director Integration initialized")

        # Initialize Agents
        self._init_agents()
        logger.info("✓ All Agents initialized")

        # Initialize Director AI
        self._init_director()
        logger.info("✓ Director AI initialized")

        logger.info("=" * 60)
        logger.info("All components initialized successfully!")
        logger.info("=" * 60)

    def _ensure_directories(self):
        """Ensure all required data directories exist."""
        root = data_root()
        dirs = [
            str(root / "specs"), str(root / "arch"), str(root / "code"),
            str(root / "bugs"), str(root / "state"), str(root / "logs"),
            str(root / "telemetry"), str(root / "config"), str(root / "reports" / "director"),
            str(root / "secrets"), str(root / "feedback"), str(git_repos_dir()),
        ]
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)

    def _init_agents(self):
        """Initialize all agent instances."""
        llm_router = self._components["llm_router"]
        
        from agents import (
            PMAgent, ArchitectAgent, DeveloperAgent, QAAgent,
            DevOpsAgent, MarketingAgent, SalesAgent, EvolutionAnalystAgent,
            MethodologyAgent,
        )
        
        self._components["agents"] = {
            "pm": PMAgent(llm_router),
            "architect": ArchitectAgent(llm_router),
            "methodologist": MethodologyAgent(llm_router),
            "developer": DeveloperAgent(llm_router),
            "qa": QAAgent(llm_router),
            "devops": DevOpsAgent(llm_router),
            "marketing": MarketingAgent(llm_router),
            "sales": SalesAgent(llm_router),
            "evolution_analyst": EvolutionAnalystAgent(llm_router),
        }

    def _init_director(self):
        """Initialize Director AI components."""
        from director import (
            MetricsCollector, DirectorAnalyzer, DecisionEngine,
            ReportGenerator, DirectorScheduler, InspectorAgent,
        )
        
        self._components["metrics_collector"] = MetricsCollector()
        self._components["analyzer"] = DirectorAnalyzer()
        self._components["decision_engine"] = DecisionEngine(
            auto_actions_enabled=self.config.get("director", {}).get("auto_actions_enabled", True),
            allowed_actions=self.config.get("director", {}).get("allowed_auto_actions", []),
        )
        self._components["report_generator"] = ReportGenerator()
        self._components["inspector"] = InspectorAgent()
        
        # Create scheduler with callback
        async def on_analysis():
            await self._run_director_analysis()
            # Update pipeline state gauges after each analysis cycle
            self._update_pipeline_metrics()
        
        self._components["scheduler"] = DirectorScheduler(
            analysis_interval_hours=self.config.get("director", {}).get("analysis_interval_hours", 4),
            on_analysis_complete=on_analysis,
        )

    async def _run_director_analysis(self):
        """Run a complete Director AI analysis cycle."""
        logger.info("Running Director AI analysis...")
        
        try:
            # Collect metrics
            metrics = self._components["metrics_collector"].collect_all()
            
            # Analyze
            analysis_timeout = float(
                os.environ.get(
                    "AIFACTORY_DIRECTOR_ANALYSIS_TIMEOUT_SEC",
                    self.config.get("director", {}).get("analysis_timeout_sec", "120"),
                )
            )
            analysis = await asyncio.wait_for(
                asyncio.to_thread(self._components["analyzer"].analyze, metrics),
                timeout=analysis_timeout,
            )
            # Independent inspection audit (quality/profit/crypto)
            inspector_timeout = float(
                os.environ.get(
                    "AIFACTORY_DIRECTOR_INSPECTOR_TIMEOUT_SEC",
                    self.config.get("director", {}).get("inspector_timeout_sec", "120"),
                )
            )
            inspector_report = await asyncio.wait_for(
                asyncio.to_thread(self._components["inspector"].run_audit, 24),
                timeout=inspector_timeout,
            )
            analysis["inspector_report"] = inspector_report
            
            # Generate decisions
            decisions = self._components["decision_engine"].generate_decisions(analysis, metrics)
            
            # Apply auto-decisions
            for decision in decisions:
                if not decision.get("requires_approval"):
                    self._components["director_integration"].apply_decision(decision)
            
            # Generate report
            report = self._components["report_generator"].generate_report(
                analysis,
                metrics,
                decisions,
                inspector_report=inspector_report,
            )
            
            logger.info(f"Director AI analysis complete: {len(decisions)} decisions generated")
            return {"success": True, "decisions": len(decisions)}
            
        except asyncio.TimeoutError:
            logger.error("Director AI analysis failed: timeout")
            return {"success": False, "error": "director_analysis_timeout"}
        except Exception as e:
            logger.error(f"Director AI analysis failed: {e}")
            return {"success": False, "error": str(e)}

    async def _update_pipeline_metrics(self):
        """Update Prometheus gauges with current pipeline state."""
        try:
            state_machine = self._components.get("state_machine")
            if state_machine:
                products = state_machine.get_all_products()
                PrometheusMetrics.update_pipeline_gauges(products)
                logger.debug("Pipeline metrics updated")
        except Exception as e:
            logger.warning(f"Failed to update pipeline metrics: {e}")

    async def _periodic_metrics_update(self, interval_sec: int = 30):
        """Periodically update Prometheus gauges."""
        while self._running:
            self._update_pipeline_metrics()
            await asyncio.sleep(interval_sec)

    async def start(self):
        """Start all components."""
        if self._running:
            logger.warning("AI-Factory is already running")
            return

        self._running = True
        await self.initialize()

        # Start Director scheduler
        await self._components["scheduler"].start()
        logger.info("Director scheduler started")

        # Start periodic metrics update (every 30 seconds)
        asyncio.create_task(self._periodic_metrics_update(30))
        logger.info("Periodic metrics update started (every 30s)")

        logger.info("AI-Factory is now running!")
        logger.info("Web backend: http://localhost:8080")
        logger.info("Admin panel: http://localhost:8080/admin")
        logger.info("Storefront: http://localhost:3000")

        # Keep running
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (main.py)", exc_info=_suppressed_exc)
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Gracefully shut down all components."""
        logger.info("Shutting down AI-Factory...")
        self._running = False

        # Stop Director scheduler
        if "scheduler" in self._components:
            await self._components["scheduler"].stop()

        # Stop timeout monitoring
        if "timeout_manager" in self._components:
            await self._components["timeout_manager"].stop_monitoring()

        # Stop health checks
        if "llm_router" in self._components:
            await self._components["llm_router"].close()

        logger.info("AI-Factory shutdown complete")

    def get_status(self) -> dict:
        """Get platform status."""
        return {
            "running": self._running,
            "components": list(self._components.keys()),
            "config": {
                "director_interval_hours": self.config.get("director", {}).get("analysis_interval_hours", 4),
                "auto_actions": self.config.get("director", {}).get("auto_actions_enabled", False),
            },
        }


async def main():
    """Main entry point."""
    factory = AIFactory()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(factory.shutdown()),
            )
        except NotImplementedError as _suppressed_exc:
            # Windows doesn't support add_signal_handler
            log_suppressed(logger, "non-fatal (main.py)", exc_info=_suppressed_exc)

    try:
        await factory.start()
    except KeyboardInterrupt:
        await factory.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
