"""A peer's escrow reaches a stranger two hops away, without an operator in the loop.

The federation is cyclic, so a monitor stops at the second hop and never fetches a peer's
peers. That is what bounds the graph — and it is why a hub over there used to arrive as a
name and a number, with nothing about it that could be checked. So each hub re-exports
what its peers declared: the peer's escrow travels with the peers list, and the reader can
go and look at the chain itself.

"Without an operator in the loop" is the property under test. The declaration is re-read
on EVERY crawl, so a peer that deploys an escrow tomorrow is re-exported with one on the
next pass, and a peer that withdraws it stops being re-exported with one. There is no env
var to set and no admin action, because a step an operator has to remember is a step that
does not happen.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer

ESCROW = "0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb"
PEER_ESCROW = "0xab6E20aE29A4c7C10C6131Da9721aE98201B6600"


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client, db


def _declared(address=PEER_ESCROW):
    return {
        "version": 1, "chain": "base", "chain_id": 8453, "network": "Base",
        "explorer": "https://basescan.org",
        "entries": [{"role": "escrow", "name": "AIMarketEscrow", "address": address}],
    }


def test_the_hub_publishes_its_own_escrow(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIFACTORY_CRYPTO_ENABLED="1", AIMARKET_CHAIN="base",
              AIMARKET_ESCROW_EVM_ADDRESS=ESCROW) as (client, _db):
        wk = client.get("/.well-known/ai-market.json").json()
        assert wk["contracts"]["chain_id"] == 8453
        roles = {e["role"]: e["address"] for e in wk["contracts"]["entries"]}
        assert roles["escrow"] == ESCROW


def test_a_peers_declaration_is_re_exported_in_our_peers_list(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIFACTORY_CRYPTO_ENABLED="1") as (client, db):
        db.upsert_peer(Peer(
            url="https://stranger.example", name="Stranger Hub",
            capabilities_count=0, trusted=True,
            declared_contracts=_declared(),
        ))
        peers = client.get("/.well-known/ai-market.json").json()["peers"]
        mine = next(p for p in peers if p["url"] == "https://stranger.example")
        assert mine["contracts"]["entries"][0]["address"] == PEER_ESCROW


def test_a_peer_that_declares_nothing_carries_no_contracts_key(monkeypatch, tmp_path):
    """Absent, not an empty object: `contracts: {}` reads as "asked and there is none"."""
    with _hub(monkeypatch, tmp_path, AIFACTORY_CRYPTO_ENABLED="1") as (client, db):
        db.upsert_peer(Peer(url="https://quiet.example", name="Quiet", trusted=True))
        peers = client.get("/.well-known/ai-market.json").json()["peers"]
        assert "contracts" not in next(p for p in peers if p["url"] == "https://quiet.example")


def test_an_escrow_that_APPEARS_later_is_picked_up_with_no_operator_action(monkeypatch, tmp_path):
    """The case the feature exists for: the peer had none, then deployed one."""
    with _hub(monkeypatch, tmp_path, AIFACTORY_CRYPTO_ENABLED="1") as (client, db):
        db.upsert_peer(Peer(url="https://grows.example", name="Grows", trusted=True))
        first = client.get("/.well-known/ai-market.json").json()["peers"]
        assert "contracts" not in next(p for p in first if p["url"] == "https://grows.example")

        # …the next crawl reads its well-known again and finds one.
        db.upsert_peer(Peer(
            url="https://grows.example", name="Grows", trusted=True,
            declared_contracts=_declared(),
        ))
        second = client.get("/.well-known/ai-market.json").json()["peers"]
        grown = next(p for p in second if p["url"] == "https://grows.example")
        assert grown["contracts"]["entries"][0]["address"] == PEER_ESCROW


def test_a_withdrawn_declaration_stops_being_re_exported(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIFACTORY_CRYPTO_ENABLED="1") as (client, db):
        db.upsert_peer(Peer(url="https://shrinks.example", name="Shrinks", trusted=True,
                            declared_contracts=_declared()))
        db.upsert_peer(Peer(url="https://shrinks.example", name="Shrinks", trusted=True))
        peers = client.get("/.well-known/ai-market.json").json()["peers"]
        assert "contracts" not in next(p for p in peers if p["url"] == "https://shrinks.example")


def test_the_declaration_round_trips_through_the_database(monkeypatch, tmp_path):
    """Migration 030 plus the three column lists database.py warns about: a column named in
    one list and missing from another blanks itself on every crawl with no error anywhere."""
    with _hub(monkeypatch, tmp_path) as (_client, db):
        db.upsert_peer(Peer(url="https://rt.example", name="RT", trusted=True,
                            declared_contracts=_declared()))
        again = db.get_peer("https://rt.example")
        assert again.declared_contracts["entries"][0]["address"] == PEER_ESCROW
        # and a second write of the SAME row must not blank it
        db.upsert_peer(Peer(url="https://rt.example", name="RT2", trusted=True,
                            declared_contracts=_declared()))
        assert db.get_peer("https://rt.example").declared_contracts["entries"]


def test_a_row_predating_the_migration_reads_as_no_declaration(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as (_client, db):
        db.upsert_peer(Peer(url="https://old.example", name="Old", trusted=True))
        db._conn.execute("UPDATE peers SET declared_contracts=NULL WHERE url=?",
                         ("https://old.example",))
        db._conn.commit()
        assert db.get_peer("https://old.example").declared_contracts == {}
