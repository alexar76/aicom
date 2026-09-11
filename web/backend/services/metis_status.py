"""Admin-facing Metis ecosystem + factory gate status."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from llm.metis_gate import metis_gate_blocking, metis_gate_enabled, metis_gate_mode


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


DEFAULT_METIS_URL = "http://127.0.0.1:8080"
METIS_URL_ENV_VARS = ("AIFACTORY_METIS_URL", "METIS_URL")


def _resolve_metis_url() -> tuple[str, str]:
    """The Metis base URL and where it came from.

    Returns ``(url, source)`` where ``source`` is the env var that supplied it, or
    ``"default"`` when neither is set.

    The distinction carries the whole point: with no variable set the probe hits a
    localhost fallback that in most deployments has nothing behind it, so a failed
    probe means "nobody told this process where Metis is" — not "Metis is not
    deployed". The card used to render both as a flat "No", which told the operator
    something false about the world while Metis was live and answering elsewhere.
    """
    for name in METIS_URL_ENV_VARS:
        value = _env(name)
        if value:
            return value.rstrip("/"), name
    return DEFAULT_METIS_URL, "default"


def _metis_url() -> str:
    return _resolve_metis_url()[0]


def _metis_api_key() -> str:
    return _env("AIFACTORY_METIS_API_KEY") or _env("METIS_API_KEY")


def _probe_timeout() -> float:
    try:
        return min(5.0, max(0.2, float(_env("AIFACTORY_METIS_PROBE_TIMEOUT", "2"))))
    except ValueError:
        return 2.0


def probe_metis_health(*, timeout: Optional[float] = None) -> tuple[bool, dict[str, Any]]:
    """GET /health — never raises."""
    url = _metis_url()
    req = urllib.request.Request(f"{url}/health", method="GET")
    key = _metis_api_key()
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout or _probe_timeout()) as resp:
            if not (200 <= getattr(resp, "status", resp.getcode()) < 300):
                return False, {}
            raw = resp.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            return True, body if isinstance(body, dict) else {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False, {}


def _gate_stages() -> list[str]:
    raw = _env("AIFACTORY_METIS_GATE_STAGES", "architect,methodologist")
    return [s.strip() for s in raw.split(",") if s.strip()]


def _aggregate_usage(products: dict[str, Any]) -> dict[str, Any]:
    total = len(products)
    checked = approved = flagged = 0
    scores: list[float] = []
    last_at: Optional[float] = None

    for product in products.values():
        if not isinstance(product, dict):
            continue
        gate = product.get("metis_gate")
        if not isinstance(gate, dict) or gate.get("at") is None:
            continue
        checked += 1
        try:
            at = float(gate["at"])
            last_at = at if last_at is None else max(last_at, at)
        except (TypeError, ValueError):
            pass
        if gate.get("ok") is False:
            flagged += 1
        else:
            approved += 1
        try:
            scores.append(float(gate.get("verify_score") or 0.0))
        except (TypeError, ValueError):
            pass

    avg_score = round(sum(scores) / len(scores), 3) if scores else None
    return {
        "total_products": total,
        "checked": checked,
        "approved": approved,
        "flagged": flagged,
        "pending": max(0, total - checked),
        "avg_verify_score": avg_score,
        "last_checked_at": last_at,
    }


def build_metis_admin_status(*, products: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Snapshot for admin Metis dashboard card."""
    mode = metis_gate_mode()
    gate_on = metis_gate_enabled()
    url, url_source = _resolve_metis_url()
    configured = url_source != "default"
    deployed, health = probe_metis_health()
    factory_uses = gate_on and (mode == "on" or (mode == "auto" and deployed))

    # Three states, not two. A probe can fail because nothing answered at a URL an
    # operator chose, or because no operator ever chose one — those need different
    # actions and must not render as the same word.
    if deployed:
        ecosystem_state = "deployed"
    elif configured:
        ecosystem_state = "unreachable"
    else:
        ecosystem_state = "unconfigured"

    if factory_uses:
        blocked_reason = None
    elif not gate_on:
        blocked_reason = "gate-disabled"
    elif ecosystem_state == "unconfigured":
        blocked_reason = "metis-unconfigured"
    elif ecosystem_state == "unreachable":
        blocked_reason = "metis-unreachable"
    else:
        blocked_reason = None

    if deployed and factory_uses:
        status = "active"
    elif ecosystem_state == "unconfigured":
        status = "unconfigured"
    else:
        status = "inactive"

    usage = _aggregate_usage(products or {})

    return {
        "status": status,
        "ecosystem": {
            "deployed": deployed,
            "state": ecosystem_state,
            "configured": configured,
            "url": url,
            # Which env var answered, so an operator reading "unconfigured" knows
            # exactly what to set instead of guessing.
            "url_source": url_source,
            "url_env_vars": list(METIS_URL_ENV_VARS),
            "health": {
                "status": health.get("status"),
                "service": health.get("service"),
                "version": health.get("version"),
                "knowledge_entries": health.get("knowledge_entries"),
                "cluster_nodes": len(health.get("nodes") or []),
            }
            if deployed
            else None,
        },
        "factory": {
            "gate_mode": mode,
            "gate_enabled": gate_on,
            "uses_metis": factory_uses,
            # Why not, when not: "gate-disabled" | "metis-unconfigured" |
            # "metis-unreachable" | null. In `auto` mode a single failed probe
            # zeroes this card too, so without a reason the operator sees two
            # "No"s and one cause.
            "blocked_reason": blocked_reason,
            "gate_blocking": metis_gate_blocking(),
            "gate_stages": _gate_stages(),
            "gate_route": _env("AIFACTORY_METIS_GATE_ROUTE", "council") or "council",
            "min_score": _env("AIFACTORY_METIS_GATE_MIN_SCORE", "0.7") or "0.7",
        },
        "usage": usage,
    }
