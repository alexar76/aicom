"""Public ecosystem status endpoint tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_build_public_ecosystem_status_merges_hub_summary():
    from web.backend.services.public_ecosystem_status import build_public_ecosystem_status

    hub_payload = {
        "summary": {
            "total_invocations": 100,
            "successful_invocations": 99,
            "success_rate": 0.99,
            "avg_latency_ms": 40.0,
            "open_channels": 2,
            "settled_volume_usd": 12.5,
            "invocations_24h": 50,
            "invocations_1h": 10,
            "failed_invocations_24h": 1,
            "rps_1h": 0.0028,
            "p50_latency_ms_24h": 35.0,
            "p95_latency_ms_24h": 80.0,
        },
        "events": [],
    }

    async def fake_fetch(client, url):
        if url.endswith("/health"):
            return {"status": "ok", "uptime_seconds": 3600}, None
        if "stats/live" in url:
            return hub_payload, None
        return None, "404"

    with patch(
        "web.backend.services.public_ecosystem_status._fetch_json",
        new=AsyncMock(side_effect=fake_fetch),
    ):
        with patch(
            "web.backend.services.public_ecosystem_status.factory_uptime_seconds",
            return_value=7200,
        ):
            out = await build_public_ecosystem_status()

    assert out["services"]["factory"]["uptime_seconds"] == 7200
    assert out["hub"]["invocations_24h"] == 50
    assert out["slo"]["rps_1h"] == 0.0028
    assert out["slo"]["success_rate_24h"] == pytest.approx(0.98)


def test_enrich_hub_summary_from_events():
    from web.backend.services.public_ecosystem_status import enrich_hub_summary
    import time

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    events = [
        {"timestamp": now, "latency_ms": 30, "success": 1},
        {"timestamp": now, "latency_ms": 50, "success": 0},
    ]
    out = enrich_hub_summary({"total_invocations": 2}, events)
    assert out["invocations_24h"] == 2
    assert out["failed_invocations_24h"] == 1
    assert out["p50_latency_ms_24h"] == 30.0


def test_production_incidents_file_valid():
    path = ROOT / "docs" / "production-incidents.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw.get("incidents"), list)
