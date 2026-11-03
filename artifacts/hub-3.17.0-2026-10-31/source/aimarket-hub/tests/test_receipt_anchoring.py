"""A work receipt issued by the hub ends up provable in HISTOR's receipts log — for real.

Two real systems: this hub with its provenance plugin, and HISTOR's `ReceiptLog` on its own
database. The only thing replaced is the network between them (HTTP is routed into HISTOR's
ASGI app). So a signature format that drifted between the two — the plugin signing different
bytes from the ones HISTOR verifies — fails here, not in production.
"""
from __future__ import annotations

import base64
import hashlib
import time
import urllib.parse

import pytest

pytest.importorskip("aimarket_provenance")
pytest.importorskip("histor.receipts")

from awr import canonicalize  # noqa: E402

from tests._mandate_kit import ECHO, funded_account, hub, key, list_static  # noqa: E402


@pytest.fixture
def histor_log(tmp_path):
    from histor.db import open_backend
    from histor.keys import issuer_key
    from histor.migrations import apply_migrations
    from histor.receipts import ReceiptLog
    from histor.store import Store

    backend = open_backend(tmp_path / "histor.sqlite3")
    apply_migrations(backend)
    store = Store(backend)
    key = issuer_key(tmp_path / "histor.key", create=True)
    log = ReceiptLog(store, key, set())
    yield log, key
    backend.close()


def _outbox(client):
    for plugin in client.app_ref.state.plugins.plugins:
        if getattr(plugin, "name", "") == "provenance":
            return plugin, plugin._anchors
    raise AssertionError("provenance plugin not loaded")


def test_an_issued_receipt_is_anchored_and_provable(monkeypatch, tmp_path, histor_log):
    log, histor_key = histor_log
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        plugin, outbox = _outbox(client)
        assert outbox is not None and outbox.enabled
        # HISTOR accepts exactly this hub's receipt key, as an operator would configure it.
        log.issuers = frozenset({outbox._key.did})

        class _Resp:
            def __init__(self, status, body):
                self.status_code, self._body, self.text = status, body, str(body)

            def json(self):
                return self._body

        def post(url, payload):
            assert url == "https://histor.test/api/v1/receipts/anchors"
            return _Resp(200, {"results": log.submit(payload["anchors"])})

        outbox._post = post

        list_static(db, price=0.004)
        _, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=ECHO)
        assert r.status_code == 200, r.text
        receipt = r.json()["provenance_receipt"]
        digest = receipt["digest_sri"]

        pending = client.get(f"/ai-market/v2/p/provenance/anchor/{receipt['receipt_id']}").json()
        assert pending["status"] == "pending"
        assert outbox.flush_once()["anchored"] == 1
        state = client.get(f"/ai-market/v2/p/provenance/anchor/{receipt['receipt_id']}").json()
        assert state["status"] == "anchored" and state["leaf_index"] == 0
        # The link must give back the SAME digest once a server decodes the query string —
        # base64 carries '+' and '/', and a raw '+' reads back as a space.
        query = urllib.parse.urlsplit(state["proof_url"]).query
        assert urllib.parse.parse_qs(query)["digest"] == [digest]

        # The proof, checked as an outsider would: the anchor names this receipt's digest and
        # the hub's key, and it hashes to the leaf the signed head covers.
        proof = log.proof(digest)
        assert proof["anchor"]["receiptDigest"] == digest
        assert proof["anchor"]["issuer"] == outbox._key.did
        from histor import merkle
        from histor.logbook import verify_document
        from histor.receipts import RECEIPT_STH_TYPE

        assert verify_document(proof["sth"], histor_key.did, RECEIPT_STH_TYPE)
        leaf = merkle.leaf_hash(canonicalize(proof["anchor"]))
        assert merkle.verify_inclusion(leaf, proof["leaf_index"], proof["tree_size"],
                                       [bytes.fromhex(h) for h in proof["audit_path"]],
                                       bytes.fromhex(proof["sth"]["rootHash"]))
        # and the receipt document itself really has that digest
        document = client.get(receipt["receipt_url"]).json()
        document = document.get("receipt", document)
        assert "sha256-" + base64.b64encode(hashlib.sha256(canonicalize(document)).digest()).decode() == digest


def _histor_app(tmp_path, monkeypatch, issuers: str):
    from fastapi.testclient import TestClient
    from histor.app import create_app
    from histor.config import load_settings
    from histor.service import build

    for k, v in {"HISTOR_DATA_DIR": str(tmp_path / "histor-data"), "HISTOR_OPERATOR_TOKEN": "t" * 32,
                 "HISTOR_CRAWL_INTERVAL_S": "0", "HISTOR_RECEIPT_ISSUERS": issuers}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("HISTOR_DATABASE_URL", raising=False)
    services = build(load_settings())
    return services, TestClient(create_app(services))


def _route_httpx_to(monkeypatch, histor_client):
    import httpx

    def fake_post(url, **kwargs):
        assert url.startswith("https://histor.test/"), url
        return histor_client.post(url[len("https://histor.test"):],
                                  **{k: v for k, v in kwargs.items() if k in ("json", "content")})

    monkeypatch.setattr(httpx, "post", fake_post)


def _issue_one(client, db):
    list_static(db, price=0.004)
    _, api_key = funded_account(client, db, 1.0)
    r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=ECHO)
    assert r.status_code == 200, r.text
    receipt = r.json()["provenance_receipt"]
    document = client.get(receipt["receipt_url"]).json()
    document = document.get("receipt", document)
    issuer = document["issuer"] if isinstance(document["issuer"], str) else document["issuer"]["id"]
    return receipt, issuer


def test_production_configuration_over_real_http(monkeypatch, tmp_path):
    """HISTOR trusts the issuer an operator reads off a live receipt (HISTOR_RECEIPT_ISSUERS),
    and the anchor travels through the outbox's own transport into HISTOR's HTTP route —
    not a stand-in for either. The sender thread runs while the hub does, and stops with it."""
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        _, outbox = _outbox(client)
        assert outbox._thread is not None and outbox._thread.is_alive(), "the sender thread never started"
        receipt, issuer = _issue_one(client, db)
        services, histor_client = _histor_app(tmp_path, monkeypatch, issuer)
        _route_httpx_to(monkeypatch, histor_client)
        assert outbox._post is None   # the default transport, as deployed
        assert outbox.flush_once()["anchored"] == 1
        proof = histor_client.get("/api/v1/receipts/proof", params={"digest": receipt["digest_sri"]})
        assert proof.status_code == 200 and proof.json()["anchor"]["issuer"] == issuer
        thread = outbox._thread
    assert not thread.is_alive(), "the sender thread outlived the hub"
    services.close()


def test_an_issuer_the_log_does_not_list_yet_is_retried_not_refused(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        _, outbox = _outbox(client)
        receipt, issuer = _issue_one(client, db)
        # the operator has not added this hub's key yet
        services, histor_client = _histor_app(tmp_path, monkeypatch, key(99).did)
        _route_httpx_to(monkeypatch, histor_client)
        counts = outbox.flush_once()
        assert counts["deferred"] == 1 and counts["refused"] == 0, counts
        assert outbox.status(receipt["digest_sri"])["status"] == "pending"
        # ...and then does: the same receipt lands, nothing was lost
        services.receipts.issuers = frozenset({issuer})
        assert outbox.flush_once()["anchored"] == 1
        assert outbox.status(receipt["digest_sri"])["status"] == "anchored"
        services.close()


def test_a_verdict_about_the_anchor_itself_is_final(monkeypatch, tmp_path):
    from histor.receipts import sign_anchor as histor_sign_anchor

    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        _, outbox = _outbox(client)
        receipt, issuer = _issue_one(client, db)
        squatter = key(98)
        services, histor_client = _histor_app(tmp_path, monkeypatch, f"{issuer},{squatter.did}")
        # someone else anchored this digest first
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        services.receipts.submit([histor_sign_anchor(squatter, receipt_digest=receipt["digest_sri"], issued_at=stamp)])
        _route_httpx_to(monkeypatch, histor_client)
        counts = outbox.flush_once()
        assert counts["refused"] == 1, counts
        state = outbox.status(receipt["digest_sri"])
        assert state["status"] == "refused" and "another issuer" in state["last_error"]
        assert outbox.flush_once()["sent"] == 0   # not retried
        services.close()


def test_histor_down_never_touches_an_invoke(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        _, outbox = _outbox(client)

        def down(url, payload):
            raise ConnectionError("histor unreachable")

        outbox._post = down
        list_static(db, price=0.004)
        _, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=ECHO)
        assert r.status_code == 200
        counts = outbox.flush_once()
        assert counts["failed"] == 1
        state = outbox.status(r.json()["provenance_receipt"]["digest_sri"])
        assert state["status"] == "pending" and state["attempts"] == 1
        assert "unreachable" in state["last_error"]


def test_anchoring_is_off_without_a_histor_url(monkeypatch, tmp_path):
    monkeypatch.delenv("AIMARKET_HISTOR_URL", raising=False)
    with hub(monkeypatch, tmp_path) as (client, db):
        _, outbox = _outbox(client)
        assert outbox is None


def test_a_proof_link_survives_a_plus_in_the_digest(tmp_path):
    """Base64 digests carry '+' about half the time; unencoded, a query string reads it as a
    space. Pinned with a digest that surely has one, not left to the luck of a live receipt."""
    import sqlite3

    from aimarket_provenance.anchoring import AnchorOutbox

    conn = sqlite3.connect(tmp_path / "outbox.db")
    conn.row_factory = sqlite3.Row
    outbox = AnchorOutbox(conn, key(1), url="https://histor.test")
    digest = next(d for d in ("sha256-" + base64.b64encode(hashlib.sha256(str(i).encode()).digest()).decode()
                              for i in range(100)) if "+" in d)
    outbox.enqueue(digest)
    conn.execute("UPDATE provenance_anchor_outbox SET status = 'anchored'")
    link = outbox.status(digest)["proof_url"]
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)["digest"] == [digest]
