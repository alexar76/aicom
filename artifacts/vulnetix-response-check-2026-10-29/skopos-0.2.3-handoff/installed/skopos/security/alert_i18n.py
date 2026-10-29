"""Translate rule-generated security alerts for UI and reports."""

from __future__ import annotations

import re
from dataclasses import replace

from skopos.i18n import t
from skopos.security.posture import SecurityAlert

_ACTIVE_THREAT = re.compile(r"^Active threat: (.+)$")
_STALE_SCAN = re.compile(r"^Stale security scan: (.+)$")
_KNOCK_ACTION = "Block IP in firewall / ensure fail2ban is active; verify SSH key-only auth."
_STALE_MESSAGE = "No security scan in the last 24 hours — posture may be outdated."
_STALE_ACTION = "Run: python skoposctl.py security-scan"


def localize_alert(alert: SecurityAlert, locale: str) -> SecurityAlert:
    title = alert.title
    message = alert.message or ""
    action = alert.action or ""

    if m := _ACTIVE_THREAT.match(title):
        title = t("security.alert_active_threat", locale, ip=m.group(1))
    elif m := _STALE_SCAN.match(title):
        title = t("security.alert_stale_scan_title", locale, server=m.group(1))

    if message == _STALE_MESSAGE:
        message = t("security.alert_stale_scan_message", locale)

    if action == _KNOCK_ACTION:
        action = t("report.block_ip", locale)
    elif action == _STALE_ACTION:
        action = t("security.alert_stale_scan_action", locale)

    if title == alert.title and message == alert.message and action == alert.action:
        return alert
    return replace(alert, title=title, message=message, action=action or None)
