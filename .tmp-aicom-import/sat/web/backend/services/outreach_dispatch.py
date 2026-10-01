"""
Dispatch announcements to configured channels (SMTP, webhook, Telegram).

Runs blocking SMTP in a thread pool. Uses httpx for HTTP. No secrets in JSON — only os.environ.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _strip_htmlish(s: str) -> str:
    t = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", t).strip()


async def _send_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    # SECURITY: validate webhook URL before dispatching (SSRF guard).
    if url and urlparse(url).hostname in (
        "localhost", "127.0.0.1", "::1", "169.254.169.254",
        "metadata.google.internal",
    ):
        return False, "webhook URL targets a blocked internal host"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            if r.status_code >= 400:
                return False, f"HTTP {r.status_code}: {r.text[:500]}"
            return True, f"ok status={r.status_code}"
    except Exception as e:
        logger.exception("webhook send failed")
        return False, str(e)[:500]


async def _send_telegram(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    if not token or not chat_id:
        return False, "missing token or chat_id"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(url, json=payload)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if not data.get("ok"):
                return False, str(data.get("description") or r.text)[:500]
            return True, "telegram ok"
    except Exception as e:
        logger.exception("telegram send failed")
        return False, str(e)[:500]


def _send_smtp_sync(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    body_plain: str,
) -> tuple[bool, str]:
    import smtplib
    import ssl

    if not host or not to_addrs:
        return False, "missing SMTP host or recipients"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject[:998]
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs[:20])
    msg.attach(MIMEText(body_plain, "plain", "utf-8"))
    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=45) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=45) as server:
                server.ehlo()
                server.starttls(context=context)
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())
        return True, "smtp ok"
    except Exception as e:
        logger.exception("smtp send failed")
        return False, str(e)[:500]


async def send_smtp(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    body_plain: str,
) -> tuple[bool, str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _send_smtp_sync(
            host=host,
            port=port,
            user=user,
            password=password,
            from_addr=from_addr,
            to_addrs=to_addrs,
            subject=subject,
            body_plain=body_plain,
        ),
    )


async def dispatch_to_channel(
    channel: dict[str, Any],
    *,
    announcement: dict[str, Any],
) -> tuple[bool, str]:
    """
    Send one announcement through one channel definition.
    """
    ctype = (channel.get("type") or "").lower()
    cid = channel.get("id", "?")

    title = str(announcement.get("title") or "")[:500]
    body = str(announcement.get("body_plain") or announcement.get("body_markdown") or "")[:50000]
    body_plain = _strip_htmlish(body) if announcement.get("body_plain") is None else str(announcement.get("body_plain"))[:50000]
    aid = str(announcement.get("id") or "")
    audience = str(announcement.get("audience") or "all")
    author_role = str(announcement.get("author_role") or "marketing")

    if ctype == "webhook":
        url_env = channel.get("url_env") or "OUTREACH_WEBHOOK_URL"
        url = _env(str(url_env))
        if not url:
            return False, f"env {url_env} not set"
        payload = {
            "event": "outreach.announcement",
            "announcement_id": aid,
            "title": title,
            "body_plain": body_plain[:8000],
            "audience": audience,
            "author_role": author_role,
            "channel_id": cid,
        }
        return await _send_webhook(url, payload)

    if ctype == "telegram":
        token = _env(str(channel.get("token_env") or "OUTREACH_TELEGRAM_BOT_TOKEN"))
        chat = _env(str(channel.get("chat_id_env") or "OUTREACH_TELEGRAM_CHAT_ID"))
        text = f"*{title}*\n\n{body_plain}"[:4000]
        # Telegram * may break if unclosed — use plain
        text = f"{title}\n\n{body_plain}"[:4000]
        return await _send_telegram(token, chat, text)

    if ctype == "smtp":
        host = _env("OUTREACH_SMTP_HOST")
        port_s = _env("OUTREACH_SMTP_PORT") or "587"
        try:
            port = int(port_s)
        except ValueError:
            port = 587
        user = _env("OUTREACH_SMTP_USER")
        password = _env("OUTREACH_SMTP_PASSWORD")
        from_addr = _env("OUTREACH_SMTP_FROM")
        to_raw = _env("OUTREACH_SMTP_TO")
        to_addrs = [x.strip() for x in to_raw.split(",") if x.strip()]
        if not host or not from_addr or not to_addrs:
            return False, "OUTREACH_SMTP_HOST, OUTREACH_SMTP_FROM, OUTREACH_SMTP_TO required"
        return await send_smtp(
            host=host,
            port=port,
            user=user,
            password=password,
            from_addr=from_addr,
            to_addrs=to_addrs,
            subject=title or "Announcement",
            body_plain=body_plain or "(empty)",
        )

    return False, f"unknown channel type: {ctype}"


async def dispatch_announcement(
    announcement: dict[str, Any],
    channels_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run all enabled channels; return log lines."""
    logs: list[dict[str, Any]] = []
    for ch in channels_doc.get("channels") or []:
        if not isinstance(ch, dict) or not ch.get("enabled"):
            continue
        ok, detail = await dispatch_to_channel(ch, announcement=announcement)
        logs.append({"channel_id": ch.get("id"), "ok": ok, "detail": detail})
        logger.info("outreach channel=%s ok=%s detail=%s", ch.get("id"), ok, detail[:200])
    return logs
