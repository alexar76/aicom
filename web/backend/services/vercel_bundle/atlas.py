"""ATLAS clients: a wide enough bounding box, the core layers, advisory invokes run in
parallel, and a rule engine that reads ATLAS situations.
"""

from __future__ import annotations

import re
from pathlib import Path


def widen_atlas_client_bbox(api_dir: Path) -> list[str]:
    """±0.1°/±1° around many cities has zero LIVE pins; ±5° is what ATLAS briefs need.

    Measured: Berlin at ±1 refuses; the same point at ±5 returns ok=True with score/summary.
    Only rewrites the vendored Vercel copy.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("atlas_client.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "aicom-factory-atlas-bbox" in text and "lat + 5.0" in text:
            continue
        new = text
        # Normalize any prior factory widen (±1) or product default (±0.1) to ±5.
        for old in (
            "lat + 0.1", "lat - 0.1", "lon + 0.1", "lon - 0.1",
            "lat + 1.0", "lat - 1.0", "lon + 1.0", "lon - 1.0",
        ):
            sign = "+" if "+" in old else "-"
            axis = "lat" if old.startswith("lat") else "lon"
            new = new.replace(old, f"{axis} {sign} 5.0")
        # nearest.read max_km often 100 — too tight when pins are sparse
        new = new.replace('"max_km": 100', '"max_km": 500')
        new = new.replace("'max_km': 100", "'max_km': 500")
        # ±5° briefs need more than the product's 10s default.
        new = new.replace("timeout=10.0", "timeout=40.0")
        new = new.replace("timeout=10", "timeout=40.0")
        if new == text and "aicom-factory-atlas-bbox" in text:
            continue
        if new == text:
            continue
        if "aicom-factory-atlas-bbox" not in new:
            new = "# aicom-factory-atlas-bbox\n" + new
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_ATLAS_CORE_LAYERS_MARKER = "aicom-factory-atlas-core-layers"
# Product often asked only flood/effis/… — Moscow's LIVE pin is weather (om-wx-moscow).
_ATLAS_SITUATION_LAYERS = (
    '["weather", "air", "fire", "flood", "effis", "lightning", '
    '"volcano", "alerts", "events", "tsunami"]'
)
_ATLAS_NEAREST_LAYERS = '["weather", "air", "fire", "flood", "effis"]'


def ensure_atlas_client_core_layers(api_dir: Path) -> list[str]:
    """Ensure situation/nearest invokes include weather+fire (not only hazard niches).

    Sentinel shipped with ``layers: [flood, effis, …]`` and no ``weather``. ATLAS then
    correctly refused Moscow with ``no LIVE readings…for requested layers`` even though
    ``om-wx-moscow`` is LIVE 5 km away — the pin was filtered out by the layer list.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("atlas_client.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _ATLAS_CORE_LAYERS_MARKER in text and '"weather"' in text:
            continue
        new = text
        # Replace common product layer lists (quoted JSON-ish in Python source).
        for old in (
            '["flood", "effis", "lightning", "volcano", "alerts", "events", "tsunami"]',
            "['flood', 'effis', 'lightning', 'volcano', 'alerts', 'events', 'tsunami']",
            '["flood", "effis"]',
            "['flood', 'effis']",
        ):
            if "flood" in old and "lightning" in old:
                new = new.replace(old, _ATLAS_SITUATION_LAYERS)
            else:
                new = new.replace(old, _ATLAS_NEAREST_LAYERS)
        if new == text:
            continue
        if _ATLAS_CORE_LAYERS_MARKER not in new:
            new = f"# {_ATLAS_CORE_LAYERS_MARKER}\n" + new
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_RUN_IN_EXECUTOR_SITUATION_RE = re.compile(
    r"situation\s*=\s*await\s+asyncio\.wait_for\(\s*"
    r"loop\.run_in_executor\(\s*pool\s*,\s*atlas\.invoke_situation_brief\s*,\s*"
    r"rounded_lat\s*,\s*rounded_lon\s*\)\s*,\s*timeout\s*=\s*[\d.]+\s*\)",
    re.M,
)


def rewrite_async_atlas_run_in_executor(api_dir: Path) -> list[str]:
    """``run_in_executor`` cannot take an ``async def`` — Vercel then answers UNKNOWN.

    Measured on Sentinel after a developer round: ``atlas.invoke_situation_brief`` is
    async, the handler passed it to ``loop.run_in_executor``, and every advisory
    returned ``coroutines cannot be used with run_in_executor()``.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    repl = "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)"
    for path in root.rglob("advisory.py"):
        if "router" not in path.as_posix() and path.parent.name != "routers":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new, n = _RUN_IN_EXECUTOR_SITUATION_RE.subn(repl, text)
        if n == 0:
            continue
        path.write_text(new, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


def parallelize_atlas_advisory_invokes(api_dir: Path, *, escrow_paid: bool = False) -> list[str]:
    """Tune advisory ATLAS fan-out for the publish target.

    Trial / agent-key paths: three sequential cold-start invokes blow the live-gate
    timeout, so we gather them.

    Escrow-paid channels: gather races the on-chain debit nonce (one auth per nonce).
    Collapse to a single ``situation.brief`` — it already carries weather/fire/flood
    layers the rule engine needs.
    """
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    seq = (
        "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)\n"
        "        fire_weather = await atlas.invoke_fire_weather(rounded_lat, rounded_lon)\n"
        "        nearest = await atlas.invoke_nearest(rounded_lat, rounded_lon)"
    )
    gathered = (
        "situation, fire_weather, nearest = await asyncio.gather(\n"
        "            atlas.invoke_situation_brief(rounded_lat, rounded_lon),\n"
        "            atlas.invoke_fire_weather(rounded_lat, rounded_lon),\n"
        "            atlas.invoke_nearest(rounded_lat, rounded_lon),\n"
        "        )"
    )
    single = (
        "situation = await atlas.invoke_situation_brief(rounded_lat, rounded_lon)\n"
        "        fire_weather = situation\n"
        "        nearest = situation"
    )
    for path in root.rglob("advisory.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if escrow_paid:
            if "aicom-factory-atlas-escrow-single" in text:
                continue
            changed = False
            if gathered in text:
                text = text.replace(gathered, single)
                changed = True
            elif seq in text:
                text = text.replace(seq, single)
                changed = True
            if not changed:
                continue
            text = text.replace("# aicom-factory-atlas-gather\n", "")
            text = "# aicom-factory-atlas-escrow-single\n" + text
            path.write_text(text, encoding="utf-8")
            notes.append(path.relative_to(root).as_posix())
            continue
        if "aicom-factory-atlas-gather" in text or "aicom-factory-atlas-escrow-single" in text:
            continue
        if seq not in text:
            continue
        text = text.replace(seq, gathered)
        if "import asyncio" not in text:
            text = "import asyncio\n" + text
        text = "# aicom-factory-atlas-gather\n" + text
        path.write_text(text, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes


_ATLAS_RULE_ENGINE = '''# aicom-factory-atlas-rule-engine-v4 — vendored only (data/code untouched).
"""Map ATLAS ai-market/v2 capability payloads into Sentinel hazard levels."""

from __future__ import annotations

from typing import Any


def _score_level(score: int | float | None) -> str:
    if score is None:
        return "UNKNOWN"
    s = float(score)
    if s >= 80:
        return "EMERGENCY"
    if s >= 60:
        return "WARNING"
    if s >= 40:
        return "WATCH"
    return "CALM"


def _layer_live(coverage: dict[str, Any] | None, *names: str) -> int:
    if not isinstance(coverage, dict):
        return 0
    total = 0
    for name in names:
        block = coverage.get(name)
        if isinstance(block, dict):
            total += int(block.get("live") or block.get("with_reading") or block.get("pins") or 0)
    return total


class RuleEngine:
    """Deterministic rule engine for ATLAS situation / fire.weather / nearest payloads."""

    def evaluate(
        self,
        situation: dict[str, Any],
        fire_weather: dict[str, Any],
        nearest: dict[str, Any],
    ) -> dict[str, Any]:
        hazards: list[dict[str, Any]] = []
        thresholds: list[dict[str, Any]] = []

        weather_level, weather_measurement, weather_thresholds = self._evaluate_weather(
            fire_weather, situation
        )
        hazards.append(
            {
                "type": "WEATHER",
                "level": weather_level,
                "measurement": weather_measurement or "",
                "distance_km": 0.0,
                "receipt": (fire_weather or {}).get("receipt_digest")
                or ((fire_weather or {}).get("receipt") or {}).get("digest"),
                "timestamp": "",
                "is_cached": False,
                "sim": bool((fire_weather or {}).get("sim")),
            }
        )
        thresholds.extend(weather_thresholds)

        fire_level, fire_measurement, fire_thresholds = self._evaluate_fire(
            situation, fire_weather, nearest
        )
        hazards.append(
            {
                "type": "WILDFIRE",
                "level": fire_level,
                "measurement": fire_measurement or "",
                "distance_km": 0.0,
                "receipt": (fire_weather or {}).get("receipt_digest")
                or ((situation or {}).get("receipt") or {}).get("digest"),
                "timestamp": "",
                "is_cached": False,
                "sim": bool((fire_weather or {}).get("sim") or (situation or {}).get("sim")),
            }
        )
        thresholds.extend(fire_thresholds)

        flood_level, flood_measurement, flood_thresholds = self._evaluate_flood(situation, nearest)
        hazards.append(
            {
                "type": "FLOOD",
                "level": flood_level,
                "measurement": flood_measurement or "",
                "distance_km": 0.0,
                "receipt": ((situation or {}).get("receipt") or {}).get("digest"),
                "timestamp": "",
                "is_cached": False,
                "sim": bool((situation or {}).get("sim")),
            }
        )
        thresholds.extend(flood_thresholds)

        overall_level, overall_reason = self._overall(hazards, situation, fire_weather)
        return {
            "overall": {
                "level": overall_level,
                "reason": overall_reason,
                "receipt": ((situation or {}).get("receipt") or {}).get("digest"),
            },
            "hazards": hazards,
            "thresholds": thresholds,
        }

    def _mesh_payload(self, data: dict[str, Any] | None) -> dict[str, Any]:
        """Hub/participant often nests the real body under result/output/data without ok=True."""
        if not isinstance(data, dict):
            return {}
        if (
            data.get("ok") is True
            or data.get("score") is not None
            or data.get("wind_speed_kmh") is not None
            or isinstance(data.get("weather"), dict)
            or data.get("refuse_reason")
            or data.get("error")
        ):
            return data
        for key in ("result", "output", "data", "body", "payload"):
            nested = data.get(key)
            if isinstance(nested, dict):
                return nested
        return data

    def _refuse_reason(self, *payloads: dict[str, Any] | None) -> str:
        for raw in payloads:
            p = self._mesh_payload(raw if isinstance(raw, dict) else None)
            if not p:
                continue
            if p.get("refuse_reason"):
                return str(p.get("refuse_reason"))[:220]
            # Prefer nested Hub bodies over bare "Status 402" from the participant wrapper.
            detail = p.get("detail")
            if isinstance(detail, dict):
                nested = (
                    detail.get("detail")
                    or detail.get("error")
                    or detail.get("message")
                    or detail.get("refuse_reason")
                )
                if nested:
                    return str(nested)[:220]
            elif detail:
                return str(detail)[:220]
            for key in ("error", "message"):
                val = p.get(key)
                if not val:
                    continue
                if isinstance(val, dict):
                    nested = val.get("detail") or val.get("error") or val.get("message")
                    if nested:
                        return str(nested)[:220]
                    return str(val)[:220]
                text = str(val)
                if text.lower().startswith("status ") and isinstance(detail, dict):
                    continue
                return text[:220]
        return "mesh response unavailable"

    def _evaluate_weather(
        self, fire_weather: dict[str, Any] | None, situation: dict[str, Any] | None
    ) -> tuple:
        data = self._mesh_payload(fire_weather if isinstance(fire_weather, dict) else None)
        if data.get("ok") is True or data.get("wind_speed_kmh") is not None or data.get("score") is not None:
            wind = data.get("wind_speed_kmh")
            if wind is None and isinstance(data.get("weather"), dict):
                wind = data["weather"].get("wind_speed_kmh")
            if wind is not None:
                w = float(wind)
                if w > 80:
                    return ("EMERGENCY", f"Wind {w} km/h", [{"name": "Wind speed", "condition": ">80 km/h", "fired": True}])
                if w > 50:
                    return ("WARNING", f"Wind {w} km/h", [{"name": "Wind speed", "condition": ">50 km/h", "fired": True}])
                if w > 30:
                    return ("WATCH", f"Wind {w} km/h", [{"name": "Wind speed", "condition": ">30 km/h", "fired": True}])
                return ("CALM", f"Wind {w} km/h", [{"name": "Wind speed", "condition": "<=30 km/h", "fired": False}])
            score = data.get("score")
            if score is not None:
                return (
                    _score_level(score),
                    str(data.get("summary") or f"score {score}"),
                    [{"name": "ATLAS fire.weather score", "condition": "score bands", "fired": True}],
                )
        sit = self._mesh_payload(situation if isinstance(situation, dict) else None)
        if (sit.get("ok") is True or sit.get("score") is not None) and sit.get("score") is not None:
            return (
                _score_level(sit.get("score")),
                str(sit.get("summary") or f"score {sit.get('score')}"),
                [{"name": "ATLAS situation score", "condition": "score bands", "fired": True}],
            )
        reason = self._refuse_reason(fire_weather, situation)
        return ("UNKNOWN", reason, [{"name": "Weather data", "condition": reason, "fired": False}])

    def _evaluate_fire(
        self,
        situation: dict[str, Any] | None,
        fire_weather: dict[str, Any] | None,
        nearest: dict[str, Any] | None,
    ) -> tuple:
        for raw in (fire_weather, situation, nearest):
            data = self._mesh_payload(raw if isinstance(raw, dict) else None)
            if not data:
                continue
            if data.get("ok") is not True and data.get("score") is None and data.get("active_fires") is None and data.get("nearest_fire_km") is None:
                if not isinstance(data.get("coverage"), dict) and not isinstance(data.get("nearest"), dict):
                    continue
            active = data.get("active_fires")
            nearest_km = data.get("nearest_fire_km")
            if active is None:
                active = _layer_live(data.get("coverage"), "effis", "fire", "wildfire")
            if nearest_km is None and isinstance(data.get("nearest"), dict):
                nearest_km = data["nearest"].get("km")
            if nearest_km is not None and float(nearest_km) < 10:
                return (
                    "EMERGENCY",
                    f"Fire within {nearest_km} km",
                    [{"name": "Active fire distance", "condition": "<10 km", "fired": True}],
                )
            if active and int(active) > 3:
                return (
                    "WARNING",
                    f"{active} active fires",
                    [{"name": "Active fires", "condition": ">3", "fired": True}],
                )
            if active and int(active) > 0:
                return (
                    "WATCH",
                    f"{active} active fires",
                    [{"name": "Active fires", "condition": ">0", "fired": True}],
                )
            if data.get("score") is not None and "effis" in str(data.get("layers") or []):
                return (
                    _score_level(data.get("score")),
                    str(data.get("summary") or "ATLAS wildfire coverage"),
                    [{"name": "ATLAS wildfire score", "condition": "score bands", "fired": True}],
                )
            if data.get("ok") is True or active == 0 or (active is None and nearest_km is None and data.get("score") is None):
                if data.get("ok") is True or active == 0:
                    return ("CALM", "No active fires", [{"name": "Active fires", "condition": "=0", "fired": False}])
        reason = self._refuse_reason(fire_weather, situation, nearest)
        return ("UNKNOWN", reason, [{"name": "Fire data", "condition": reason, "fired": False}])

    def _evaluate_flood(
        self, situation: dict[str, Any] | None, nearest: dict[str, Any] | None
    ) -> tuple:
        for raw in (situation, nearest):
            data = self._mesh_payload(raw if isinstance(raw, dict) else None)
            if not data:
                continue
            if data.get("ok") is not True and data.get("flood_alerts") is None and not isinstance(data.get("coverage"), dict):
                continue
            alerts = data.get("flood_alerts")
            if alerts is None:
                alerts = _layer_live(data.get("coverage"), "flood", "alerts")
            if alerts and int(alerts) > 5:
                return ("EMERGENCY", f"{alerts} flood alerts", [{"name": "Flood alerts", "condition": ">5", "fired": True}])
            if alerts and int(alerts) > 2:
                return ("WARNING", f"{alerts} flood alerts", [{"name": "Flood alerts", "condition": ">2", "fired": True}])
            if alerts and int(alerts) > 0:
                return ("WATCH", f"{alerts} flood alerts", [{"name": "Flood alerts", "condition": ">0", "fired": True}])
            if data.get("ok") is True or alerts == 0:
                return ("CALM", "No flood alerts", [{"name": "Flood alerts", "condition": "=0", "fired": False}])
        reason = self._refuse_reason(situation, nearest)
        return ("UNKNOWN", reason, [{"name": "Flood data", "condition": reason, "fired": False}])

    def _overall(
        self,
        hazards: list[dict[str, Any]],
        situation: dict[str, Any] | None,
        fire_weather: dict[str, Any] | None,
    ) -> tuple:
        levels = {"CALM": 0, "WATCH": 1, "WARNING": 2, "EMERGENCY": 3, "UNKNOWN": -1}
        max_level = "CALM"
        max_val = -1
        has_unknown = False
        for h in hazards:
            lvl = h["level"]
            if lvl == "UNKNOWN":
                has_unknown = True
                continue
            val = levels.get(lvl, -1)
            if val > max_val:
                max_val = val
                max_level = lvl
        if has_unknown and max_val == -1:
            reason = self._refuse_reason(situation, fire_weather)
            if situation and situation.get("ok") is True and situation.get("summary"):
                return (_score_level(situation.get("score")), str(situation.get("summary")))
            return ("UNKNOWN", reason)
        if has_unknown:
            return (max_level, "Highest hazard level is " + max_level + " (some unknowns)")
        if situation and situation.get("ok") is True and situation.get("summary"):
            return (max_level, str(situation.get("summary")))
        return (max_level, "Highest hazard level determined")
'''


def ensure_atlas_aware_rule_engine(api_dir: Path) -> list[str]:
    """Replace stub rule engines that expect fake wind_speed fields with ATLAS v2 mapping."""
    notes: list[str] = []
    root = Path(api_dir)
    if not root.is_dir():
        return notes
    for path in root.rglob("rule_engine.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "aicom-factory-atlas-rule-engine-v4" in text:
            continue
        # Only replace engines that map ATLAS / soft-mesh placeholders.
        if "wind_speed_kmh" not in text and "mesh response unavailable" not in text:
            continue
        path.write_text(_ATLAS_RULE_ENGINE, encoding="utf-8")
        notes.append(path.relative_to(root).as_posix())
    return notes
