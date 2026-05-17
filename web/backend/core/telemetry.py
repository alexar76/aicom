"""
Telemetry Collector
===================
Collects and stores telemetry data from product sandboxes.
Used by Evolution Engine for auto-improvement analysis.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from core.paths import data_root as factory_data_root
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """
    Collects telemetry from product sandboxes.
    
    Data points:
    - User interactions (clicks, navigation)
    - Performance metrics (load time, response time)
    - Error events
    - Feature usage
    - Session duration
    """

    def __init__(self, data_root: str | None = None):
        base = Path(data_root) if data_root else factory_data_root()
        self.data_root = base / "telemetry"
        self.data_root.mkdir(parents=True, exist_ok=True)

    def record_event(
        self,
        product_id: str,
        event_type: str,
        data: dict,
        session_id: Optional[str] = None,
    ):
        """Record a telemetry event."""
        event = {
            "product_id": product_id,
            "event_type": event_type,
            "data": data,
            "session_id": session_id,
            "timestamp": time.time(),
        }

        # Save to product telemetry file
        product_dir = self.data_root / product_id
        product_dir.mkdir(parents=True, exist_ok=True)

        date_str = time.strftime("%Y-%m-%d")
        log_file = product_dir / f"telemetry_{date_str}.jsonl"

        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def get_product_telemetry(
        self,
        product_id: str,
        limit: int = 1000,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        """Get telemetry data for a product."""
        product_dir = self.data_root / product_id
        if not product_dir.exists():
            return []

        events = []
        for log_file in sorted(product_dir.glob("*.jsonl"), reverse=True):
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            event = json.loads(line)
                            if event_type and event.get("event_type") != event_type:
                                continue
                            events.append(event)
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/core/telemetry.py)", exc_info=_suppressed_exc)
            if len(events) >= limit:
                break

        return events[-limit:]

    def get_product_summary(self, product_id: str) -> dict:
        """Get a summary of telemetry for a product."""
        events = self.get_product_telemetry(product_id, limit=5000)

        if not events:
            return {
                "product_id": product_id,
                "total_events": 0,
                "unique_sessions": 0,
                "event_types": {},
                "first_event": None,
                "last_event": None,
            }

        event_types = {}
        sessions = set()

        for event in events:
            etype = event.get("event_type", "unknown")
            event_types[etype] = event_types.get(etype, 0) + 1
            if event.get("session_id"):
                sessions.add(event["session_id"])

        return {
            "product_id": product_id,
            "total_events": len(events),
            "unique_sessions": len(sessions),
            "event_types": event_types,
            "first_event": events[0].get("timestamp"),
            "last_event": events[-1].get("timestamp"),
        }

    def get_all_products_summary(self) -> dict[str, dict]:
        """Get telemetry summaries for all products."""
        summaries = {}
        for product_dir in self.data_root.iterdir():
            if product_dir.is_dir():
                summaries[product_dir.name] = self.get_product_summary(product_dir.name)
        return summaries
