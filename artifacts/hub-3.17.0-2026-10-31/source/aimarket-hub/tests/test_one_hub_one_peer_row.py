"""One hub must not hold two peer rows.

The peers table is keyed on URL, but a hub's identity is its signing key. So the same hub
announced under a second address becomes a second row — and both rows get crawled and both
re-export the same catalogue, which is double weight in the index for one operator.

Found in production on 2026-09-04: the competing-lab hub was an ACTIVE peer at
`http://108.165.32.182:9083` and simultaneously a PENDING announcement for
`https://hub.modelmarket.dev` — the same machine, two identities, one Approve click away
from being counted twice.

Announcement itself deliberately stores no key (an unauthenticated caller must not be able to
establish someone else's pin), so the check belongs at admission, where the assay has read
`signer_public_key` from the candidate's own well-known.
"""

from __future__ import annotations

import pytest

from aimarket_hub.database import HubDatabase, Peer
from aimarket_hub.federation_assay import admit_peer

KEY = "lUgnD6FKzGU0gMaTVjtKzUExampleKeyForTests="
OTHER_KEY = "jmh/t/PAQ+dFsyCQDtTioqExampleKeyForTests="


@pytest.fixture
def db(tmp_path):
    return HubDatabase(str(tmp_path / "hub.db"))


def _peer(url: str, key: str = "", name: str = "Peer") -> Peer:
    return Peer(
        url=url,
        name=name,
        capabilities_count=0,
        well_known_url=f"{url}/.well-known/ai-market.json",
        public_key=key,
        depth=1,
        discoverer="test",
    )


def test_second_url_for_a_known_key_is_refused(db):
    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY, "Competing Lab Hub"), status="active")
    db.upsert_peer(_peer("https://hub.modelmarket.dev"), status="pending")

    admitted = admit_peer(db, "https://hub.modelmarket.dev", KEY)

    assert admitted is False, "the same hub was admitted a second time under a new URL"
    still_pending = [p.url for p in db.list_pending_peers()]
    assert "https://hub.modelmarket.dev" in still_pending, (
        "the row must stay pending for the operator to see, not silently vanish"
    )


def test_a_genuinely_different_hub_is_still_admitted(db):
    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY), status="active")
    db.upsert_peer(_peer("https://someone-else.example"), status="pending")

    assert admit_peer(db, "https://someone-else.example", OTHER_KEY) is True
    assert "https://someone-else.example" in [p.url for p in db.list_peers()]


def test_no_key_means_previous_behaviour(db):
    """Every caller that does not know a key must behave exactly as before."""
    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY), status="active")
    db.upsert_peer(_peer("https://unknown-key.example"), status="pending")

    assert admit_peer(db, "https://unknown-key.example") is True


def test_readmitting_the_same_url_is_not_blocked_by_its_own_key(db):
    """The peer's own row must not count as its twin."""
    db.upsert_peer(_peer("https://self.example", KEY), status="pending")
    assert admit_peer(db, "https://self.example", KEY) is True


def test_an_inactive_twin_does_not_block(db):
    """Only an ACTIVE peer occupies an index slot; a rejected twin must not veto."""
    db.upsert_peer(_peer("http://old.example", KEY), status="key_mismatch")
    db.upsert_peer(_peer("https://new.example"), status="pending")
    assert admit_peer(db, "https://new.example", KEY) is True


# ── The operator door ────────────────────────────────────────────────────────────────────

def test_approve_refuses_a_duplicate_identity(tmp_path, monkeypatch):
    """`admit_peer` guards auto-admit; POST /federation/peers/approve is the actual click.

    In production the competing-lab hub was ACTIVE at http://108.165.32.182:9083 and PENDING
    as https://hub.modelmarket.dev — one Approve away from being crawled and re-exported
    twice under a single identity.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY_REQUIRE", "0")

    from aimarket_hub.api import create_app

    app = create_app()
    db = app.state.hub_db if hasattr(app.state, "hub_db") else None
    if db is None:  # the app does not expose it — open the same file
        db = HubDatabase(str(tmp_path / "hub.db"))

    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY, "Competing Lab Hub"), status="active")
    db.upsert_peer(_peer("https://hub.modelmarket.dev", KEY, "Competing Lab Hub"), status="pending")

    client = TestClient(app)
    r = client.post(
        "/ai-market/v2/federation/peers/approve",
        json={"url": "https://hub.modelmarket.dev", "trusted": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert r.status_code == 409, r.text
    assert "duplicate_identity" in r.text
    assert "108.165.32.182" in r.text, "the operator must be told which row already holds it"


def test_approve_still_works_for_a_distinct_hub(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub2.db"))
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY_REQUIRE", "0")

    from aimarket_hub.api import create_app

    app = create_app()
    db = HubDatabase(str(tmp_path / "hub2.db"))
    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY), status="active")
    db.upsert_peer(_peer("https://someone-else.example", OTHER_KEY), status="pending")

    client = TestClient(app)
    r = client.post(
        "/ai-market/v2/federation/peers/approve",
        json={"url": "https://someone-else.example", "trusted": True},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert r.status_code == 200, r.text


# ── The gossip loop ─────────────────────────────────────────────────────────────────────

def test_a_known_alias_is_not_republished_as_an_observation(tmp_path, monkeypatch):
    """`observed_hubs` must not keep a plaintext alias circulating.

    Neither hub self-advertised `http://108.165.32.182:9083`: we observed it, we published
    it, the competing lab read it back from us and published it again, and the address kept
    being adopted as a peer. The observation layer sustained it entirely on its own.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub3.db"))
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://us.example")

    from aimarket_hub.api import create_app

    db = HubDatabase(str(tmp_path / "hub3.db"))
    # The real hub, active and trusted, and its raw-IP alias sitting pending with the SAME key.
    db.upsert_peer(_peer("https://hub.modelmarket.dev", KEY, "Competing Lab Hub"), status="active")
    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY, "Competing Lab Hub"), status="pending")
    # A genuine unknown must still be advertised — that is what the layer is for.
    db.upsert_peer(_peer("https://a-real-stranger.example", OTHER_KEY, "Stranger"), status="pending")

    app = create_app()
    doc = TestClient(app).get("/.well-known/ai-market.json").json()
    observed = [o.get("url") for o in (doc.get("observed_hubs") or [])]

    assert "http://108.165.32.182:9083" not in observed, (
        "the alias is still being gossiped — the loop stays alive"
    )
    assert "https://a-real-stranger.example" in observed, (
        "a genuine unknown must remain visible; the filter must not empty the layer"
    )


def test_an_unkeyed_pending_peer_is_still_observed(tmp_path, monkeypatch):
    """Only crawled peers carry a key. An announcement we have never dialled must stay
    visible, or open federation stops working."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub4.db"))
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://us.example")

    from aimarket_hub.api import create_app

    db = HubDatabase(str(tmp_path / "hub4.db"))
    db.upsert_peer(_peer("https://hub.modelmarket.dev", KEY), status="active")
    db.upsert_peer(_peer("https://never-dialled.example", "", "Fresh knock"), status="pending")

    doc = TestClient(create_app()).get("/.well-known/ai-market.json").json()
    observed = [o.get("url") for o in (doc.get("observed_hubs") or [])]
    assert "https://never-dialled.example" in observed


def test_the_public_pending_list_also_withholds_the_alias(tmp_path, monkeypatch):
    """Filtering only `/.well-known` was not enough.

    `GET /federation/peers` is unauthenticated and the landing page renders its `pending`
    array, so the raw-IP alias stayed on the public landing with a red "assay failed" badge
    even after observed_hubs was cleaned. One rule, every public surface.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub5.db"))
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://us.example")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token")

    from aimarket_hub.api import create_app

    db = HubDatabase(str(tmp_path / "hub5.db"))
    db.upsert_peer(_peer("https://hub.modelmarket.dev", KEY, "Competing Lab Hub"), status="active")
    db.upsert_peer(_peer("http://108.165.32.182:9083", KEY, "Competing Lab Hub"), status="pending")
    db.upsert_peer(_peer("https://a-real-stranger.example", OTHER_KEY, "Stranger"), status="pending")

    client = TestClient(create_app())

    public = client.get("/ai-market/v2/federation/peers").json()
    urls = [p["url"] for p in public["pending"]]
    assert "http://108.165.32.182:9083" not in urls, "the alias is still public"
    assert "https://a-real-stranger.example" in urls, "a genuine knock must stay visible"
    assert public["pending_count"] == len(urls), "the count must match what is shown"

    # The operator still sees everything.
    seen = client.get(
        "/ai-market/v2/federation/peers",
        headers={"Authorization": "Bearer test-admin-token"},
    ).json()
    assert "http://108.165.32.182:9083" in [p["url"] for p in seen["pending"]], (
        "the operator must still be able to see and act on the alias"
    )


def test_the_hub_withholds_a_pending_row_signed_with_its_OWN_key(tmp_path, monkeypatch):
    """The first alias to check is your own.

    A hub is never a peer of itself, so it holds no active row carrying its own key and
    `active_peer_with_public_key` can never match one. The alias guard therefore looked
    straight past the one identity a hub cannot be wrong about.

    Found live on 2026-09-05: hub.modelmarket.dev rendered `http://108.165.32.182:9083` in
    its own UNAPPROVED HUBS block with a red "assay failed" badge. That row's advertised key,
    the raw-IP endpoint's `signer_public_key` and the page's own `signer_public_key` were one
    and the same string — it was advertising itself to itself as an untrusted stranger.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "self.db"))
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://hub.example")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token")

    from aimarket_hub.api import create_app

    client = TestClient(create_app())
    own_key = client.get("/.well-known/ai-market.json").json()["signer_public_key"]
    assert own_key, "the hub must publish the key this test is about"

    db = HubDatabase(str(tmp_path / "self.db"))
    # No ACTIVE row anywhere carrying this key — that is the whole point.
    db.upsert_peer(_peer("http://203.0.113.7:9083", own_key, "Us, by raw IP"), status="pending")
    db.upsert_peer(_peer("https://a-real-stranger.example", OTHER_KEY, "Stranger"), status="pending")

    public = client.get("/ai-market/v2/federation/peers").json()
    urls = [p["url"] for p in public["pending"]]
    assert "http://203.0.113.7:9083" not in urls, "the hub is publishing itself as a stranger"
    assert "https://a-real-stranger.example" in urls, "a genuine knock must stay visible"
    assert public["pending_count"] == len(urls), "the count must match what is shown"

    # The operator still sees it, so the row can be cleaned up rather than silently vanishing.
    seen = client.get(
        "/ai-market/v2/federation/peers",
        headers={"Authorization": "Bearer test-admin-token"},
    ).json()
    assert "http://203.0.113.7:9083" in [p["url"] for p in seen["pending"]]
