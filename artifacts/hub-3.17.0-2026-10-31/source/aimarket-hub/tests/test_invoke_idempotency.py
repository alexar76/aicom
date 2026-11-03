"""Idempotency-Key on paid invokes: a retry after a timeout is answered, not bought again.

The outside review of 2026-10-22 asked what happens when "the client repeats a paid
operation after a timeout, when it is unknown whether the previous call completed". On the
credits rail the answer was: a second purchase.
"""
from __future__ import annotations

import time

import pytest

from tests._mandate_kit import balance, funded_account, hub, list_static

BODY = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "input": {"text": "hi"}, "source_hub": "local"}
INVOKE = "/ai-market/v2/invoke"


@pytest.fixture
def market(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        list_static(db, price=0.004)
        account, api_key = funded_account(client, db, 1.0)
        yield client, db, account, api_key


def _rows(db) -> list[dict]:
    rows = db._conn.execute("SELECT * FROM invoke_idempotency").fetchall()
    db._conn.commit()
    return [dict(r) for r in rows]


def test_a_retry_with_the_same_key_is_answered_once_and_charged_once(market):
    client, db, account, api_key = market
    headers = {"X-API-Key": api_key, "Idempotency-Key": "order-7f3a"}
    first = client.post(INVOKE, json=BODY, headers=headers)
    assert first.status_code == 200, first.text
    assert first.headers["x-aimarket-idempotency"] == "stored"
    assert balance(db, account) == pytest.approx(0.996)
    again = client.post(INVOKE, json=BODY, headers=headers)
    assert again.status_code == 200
    assert again.headers["x-aimarket-idempotency"] == "replayed"
    assert again.json() == first.json()
    assert balance(db, account) == pytest.approx(0.996)        # charged once
    # Without a key every request is a purchase, as before.
    for _ in range(2):
        assert client.post(INVOKE, json=BODY, headers={"X-API-Key": api_key}).status_code == 200
    assert balance(db, account) == pytest.approx(0.988)


def test_the_same_key_with_another_body_is_refused(market):
    client, db, account, api_key = market
    headers = {"X-API-Key": api_key, "Idempotency-Key": "k-1"}
    assert client.post(INVOKE, json=BODY, headers=headers).status_code == 200
    other = client.post(INVOKE, json={**BODY, "input": {"text": "bye"}}, headers=headers)
    assert other.status_code == 422
    assert other.json()["error"] == "idempotency_key_reused"
    assert balance(db, account) == pytest.approx(0.996)


def test_keys_belong_to_the_credential_that_pays(market):
    client, db, account, api_key = market
    other_account, other_key = funded_account(client, db, 1.0)
    for key in (api_key, other_key):
        r = client.post(INVOKE, json=BODY, headers={"X-API-Key": key, "Idempotency-Key": "shared-name"})
        assert r.headers["x-aimarket-idempotency"] == "stored"
    assert balance(db, account) == pytest.approx(0.996)
    assert balance(db, other_account) == pytest.approx(0.996)
    assert all(api_key not in str(r) and other_key not in str(r) for r in _rows(db))   # hashed, never kept


def test_a_first_request_still_running_or_lost_is_never_run_again(market):
    client, db, account, api_key = market
    import hashlib
    import json

    from aimarket_hub.idempotency import credential_scope

    scope = credential_scope({"x-api-key": api_key})
    body = json.dumps(BODY).encode()
    db._conn.execute(
        "INSERT INTO invoke_idempotency (scope, idem_key, request_sha256, status, created_at) VALUES (?, ?, ?, 'running', ?)",
        (scope, "lost-1", hashlib.sha256(body).hexdigest(), time.time()))
    db._conn.commit()
    headers = {"X-API-Key": api_key, "Idempotency-Key": "lost-1", "Content-Type": "application/json"}
    busy = client.post(INVOKE, content=body, headers=headers)
    assert busy.status_code == 409 and busy.json()["error"] == "idempotency_in_progress"
    db._conn.execute("UPDATE invoke_idempotency SET created_at = ? WHERE idem_key = 'lost-1'", (time.time() - 3600,))
    db._conn.commit()
    lost = client.post(INVOKE, content=body, headers=headers)
    assert lost.status_code == 409 and lost.json()["error"] == "idempotency_outcome_unknown"
    assert balance(db, account) == pytest.approx(1.0)          # nothing ran, nothing charged
    # A day later the key is free again.
    db._conn.execute("UPDATE invoke_idempotency SET created_at = ? WHERE idem_key = 'lost-1'", (time.time() - 90_000,))
    db._conn.commit()
    assert client.post(INVOKE, content=body, headers=headers).status_code == 200
    assert balance(db, account) == pytest.approx(0.996)


def test_answers_from_before_any_money_moved_are_not_kept(market):
    client, db, account, api_key = market
    bad = client.post(INVOKE, json=BODY, headers={"X-API-Key": "aimk_not-a-key", "Idempotency-Key": "k-401"})
    assert bad.status_code == 401
    assert _rows(db) == []                                      # a fixed credential retries afresh
    malformed = client.post(INVOKE, json=BODY, headers={"X-API-Key": api_key, "Idempotency-Key": "no spaces allowed"})
    assert malformed.status_code == 400 and malformed.json()["error"] == "idempotency_key_invalid"


def test_other_rails_say_the_key_does_not_apply(market):
    client, db, account, api_key = market
    r = client.post(INVOKE, json=BODY, headers={"Idempotency-Key": "anon-1"})
    assert r.headers["x-aimarket-idempotency"] == "not-applicable"
    assert _rows(db) == []
