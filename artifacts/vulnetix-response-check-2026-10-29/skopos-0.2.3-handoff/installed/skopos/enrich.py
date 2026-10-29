from __future__ import annotations

from dataclasses import dataclass

import tldextract
from user_agents import parse as ua_parse

from .traffic import looks_like_bot


@dataclass(frozen=True)
class UAInfo:
    browser: str | None
    os: str | None
    device: str | None
    is_bot: bool | None


def parse_user_agent(ua: str | None) -> UAInfo:
    if not ua:
        return UAInfo(browser=None, os=None, device=None, is_bot=True)
    raw = ua.strip()
    if not raw or raw == "-":
        return UAInfo(browser=None, os=None, device=None, is_bot=True)

    try:
        u = ua_parse(raw)
        browser = (u.browser.family or None) if u.browser else None
        os = (u.os.family or None) if u.os else None

        if browser in (None, "Other") and not raw.startswith("Mozilla/"):
            browser = raw.split("/")[0][:60] or raw[:60]

        device = None
        if u.is_mobile:
            device = "Mobile"
        elif u.is_tablet:
            device = "Tablet"
        elif u.is_pc:
            device = "Desktop"
        elif browser and browser not in ("Other",):
            device = "Service"
        else:
            device = None

        is_bot = bool(u.is_bot) or looks_like_bot(user_agent=raw, ua_browser=browser)
        return UAInfo(browser=browser, os=os, device=device, is_bot=is_bot)
    except Exception:
        label = raw.split("/")[0][:60] if "/" in raw[:40] else raw[:60]
        return UAInfo(
            browser=label,
            os=None,
            device=None,
            is_bot=looks_like_bot(user_agent=raw, ua_browser=label),
        )


def referer_domain(referer: str | None) -> str | None:
    if not referer:
        return None
    ref = referer.strip()
    if not ref or ref == "-":
        return None
    try:
        ext = tldextract.extract(ref)
        if not ext.domain or not ext.suffix:
            return None
        return ".".join([p for p in [ext.domain, ext.suffix] if p])
    except Exception:
        return None
