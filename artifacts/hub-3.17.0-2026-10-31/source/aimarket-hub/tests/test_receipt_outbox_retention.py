"""The HISTOR outbox forgets anchored rows after a while; the anchor route does not.

Pinned: which rows retention may delete (anchored ones older than
AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS, aged by their real instant whatever clock format the
database wrote) and which it never may (pending, refused, unreadable, or re-read as no longer
anchored); that the sender thread prunes on its first tick and then at most hourly, and keeps
sending when a prune fails; and that once a row is gone the anchor route answers from the log
itself: anchored with the log's leaf index, not_queued on a 404, and unknown, never anchored,
when the log cannot say. Plain ``status()`` stays an outbox lookup, because the backfill reads
"not None" as "already queued".

The unit cases use a bare outbox on SQLite. The route cases use the real hub and a real
HISTOR app reached over its HTTP routes (test_receipt_anchoring's harness).
"""
from __future__ import annotations

import base64
import hashlib
import sqlite3
import time
import urllib.parse
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("aimarket_provenance")
pytest.importorskip("histor.receipts")

from aimarket_provenance.anchoring import AnchorOutbox

from tests._mandate_kit import hub, key
from tests.test_receipt_anchoring import _histor_app, _issue_one, _outbox, _route_httpx_to

ENV = "AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS"
LOG = "https://histor.test"
NOW = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
OLD = (NOW - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")


class _Resp:
    def __init__(self, status, body=None, *, broken_json=False):
        self.status_code, self._body, self._broken = status, body, broken_json
        self.text = str(body)

    def json(self):
        if self._broken:
            raise ValueError("not JSON")
        return self._body


def _logs_everything(url, payload):
    return _Resp(200, {"results": [{"receipt_digest": a["receiptDigest"], "status": "logged", "leaf_index": i}
                                   for i, a in enumerate(payload["anchors"])]})


def _no_log(url):
    raise AssertionError(f"the log was asked: {url}")


def _digest(n: int, *, plus: bool = False) -> str:
    candidates = ("sha256-" + base64.b64encode(hashlib.sha256(f"receipt-{n}-{i}".encode()).digest()).decode()
                  for i in range(1000))
    return next(d for d in candidates if ("+" in d) == plus)


def _bare_outbox(tmp_path, **kwargs):
    conn = sqlite3.connect(tmp_path / "outbox.db")
    conn.row_factory = sqlite3.Row
    return AnchorOutbox(conn, key(1), url=LOG, **kwargs), conn


def _row(conn, digest, status, anchored_at):
    conn.execute("INSERT INTO provenance_anchor_outbox (receipt_digest, issued_at, status, anchored_at) "
                 "VALUES (?, ?, ?, ?)", (digest, "2026-09-01T00:00:00Z", status, anchored_at))
    conn.commit()


def _left(conn) -> set[str]:
    """The rows another connection sees: a DELETE left uncommitted is not a deletion (on
    PostgreSQL it would also sit in an open transaction on the sender's connection)."""
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    other = sqlite3.connect(path)
    try:
        return {r[0] for r in other.execute("SELECT receipt_digest FROM provenance_anchor_outbox")}
    finally:
        other.close()


class _Connection:
    """The outbox's connection, writing down every DELETE it runs. With *flip*, the row is
    marked pending just before its DELETE runs, as a concurrent writer could."""

    def __init__(self, conn, *, flip: bool = False):
        self._conn, self._flip, self.deleted = conn, flip, []

    def execute(self, sql, params=()):
        if sql.lstrip().upper().startswith("DELETE"):
            self.deleted.append(params[0])
            if self._flip:
                self._conn.execute("UPDATE provenance_anchor_outbox SET status = 'pending' "
                                   "WHERE receipt_digest = ?", (params[0],))
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


# -- what retention deletes -------------------------------------------------------------

def test_an_anchored_row_goes_once_older_than_the_default_thirty_days(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV, raising=False)
    outbox, _ = _bare_outbox(tmp_path, post=_logs_everything)
    digest = _digest(1)
    outbox.enqueue(digest)
    assert outbox.flush_once()["anchored"] == 1   # anchored_at written by the database's own clock
    now = datetime.now(UTC)
    assert outbox.prune(now + timedelta(days=29)) == 0
    assert outbox.status(digest)["status"] == "anchored"
    assert outbox.prune(now + timedelta(days=31)) == 1
    assert outbox.status(digest) is None


def test_the_retention_is_read_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "7")
    outbox, conn = _bare_outbox(tmp_path)
    older, younger = _digest(1), _digest(2)
    _row(conn, older, "anchored", (NOW - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S"))
    _row(conn, younger, "anchored", (NOW - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"))
    assert outbox.prune(NOW) == 1
    assert _left(conn) == {younger}


def test_pending_and_refused_rows_are_never_pruned_whatever_their_age(monkeypatch, tmp_path):
    """A pending row is a receipt not yet delivered; a refused one is the only record of why
    an anchor failed. Neither is even offered to the DELETE."""
    monkeypatch.setenv(ENV, "1")
    outbox, conn = _bare_outbox(tmp_path)
    pending, refused, anchored = _digest(1), _digest(2), _digest(3)
    for digest, status in ((pending, "pending"), (refused, "refused"), (anchored, "anchored")):
        _row(conn, digest, status, OLD)
    conn.execute("UPDATE provenance_anchor_outbox SET created_at = ?", (OLD,))
    conn.commit()
    outbox._db = recorder = _Connection(conn)
    assert outbox.prune(NOW) == 1
    assert _left(conn) == {pending, refused}
    assert recorder.deleted == [anchored]


def test_a_row_that_is_no_longer_anchored_when_deleted_is_kept(monkeypatch, tmp_path):
    """The status read by the SELECT may be stale by the time of the DELETE; the DELETE checks
    it again rather than trusting the earlier read."""
    monkeypatch.setenv(ENV, "1")
    outbox, conn = _bare_outbox(tmp_path)
    digest = _digest(1)
    _row(conn, digest, "anchored", OLD)
    outbox._db = recorder = _Connection(conn, flip=True)
    assert outbox.prune(NOW) == 0
    assert recorder.deleted == [digest]
    assert conn.execute("SELECT status FROM provenance_anchor_outbox").fetchone()[0] == "pending"


@pytest.mark.parametrize("setting", ["0", "-5", "not-a-number", "nan", "inf"],
                         ids=["zero", "negative", "unreadable", "nan", "infinite"])
def test_a_retention_of_zero_or_less_keeps_everything(monkeypatch, tmp_path, setting):
    monkeypatch.setenv(ENV, setting)
    outbox, conn = _bare_outbox(tmp_path)
    digests = {_digest(1), _digest(2)}
    for digest in digests:
        _row(conn, digest, "anchored", OLD)
    assert outbox.prune(NOW) == 0
    assert _left(conn) == digests


def test_an_anchored_at_with_an_offset_is_aged_by_its_real_instant(monkeypatch, tmp_path):
    """On PostgreSQL anchored_at is NOW() as text in the session's time zone. Read as text,
    the east row below would look younger than the cutoff and the west row older, both by
    hours. A value with no offset is SQLite's datetime('now') and is UTC."""
    monkeypatch.setenv(ENV, "1")   # cutoff: 2026-09-26 00:00 UTC
    outbox, conn = _bare_outbox(tmp_path)
    rows = {
        "east": ("2026-09-26 02:30:00.123456+03", True),    # 2026-09-25 23:30 UTC
        "west": ("2026-09-25 22:00:00.5-05", False),        # 2026-09-26 03:00:00.5 UTC
        "utc_z": ("2026-09-25T23:00:00Z", True),
        "naive_older": ("2026-09-25 23:59:59", True),
        "naive_younger": ("2026-09-26 00:00:01", False),
    }
    digests = {name: _digest(i) for i, name in enumerate(rows)}
    for name, (anchored_at, _) in rows.items():
        _row(conn, digests[name], "anchored", anchored_at)
    assert outbox.prune(NOW) == 3
    assert _left(conn) == {digests[name] for name, (_, pruned) in rows.items() if not pruned}


def test_an_anchored_at_that_cannot_be_read_is_kept(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "1")
    outbox, conn = _bare_outbox(tmp_path)
    unreadable = {_digest(1), _digest(2)}
    for digest, anchored_at in zip(sorted(unreadable), ("", "last tuesday"), strict=True):
        _row(conn, digest, "anchored", anchored_at)
    readable = _digest(3)
    _row(conn, readable, "anchored", OLD)
    assert outbox.prune(NOW) == 1
    assert _left(conn) == unreadable


# -- the sender thread ------------------------------------------------------------------

class _Ticks:
    """Stands in for the stop event: lets the sender loop run *n* times, then stops it."""

    def __init__(self, n: int):
        self.left = n

    def wait(self, timeout):
        self.left -= 1
        return self.left < 0

    def set(self):
        self.left = -1


def test_a_failing_prune_never_stops_the_sender(tmp_path):
    """Every flush still happens, and a prune that keeps failing is retried hourly, not on
    every tick."""
    outbox, _ = _bare_outbox(tmp_path)
    now = [0.0]
    flushes, prunes = [], []

    def flush():
        now[0] += 1200.0
        flushes.append(now[0])
        return {"sent": 0}

    def broken(now_=None):
        prunes.append(now[0])
        raise RuntimeError("database is locked")

    outbox.flush_once = flush
    outbox.prune = broken
    outbox._monotonic = lambda: now[0]
    outbox._stop = _Ticks(7)
    outbox._run()
    assert len(flushes) == 7
    assert prunes == [1200.0, 4800.0, 8400.0]


def test_the_sender_prunes_on_its_first_tick_then_at_most_hourly(tmp_path):
    outbox, _ = _bare_outbox(tmp_path)
    assert outbox._monotonic is time.monotonic   # wall-clock jumps must not trigger or skip a prune
    now = [0.0]
    pruned_at = []

    def flush():
        now[0] += 1200.0                          # twenty minutes per tick
        return {"sent": 0}

    outbox.flush_once = flush
    outbox.prune = lambda now_=None: pruned_at.append(now[0]) or 0
    outbox._monotonic = lambda: now[0]
    outbox._stop = _Ticks(7)
    outbox._run()
    # The first tick prunes: a hub redeployed more often than hourly would otherwise never prune.
    assert pruned_at == [1200.0, 4800.0, 8400.0]


# -- what status() says without a row ---------------------------------------------------

def test_a_row_the_outbox_holds_is_answered_as_before_without_asking_the_log(tmp_path):
    outbox, _ = _bare_outbox(tmp_path, post=_logs_everything, get=_no_log)
    digest = _digest(1, plus=True)
    outbox.enqueue(digest)
    pending = outbox.status(digest, ask_log=True)
    assert pending == outbox.status(digest)
    assert set(pending) == {"receipt_digest", "status", "attempts", "leaf_index", "anchored_at", "log"}
    outbox.flush_once()
    anchored = outbox.status(digest, ask_log=True)
    assert anchored == outbox.status(digest)
    assert set(anchored) == {"receipt_digest", "status", "attempts", "leaf_index", "anchored_at", "log", "proof_url"}
    assert anchored["proof_url"] == f"{LOG}/api/v1/receipts/proof?digest={urllib.parse.quote(digest, safe='')}"


def test_only_an_explicit_ask_on_an_anchoring_outbox_reaches_the_log(monkeypatch, tmp_path):
    """The backfill reads status() as "already queued": asking the log there would cost a
    request per receipt, and an outage would count every receipt as queued."""
    outbox, conn = _bare_outbox(tmp_path, get=_no_log)
    assert outbox.status(_digest(1)) is None
    monkeypatch.delenv("AIMARKET_HISTOR_URL", raising=False)
    off = AnchorOutbox(conn, key(1), url="", get=_no_log)
    assert not off.enabled
    assert off.status(_digest(1), ask_log=True) is None


def _proof(digest, *, issuer=None, leaf_index=7):
    body = {"anchor": {"receiptDigest": digest, "issuer": issuer or key(1).did}, "tree_size": 9}
    if leaf_index is not None:
        body["leaf_index"] = leaf_index
    return body


def test_a_proof_the_log_holds_reads_anchored_from_the_log(tmp_path):
    digest = _digest(1, plus=True)
    asked = []

    def get(url):
        asked.append(url)
        return _Resp(200, _proof(digest))

    outbox, _ = _bare_outbox(tmp_path, get=get)
    proof_url = f"{LOG}/api/v1/receipts/proof?digest={urllib.parse.quote(digest, safe='')}"
    assert outbox.status(digest, ask_log=True) == {
        "receipt_digest": digest, "status": "anchored", "leaf_index": 7, "log": LOG,
        "proof_url": proof_url, "source": "log",
    }
    assert asked == [proof_url]
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(asked[0]).query)["digest"] == [digest]


def test_a_digest_the_log_does_not_hold_reads_as_no_row(tmp_path):
    outbox, _ = _bare_outbox(tmp_path, get=lambda url: _Resp(404, {"detail": "no anchor for that receipt digest"}))
    assert outbox.status(_digest(1), ask_log=True) is None


def _unreachable(url):
    raise ConnectionError("histor unreachable")


@pytest.mark.parametrize("answer, reason", [
    (_unreachable, "unreachable"),
    (lambda url: _Resp(503, {"detail": "down"}), "503"),
    (lambda url: _Resp(302, {}), "302"),
    (lambda url: _Resp(200, broken_json=True), "not JSON"),
    (lambda url: _Resp(200, _proof(_digest(2))), "different receipt"),
    (lambda url: _Resp(200, {"leaf_index": 7}), "different receipt"),
    (lambda url: _Resp(200, _proof(_digest(1), issuer=key(98).did)), "another issuer"),
    (lambda url: _Resp(200, _proof(_digest(1), leaf_index=None)), "no leaf index"),
    (lambda url: _Resp(200, _proof(_digest(1), leaf_index="7")), "no leaf index"),
    (lambda url: _Resp(200, _proof(_digest(1), leaf_index=True)), "no leaf index"),
    (lambda url: _Resp(200, _proof(_digest(1), leaf_index=-1)), "no leaf index"),
], ids=["outage", "server-error", "redirect", "not-json", "other-digest", "no-anchor",
        "other-issuer", "no-leaf", "text-leaf", "bool-leaf", "negative-leaf"])
def test_a_log_that_cannot_say_reads_unknown_never_anchored(tmp_path, answer, reason):
    outbox, _ = _bare_outbox(tmp_path, get=answer)
    digest = _digest(1)
    state = outbox.status(digest, ask_log=True)
    assert set(state) == {"receipt_digest", "status", "log", "last_error"}
    assert (state["receipt_digest"], state["status"], state["log"]) == (digest, "unknown", LOG)
    assert reason in state["last_error"] and len(state["last_error"]) <= 200


# -- the anchor route, against a real HISTOR --------------------------------------------

def _route_httpx_get_to(monkeypatch, histor_client) -> list[dict]:
    import httpx

    seen: list[dict] = []

    def fake_get(url, **kwargs):
        assert url.startswith(f"{LOG}/"), url
        seen.append(kwargs)
        return histor_client.get(url[len(LOG):])

    monkeypatch.setattr(httpx, "get", fake_get)
    return seen


def _anchor(client, receipt):
    r = client.get(f"/ai-market/v2/p/provenance/anchor/{receipt['receipt_id']}")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_pruned_receipt_still_reads_anchored_with_the_logs_leaf_index(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV, raising=False)
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL=LOG) as (client, db):
        _, outbox = _outbox(client)
        receipts = [_issue_one(client, db)[0], _issue_one(client, db)[0]]
        services, histor_client = _histor_app(tmp_path, monkeypatch, outbox._key.did)
        _route_httpx_to(monkeypatch, histor_client)
        gets = _route_httpx_get_to(monkeypatch, histor_client)
        assert outbox._get is None   # the default transport, as deployed
        assert outbox.flush_once()["anchored"] == 2
        before = {r["receipt_id"]: _anchor(client, r) for r in receipts}
        assert gets == []            # while the rows exist the log is not asked

        assert outbox.prune(datetime.now(UTC) + timedelta(days=31)) == 2
        for receipt in receipts:
            assert outbox.status(receipt["digest_sri"]) is None   # the row really is gone
            after = _anchor(client, receipt)
            logged = histor_client.get("/api/v1/receipts/proof", params={"digest": receipt["digest_sri"]}).json()
            assert after["status"] == "anchored" and after["source"] == "log"
            assert after["leaf_index"] == logged["leaf_index"] == before[receipt["receipt_id"]]["leaf_index"]
            assert after["proof_url"] == before[receipt["receipt_id"]]["proof_url"]
            assert (after["log"], after["digest_sri"]) == (LOG, receipt["digest_sri"])
        assert sorted(before[r["receipt_id"]]["leaf_index"] for r in receipts) == [0, 1]
        assert len(gets) == 2 and all(0 < g.get("timeout", 0) <= 5 for g in gets)
        services.close()


def test_a_receipt_the_log_never_saw_reads_not_queued(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL=LOG) as (client, db):
        _, outbox = _outbox(client)
        receipt, issuer = _issue_one(client, db)
        # as for a receipt issued before this hub anchored, and never backfilled
        outbox._db.execute("DELETE FROM provenance_anchor_outbox")
        outbox._db.commit()
        services, histor_client = _histor_app(tmp_path, monkeypatch, issuer)
        gets = _route_httpx_get_to(monkeypatch, histor_client)
        state = _anchor(client, receipt)
        assert state == {"receipt_id": receipt["receipt_id"], "digest_sri": receipt["digest_sri"],
                         "status": "not_queued"}
        assert len(gets) == 1
        services.close()


def test_a_log_outage_reads_unknown_on_the_route_never_anchored(monkeypatch, tmp_path):
    import httpx

    monkeypatch.delenv(ENV, raising=False)
    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL=LOG) as (client, db):
        _, outbox = _outbox(client)
        receipt, issuer = _issue_one(client, db)
        services, histor_client = _histor_app(tmp_path, monkeypatch, issuer)
        _route_httpx_to(monkeypatch, histor_client)
        assert outbox.flush_once()["anchored"] == 1
        assert outbox.prune(datetime.now(UTC) + timedelta(days=31)) == 1

        def down(url, **kwargs):
            raise httpx.ConnectError("histor unreachable")

        monkeypatch.setattr(httpx, "get", down)
        state = _anchor(client, receipt)
        assert state["status"] == "unknown" and "unreachable" in state["last_error"]
        assert "leaf_index" not in state and "proof_url" not in state and "source" not in state
        services.close()


def test_the_public_route_cannot_make_the_hub_hammer_the_log(tmp_path, monkeypatch):
    """The status route is public. Every request for a receipt the outbox holds no row for
    would otherwise be one more request to HISTOR, so answers are remembered: an anchor for
    an hour (it cannot change), "not in the log" for minutes, "could not ask" for seconds."""
    asked: list[str] = []
    answers = {"absent": _Resp(404), "down": _Resp(503)}
    current = {"answer": "absent"}

    def get(url):
        asked.append(url)
        return answers[current["answer"]]

    outbox, _ = _bare_outbox(tmp_path, get=get)
    clock = {"t": 1000.0}
    outbox._monotonic = lambda: clock["t"]
    digest = _digest(7)
    for _ in range(50):
        assert outbox.status(digest, ask_log=True) is None
    assert len(asked) == 1
    clock["t"] += 301                           # "absent" is re-asked after five minutes
    current["answer"] = "down"
    assert outbox.status(digest, ask_log=True)["status"] == "unknown"
    assert outbox.status(digest, ask_log=True)["status"] == "unknown"
    assert len(asked) == 2
    clock["t"] += 31                            # an outage is re-asked within a minute
    current["answer"] = "absent"
    assert outbox.status(digest, ask_log=True) is None and len(asked) == 3
    current["answer"] = "down"
    clock["t"] += 400
    outbox.status(digest, ask_log=True)         # fills the memory
    served = outbox.status(digest, ask_log=True)
    served["status"] = "anchored"               # a caller editing what it was served...
    assert outbox.status(digest, ask_log=True)["status"] == "unknown"   # ...changes nothing
    # the memory is bounded, oldest out first
    import aimarket_provenance.anchoring as anchoring

    monkeypatch.setattr(anchoring, "LOG_CACHE_SIZE", 3)
    for n in range(20, 26):
        outbox.status(_digest(n), ask_log=True)
    assert len(outbox._log_cache) == 3 and _digest(25) in outbox._log_cache
    assert _digest(20) not in outbox._log_cache


def test_a_naive_now_is_read_as_utc(tmp_path):
    outbox, conn = _bare_outbox(tmp_path)
    young, old = _digest(1), _digest(2)
    _row(conn, young, "anchored", (NOW - timedelta(days=29)).strftime("%Y-%m-%d %H:%M:%S"))
    _row(conn, old, "anchored", (NOW - timedelta(days=31)).strftime("%Y-%m-%d %H:%M:%S"))
    assert outbox.prune(NOW.replace(tzinfo=None)) == 1
    assert _left(conn) == {young}


def test_a_database_whose_times_cannot_be_read_says_so_once(tmp_path, caplog):
    """PostgreSQL with a non-ISO DateStyle writes 'Sat Sep 26 22:14:03 2026 MSK'. Nothing is
    deleted (safe), but retention would do nothing forever without a word."""
    outbox, conn = _bare_outbox(tmp_path)
    for n in (1, 2):
        _row(conn, _digest(n), "anchored", "Sat Sep 26 22:14:03.12 2026 MSK")
    with caplog.at_level("WARNING", logger="aimarket_provenance.anchoring"):
        assert outbox.prune(NOW) == 0
        assert outbox.prune(NOW) == 0
    warnings = [r for r in caplog.records if "retention cannot age them" in r.getMessage()]
    assert len(warnings) == 1
    assert _left(conn) == {_digest(1), _digest(2)}
