from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

import httpx

from relay_scout.models import AlertRecord, EndpointTarget, Snapshot

_ALERT_CACHE: OrderedDict[str, float] = OrderedDict()
_CACHE_TTL_SEC = 300
_CACHE_MAX = 256


def _cache_key(endpoint: str, alert_type: str, message: str) -> str:
    return f"{endpoint}:{alert_type}:{message[:120]}"


def _prune_cache(now: float) -> None:
    stale = [k for k, ts in _ALERT_CACHE.items() if now - ts > _CACHE_TTL_SEC]
    for k in stale:
        _ALERT_CACHE.pop(k, None)
    while len(_ALERT_CACHE) > _CACHE_MAX:
        _ALERT_CACHE.popitem(last=False)


async def _post_webhook(client: httpx.AsyncClient, url: str, payload: dict) -> bool:
    try:
        resp = await client.post(url, json=payload, timeout=10.0)
        return 200 <= resp.status_code < 300
    except Exception:
        return False


async def send_alert(
    target: EndpointTarget,
    snapshot: Snapshot,
    alert_type: str,
    message: str,
) -> AlertRecord:
    now = time.time()
    _prune_cache(now)
    key = _cache_key(target.name, alert_type, message)
    if key in _ALERT_CACHE:
        return AlertRecord(target.name, alert_type, message, snapshot.timestamp, sent=False)

    record = AlertRecord(target.name, alert_type, message, snapshot.timestamp, sent=False)
    if not target.webhook_urls:
        _ALERT_CACHE[key] = now
        return record

    payload = {
        "endpoint": target.name,
        "type": alert_type,
        "message": message,
        "timestamp": snapshot.timestamp,
        "status_code": snapshot.status_code,
    }
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_post_webhook(client, url, payload) for url in target.webhook_urls]
        )
    record.sent = any(results)
    _ALERT_CACHE[key] = now
    return record
