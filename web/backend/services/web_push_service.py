"""Web Push: VAPID keypair, subscription store, optional pywebpush broadcast."""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.paths import data_root as factory_data_root

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_MAX_SUBS = 500


def _vapid_path() -> Path:
    p = factory_data_root() / "secrets" / "web_push_vapid.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _subs_path() -> Path:
    p = factory_data_root() / "config" / "web_push_subscriptions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _public_b64url_from_vapid(v: Any) -> str:
    raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def get_or_create_vapid_material() -> dict[str, str]:
    """Return dict with publicKey (urlsafe b64), privateKeyPem (utf-8 string)."""
    path = _vapid_path()
    if path.is_file():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            pub = str(d.get("publicKey") or "")
            priv = str(d.get("privateKeyPem") or "")
            if pub and priv:
                return {"publicKey": pub, "privateKeyPem": priv}
        except Exception as e:
            logger.warning("web_push: bad vapid file: %s", e)
    try:
        from pywebpush import Vapid

        v = Vapid()
        v.generate_keys()
        priv_pem = v.private_pem().decode("utf-8")
        pub_b64 = _public_b64url_from_vapid(v)
    except Exception as e:
        logger.error("web_push: could not generate VAPID keys: %s", e)
        raise
    path.write_text(
        json.dumps({"publicKey": pub_b64, "privateKeyPem": priv_pem}, indent=2),
        encoding="utf-8",
    )
    return {"publicKey": pub_b64, "privateKeyPem": priv_pem}


def vapid_public_key() -> str:
    return get_or_create_vapid_material()["publicKey"]


def _load_subs() -> list[dict[str, Any]]:
    path = _subs_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception as e:
        logger.warning("web_push: load subs failed: %s", e)
        return []


def _save_subs(rows: list[dict[str, Any]]) -> None:
    _subs_path().write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def add_subscription(sub: dict[str, Any]) -> dict[str, Any]:
    """Persist a PushSubscription JSON (endpoint + keys). Returns stored row with id."""
    endpoint = str(sub.get("endpoint") or "").strip()
    if not endpoint:
        raise ValueError("missing endpoint")
    keys = sub.get("keys")
    if not isinstance(keys, dict):
        raise ValueError("missing keys")
    p256 = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not p256 or not auth:
        raise ValueError("missing p256dh or auth")
    row = {
        "id": uuid.uuid4().hex[:20],
        "endpoint": endpoint,
        "keys": {"p256dh": p256, "auth": auth},
        "created_at": time.time(),
        "user_agent": str(sub.get("userAgent") or "")[:512],
    }
    with _lock:
        rows = _load_subs()
        rows = [r for r in rows if str(r.get("endpoint")) != endpoint]
        rows.insert(0, row)
        _save_subs(rows[:_MAX_SUBS])
    return row


def list_subscriptions() -> list[dict[str, Any]]:
    return _load_subs()


def _vapid_claims() -> dict[str, str]:
    sub = (os.environ.get("AIFACTORY_VAPID_CONTACT") or "").strip()
    if not sub.startswith("mailto:"):
        sub = "mailto:factory-webpush@local"
    return {"sub": sub}


def broadcast_payload(
    *,
    title: str,
    body: str,
    url: str = "/admin",
    ttl: int = 86400,
) -> dict[str, Any]:
    """Send a simple notification to all stored subscriptions (best-effort)."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return {"ok": False, "error": "pywebpush not installed", "sent": 0, "failed": 0}

    try:
        mat = get_or_create_vapid_material()
        priv = mat["privateKeyPem"]
    except Exception as e:
        return {"ok": False, "error": str(e), "sent": 0, "failed": 0}

    payload = json.dumps(
        {"title": title or "AI Factory", "body": body or "", "data": {"url": url or "/admin"}}
    )
    subs = _load_subs()
    sent = 0
    failed = 0
    dead: list[str] = []
    vapid_claims = _vapid_claims()
    for row in subs:
        info = {
            "endpoint": str(row.get("endpoint") or ""),
            "keys": row.get("keys") if isinstance(row.get("keys"), dict) else {},
        }
        if not info["endpoint"]:
            dead.append(str(row.get("id") or ""))
            failed += 1
            continue
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=priv,
                vapid_claims=vapid_claims,
                ttl=ttl,
                timeout=15,
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            if e.response is not None and getattr(e.response, "status_code", None) in (404, 410):
                rid = str(row.get("id") or "")
                if rid:
                    dead.append(rid)
            logger.debug("webpush fail: %s", e)
        except Exception as e:
            failed += 1
            logger.debug("webpush fail: %s", e)

    if dead:
        with _lock:
            rows2 = _load_subs()
            _save_subs([r for r in rows2 if str(r.get("id")) not in set(dead)])
    return {"ok": True, "sent": sent, "failed": failed, "removed": len(dead)}
