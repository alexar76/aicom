"""Scratch reproductions for the Pay-on-Verified audit (read-only on the repo)."""
import os
import sys

os.environ.setdefault("AIMARKET_ALLOW_DEMO_CREDIT", "1")
os.environ.setdefault("AIMARKET_AUTO_CRAWL", "0")
os.environ.setdefault("AIMARKET_VERIFY_METIS_URL", "http://127.0.0.1:8080")
os.environ.setdefault("AIMARKET_UPDATE_CHECK", "0")
os.environ.setdefault("AIMARKET_WELL_KNOWN_CACHE_S", "0")
os.environ.setdefault("AIMARKET_STATS_LIVE_CACHE_S", "0")

HUB = "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub"
sys.path.insert(0, HUB)
sys.path.insert(0, HUB + "/tests")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import test_verified_settlement as T  # noqa: E402


@pytest.fixture(autouse=True)
def _claims(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("AIMARKET_DEPOSIT_CLAIMS_DIR", str(tmp_path_factory.mktemp("claims")))


def _publisher(client, db):
    acct = client.post("/ai-market/v2/accounts", json={"label": "seller"}).json()
    db._conn.execute("UPDATE capabilities SET publisher_id = ? WHERE capability_id = ?",
                     (acct["account_id"], T.CAP["capability_id"]))
    db._conn.commit()
    return acct


def _balance(client, key):
    return client.get("/ai-market/v2/account", headers={"X-API-Key": key}).json()["balance_usd"]


def test_verified_pass_never_credits_publisher_share(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0")
    monkeypatch.setenv("AIMARKET_SIGNUP_GRANT_USD", "0")
    app, db = T._build(tmp_path, monkeypatch, T._MetisScript([("judged", True, 0.95)]))
    with TestClient(app) as client:
        seller = _publisher(client, db)
        start = _balance(client, seller["api_key"])
        channel_id, secret = T._open_channel(client)

        # Plain channel invoke: the seller is credited its share at capture.
        r = T._invoke(client, channel_id, secret)
        assert r.status_code == 200, r.text
        after_plain = _balance(client, seller["api_key"])

        # Same sale, Pay-on-Verified, passes verification and is captured.
        r = T._invoke(client, channel_id, secret, verify={**T.VERIFY, "wait": True})
        assert r.status_code == 200, r.text
        env = r.json()["verification"]
        after_verified = _balance(client, seller["api_key"])
        ch = T._channel_state(client, channel_id=channel_id)
        print("start", start, "after_plain", after_plain, "after_verified", after_verified,
              "env", env["status"], "used", ch["used_usd"])
        assert env["status"] == "settled" and env["settled"] is True
        assert ch["used_usd"] == pytest.approx(0.80)           # both sales captured
        assert after_plain - start == pytest.approx(0.28)      # 70% share on the plain sale
        # BUG: the verified (captured) sale credits the seller nothing
        assert after_verified == pytest.approx(after_plain)


def test_jury_never_sees_the_request_input(tmp_path, monkeypatch):
    """The audit prompt holds only the buyer-chosen intent and the output: a buyer can ask
    for X in `input` and state Y in `intent`; any honest judge then fails the delivery."""
    script = T._MetisScript([("judged", False, 0.05)])
    app, db = T._build(tmp_path, monkeypatch, script)
    with TestClient(app) as client:
        channel_id, secret = T._open_channel(client)
        body = {**T.CAP, "source_hub": "local", "input": {"text": "ZQX_REAL_REQUEST_42"},
                "verify": {"requested": True, "intent": "Summarise the French constitution in German",
                           "mode": "fast", "wait": True}}
        r = client.post("/ai-market/v2/invoke", json=body,
                        headers={"X-Payment-Channel": channel_id, "X-Payment-Channel-Secret": secret})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["result"]                              # buyer keeps the delivered work
        assert out["verification"]["status"] == "refunded"
        assert all("ZQX_REAL_REQUEST_42" not in p for p in script.prompts)
        ch = T._channel_state(client, channel_id=channel_id)
        assert ch["used_usd"] == pytest.approx(0.0)       # nothing paid
        assert "verify_failed" in T._reputation_types(db)  # and the seller is blamed


def test_credits_buyer_told_refunded_but_charged(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "5.00")
    app, db = T._build(tmp_path, monkeypatch, T._MetisScript([("judged", False, 0.1)]))
    with TestClient(app) as client:
        buyer = client.post("/ai-market/v2/accounts", json={"label": "buyer"}).json()
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": buyer["api_key"]},
                        json={**T.CAP, "source_hub": "local", "input": {"text": "paid"},
                              "verify": {**T.VERIFY, "wait": True}})
        assert r.status_code == 200, r.text
        out = r.json()
        acct = client.get("/ai-market/v2/account", headers={"X-API-Key": buyer["api_key"]}).json()
        print("verification", out["verification"]["status"], out["verification"]["reason"],
              "rejection", out.get("rejection_receipt", {}).get("refunded"),
              "spent", acct["spent_usd"], "balance", acct["balance_usd"])
        assert out["verification"]["status"] == "refunded"
        assert acct["spent_usd"] == pytest.approx(0.40)     # but the money is gone


def test_one_buyer_two_channels_mismatched_intent_slashes_stake(tmp_path, monkeypatch):
    """One buyer, two channels, three verified calls whose intent does not describe the
    input: every call is refunded and the publisher's stake is slashed."""
    script = T._MetisScript([("judged", False, 0.05)])
    app, db = T._build(tmp_path, monkeypatch, script)
    db.supply_stake_add("pub-translate", 50.0, tx_hash="")
    stake0 = db.supply_stake_get("pub-translate")
    with TestClient(app) as client:
        chans = [T._open_channel(client), T._open_channel(client)]
        for i in range(3):
            cid, sec = chans[i % 2]
            body = {**T.CAP, "source_hub": "local", "input": {"text": "hello"},
                    "verify": {"requested": True, "intent": "Write a sonnet about the sea",
                               "mode": "fast", "wait": True}}
            r = client.post("/ai-market/v2/invoke", json=body,
                            headers={"X-Payment-Channel": cid, "X-Payment-Channel-Secret": sec})
            assert r.status_code == 200, r.text
            assert r.json()["verification"]["status"] == "refunded"
        used = [T._channel_state(client, channel_id=c)["used_usd"] for c, _ in chans]
    stake1 = db.supply_stake_get("pub-translate")
    slashes = db._conn.execute("SELECT amount_usd, reason FROM supply_slash_events").fetchall()
    print("used", used, "stake", stake0, "->", stake1, "slashes", [dict(s) for s in slashes])
    assert used == [0.0, 0.0]
    assert stake1 < stake0
