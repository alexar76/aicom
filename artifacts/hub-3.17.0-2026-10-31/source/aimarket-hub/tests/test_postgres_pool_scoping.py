"""The checked-out PostgreSQL connection belongs to one execution context.

The backend is a process-wide singleton and its callers are not. Keeping the
checked-out connection on the backend meant two callers in flight at once got the
same connection: whichever finished first handed it back to the pool while the other
was still using it, committing or rolling back its transaction under it and
overwriting the cursor its `fetchall()` was about to read.

This needs no threads to reproduce. The crawler holds a dirty connection across an
`await` and the event loop runs a request handler in the gap — which is how
signal-hunt-hub-1 ended up logging `rolling back returned connection: [INTRANS]`
seventeen times a second and eventually hanging with its health check timing out.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from aimarket_hub.db_backend import PostgresBackend


class _FakeCursor:
    """Reports which connection produced it, so a mix-up is visible in the rows."""

    def __init__(self, conn: "_FakeConn", sql: str) -> None:
        self.conn = conn
        self.sql = sql
        self._rows = [{"conn_id": conn.conn_id}]
        self.rowcount = 1
        self.description = [("conn_id",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeInfo:
    """The bit of libpq state the backend reads: 0 == IDLE, non-zero == in a transaction."""

    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    @property
    def transaction_status(self) -> int:
        return 1 if self._conn.in_transaction else 0


class _FakeConn:
    def __init__(self, conn_id: int) -> None:
        self.conn_id = conn_id
        self.commits = 0
        self.rollbacks = 0
        # A statement opens a transaction, exactly as psycopg does with autocommit off.
        self.in_transaction = False
        self.info = _FakeInfo(self)

    def execute(self, sql, params=()):
        self.in_transaction = True
        return _FakeCursor(self, sql)

    def executemany(self, sql, seq):
        self.in_transaction = True
        return _FakeCursor(self, sql)

    def cursor(self):
        return _FakeCursor(self, "")

    def commit(self):
        self.commits += 1
        self.in_transaction = False

    def rollback(self):
        self.rollbacks += 1
        self.in_transaction = False


class _FakePool:
    """Hands out distinct connections and refuses to over-issue, like a real pool."""

    def __init__(self, max_size: int = 8) -> None:
        self.max_size = max_size
        self._next_id = 0
        self.checked_out: set[int] = set()
        self.high_water = 0
        self.double_returns: list[int] = []

    def getconn(self):
        if len(self.checked_out) >= self.max_size:
            raise AssertionError("pool exhausted — a connection was never returned")
        self._next_id += 1
        conn = _FakeConn(self._next_id)
        self.checked_out.add(conn.conn_id)
        self.high_water = max(self.high_water, len(self.checked_out))
        return conn

    def putconn(self, conn):
        if conn.conn_id not in self.checked_out:
            # The bug this file exists for: the same connection handed back twice,
            # because two contexts each thought they owned it.
            self.double_returns.append(conn.conn_id)
            return
        self.checked_out.discard(conn.conn_id)


def _backend(max_size: int = 8) -> tuple[PostgresBackend, _FakePool]:
    """A backend around a fake pool, bypassing __init__ (which needs a live server)."""
    backend = object.__new__(PostgresBackend)
    pool = _FakePool(max_size)
    backend._pool = pool
    backend.database_url = "postgresql://fake/fake"
    # Also give an instance-state implementation a valid object, so a failure here is the
    # behaviour under test and not an AttributeError from the bypassed __init__.
    backend._last_conn = None
    backend._last_cursor = None
    backend._dirty = False
    return backend, pool


@pytest.fixture(autouse=True)
def _clean_session():
    """No context state leaks between tests (the ContextVars are module-level).

    Written defensively so this file also runs against an implementation that keeps the
    state on the backend instead — which is how these assertions were shown to fail
    before the fix rather than error out in the fixture.
    """
    from aimarket_hub import db_backend

    tokens = []
    for name in ("_PG_SESSION", "_PG_RESULT"):
        var = getattr(db_backend, name, None)
        if var is not None:
            tokens.append((var, var.set(None)))
    yield
    for var, token in tokens:
        var.reset(token)


class TestOneContextOneConnection:
    def test_a_read_returns_its_connection_immediately(self):
        backend, pool = _backend()
        backend.execute("SELECT 1")
        assert pool.checked_out == set(), "a read must not hold a pool slot"
        assert backend.fetchall() == [{"conn_id": 1}], "rows survive the release"

    def test_many_reads_never_grow_past_one_slot(self):
        backend, pool = _backend()
        for _ in range(50):
            backend.execute("SELECT 1")
            backend.fetchall()
        assert pool.high_water == 1
        assert pool.checked_out == set()

    def test_a_write_holds_one_connection_until_commit(self):
        backend, pool = _backend()
        backend.execute("INSERT INTO t VALUES (1)")
        held = set(pool.checked_out)
        assert len(held) == 1
        backend.execute("INSERT INTO t VALUES (2)")
        assert pool.checked_out == held, "a multi-statement write stays on one connection"
        backend.commit()
        assert pool.checked_out == set()

    def test_a_read_after_a_write_stays_in_the_write_transaction(self):
        """Releasing mid-write would commit half of it."""
        backend, pool = _backend()
        backend.execute("INSERT INTO t VALUES (1)")
        held = set(pool.checked_out)
        backend.execute("SELECT 1")
        assert pool.checked_out == held
        backend.rollback()
        assert pool.checked_out == set()


class TestConcurrentContexts:
    @pytest.mark.asyncio
    async def test_two_tasks_do_not_share_a_connection(self):
        backend, pool = _backend()
        seen: dict[str, int] = {}
        gate = asyncio.Event()

        async def writer():
            backend.execute("INSERT INTO t VALUES (1)")
            seen["writer"] = backend.fetchone()["conn_id"]
            gate.set()
            await asyncio.sleep(0)          # the crawler's await
            backend.execute("INSERT INTO t VALUES (2)")
            seen["writer_after"] = backend.fetchone()["conn_id"]
            backend.commit()

        async def reader():
            await gate.wait()
            backend.execute("SELECT 1")
            seen["reader"] = backend.fetchone()["conn_id"]

        await asyncio.gather(writer(), reader())

        assert seen["writer"] != seen["reader"], "tasks shared one connection"
        assert seen["writer_after"] == seen["writer"], (
            "the writer's connection was pulled out from under it across the await"
        )
        assert pool.double_returns == [], "a connection was handed back twice"
        assert pool.checked_out == set()

    @pytest.mark.asyncio
    async def test_a_reader_cannot_release_a_writers_connection(self):
        """The reader finishing first must not return the writer's slot to the pool."""
        backend, pool = _backend()
        backend.execute("INSERT INTO t VALUES (1)")   # this context holds one
        held = set(pool.checked_out)

        async def child():
            # Inherits the ContextVar value, but not ownership of it.
            backend.execute("SELECT 1")
            backend.fetchall()

        await asyncio.gather(child())
        assert pool.checked_out == held, "the child released its parent's connection"
        assert pool.double_returns == []
        backend.commit()
        assert pool.checked_out == set()

    def test_threads_do_not_share_a_connection(self):
        """Four threads writing at once must never land on one connection.

        Asserting only on the pool high-water mark passes when every thread SHARES one
        connection — the failure this is about — so the assertion is on which thread saw
        which connection id.
        """
        backend, pool = _backend()
        seen: list[tuple[int, int]] = []
        seen_lock = threading.Lock()
        errors: list[BaseException] = []
        start = threading.Barrier(4)

        def run():
            try:
                start.wait(timeout=5)
                for _ in range(20):
                    backend.execute("INSERT INTO t VALUES (1)")
                    conn_id = backend.fetchone()["conn_id"]
                    with seen_lock:
                        seen.append((threading.get_ident(), conn_id))
                    backend.commit()
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert errors == []
        assert pool.double_returns == []
        assert pool.checked_out == set()
        owners: dict[int, set[int]] = {}
        for thread_id, conn_id in seen:
            owners.setdefault(conn_id, set()).add(thread_id)
        shared = {c: t for c, t in owners.items() if len(t) > 1}
        assert not shared, f"connection(s) used by more than one thread: {shared}"

    @pytest.mark.asyncio
    async def test_the_pool_is_not_exhausted_by_interleaved_reads(self):
        """The original leak: eight reads and the ninth caller blocks forever."""
        backend, pool = _backend(max_size=8)

        async def one_read(_i: int):
            backend.execute("SELECT 1")
            await asyncio.sleep(0)
            return backend.fetchall()

        results = await asyncio.gather(*(one_read(i) for i in range(40)))
        assert len(results) == 40
        assert pool.checked_out == set()


class TestFailurePaths:
    def test_a_failed_statement_rolls_back_and_releases(self):
        backend, pool = _backend()

        class _Boom(_FakeConn):
            def execute(self, sql, params=()):
                raise RuntimeError("statement failed")

        def getconn():
            conn = _Boom(99)
            pool.checked_out.add(conn.conn_id)
            return conn

        pool.getconn = getconn  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            backend.execute("SELECT 1")
        assert pool.checked_out == set(), "a failed statement leaked its connection"

    def test_commit_without_a_session_is_a_no_op(self):
        backend, pool = _backend()
        backend.commit()
        backend.rollback()
        assert pool.checked_out == set()
        assert pool.double_returns == []

    def test_rowcount_and_fetch_are_empty_outside_a_session(self):
        backend, _pool = _backend()
        assert backend.rowcount == 0
        assert backend.fetchone() is None
        assert backend.fetchall() == []


class TestTheReadTransactionIsClosed:
    """A read must not go back to the pool inside a transaction.

    psycopg opens one for any statement, SELECT included. Left INTRANS, psycopg_pool rolls
    it back and logs a warning per read — seventeen a second on this hub, which is what
    made its log unreadable.
    """

    def test_a_read_is_rolled_back_before_it_is_returned(self):
        backend, pool = _backend()
        returned: list[_FakeConn] = []
        real_putconn = pool.putconn

        def spy(conn):
            returned.append(conn)
            real_putconn(conn)

        pool.putconn = spy  # type: ignore[method-assign]
        backend.execute("SELECT 1")
        assert len(returned) == 1
        conn = returned[0]
        assert conn.rollbacks == 1, "the read's transaction was left open"
        assert not conn.in_transaction, "returned to the pool INTRANS"

    def test_a_committed_write_is_not_rolled_back_as_well(self):
        backend, pool = _backend()
        backend.execute("INSERT INTO t VALUES (1)")
        session = backend._session(create=False)
        conn = session.conn
        backend.commit()
        assert conn.commits == 1
        assert conn.rollbacks == 0, "a committed write was rolled back on release"

    def test_an_idle_connection_is_not_given_a_pointless_rollback(self):
        backend, pool = _backend()
        conn = backend._acquire()          # checked out, no statement run
        assert not conn.in_transaction
        backend._release()
        assert conn.rollbacks == 0
