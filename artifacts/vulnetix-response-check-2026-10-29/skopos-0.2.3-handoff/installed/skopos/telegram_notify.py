"""Telegram notifications for security posture and scan results."""

from __future__ import annotations

import html
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .config import AppConfig, load_app_env
from .security.posture import SecurityPosture
from .security.posture_loader import load_security_posture

_log = logging.getLogger(__name__)

DEFAULT_TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
DEFAULT_TELEGRAM_NOTIFY_INTERVAL_MINUTES = 60

#: Sentinel for the BENIGN outcome of `maybe_send_security_telegram`: there was nothing worth
#: sending. Any other falsy return is a delivery failure and must be surfaced as one.
SKIP_NO_ALERTS = "No actionable alerts"

_lock = threading.Lock()
_last_notify_utc: str | None = None
_last_password_notify_utc: str | None = None
_PASSWORD_NOTIFY_MIN_INTERVAL_MINUTES = 1440  # at most once per day


def get_telegram_notify_status() -> dict:
    with _lock:
        return {"last_notify_utc": _last_notify_utc}


def resolve_bot_token(cfg: AppConfig) -> str | None:
    load_app_env()
    env_name = (cfg.telegram_bot_token_env or DEFAULT_TELEGRAM_BOT_TOKEN_ENV).strip()
    token = os.environ.get(env_name, "").strip()
    return token or None


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _minutes_since(ts: str | None) -> float | None:
    dt = _parse_ts(ts)
    if not dt:
        return None
    return (datetime.now(tz=timezone.utc) - dt).total_seconds() / 60.0


def format_security_message(
    posture: SecurityPosture,
    *,
    scan_results: list[dict] | None = None,
) -> str:
    sev_counts: dict[str, int] = {}
    for alert in posture.alerts:
        sev_counts[alert.severity] = sev_counts.get(alert.severity, 0) + 1

    lines = [
        "🛡 <b>SKOPOS — Security alert</b>",
        f"Score: <b>{posture.fleet_score}</b> ({html.escape(posture.grade)})",
        f"Critical: {posture.critical_count} · High: {posture.high_count}",
    ]

    failed = [r for r in (scan_results or []) if not r.get("ok")]
    if failed:
        names = ", ".join(html.escape(str(r.get("server_name", "?"))) for r in failed[:5])
        lines.append(f"⚠️ Scan errors: {names}")

    top = sorted(
        posture.alerts,
        key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(a.severity, 9),
    )[:8]
    if top:
        lines.append("")
        lines.append("<b>Top findings:</b>")
        for alert in top:
            srv = f" ({html.escape(alert.server_name)})" if alert.server_name else ""
            lines.append(f"• [{html.escape(alert.severity.upper())}] {html.escape(alert.title)}{srv}")

    if posture.remarks:
        lines.append("")
        lines.append(html.escape(posture.remarks[0][:240]))

    return "\n".join(lines)


def send_telegram_message(token: str, chat_id: str, text: str, *, timeout: float = 15.0) -> tuple[bool, str]:
    """Send one message, falling back to plain text if the HTML parse is refused.

    Why the fallback exists: `parse_mode: HTML` used to be unconditional, and Telegram answers a
    body it cannot parse with a 400. The caller advances the notify cooldown ONLY on success, so a
    single unparseable message was rebuilt and re-refused every interval forever — and because the
    call site logged the failure at DEBUG as "skipped", it looked exactly like "nothing to report".
    A security channel that fails that way is worse than none, because it looks alive.

    A retry without `parse_mode` cannot be refused for markup, so the poison body is delivered as
    plain text instead of silently dropped for good.
    """
    if not token.strip():
        return False, "Bot token is empty"
    if not str(chat_id).strip():
        return False, "Chat ID is empty"

    ok, detail = _post_message(token, chat_id, text, timeout=timeout, html=True)
    if ok:
        return True, detail
    ok2, detail2 = _post_message(token, chat_id, text, timeout=timeout, html=False)
    if ok2:
        return True, f"ok (plain-text fallback after: {detail})"
    return False, f"{detail}; plain-text retry also failed: {detail2}"


def _post_message(token: str, chat_id: str, text: str, *, timeout: float,
                  html: bool) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
    body_fields = {
        "chat_id": str(chat_id).strip(),
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    if html:
        body_fields["parse_mode"] = "HTML"
    payload = json.dumps(body_fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("ok"):
            return True, "ok"
        return False, str(body.get("description") or body)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("description", str(exc))
        except Exception:
            detail = str(exc)
        return False, str(detail)
    except Exception as exc:
        return False, str(exc)


def _should_notify(posture: SecurityPosture, scan_results: list[dict] | None) -> bool:
    if posture.critical_count or posture.high_count:
        return True
    if any(not r.get("ok") for r in (scan_results or [])):
        return True
    if any(a.severity == "medium" for a in posture.alerts):
        return True
    return False


def maybe_send_security_telegram(
    cfg: AppConfig,
    *,
    scan_results: list[dict] | None = None,
    force: bool = False,
    agent_yaml_path: str = "./agent.yaml",
) -> tuple[bool, str]:
    global _last_notify_utc

    if not cfg.telegram_enabled:
        return False, "Telegram notifications disabled"

    chat_id = (cfg.telegram_chat_id or "").strip()
    if not chat_id:
        return False, "Telegram chat ID not configured"

    token = resolve_bot_token(cfg)
    if not token:
        env_name = cfg.telegram_bot_token_env or DEFAULT_TELEGRAM_BOT_TOKEN_ENV
        return False, f"Bot token not set ({env_name})"

    interval = max(5, min(10080, int(cfg.telegram_notify_interval_minutes)))
    with _lock:
        elapsed = _minutes_since(_last_notify_utc)
        if not force and elapsed is not None and elapsed < interval:
            return False, f"Rate limited ({interval} min)"

    try:
        from skopos.db_dialect import resolve_db_target
        from skopos.security.posture_loader import load_security_posture

        posture = load_security_posture(resolve_db_target(cfg), cfg, agent_yaml_path=agent_yaml_path)
    except Exception as exc:
        _log.exception("Failed to load posture for Telegram: %s", exc)
        return False, str(exc)

    if not force and not _should_notify(posture, scan_results):
        # Marked so callers can tell "nothing to report" from "we could not deliver". Both used to
        # return (False, <text>) and be logged at DEBUG as "skipped".
        return False, SKIP_NO_ALERTS

    text = format_security_message(posture, scan_results=scan_results)
    ok, detail = send_telegram_message(token, chat_id, text)
    if ok:
        from .db import now_utc_iso

        with _lock:
            _last_notify_utc = now_utc_iso()
    return ok, detail


def maybe_send_password_expiry_telegram(
    cfg: AppConfig,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """Notify over Telegram when the dashboard password is expired or expiring soon."""
    global _last_password_notify_utc

    if not cfg.telegram_enabled:
        return False, "Telegram notifications disabled"

    chat_id = (cfg.telegram_chat_id or "").strip()
    if not chat_id:
        return False, "Telegram chat ID not configured"

    try:
        from .auth_store import (
            password_expired,
            password_expires_in_days,
            password_expiring_soon,
        )

        remaining = password_expires_in_days()
        if remaining is None:
            return False, "Password expiry tracking disabled"
        expired = password_expired()
        expiring = password_expiring_soon()
    except Exception as exc:
        return False, str(exc)

    if not force and not (expired or expiring):
        return False, "Password not near expiry"

    with _lock:
        elapsed = _minutes_since(_last_password_notify_utc)
        if not force and elapsed is not None and elapsed < _PASSWORD_NOTIFY_MIN_INTERVAL_MINUTES:
            return False, "Rate limited (24h)"

    token = resolve_bot_token(cfg)
    if not token:
        env_name = cfg.telegram_bot_token_env or DEFAULT_TELEGRAM_BOT_TOKEN_ENV
        return False, f"Bot token not set ({env_name})"

    days = int(round(remaining))
    if expired:
        text = (
            "🔐 <b>SKOPOS — password expired</b>\n"
            f"The dashboard password is <b>{abs(days)} day(s)</b> overdue for rotation.\n"
            "Open Settings → Dashboard access and set a new password."
        )
    else:
        text = (
            "🔐 <b>SKOPOS — password expiring soon</b>\n"
            f"The dashboard password expires in <b>{days} day(s)</b>.\n"
            "Rotate it in Settings → Dashboard access."
        )

    ok, detail = send_telegram_message(token, chat_id, text)
    if ok:
        from .db import now_utc_iso

        with _lock:
            _last_password_notify_utc = now_utc_iso()
    return ok, detail


def send_test_notification(
    cfg: AppConfig,
    *,
    token_override: str | None = None,
    chat_id_override: str | None = None,
) -> tuple[bool, str]:
    chat_id = (chat_id_override or cfg.telegram_chat_id or "").strip()
    token = (token_override or resolve_bot_token(cfg) or "").strip()
    if not token or not chat_id:
        return False, "Token and chat ID are required"
    text = "✅ <b>SKOPOS</b>\nTest security notification — Telegram is configured correctly."
    return send_telegram_message(token, chat_id, text)
