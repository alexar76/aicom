"""Background security scan scheduler."""

from __future__ import annotations

import logging
import threading
import time

from ..config import AppConfig, load_config
from .collector import scan_all_servers

_log = logging.getLogger(__name__)

_lock = threading.Lock()
_last_run_utc: str | None = None
_last_results: list[dict] | None = None


def get_auto_scan_status() -> dict:
    with _lock:
        return {
            "last_run_utc": _last_run_utc,
            "last_results": list(_last_results or []),
        }


def run_security_scan_once(cfg: AppConfig) -> list[dict]:
    global _last_run_utc, _last_results
    from ..db import now_utc_iso

    results = scan_all_servers(cfg)
    payload = [
        {
            "server_name": r.server_name,
            "ok": r.ok,
            "snapshot_id": r.snapshot_id,
            "findings_count": r.findings_count,
            "error": r.error,
        }
        for r in results
    ]
    with _lock:
        _last_run_utc = now_utc_iso()
        _last_results = payload

    if cfg.telegram_enabled:
        try:
            from ..telegram_notify import maybe_send_security_telegram

            from ..telegram_notify import SKIP_NO_ALERTS

            ok, detail = maybe_send_security_telegram(cfg, scan_results=payload)
            if ok:
                _log.info("Telegram security notification sent")
            elif detail == SKIP_NO_ALERTS:
                _log.debug("Telegram notification skipped: %s", detail)
            else:
                # A DELIVERY FAILURE, not a skip. At DEBUG and called "skipped" this was
                # indistinguishable from "nothing to report", which is how a security channel
                # can be down for weeks while looking healthy.
                _log.warning("Telegram security notification FAILED to send: %s", detail)
        except Exception as exc:
            _log.exception("Telegram notification failed: %s", exc)

        try:
            from ..telegram_notify import maybe_send_password_expiry_telegram

            ok, detail = maybe_send_password_expiry_telegram(cfg)
            if ok:
                _log.info("Telegram password-expiry notification sent")
            else:
                _log.debug("Password-expiry notification skipped: %s", detail)
        except Exception as exc:
            _log.exception("Password-expiry notification failed: %s", exc)

    return payload


def run_forever(config_path: str) -> None:
    while True:
        try:
            cfg = load_config(config_path)
            if cfg.security_auto_scan and cfg.servers:
                _log.info("Auto security scan starting (interval %s min)", cfg.security_scan_interval_minutes)
                run_security_scan_once(cfg)
        except Exception as e:
            _log.exception("Auto security scan failed: %s", e)
        try:
            cfg = load_config(config_path)
            interval = max(5, int(cfg.security_scan_interval_minutes)) * 60
        except Exception:
            interval = 3600
        time.sleep(interval)


def start_auto_scan_thread(config_path: str) -> threading.Thread:
    t = threading.Thread(target=run_forever, args=(config_path,), daemon=True, name="security-auto-scan")
    t.start()
    return t
