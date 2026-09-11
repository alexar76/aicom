"""
Registry of factory-born agents — the products that go on to trade in our economy.

A product the factory ships is not always a page someone visits. Increasingly it
is an *agent*: it runs on its own, it invokes capabilities from the mesh, it pays
for them, and it produces receipts. Those agents were invisible — the catalog
knew the product existed, but nothing tracked the running thing or what it spent.

An agent heartbeats here every minute with who it is, which SDK it speaks, which
capabilities it consumes, and its counters. The monitor renders the roster; the
operator sees spend and health per participant.

Storage is a single JSON document under ``data/agents/registry.json`` — the
cardinality is agents, not events, and the write path is one small file per
heartbeat interval.

Auth: heartbeats carry ``X-Agent-Key``. When ``AIFACTORY_AGENT_REGISTRY_KEY`` is
configured the key must match. In production an unset key fails **closed** —
an open write endpoint would let anyone inject a fake participant.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from core.paths import data_root

logger = logging.getLogger(__name__)

MAX_AGENTS = 500
STALE_AFTER_SEC = 300.0
OFFLINE_AFTER_SEC = 3600.0

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")

# Counter names accepted from an agent. Anything else is dropped rather than
# stored, so a chatty agent cannot grow the document without bound.
STAT_FIELDS = (
    "invokes_total",
    "invokes_24h",
    "spend_usd_total",
    "spend_usd_24h",
    "advisories_served",
    "receipts_verified",
    "errors_24h",
    "cache_hit_rate",
    "uptime_sec",
)


def registry_path() -> Path:
    return Path(data_root()) / "agents" / "registry.json"


def is_production() -> bool:
    return (
        os.environ.get("AIFACTORY_PROD", "").strip() == "1"
        or os.environ.get("AIFACTORY_PRODUCTION", "").strip() == "1"
        or os.environ.get("AIFACTORY_ENV", "").strip().lower() in ("prod", "production")
    )


def configured_key() -> str:
    return os.environ.get("AIFACTORY_AGENT_REGISTRY_KEY", "").strip()


def check_agent_key(presented: str | None) -> tuple[bool, str]:
    """Validate a heartbeat key. Returns ``(ok, reason)``."""
    expected = configured_key()
    if not expected:
        if is_production():
            return False, "registry_key_not_configured"
        return True, "unverified_dev"
    if not presented:
        return False, "missing_key"
    if not hmac.compare_digest(presented.strip(), expected):
        return False, "bad_key"
    return True, "verified"


def _load() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"agents": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("agent_registry: unreadable registry (%s) — starting empty", exc)
        return {"agents": {}}
    if not isinstance(doc, dict) or not isinstance(doc.get("agents"), dict):
        return {"agents": {}}
    return doc


def _save(doc: dict[str, Any]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _clean_str(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


def _clean_stats(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key in STAT_FIELDS:
        if key not in raw:
            continue
        try:
            out[key] = round(float(raw[key]), 6)
        except (TypeError, ValueError):
            continue
    return out


def _clean_capabilities(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    seen: list[str] = []
    for item in raw:
        text = _clean_str(item, 120)
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= 24:
            break
    return seen


def status_for(last_seen: float, *, now: float | None = None) -> str:
    age = (now if now is not None else time.time()) - float(last_seen or 0)
    if age <= STALE_AFTER_SEC:
        return "live"
    if age <= OFFLINE_AFTER_SEC:
        return "stale"
    return "offline"


def record_heartbeat(payload: dict[str, Any], *, verified: bool = True) -> dict[str, Any]:
    """Upsert one agent from a heartbeat body. Returns the stored record."""
    # Validate the id as sent — truncating it here would silently merge two agents.
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id or not _ID_RE.match(agent_id):
        raise ValueError("agent_id must match [A-Za-z0-9][A-Za-z0-9._:-]{0,63}")

    now = time.time()
    doc = _load()
    agents: dict[str, Any] = doc["agents"]
    existing = agents.get(agent_id) if isinstance(agents.get(agent_id), dict) else {}

    record = {
        "agent_id": agent_id,
        "name": _clean_str(payload.get("name"), 120) or agent_id,
        "product_id": _clean_str(payload.get("product_id"), 64),
        "sdk": _clean_str(payload.get("sdk"), 80),
        "version": _clean_str(payload.get("version"), 40),
        "public_url": _clean_str(payload.get("public_url"), 300),
        "kind": _clean_str(payload.get("kind"), 40) or "agent",
        "capabilities_used": _clean_capabilities(payload.get("capabilities_used")),
        "stats": _clean_stats(payload.get("stats")),
        "verified": bool(verified),
        "first_seen": float(existing.get("first_seen") or now),
        "last_seen": now,
        "heartbeats": int(existing.get("heartbeats") or 0) + 1,
    }
    agents[agent_id] = record

    if len(agents) > MAX_AGENTS:
        # Drop the least recently seen agents rather than refusing new ones.
        ordered = sorted(agents.items(), key=lambda kv: float(kv[1].get("last_seen") or 0))
        for stale_id, _ in ordered[: len(agents) - MAX_AGENTS]:
            agents.pop(stale_id, None)

    doc["updated_at"] = now
    _save(doc)
    return record


def product_is_agent(product: dict[str, Any] | None) -> bool:
    """True when a shipped product is an autonomous agent, not a page.

    Read from the order itself (tags / category / charter) rather than guessed,
    so the roster stays a list of participants instead of a second catalog.
    """
    if not isinstance(product, dict):
        return False
    tags = product.get("tags")
    if isinstance(tags, (list, tuple)) and any(str(t).strip().lower() == "agent" for t in tags):
        return True
    if str(product.get("category") or "").strip().lower() == "agent":
        return True
    spec = product.get("spec") if isinstance(product.get("spec"), dict) else {}
    inner = spec.get("specification") if isinstance(spec.get("specification"), dict) else spec
    if str(inner.get("product_kind") or "").strip().lower() == "agent":
        return True
    return False


def bootstrap_from_publish(
    *,
    product_id: str,
    name: str,
    public_url: str,
    sdk: str = "",
    version: str = "",
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Seed a registry record when an agent is published.

    A serverless agent only executes when someone calls it, so waiting for its
    first heartbeat would leave a freshly shipped participant invisible — and
    invisible for exactly as long as nobody visits it. Publishing is itself the
    event worth recording; the agent's own heartbeats refine it from there.
    """
    agent_id = f"{product_id}".strip()
    record = record_heartbeat(
        {
            "agent_id": agent_id,
            "name": name or product_id,
            "product_id": product_id,
            "sdk": sdk,
            "version": version,
            "public_url": public_url,
            "kind": "agent",
            "capabilities_used": capabilities or [],
        },
        verified=True,
    )
    # A published-but-never-run agent is not "live" — only its own heartbeat
    # can claim that. Backdate so the roster shows it as awaiting first contact.
    doc = _load()
    stored = doc["agents"].get(agent_id)
    if isinstance(stored, dict) and int(stored.get("heartbeats") or 0) <= 1:
        stored["last_seen"] = time.time() - (STALE_AFTER_SEC + 1)
        stored["published_at"] = time.time()
        _save(doc)
        record = stored
    return record


def list_agents(*, include_offline: bool = True) -> list[dict[str, Any]]:
    """Roster sorted most-recently-seen first, with a derived liveness status."""
    now = time.time()
    out: list[dict[str, Any]] = []
    for record in _load()["agents"].values():
        if not isinstance(record, dict):
            continue
        status = status_for(float(record.get("last_seen") or 0), now=now)
        if status == "offline" and not include_offline:
            continue
        item = dict(record)
        item["status"] = status
        item["age_sec"] = round(now - float(record.get("last_seen") or 0), 1)
        out.append(item)
    out.sort(key=lambda r: float(r.get("last_seen") or 0), reverse=True)
    return out


def registry_summary() -> dict[str, Any]:
    """Economy-level totals — what the participants add up to."""
    agents = list_agents()
    live = [a for a in agents if a["status"] == "live"]
    spend = sum(float(a.get("stats", {}).get("spend_usd_total") or 0) for a in agents)
    invokes = sum(float(a.get("stats", {}).get("invokes_total") or 0) for a in agents)
    sdks: dict[str, int] = {}
    capabilities: dict[str, int] = {}
    for a in agents:
        sdk = a.get("sdk") or "unknown"
        sdks[sdk] = sdks.get(sdk, 0) + 1
        for cap in a.get("capabilities_used") or []:
            capabilities[cap] = capabilities.get(cap, 0) + 1
    return {
        "agents_total": len(agents),
        "agents_live": len(live),
        "spend_usd_total": round(spend, 4),
        "invokes_total": int(invokes),
        "sdks": sdks,
        "capabilities": capabilities,
        "updated_at": time.time(),
    }
