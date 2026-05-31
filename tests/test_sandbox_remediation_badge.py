"""Sandbox corner badge while product is in remediation."""

from __future__ import annotations

import time

import pytest


def test_inject_remediation_badge_before_body_close(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services import sandbox_remediation_badge as badge

    monkeypatch.setattr(
        badge,
        "remediation_badge_markup",
        lambda _pid, **_: '<motion.div id="aicom-rework-badge">test</div>',
    )
    out = badge.inject_remediation_badge("<html><body><p>x</p></body></html>", "prod-x")
    assert "aicom-rework-badge" in out
    assert out.index("aicom-rework-badge") < out.lower().index("</body>")


def test_established_pinned_keeps_completed_on_grid(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.product_followup import merge_mark_storefront_established_listing
    from web.backend.services.storefront_visibility import established_storefront_pinned

    pid = "prod-pinned"
    merge_mark_storefront_established_listing(pid)
    assert established_storefront_pinned(
        pid,
        has_generated_code=True,
        storefront_blocked=False,
    )


def test_ensure_remediation_eta_written_once(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.product_followup import read_followup
    from web.backend.services.sandbox_remediation_badge import (
        REMEDIATION_ETA_KEY,
        ensure_remediation_eta_recorded,
    )

    pid = "prod-eta"
    ensure_remediation_eta_recorded(pid, state_upper="DEV_FIXING")
    raw = read_followup(pid)
    assert raw and raw.get(REMEDIATION_ETA_KEY)
    first = raw[REMEDIATION_ETA_KEY]
    time.sleep(0.01)
    ensure_remediation_eta_recorded(pid, state_upper="DEV_FIXING")
    raw2 = read_followup(pid)
    assert raw2[REMEDIATION_ETA_KEY] == first


def test_remediation_badge_locale_en(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.product_followup import write_followup
    from web.backend.services.sandbox_remediation_badge import (
        REMEDIATION_ETA_KEY,
        remediation_badge_markup,
    )

    pid = "prod-badge-en"
    write_followup(pid, {REMEDIATION_ETA_KEY: time.time() + 3600})
    html = remediation_badge_markup(pid, locale="en")
    assert "Sent for rework" in html
    assert "Expected return:" in html
    assert "REWORK" in html
    assert "Отправлен" not in html


def test_remediation_badge_locale_ru(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    from web.backend.services.product_followup import write_followup
    from web.backend.services.sandbox_remediation_badge import (
        REMEDIATION_ETA_KEY,
        remediation_badge_markup,
    )

    pid = "prod-badge-ru"
    write_followup(pid, {REMEDIATION_ETA_KEY: time.time() + 3600})
    html = remediation_badge_markup(pid, locale="ru")
    assert "Отправлен на доработку" in html
    assert "Ожидаемый возврат:" in html
    assert "ДОРАБОТКА" in html


def test_resolve_remediation_badge_locale_from_query():
    from web.backend.services.sandbox_remediation_badge import resolve_remediation_badge_locale

    class Q:
        def __init__(self, lang=None):
            self._lang = lang

        def get(self, key):
            if key == "lang":
                return self._lang
            return None

    class Req:
        query_params = Q("en")
        headers = {}

    assert resolve_remediation_badge_locale(Req()) == "en"
