"""
Director Scheduler
=================
Schedules periodic Director AI analysis runs.
Runs every N hours (configurable) or on-demand.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class DirectorScheduler:
    """
    Schedules and manages Director AI analysis cycles.
    
    Features:
    - Periodic analysis (configurable interval)
    - On-demand analysis trigger
    - Event-based analysis (on significant changes)
    - Status tracking
    """

    def __init__(
        self,
        analysis_interval_hours: int = 4,
        on_analysis_complete: Optional[Callable] = None,
        discovery_interval_hours: int = 6,
        on_discovery_complete: Optional[Callable] = None,
    ):
        self.analysis_interval_hours = analysis_interval_hours
        self.interval_seconds = analysis_interval_hours * 3600
        self.on_analysis_complete = on_analysis_complete
        self.discovery_interval_hours = discovery_interval_hours
        self.discovery_interval_seconds = discovery_interval_hours * 3600
        self.on_discovery_complete = on_discovery_complete
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._last_analysis_time: float = 0
        self._last_discovery_time: float = 0
        self._analysis_count: int = 0
        self._discovery_count: int = 0
        self._last_status: Optional[dict] = None

    @staticmethod
    def _log(level: str, message: str, **kwargs):
        """Log structured JSONL entry for Director AI operations."""
        log_data = {
            "agent": "director",
            "component": "scheduler",
            "level": level,
            "message": message,
            "time": time.time(),
            **kwargs,
        }
        from core.paths import logs_dir

        log_path = logs_dir() / "director.jsonl"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(log_data) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write director scheduler log: {e}")

    async def start(self):
        """Start the scheduled analysis loop."""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self._log("INFO", f"Director scheduler started (interval: {self.analysis_interval_hours}h)")
        logger.info(f"Director scheduler started (interval: {self.analysis_interval_hours}h)")

    async def stop(self):
        """Stop the scheduled analysis loop."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        self._log("INFO", "Director scheduler stopped")
        logger.info("Director scheduler stopped")

    async def run_analysis_now(self) -> dict:
        """
        Trigger an immediate analysis cycle.
        
        Returns:
            Analysis status
        """
        self._log("INFO", "Running on-demand Director analysis", action="run_analysis")
        logger.info("Running on-demand Director analysis")
        
        if self.on_analysis_complete:
            try:
                if asyncio.iscoroutinefunction(self.on_analysis_complete):
                    result = await self.on_analysis_complete()
                else:
                    result = self.on_analysis_complete()
                
                self._last_analysis_time = time.time()
                self._analysis_count += 1
                self._last_status = {
                    "success": True,
                    "timestamp": self._last_analysis_time,
                    "analysis_count": self._analysis_count,
                }
                self._log("INFO", f"Analysis cycle #{self._analysis_count} completed successfully",
                          analysis_count=self._analysis_count,
                          duration=round(time.time() - self._last_analysis_time, 2))
                return self._last_status
            except Exception as e:
                logger.error(f"On-demand analysis failed: {e}")
                self._log("ERROR", f"On-demand analysis failed: {e}", error=str(e))
                return {"success": False, "error": str(e)}
        
        self._log("WARNING", "No analysis callback configured", action="run_analysis")
        return {"success": False, "error": "No analysis callback configured"}

    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                now = time.time()
                time_since_last = now - self._last_analysis_time
                time_since_discovery = now - self._last_discovery_time

                if time_since_last >= self.interval_seconds:
                    self._log("INFO", f"Running scheduled analysis (interval: {self.analysis_interval_hours}h)",
                              action="scheduled_run")
                    logger.info(f"Running scheduled Director analysis (interval: {self.analysis_interval_hours}h)")
                    await self.run_analysis_now()
                if self.on_discovery_complete and time_since_discovery >= self.discovery_interval_seconds:
                    self._log(
                        "INFO",
                        f"Running scheduled discovery (interval: {self.discovery_interval_hours}h)",
                        action="scheduled_discovery_run",
                    )
                    try:
                        if asyncio.iscoroutinefunction(self.on_discovery_complete):
                            await self.on_discovery_complete()
                        else:
                            self.on_discovery_complete()
                        self._last_discovery_time = time.time()
                        self._discovery_count += 1
                    except Exception as e:
                        self._log("ERROR", f"Scheduled discovery failed: {e}", error=str(e))
                        logger.error(f"Scheduled discovery failed: {e}")

                next_analysis_wait = max(0.0, self.interval_seconds - (time.time() - self._last_analysis_time))
                next_discovery_wait = (
                    max(0.0, self.discovery_interval_seconds - (time.time() - self._last_discovery_time))
                    if self.on_discovery_complete
                    else 60.0
                )
                await asyncio.sleep(min(next_analysis_wait, next_discovery_wait, 60.0))

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log("ERROR", f"Director scheduler loop error: {e}", error=str(e))
                logger.error(f"Director scheduler error: {e}")
                await asyncio.sleep(60)

    def set_interval(self, hours: int):
        """Change the analysis interval."""
        self.analysis_interval_hours = hours
        self.interval_seconds = hours * 3600
        self._log("INFO", f"Director analysis interval changed to {hours}h")
        logger.info(f"Director analysis interval changed to {hours}h")

    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self._running,
            "interval_hours": self.analysis_interval_hours,
            "last_analysis_time": self._last_analysis_time,
            "discovery_interval_hours": self.discovery_interval_hours,
            "last_discovery_time": self._last_discovery_time,
            "time_since_last_analysis": time.time() - self._last_analysis_time if self._last_analysis_time else 0,
            "analysis_count": self._analysis_count,
            "discovery_count": self._discovery_count,
            "last_status": self._last_analysis_time > 0,
        }
