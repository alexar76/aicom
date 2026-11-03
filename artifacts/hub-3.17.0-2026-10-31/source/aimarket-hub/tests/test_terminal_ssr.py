"""Crawlers must see live ticker numbers in GET /, not the JS placeholders.

The static shell ships `0 / $0.00 / 0` so a file:// preview still paints. Google
indexed those zeros because `/` used to serve the file unmodified. The hub now
seeds the HTML from the same public summary `/ai-market/v2/stats/live` publishes.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import InvocationStat, Peer
from aimarket_hub.signing import Signer
from aimarket_hub.terminal_ssr import _feed_html, seed_terminal_home, snapshot

PAGE = Path(__file__).resolve().parents[1] / "terminal-home.html"


def test_static_shell_still_has_placeholders_for_file_preview():
    t = PAGE.read_text()
    assert 'id="s-inv">0</div>' in t
    assert 'id="s-hubs">0</div>' in t
    assert 'id="hub-ssr-live">{}</script>' in t
    assert 'id="hub-ssr-noscript"' in t


def test_seed_rewrites_the_real_page_file():
    html = PAGE.read_text()
    summary = {
        "total_invocations": 538,
        "successful_invocations": 534,
        "success_rate": 0.9925,
        "revenue_per_hour_usd": 0.0,
        "peers_count": 14,
        "capabilities_count": 179,
        "offerable_capabilities_count": 179,
        "federated_capabilities_count": 179,
        "external_invocations": 528,
        "operator_self_invocations": 10,
        "refused_invocations": 8,
        "incomplete_invocations": 5,
    }
    events = [{
        "capability_id": "atlas.situation.brief@v1",
        "product_id": "atlas.products",
        "source_hub": "https://atlas.modelmarket.dev",
        "price_usd": 0.0,
        "latency_ms": 692,
        "success": 1,
        "traffic_class": "external",
        "consumer_hub": "sandbox:abc",
    }]
    out = seed_terminal_home(html, summary, events)
    assert 'id="s-inv">538</div>' in out
    assert 'id="s-hubs">14</div>' in out
    assert 'id="s-caps">179</div>' in out
    assert "538 invocations, 14 federation peers, 179 capabilities" in out
    # Two separate classes on the subtitle, each with its own glyph and count.
    assert "528 external / 10 self · ⋯ 5 incomplete input · ⊘ 8 refused" in out
    assert "atlas.situation.brief@v1" in out
    assert "Marketplace warming up" not in out
    assert "collecting…" not in out
    noscript = out[out.find('id="hub-ssr-noscript"'):out.find("</noscript>") + 11]
    assert "538 invocations" in noscript
    blob = json.loads(
        out.split('id="hub-ssr-live">', 1)[1].split("</script>", 1)[0]
    )
    assert blob["summary"]["total_invocations"] == 538
    assert blob["events"][0]["capability_id"] == "atlas.situation.brief@v1"


def test_empty_snapshot_stays_honest_zeros():
    html = seed_terminal_home(PAGE.read_text(), {
        "total_invocations": 0,
        "revenue_per_hour_usd": 0,
        "peers_count": 0,
        "offerable_capabilities_count": 0,
        "federated_capabilities_count": 0,
        "success_rate": 0,
        "external_invocations": 0,
        "operator_self_invocations": 0,
    }, [])
    assert 'id="s-inv">0</div>' in html
    assert "awaiting traffic" in html


def test_game_actions_are_named_in_the_feed_before_javascript_runs():
    events = [
        {"capability_id": "gaia.weather.read@v1", "purpose": purpose, "success": True}
        for purpose in ("feed", "home-weather")
    ]
    out = seed_terminal_home(PAGE.read_text(), {"total_invocations": 2}, events)
    # Inspect the actual server-rendered rows, not the JSON snapshot or JS template.
    feed = out.split('<div id="feed">', 1)[1].split('<div class="card market-pulse">', 1)[0]
    assert '<span class="purpose">feed</span>' in feed
    assert '<span class="purpose">home-weather</span>' in feed


@pytest.mark.parametrize(("purpose", "expected"), [
    ("  Feed ", "feed"),
    ("home-weather", "home-weather"),
    (None, None),
    ('feed\"><script>alert(1)</script>', None),
    ("feed the cat", None),
])
def test_server_feed_uses_the_public_purpose_slug(purpose, expected):
    row = ET.fromstring(_feed_html([{"purpose": purpose, "success": True}]))
    label = row.find('.//span[@class="purpose"]')
    assert (label.text if label is not None else None) == expected
    assert row.find(".//script") is None


def test_server_feed_keeps_six_grid_cells_and_escapes_provider_text():
    cap = '<script>alert("cap")</script>'
    hub = '<img src=x onerror="alert(1)">'
    row = ET.fromstring(_feed_html([{
        "capability_id": cap, "source_hub": hub, "purpose": "feed",
        "traffic_class": "external", "success": True, "price_usd": 0.001,
        "latency_ms": 16,
    }]))
    cells = list(row)
    assert len(cells) == 6  # icon, capability/route, class, price, latency, outcome
    assert cells[0].text == "🤖"
    assert cells[1].find('span[@class="cap-id"]').text == cap
    assert cells[1].find('.//span[@class="host"]').text == hub
    assert [cell.get("class") for cell in cells[2:]] == ["tc ext", "usd", "lat", "ok"]
    assert row.find(".//script") is None
    assert row.find(".//img") is None


def test_get_slash_seeds_live_numbers(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_HUB_NAME", "modelmarket.dev")
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://modelmarket.dev")
    db = HubDatabase(tmp_path / "ssr.db")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for i in range(7):
        db.record_invocation(InvocationStat(
            capability_id="atlas.situation.brief@v1",
            product_id="atlas.products",
            source_hub="https://atlas.modelmarket.dev",
            price_usd=0.01,
            latency_ms=100 + i,
            success=True,
            timestamp=now,
            consumer_hub="sandbox:visitor-ssr",
        ))
    db.upsert_peer(Peer(url="https://atlas.example.com", name="ATLAS"), status="active")
    db.upsert_peer(Peer(url="https://iot.example.com", name="GAIA"), status="active")
    cfg = HubConfig()
    cfg.db_path = str(tmp_path / "ssr.db")
    cfg.signing_key_path = str(tmp_path / "key")
    cfg.hub_name = "modelmarket.dev"
    cfg.hub_url = "https://modelmarket.dev"
    app = create_app(config=cfg, db=db, signer=Signer(cfg.signing_key_path))
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert "max-age=30" in r.headers.get("cache-control", "")
    html = r.text
    assert 'id="s-inv">7</div>' in html
    assert 'id="s-hubs">2</div>' in html
    assert "atlas.situation.brief@v1" in html
    assert "7 invocations" in html
    # The JS placeholder string must not be what a crawler is left with. The inline English
    # dictionary (#hub-ui-en, the page's fallback when its fetch fails) carries every string as
    # data, so only the markup outside it is read here.
    markup = re.sub(r'<script type="application/json" id="hub-ui-en">.*?</script>', "", html,
                    flags=re.S)
    assert "Marketplace warming up" not in markup
    summary, events = snapshot(db, hub_url="https://modelmarket.dev")
    assert summary["total_invocations"] == 7
    assert summary["external_invocations"] == 7
    assert events[0]["traffic_class"] == "external"
    assert events[0]["consumer_hub"].startswith("sandbox:")
    assert events[0]["consumer_hub"] != "sandbox:visitor-ssr"


def test_capability_id_cannot_smuggle_markup_through_the_sub_template():
    """A capability id is attacker-controlled; the SSR must not expand it as a regex template.

    `re.sub` treats a replacement STRING as a template — it expands `\\g<1>`, `\\1` and,
    the one that actually bites, OCTAL escapes: `\\074` becomes `<`. `html.escape` does not
    touch backslashes, so `\\074script\\076` sailed through escaping and was expanded into a
    real `<script>` tag in the page every visitor and crawler is served.
    """
    payload = r"\074script\076alert(1)\074/script\076"
    page = PAGE.read_text(encoding="utf-8")
    summary = {
        "total_invocations": 3,
        "revenue_per_hour_usd": 0.5,
        "peers_count": 1,
        "capabilities_count": 2,
        "success_rate": 1.0,
        "external_invocations": 3,
        "operator_self_invocations": 0,
    }
    events = [
        {
            "capability_id": payload,
            "source_hub": payload,
            "success": True,
            "price_usd": 0.01,
            "latency_ms": 12,
            "traffic_class": "external",
        }
    ]
    out = seed_terminal_home(page, summary, events)
    assert "<script>alert(1)" not in out
    assert "</script>alert" not in out
    # The literal text still shows up, escaped — the feed is seeded, just not executed.
    assert r"\074script\076" in out
    # And the numbers are still substituted: the fix must not disable SSR.
    assert 'id="s-inv">3</div>' in out


def test_group_reference_in_a_capability_id_is_not_expanded():
    """`\\g<1>` in an id used to splice the captured page markup back into the feed."""
    page = PAGE.read_text(encoding="utf-8")
    summary = {"total_invocations": 1, "peers_count": 1, "capabilities_count": 1}
    events = [
        {
            "capability_id": r"a\g<1>b",
            "source_hub": "peer",
            "success": True,
            "price_usd": 0,
            "latency_ms": 1,
            "traffic_class": "external",
        }
    ]
    out = seed_terminal_home(page, summary, events)
    assert r"a\g&lt;1&gt;b" in out or r"a\g<1>b" in out
    assert out.count('<ul class="lb" id="top-caps">') == 1
