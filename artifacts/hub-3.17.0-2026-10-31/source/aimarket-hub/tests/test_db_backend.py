"""Database backend factory + single-winner claims.

Two production failure modes are pinned here:

* ``AIMARKET_DB_PATH`` used to override the explicit ``db_path`` ARGUMENT, so every
  subsystem that asked for its own SQLite file (channel ledger, provenance store) was
  silently handed the hub file instead — while still reporting its own path.
* ``claim_unique`` is the atomic INSERT-claim the stake-deposit burn rides on: exactly one
  concurrent writer may win, and a failure that is not a uniqueness violation must never be
  reported as "someone else won".
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

import os

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.db_backend import (
    DEFAULT_DB_PATH,
    SQLiteBackend,
    claim_unique,
    create_backend,
    single_winner_statement,
)
import aimarket_hub.db_backend as db_backend_mod


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """These tests are ABOUT the env vars — never inherit them from the runner."""
    monkeypatch.delenv("AIMARKET_DB_PATH", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # The "ignored env var" warning is deduplicated per (argument, env) pair for the life
    # of the process; a test that asserts on it must start from a clean slate.
    monkeypatch.setattr(db_backend_mod, "_reported_path_overrides", set())
    monkeypatch.setattr(db_backend_mod, "_env_db_predates_process", {})


def _open(**kwargs) -> SQLiteBackend:
    backend = create_backend(**kwargs)
    assert isinstance(backend, SQLiteBackend)
    return backend


class TestSQLitePathPrecedence:
    """Explicit argument > AIMARKET_DB_PATH > built-in default."""

    def test_no_argument_and_no_env_uses_the_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)          # DEFAULT_DB_PATH is relative
        backend = _open()
        assert backend.db_path == Path(DEFAULT_DB_PATH)
        backend.close()

    def test_no_argument_falls_back_to_the_env_var(self, tmp_path, monkeypatch):
        env_db = tmp_path / "env" / "hub.db"
        monkeypatch.setenv("AIMARKET_DB_PATH", str(env_db))
        backend = _open()
        assert backend.db_path == env_db
        backend.close()

    def test_the_hub_default_argument_still_honours_the_env_var(self, tmp_path, monkeypatch):
        """HubDatabase()'s own signature default is ``data/hub.db``. That is "no choice
        made", not a choice, so relocating the HUB database with AIMARKET_DB_PATH keeps
        working — the deployment behaviour this env var exists for."""
        env_db = tmp_path / "relocated.db"
        monkeypatch.setenv("AIMARKET_DB_PATH", str(env_db))
        backend = _open(db_path=DEFAULT_DB_PATH)
        assert backend.db_path == env_db
        backend.close()

    def test_an_explicit_path_wins_over_the_env_var(self, tmp_path, monkeypatch):
        """The aliasing bug: the channel ledger asks for channels.db, the env var names
        hub.db, and both used to end up as ONE file."""
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
        backend = _open(db_path=str(tmp_path / "channels.db"))
        assert backend.db_path == tmp_path / "channels.db"
        backend.close()

    def test_an_explicit_path_is_used_when_no_env_var_is_set(self, tmp_path):
        backend = _open(db_path=str(tmp_path / "provenance.db"))
        assert backend.db_path == tmp_path / "provenance.db"
        backend.close()

    def test_a_path_object_argument_wins_too(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
        backend = _open(db_path=tmp_path / "channels.db")
        assert backend.db_path == tmp_path / "channels.db"
        backend.close()

    def test_an_empty_env_var_is_not_a_path(self, tmp_path, monkeypatch):
        """``AIMARKET_DB_PATH=`` used to resolve to the empty string only because
        ``os.environ.get(name, default)`` returns the default just for a MISSING key."""
        monkeypatch.setenv("AIMARKET_DB_PATH", "   ")
        backend = _open(db_path=str(tmp_path / "explicit.db"))
        assert backend.db_path == tmp_path / "explicit.db"
        monkeypatch.chdir(tmp_path)
        fallback = _open()
        assert fallback.db_path == Path(DEFAULT_DB_PATH)
        backend.close()
        fallback.close()

    def test_two_subsystems_get_two_files(self, tmp_path, monkeypatch):
        """The consequence that matters: separate databases stay separate. With the env
        var winning, a row written through one backend was visible through the other."""
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
        hub = _open(db_path=str(tmp_path / "hub.db"))
        ledger = _open(db_path=str(tmp_path / "channels.db"))
        try:
            hub.executescript("CREATE TABLE marker (id INTEGER PRIMARY KEY);")
            hub.commit()
            with pytest.raises(sqlite3.OperationalError, match="no such table"):
                ledger.execute("SELECT 1 FROM marker")
        finally:
            hub.close()
            ledger.close()

    def test_the_ignored_env_var_is_logged_once_per_pair(self, tmp_path, monkeypatch, caplog):
        """Loud, not silent: an operator who relied on the aliasing must be able to find
        out from the log why the file moved — and not be drowned in repeats."""
        SQLiteBackend(tmp_path / "hub.db").close()      # a hub that already ran
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
        with caplog.at_level(logging.WARNING, logger="aimarket_hub.db_backend"):
            for _ in range(3):
                _open(db_path=str(tmp_path / "channels.db")).close()
        warnings = [r for r in caplog.records if "ignoring AIMARKET_DB_PATH" in r.getMessage()]
        assert len(warnings) == 1
        assert str(tmp_path / "channels.db") in warnings[0].getMessage()
        assert str(tmp_path / "hub.db") in warnings[0].getMessage()

    def test_the_upgrade_case_names_the_file_the_data_is_still_in(self, tmp_path, monkeypatch, caplog):
        """A hub that ran under the old precedence has this subsystem's tables INSIDE the
        env-var file. Splitting them apart starts an empty database — for the channel
        ledger that also empties ``consumed_deposits``, i.e. re-opens every spent on-chain
        deposit — so the situation has to be named, not just the path swap."""
        env_db = tmp_path / "hub.db"
        SQLiteBackend(env_db).close()                     # the pre-upgrade shared file
        monkeypatch.setenv("AIMARKET_DB_PATH", str(env_db))
        with caplog.at_level(logging.WARNING, logger="aimarket_hub.db_backend"):
            _open(db_path=str(tmp_path / "channels.db")).close()
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errors) == 1, [r.getMessage() for r in caplog.records]
        assert str(env_db) in errors[0].getMessage()

    def test_a_fresh_install_is_not_told_about_an_upgrade(self, tmp_path, monkeypatch, caplog):
        """No hub file when the process started: nothing was ever aliased into it. Both
        messages used to print on every first start of the standalone image — the ERROR one
        in capitals — and were the first thing a new operator read (2026-10-12)."""
        env_db = tmp_path / "hub.db"
        monkeypatch.setenv("AIMARKET_DB_PATH", str(env_db))
        with caplog.at_level(logging.INFO, logger="aimarket_hub.db_backend"):
            _open().close()                                   # the hub creates its file
            _open(db_path=str(tmp_path / "channels.db")).close()
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert [r for r in caplog.records if "fresh install" in r.getMessage()]

    def test_no_upgrade_error_when_the_requested_file_already_exists(self, tmp_path, monkeypatch, caplog):
        """Steady state after the migration: both files exist, nothing to move."""
        env_db = tmp_path / "hub.db"
        own_db = tmp_path / "channels.db"
        SQLiteBackend(env_db).close()
        SQLiteBackend(own_db).close()
        monkeypatch.setenv("AIMARKET_DB_PATH", str(env_db))
        with caplog.at_level(logging.WARNING, logger="aimarket_hub.db_backend"):
            _open(db_path=str(own_db)).close()
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_no_warning_when_the_paths_agree(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
        with caplog.at_level(logging.WARNING, logger="aimarket_hub.db_backend"):
            _open(db_path=str(tmp_path / "hub.db")).close()
        assert not [r for r in caplog.records if "ignoring AIMARKET_DB_PATH" in r.getMessage()]

    def test_hub_database_no_longer_reports_a_path_it_does_not_use(self, tmp_path, monkeypatch):
        """``HubDatabase.db_path`` and the file it actually opens must be the same file.
        They diverged whenever AIMARKET_DB_PATH was set, which is what confused the
        orphaned-hold reaper (it compares the two paths to decide whether it can read
        verified_settlements through its own connection)."""
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "hub.db"))
        db = HubDatabase(db_path=str(tmp_path / "somewhere-else.db"))
        try:
            assert Path(db._backend.db_path) == Path(db.db_path)
            assert (tmp_path / "somewhere-else.db").exists()
            assert not (tmp_path / "hub.db").exists()
        finally:
            db.close()


class TestClaimUnique:
    """The atomic single-winner INSERT behind the stake-deposit burn."""

    @staticmethod
    def _backend_with_claims(path) -> SQLiteBackend:
        backend = SQLiteBackend(path)
        backend.executescript(
            "CREATE TABLE IF NOT EXISTS claims (k TEXT PRIMARY KEY, v TEXT NOT NULL);"
        )
        backend.commit()
        return backend

    def test_first_claim_wins_and_the_second_loses(self, tmp_path):
        backend = self._backend_with_claims(tmp_path / "claims.db")
        try:
            sql = "INSERT INTO claims (k, v) VALUES (?, ?)"
            assert claim_unique(backend, sql, ("dep-1", "first")) is True
            assert claim_unique(backend, sql, ("dep-1", "second")) is False
            backend.execute("SELECT v FROM claims WHERE k = ?", ("dep-1",))
            assert backend.fetchone() == {"v": "first"}, "the loser must not overwrite"
        finally:
            backend.close()

    def test_the_winning_row_is_committed_immediately(self, tmp_path):
        """A claim only the writing transaction can see is not a claim: another connection
        (another worker) must be locked out the moment claim_unique returns True."""
        writer = self._backend_with_claims(tmp_path / "claims.db")
        reader = SQLiteBackend(tmp_path / "claims.db")
        try:
            assert claim_unique(writer, "INSERT INTO claims (k, v) VALUES (?, ?)", ("d", "1"))
            assert claim_unique(reader, "INSERT INTO claims (k, v) VALUES (?, ?)", ("d", "2")) is False
        finally:
            writer.close()
            reader.close()

    def test_a_non_uniqueness_failure_propagates(self, tmp_path):
        """Fail closed: a claim that could not be EVALUATED must not be reported as lost
        (the caller would treat it as "already claimed" and move on)."""
        backend = self._backend_with_claims(tmp_path / "claims.db")
        try:
            with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
                claim_unique(backend, "INSERT INTO claims (k, v) VALUES (?, ?)", ("x", None))
            with pytest.raises(sqlite3.OperationalError, match="no such table"):
                claim_unique(backend, "INSERT INTO nope (k) VALUES (?)", ("x",))
        finally:
            backend.close()

    def test_a_lost_claim_does_not_hold_the_write_lock(self, tmp_path):
        """SQLite leaves the implicit transaction open after the failed statement; if the
        loser never released it, the next writer would block until its busy timeout."""
        loser = self._backend_with_claims(tmp_path / "claims.db")
        other = SQLiteBackend(tmp_path / "claims.db")
        try:
            assert claim_unique(loser, "INSERT INTO claims (k, v) VALUES (?, ?)", ("d", "1"))
            assert claim_unique(loser, "INSERT INTO claims (k, v) VALUES (?, ?)", ("d", "2")) is False
            assert claim_unique(other, "INSERT INTO claims (k, v) VALUES (?, ?)", ("e", "1"))
        finally:
            loser.close()
            other.close()

    def test_exactly_one_of_many_threads_wins(self, tmp_path):
        backend = self._backend_with_claims(tmp_path / "claims.db")
        barrier = threading.Barrier(8, timeout=30)
        wins: list[int] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def run(i: int) -> None:
            barrier.wait()
            try:
                won = claim_unique(
                    backend, "INSERT INTO claims (k, v) VALUES (?, ?)", ("hot", str(i))
                )
            except BaseException as exc:      # noqa: BLE001 — recorded, asserted below
                with lock:
                    errors.append(exc)
                return
            if won:
                with lock:
                    wins.append(i)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        try:
            assert not errors, errors
            assert len(wins) == 1, wins
            backend.execute("SELECT COUNT(*) AS n FROM claims WHERE k = ?", ("hot",))
            assert backend.fetchone() == {"n": 1}
        finally:
            backend.close()

    def test_exactly_one_connection_wins(self, tmp_path):
        """The multi-worker shape: one file, one connection per racer."""
        seed = self._backend_with_claims(tmp_path / "claims.db")
        seed.close()
        backends = [SQLiteBackend(tmp_path / "claims.db") for _ in range(4)]
        barrier = threading.Barrier(len(backends), timeout=30)
        wins: list[int] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def run(i: int) -> None:
            barrier.wait()
            try:
                won = claim_unique(
                    backends[i], "INSERT INTO claims (k, v) VALUES (?, ?)", ("hot", str(i))
                )
            except BaseException as exc:      # noqa: BLE001 — recorded, asserted below
                with lock:
                    errors.append(exc)
                return
            if won:
                with lock:
                    wins.append(i)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(len(backends))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        try:
            assert not errors, errors
            assert len(wins) == 1, wins
            backends[0].execute("SELECT COUNT(*) AS n FROM claims WHERE k = ?", ("hot",))
            assert backends[0].fetchone() == {"n": 1}
        finally:
            for b in backends:
                b.close()


class TestClaimUniqueStatementShape:
    def test_both_clauses_are_added_for_the_caller(self):
        """Callers pass a plain INSERT. Without DO NOTHING a lost race is an exception on
        a shared connection; without RETURNING there is no reliable way to tell the winner
        from the loser."""
        built = single_winner_statement("INSERT INTO claims (k, v) VALUES (?, ?);")
        assert built == "INSERT INTO claims (k, v) VALUES (?, ?) ON CONFLICT DO NOTHING RETURNING 1"

    def test_caller_supplied_clauses_are_not_duplicated(self):
        sql = "INSERT INTO claims (k, v) VALUES (?, ?) ON CONFLICT DO NOTHING RETURNING k"
        assert single_winner_statement(sql) == sql
        conflict_only = "INSERT INTO claims (k, v) VALUES (?, ?) ON CONFLICT DO NOTHING"
        assert single_winner_statement(conflict_only) == f"{conflict_only} RETURNING 1"

    def test_a_do_update_conflict_clause_is_refused(self):
        """An upsert makes RETURNING yield a row for the LOSER too, so every racer would
        read "I won". The old substring test appended a second, contradictory DO NOTHING
        to it instead of rejecting the statement."""
        with pytest.raises(ValueError, match="DO NOTHING"):
            single_winner_statement(
                "INSERT INTO claims (k, v) VALUES (?, ?) "
                "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v"
            )

    def test_a_targeted_do_nothing_clause_is_accepted_not_duplicated(self):
        """``ON CONFLICT (k) DO NOTHING`` is already a correct claim clause. The substring
        test did not recognise it and stapled a second conflict clause on — legal SQL, but
        a claim statement nobody reviewing it would recognise."""
        sql = "INSERT INTO claims (k, v) VALUES (?, ?) ON CONFLICT (k) DO NOTHING"
        assert single_winner_statement(sql) == f"{sql} RETURNING 1"

    def test_a_targeted_claim_still_picks_one_winner(self, tmp_path):
        """The new refusal must not reject a legitimate targeted claim."""
        backend = SQLiteBackend(tmp_path / "claims.db")
        backend.executescript("CREATE TABLE claims (k TEXT PRIMARY KEY, v TEXT NOT NULL);")
        backend.commit()
        try:
            sql = "INSERT INTO claims (k, v) VALUES (?, ?) ON CONFLICT (k) DO NOTHING"
            assert claim_unique(backend, sql, ("a", "1")) is True
            assert claim_unique(backend, sql, ("a", "2")) is False
        finally:
            backend.close()

    def test_a_prebuilt_statement_still_claims_correctly(self, tmp_path):
        backend = SQLiteBackend(tmp_path / "claims.db")
        try:
            backend.executescript("CREATE TABLE claims (k TEXT PRIMARY KEY, v TEXT NOT NULL);")
            backend.commit()
            sql = "INSERT INTO claims (k, v) VALUES (?, ?) ON CONFLICT DO NOTHING"
            assert claim_unique(backend, sql, ("a", "1")) is True
            assert claim_unique(backend, sql, ("a", "2")) is False
        finally:
            backend.close()


# ── HubDatabase.db_path must name the file the backend actually opened ────────────────


class TestReportedDatabasePath:
    """`HubDatabase` used to store the ARGUMENT it was given. For the bare
    ``HubDatabase()`` shape that argument is the hub default, which means "no subsystem
    chose a path" — so `create_backend` then honours AIMARKET_DB_PATH and every read and
    write goes somewhere else. Health endpoints, backup tooling and log lines read this
    attribute; naming the wrong file is worse than naming none."""

    def test_bare_construction_reports_the_env_var_file_it_really_uses(self, tmp_path, monkeypatch):
        real = tmp_path / "elsewhere" / "hub.db"
        monkeypatch.setenv("AIMARKET_DB_PATH", str(real))
        monkeypatch.chdir(tmp_path)
        db = HubDatabase()
        try:
            assert db.db_path == real
            assert Path(db.db_path).exists()
            assert not (tmp_path / DEFAULT_DB_PATH).exists()
        finally:
            db._backend.close()

    def test_an_explicit_path_is_reported_as_given(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "env.db"))
        chosen = tmp_path / "chosen.db"
        db = HubDatabase(db_path=chosen)
        try:
            assert db.db_path == chosen
            assert chosen.exists()
        finally:
            db._backend.close()


# ── PostgreSQL pool accounting ───────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self.rowcount = len(self._rows)
        self.description = tuple((k,) for k in (self._rows[0] if self._rows else {}))

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _FakeConn:
    def __init__(self, name: str, log: list[str]):
        self.name = name
        self._log = log
        self.raise_on = ""
        self.rows: list[dict] = []
        self.statements: list[str] = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if self.raise_on and self.raise_on in sql:
            raise RuntimeError(f"boom: {sql}")
        return _FakeCursor(self.rows)

    def executemany(self, sql, seq):
        self.statements.append(sql)
        return _FakeCursor([])

    def cursor(self):
        return _FakeCursor(self.rows)

    def commit(self):
        self._log.append(f"commit:{self.name}")

    def rollback(self):
        self._log.append(f"rollback:{self.name}")


class _FakePool:
    """A pool that behaves like the real one where it matters: a finite number of slots,
    and blocking/failing once they are all checked out."""

    def __init__(self, max_size: int = 2):
        self.max_size = max_size
        self.outstanding = 0
        self.peak = 0
        self.gets = 0
        self.puts = 0
        self.closed = False
        self.log: list[str] = []
        self.conns: list[_FakeConn] = []

    def getconn(self):
        if self.outstanding >= self.max_size:
            raise AssertionError(
                f"pool exhausted: {self.outstanding} of {self.max_size} connections "
                "checked out and never returned"
            )
        self.outstanding += 1
        self.peak = max(self.peak, self.outstanding)
        self.gets += 1
        conn = _FakeConn(f"c{self.gets}", self.log)
        self.conns.append(conn)
        return conn

    def putconn(self, conn):
        self.outstanding -= 1
        self.puts += 1
        if self.outstanding < 0:
            raise AssertionError("putconn called more often than getconn")

    def close(self):
        self.closed = True


class TestUpsertConflictKeys:
    """`INSERT OR REPLACE` must translate to a conflict key the Postgres table HAS.

    The translator falls back to `ON CONFLICT (id)` for any table it does not know, which
    is valid SQL against a table with no `id` — so the failure is a runtime exception on
    the Postgres deployments only, and any caller that swallows exceptions turns it into a
    silent zero. `peer_preview_capabilities` did exactly that: every knocking hub on
    hub.attestedmemory.net displayed "capabilities: 0" while the peers offered dozens.
    """

    def test_every_upsert_target_has_a_declared_conflict_key(self):
        import re

        pkg = Path(db_backend_mod.__file__).parent
        targets: set[str] = set()
        for path in pkg.rglob("*.py"):
            for match in re.finditer(
                r"INSERT\s+OR\s+REPLACE\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                path.read_text(encoding="utf-8"),
                re.I,
            ):
                targets.add(match.group(1))
        # The scan itself must not be what breaks: if the statement form ever changes,
        # this asserts loudly instead of passing on an empty set.
        assert targets, "no INSERT OR REPLACE found — re-anchor this guard"
        declared = set(_upsert_default_conflict_keys())
        missing = sorted(targets - declared)
        assert not missing, (
            "these tables upsert with no declared conflict key, so Postgres gets "
            f"ON CONFLICT (id): {missing}"
        )

    def test_the_preview_table_conflicts_on_its_primary_key(self):
        sql = db_backend_mod.sqlite_to_pg(
            "INSERT OR REPLACE INTO peer_preview_capabilities "
            "(peer_url, capability_id, product_id, name) VALUES (?, ?, ?, ?)"
        )
        assert "ON CONFLICT (peer_url, capability_id, product_id)" in sql
        assert "ON CONFLICT (id)" not in sql
        # And the migration's key is the one we claim it is.
        from aimarket_hub import migrations

        src = Path(migrations.__file__).read_text(encoding="utf-8")
        table = src.split("CREATE TABLE IF NOT EXISTS peer_preview_capabilities", 1)[1]
        assert "PRIMARY KEY (peer_url, capability_id, product_id)" in table.split(");", 1)[0]


def _upsert_default_conflict_keys() -> list[str]:
    """The tables `sqlite_to_pg` knows a conflict key for, read from its own source.

    The map is a local inside the function, so it cannot be imported; scraping the one
    literal is still better than duplicating the list in the test and letting the two
    drift apart silently.
    """
    import re

    src = Path(db_backend_mod.__file__).read_text(encoding="utf-8")
    block = src.split("_DEFAULT_CONFLICT: dict[str, list[str]] = {", 1)[1].split("}", 1)[0]
    return re.findall(r'^\s*"([a-zA-Z_][a-zA-Z0-9_]*)":', block, re.M)


def _pg_backend(max_size: int = 2):
    """A PostgresBackend wired to a fake pool. `__init__` is bypassed because it imports
    psycopg and dials a server; every method under test only touches the pool."""
    backend = object.__new__(db_backend_mod.PostgresBackend)
    pool = _FakePool(max_size=max_size)
    backend._pool = pool
    backend._last_conn = None
    backend._last_cursor = None
    backend._dirty = False
    return backend, pool


class TestPostgresPoolAccounting:
    def test_repeated_reads_do_not_consume_the_pool(self):
        """The leak: execute() checked a connection out and only commit()/rollback() ever
        returned one, so a read-only query — which never commits — kept its slot forever.
        Twenty reads against a two-slot pool used to hang the ninth caller."""
        backend, pool = _pg_backend(max_size=2)
        for i in range(20):
            cur = backend.execute("SELECT version FROM _migrations WHERE version > ?", (i,))
            assert backend.fetchall() == []
            assert cur.rowcount == 0
            assert pool.outstanding == 0, f"leaked after read {i}"
        assert pool.gets == pool.puts == 20
        assert pool.peak == 1

    def test_a_read_with_rows_is_materialised_before_the_slot_goes_back(self):
        backend, pool = _pg_backend()
        rows = [{"version": 1, "name": "a"}, {"version": 2, "name": "b"}]
        backend._pool.getconn = _rows_pool(pool, rows)
        backend.execute("SELECT version, name FROM _migrations")
        assert pool.outstanding == 0
        # Rows survive the connection going home — this is what made the release safe.
        assert backend.fetchall() == rows
        assert backend.rowcount == 2
        backend.execute("SELECT version, name FROM _migrations")
        assert backend.fetchone() == {"version": 1, "name": "a"}
        assert backend.fetchone() == {"version": 2, "name": "b"}
        assert backend.fetchone() is None
        assert pool.outstanding == 0

    def test_a_failing_read_returns_its_slot_and_rolls_back(self):
        backend, pool = _pg_backend()
        original = pool.getconn

        def poisoned():
            conn = original()
            conn.raise_on = "SELECT"
            return conn

        pool.getconn = poisoned
        with pytest.raises(RuntimeError):
            backend.execute("SELECT 1")
        assert pool.outstanding == 0
        assert pool.puts == 1
        # A connection handed back mid-failed-transaction poisons the NEXT borrower.
        assert pool.log == ["rollback:c1"]

    def test_a_write_holds_one_slot_until_commit_then_returns_it(self):
        backend, pool = _pg_backend()
        backend.execute("INSERT INTO channels (id) VALUES (?)", ("ch",))
        assert pool.outstanding == 1
        # A second statement joins the SAME transaction instead of taking another slot.
        backend.execute("UPDATE channels SET status = ?", ("open",))
        assert pool.outstanding == 1
        assert pool.gets == 1
        # A read inside an open write transaction must NOT release the connection.
        backend.execute("SELECT status FROM channels")
        assert pool.outstanding == 1
        backend.commit()
        assert pool.outstanding == 0
        assert pool.log == ["commit:c1"]
        assert pool.gets == pool.puts == 1

    def test_a_rollback_returns_the_slot(self):
        backend, pool = _pg_backend()
        backend.execute("INSERT INTO channels (id) VALUES (?)", ("ch",))
        backend.rollback()
        assert pool.outstanding == 0
        assert pool.log == ["rollback:c1"]
        # And a no-op commit afterwards must not double-return anything.
        backend.commit()
        backend.rollback()
        assert pool.puts == 1

    def test_a_failing_write_returns_its_slot(self):
        backend, pool = _pg_backend()
        original = pool.getconn

        def poisoned():
            conn = original()
            conn.raise_on = "INSERT"
            return conn

        pool.getconn = poisoned
        with pytest.raises(RuntimeError):
            backend.execute("INSERT INTO channels (id) VALUES (?)", ("ch",))
        assert pool.outstanding == 0
        assert pool.log == ["rollback:c1"]
        # The next caller gets a clean slot, not a wedged one.
        backend.execute("SELECT 1")
        assert pool.outstanding == 0

    def test_executemany_and_executescript_balance_too(self):
        backend, pool = _pg_backend()
        backend.executemany("INSERT INTO channels (id) VALUES (?)", [("a",), ("b",)])
        assert pool.outstanding == 1
        backend.commit()
        assert pool.outstanding == 0

        class _Tx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        conn_holder = {}
        original = pool.getconn

        def with_tx():
            conn = original()
            conn.transaction = lambda: _Tx()
            conn_holder["conn"] = conn
            return conn

        pool.getconn = with_tx
        backend.executescript("CREATE TABLE t (a INT); CREATE INDEX i ON t(a);")
        # executescript's own transaction block already committed — nothing is pending,
        # so waiting for a commit() the caller has no reason to make would leak the slot.
        assert pool.outstanding == 0
        assert len(conn_holder["conn"].statements) == 2

    def test_close_returns_the_held_connection_before_closing_the_pool(self):
        backend, pool = _pg_backend()
        backend.execute("INSERT INTO channels (id) VALUES (?)", ("ch",))
        assert pool.outstanding == 1
        backend.close()
        assert pool.outstanding == 0
        assert pool.closed is True

    def test_cursor_marks_the_connection_dirty_so_it_is_not_released_early(self):
        """`cursor()` hands out a raw cursor we cannot observe, so the connection has to be
        held until an explicit commit/rollback."""
        backend, pool = _pg_backend()
        backend.cursor()
        assert pool.outstanding == 1
        backend.execute("SELECT 1")
        assert pool.outstanding == 1
        backend.rollback()
        assert pool.outstanding == 0


def _rows_pool(pool, rows):
    original = pool.getconn

    def getconn():
        conn = original()
        conn.rows = rows
        return conn

    return getconn


class TestReadOnlySqlClassification:
    """Only a certainly-read-only statement may release its pooled connection early. The
    unsure direction must be False: releasing under an uncommitted write or a row lock
    would be a correctness bug, while a false negative merely holds the slot as before."""

    @pytest.mark.parametrize("sql", [
        "SELECT 1",
        "  \n SELECT version FROM _migrations ORDER BY version",
        "-- a comment\nSELECT * FROM peers WHERE url = %s",
        "(SELECT count(*) FROM channels)",
        "SELECT c.id FROM channels c JOIN peers p ON p.url = c.source_hub",
        "SELECT created_at, updated_at FROM capabilities",
    ])
    def test_reads(self, sql):
        assert db_backend_mod.is_read_only_sql(sql) is True

    @pytest.mark.parametrize("sql", [
        "INSERT INTO channels (id) VALUES (%s)",
        "INSERT INTO claims (k) VALUES (%s) ON CONFLICT DO NOTHING RETURNING 1",
        "UPDATE channels SET status = 'closed'",
        "DELETE FROM channels",
        "SELECT id FROM channels WHERE id = %s FOR UPDATE",
        "SELECT id FROM channels FOR NO KEY UPDATE",
        "SELECT * INTO archived FROM channels",
        "CREATE TABLE t (a INT)",
        "SELECT 1; INSERT INTO channels (id) VALUES ('x')",
        "SET search_path = public",
        "SELECT nextval('seq')",
        "SELECT pg_advisory_lock(1)",
        "",
    ])
    def test_not_reads(self, sql):
        assert db_backend_mod.is_read_only_sql(sql) is False


# ── The one-time migration out of the aliased state ──────────────────────────────────
#
# Fixing the precedence is only half the job. A hub that ALREADY ran with AIMARKET_DB_PATH
# set has its channel ledger inside the hub file; after the fix the ledger opens a brand-new
# empty channels.db, which loses the open channels AND resets `consumed_deposits`, the guard
# that makes an on-chain deposit single-use.

_SPLIT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "split_aliased_sqlite_db.py"


def _load_split_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("split_aliased_sqlite_db", _SPLIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def split_mod():
    return _load_split_module()


def _make_aliased_db(path: Path) -> dict[str, int]:
    """The real aliased shape: ONE file holding the hub index tables AND the ledger tables,
    produced by the same Migrations the hub runs."""
    from aimarket_hub.migrations import Migrations

    backend = SQLiteBackend(path)
    try:
        Migrations(backend).apply()
        backend.execute(
            "INSERT INTO channels (channel_id, balance_cents, original_deposit_cents, "
            "expires_at) VALUES (?, ?, ?, ?)",
            ("ch_open_1", 5000, 5000, "2027-01-01T00:00:00Z"),
        )
        backend.execute(
            "INSERT INTO channels (channel_id, balance_cents, original_deposit_cents, "
            "expires_at) VALUES (?, ?, ?, ?)",
            ("ch_open_2", 250, 1000, "2027-01-01T00:00:00Z"),
        )
        backend.execute(
            "INSERT INTO consumed_deposits (chain, tx_hash, channel_id, amount_cents) "
            "VALUES (?, ?, ?, ?)",
            ("base", "0xdeadbeef", "ch_open_1", 5000),
        )
        backend.execute(
            "INSERT INTO debited_receipts (receipt_id, channel_id, amount_cents) "
            "VALUES (?, ?, ?)",
            ("rcpt_1", "ch_open_2", 750),
        )
        backend.execute(
            "INSERT INTO peers (url, name) VALUES (?, ?)", ("https://peer", "peer")
        )
        backend.commit()
    finally:
        backend.close()
    return {
        "channels": 2, "debited_receipts": 1, "consumed_deposits": 1,
        "channel_holds": 0, "channel_payout_obligations": 0,
    }


def _counts(path: Path, tables) -> dict[str, int]:
    conn = sqlite3.connect(str(path))
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables
        }
    finally:
        conn.close()


class TestSplitAliasedDatabase:
    def test_it_copies_the_ledger_into_its_own_file_and_verifies_the_counts(
        self, tmp_path, split_mod
    ):
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        expected = _make_aliased_db(source)

        result = split_mod.split_database(source, target, "channels")

        assert result["status"] == "copied"
        assert result["counts"] == expected
        assert result["target_counts"] == expected
        assert _counts(target, expected) == expected
        # The deposit-replay guard came across intact — an empty one would let an
        # already-credited deposit be presented again.
        conn = sqlite3.connect(str(target))
        try:
            assert conn.execute(
                "SELECT chain, tx_hash, amount_cents FROM consumed_deposits"
            ).fetchall() == [("base", "0xdeadbeef", 5000)]
            assert sorted(
                r[0] for r in conn.execute("SELECT channel_id FROM channels")
            ) == ["ch_open_1", "ch_open_2"]
            # Indexes travelled with the tables.
            names = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'")
            }
            assert {"idx_channels_status", "idx_channels_wallet"} <= names
        finally:
            conn.close()

    def test_the_source_is_never_modified(self, tmp_path, split_mod):
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        expected = _make_aliased_db(source)
        before = source.read_bytes()

        split_mod.split_database(source, target, "channels")

        assert _counts(source, expected) == expected
        assert source.read_bytes() == before
        assert _counts(source, ("peers",)) == {"peers": 1}

    def test_the_migration_marks_travel_so_the_ledger_does_not_replay_ddl(
        self, tmp_path, split_mod
    ):
        """Without the `_migrations` rows the ledger replays its migrations against
        already-migrated tables — `ALTER TABLE channels ADD COLUMN secret_hash` raises and
        `Migrations.apply()` re-raises, so the hub refuses to start."""
        from aimarket_hub.migrations import Migrations, channel_ledger_versions

        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        _make_aliased_db(source)
        result = split_mod.split_database(source, target, "channels")
        assert sorted(result["migration_marks"]) == sorted(channel_ledger_versions())

        backend = SQLiteBackend(target)
        try:
            assert Migrations(backend).apply(subsystem="channels") == 0
        finally:
            backend.close()

    def test_it_is_idempotent(self, tmp_path, split_mod):
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        expected = _make_aliased_db(source)
        split_mod.split_database(source, target, "channels")
        digest = target.read_bytes()

        again = split_mod.split_database(source, target, "channels")

        assert again["status"] == "already_split"
        assert again["prior_runs"] == 1
        assert _counts(target, expected) == expected
        assert target.read_bytes() == digest  # a second run writes nothing at all

    def test_it_refuses_a_target_holding_different_rows(self, tmp_path, split_mod):
        """Never merge, never overwrite: a run against the wrong file must not duplicate or
        clobber a live ledger."""
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        _make_aliased_db(source)
        other = _make_aliased_db(target)  # a DIFFERENT populated ledger
        conn = sqlite3.connect(str(target))
        try:
            conn.execute(
                "INSERT INTO channels (channel_id, balance_cents, "
                "original_deposit_cents, expires_at) VALUES ('ch_x', 1, 1, 'z')"
            )
            conn.commit()
        finally:
            conn.close()
        before = target.read_bytes()

        with pytest.raises(split_mod.Refused) as exc:
            split_mod.split_database(source, target, "channels")

        assert "do NOT match" in str(exc.value)
        assert target.read_bytes() == before
        assert _counts(target, other)["channels"] == 3

    def test_it_refuses_source_equal_to_target_and_a_missing_source(self, tmp_path, split_mod):
        source = tmp_path / "hub.db"
        _make_aliased_db(source)
        with pytest.raises(split_mod.Refused):
            split_mod.split_database(source, source, "channels")
        with pytest.raises(split_mod.Refused):
            split_mod.split_database(tmp_path / "nope.db", tmp_path / "c.db", "channels")
        with pytest.raises(split_mod.Refused):
            split_mod.split_database(source, tmp_path / "c.db", "nonexistent-subsystem")

    def test_a_source_without_ledger_tables_is_a_no_op(self, tmp_path, split_mod):
        source, target = tmp_path / "plain.db", tmp_path / "channels.db"
        conn = sqlite3.connect(str(source))
        try:
            conn.execute("CREATE TABLE capabilities (id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()

        result = split_mod.split_database(source, target, "channels")

        assert result["status"] == "not_aliased"
        assert not target.exists()

    def test_dry_run_writes_nothing(self, tmp_path, split_mod):
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        expected = _make_aliased_db(source)

        result = split_mod.split_database(source, target, "channels", dry_run=True)

        assert result["status"] == "would_copy"
        assert result["counts"] == expected
        assert result["aliased_with_hub_tables"] == ["capabilities", "peers"]
        assert not target.exists()

    def test_a_verification_failure_rolls_the_target_back(self, tmp_path, split_mod, monkeypatch):
        """If the copied counts ever disagree with the source, the target must end up with
        nothing rather than a partial ledger."""
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        _make_aliased_db(source)
        real_count = split_mod._count
        state = {"n": 0}

        def lying_count(conn, schema, table):
            state["n"] += 1
            # The first five calls count the SOURCE tables; the next five are the
            # post-copy verification inside the target transaction.
            if state["n"] > 5:
                return real_count(conn, schema, table) + 1
            return real_count(conn, schema, table)

        monkeypatch.setattr(split_mod, "_count", lying_count)
        with pytest.raises(split_mod.VerifyFailed):
            split_mod.split_database(source, target, "channels")

        # Rolled all the way back: not even the table DDL survived, so there is no
        # partially-populated ledger for the hub to start serving from.
        conn = sqlite3.connect(str(target))
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        finally:
            conn.close()
        assert "channels" not in names
        assert _counts(source, ("channels",)) == {"channels": 2}

    def test_the_cli_reports_and_exits_zero(self, tmp_path, split_mod, capsys):
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        _make_aliased_db(source)
        code = split_mod.main(
            ["--source", str(source), "--target", str(target), "--subsystem", "channels"]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert '"status": "copied"' in out
        assert _counts(target, ("channels",)) == {"channels": 2}

    def test_the_cli_exit_codes_distinguish_refusal_from_verification_failure(
        self, tmp_path, split_mod, monkeypatch
    ):
        source, target = tmp_path / "hub.db", tmp_path / "channels.db"
        _make_aliased_db(source)
        assert split_mod.main(["--source", str(source), "--target", str(source)]) == 2
        monkeypatch.setattr(
            split_mod, "split_database",
            lambda *a, **k: (_ for _ in ()).throw(split_mod.VerifyFailed("counts")),
        )
        assert split_mod.main(["--source", str(source), "--target", str(target)]) == 3


# ── PostgreSQL: the dialect boundary, against a REAL server ──────────────────


def _pg_url() -> str:
    """A Postgres to test against, or "" to skip.

    Gated on an env var rather than assumed: CI has no server, and a test that silently
    passes because it never connected is worse than one that says it skipped.
    """
    return (os.environ.get("AIMARKET_TEST_DATABASE_URL", "") or "").strip()


pg_only = pytest.mark.skipif(
    not _pg_url(),
    reason="set AIMARKET_TEST_DATABASE_URL to a scratch Postgres to run these",
)


@pytest.fixture
def pg_backend():
    """A migrated backend on the scratch database, with the tables these tests touch empty.

    No per-test schema: the pool opens connections eagerly (min_size=2), so a search_path
    set after construction does not reach them — DDL lands in one schema and the next
    statement looks for it in another. Migrations are idempotent, so applying them and
    truncating is both simpler and closer to how a real deployment starts up.
    """
    from aimarket_hub.db_backend import create_backend
    from aimarket_hub.migrations import Migrations

    backend = create_backend(database_url=_pg_url())
    Migrations(backend).apply()
    with backend.get_connection() as conn:
        conn.execute("TRUNCATE channels, verified_settlements")
        conn.commit()
    return backend


@pg_only
class TestPostgresDialectBoundary:
    """What used to be "unverified by code reading only".

    Two defects lived here, and both were invisible without a real server: the connection
    handed to callers did not translate SQL at all, and its rows did not support the
    positional access `sqlite3.Row` allows. Between them, EVERY parameterized statement and
    EVERY `fetchone()[0]` in the hub failed the moment DATABASE_URL was set — while the
    migrations applied cleanly, because DDL carries no parameters and no row reads.
    """

    def test_all_migrations_apply(self, pg_backend):
        from aimarket_hub.migrations import MIGRATIONS, Migrations

        applied = Migrations(pg_backend).applied_versions()
        assert applied == {v for v, _n, _u, _d in MIGRATIONS}

    def test_a_parameterized_statement_is_translated(self, pg_backend):
        """`?` must become `%s`; a raw connection reports "0 placeholders"."""
        with pg_backend.get_connection() as conn:
            conn.execute(
                "INSERT INTO channels (channel_id, balance_cents, original_deposit_cents, "
                "used_cents, token, chain, wallet, tx_hash, recipient, status, opened_at, "
                "expires_at) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, 'open', ?, ?)",
                ("ch_pg", 500, 500, "USDC", "base", "0xaaa", "0xtx", "0xrcp", "t0", "t1"),
            )
            conn.commit()
            row = conn.execute(
                "SELECT balance_cents FROM channels WHERE channel_id = ?", ("ch_pg",)
            ).fetchone()
        assert row["balance_cents"] == 500

    def test_positional_row_access_works_like_sqlite(self, pg_backend):
        """23 call sites read scalars as `fetchone()[0]` — aggregates have no column name."""
        with pg_backend.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM channels").fetchone()
            assert row[0] == 0
            row = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(used_cents), 0) AS used "
                               "FROM channels").fetchone()
            assert row[0] == 0 and row["n"] == 0
            assert row["used"] == 0

    def test_a_row_supports_the_sqlite_row_contract(self, pg_backend):
        """`dict(row)`, `row.keys()`, `"x" in row.keys()` and value iteration are all used."""
        with pg_backend.get_connection() as conn:
            conn.execute(
                "INSERT INTO channels (channel_id, balance_cents, original_deposit_cents, "
                "used_cents, token, chain, wallet, tx_hash, recipient, status, opened_at, "
                "expires_at) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, 'open', ?, ?)",
                ("ch_r", 700, 700, "USDC", "base", "0xa", "0xt", "0xr", "t0", "t1"),
            )
            conn.commit()
            row = conn.execute(
                "SELECT channel_id, balance_cents FROM channels WHERE channel_id = ?",
                ("ch_r",),
            ).fetchone()
        assert dict(row) == {"channel_id": "ch_r", "balance_cents": 700}
        assert "balance_cents" in row.keys()
        assert list(row) == ["ch_r", 700]          # sqlite3.Row iterates VALUES
        assert len(row) == 2

    def test_datetime_now_is_translated(self, pg_backend):
        with pg_backend.get_connection() as conn:
            row = conn.execute("SELECT datetime('now') AS ts").fetchone()
        assert row["ts"] is not None

    def test_rowcount_guards_the_exactly_once_transition(self, pg_backend):
        """The verified-settlement claim and _finalize both key on UPDATE rowcount."""
        with pg_backend.get_connection() as conn:
            conn.execute(
                "INSERT INTO verified_settlements (nonce, product_id, capability_id, "
                "status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                ("n_pg", "p", "c", "t0"),
            )
            conn.commit()
            first = conn.execute(
                "UPDATE verified_settlements SET status = 'verifying' WHERE nonce = ? "
                "AND status IN ('pending', 'verifying')", ("n_pg",),
            )
            conn.commit()
            assert first.rowcount == 1
            second = conn.execute(
                "UPDATE verified_settlements SET status = 'verifying' WHERE nonce = ? "
                "AND status = 'pending'", ("n_pg",),
            )
            conn.commit()
            assert second.rowcount == 0

    def test_reads_do_not_starve_the_pool(self, pg_backend):
        """A read that never returns its connection exhausts an 8-slot pool silently."""
        for _ in range(200):
            with pg_backend.get_connection() as conn:
                conn.execute("SELECT 1").fetchone()


def test_sqlite_read_rows_survive_concurrent_updates(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    backend = SQLiteBackend(tmp_path / "concurrent-reads.db")
    backend.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value INTEGER)")
    backend.execute("INSERT INTO items VALUES (1, 0)")
    backend.commit()
    barrier = threading.Barrier(12)
    def reader_writer(worker):
        barrier.wait()
        for _ in range(100):
            row = backend.execute("SELECT id, value FROM items WHERE id = 1").fetchone()
            assert row is not None and row["id"] == 1
            backend.execute("UPDATE items SET value = value + 1 WHERE id = 1")
            backend.commit()
    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(reader_writer, range(12)))
        assert backend.execute("SELECT value FROM items WHERE id = 1").fetchone()[0] == 1200
    finally:
        backend.close()
