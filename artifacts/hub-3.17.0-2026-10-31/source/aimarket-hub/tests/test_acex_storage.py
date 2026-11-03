"""ACEX ledger storage on a hub that mounts only the read-only Factory catalog export.

The hub runs with AIFACTORY_DATA_ROOT=/factory_data, and /factory_data is now the export
(state/pipeline.json and nothing else), mounted read-only. The ACEX ledgers resolve their
SQLite fallback path under that root even when PostgreSQL is configured. Resolving used to
create <root>/data as a side effect; the full Factory tree happened to contain that
directory, the export does not, so every paid invoke failed its ACEX accrual.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

import pytest

PG_URL = "postgresql://acex:unused@db.invalid:5432/acex"


class _FakePostgres:
    """Stands in for PostgresBackend: the SQL runs on a private in-memory database."""

    backend_type = "postgresql"

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    @contextlib.contextmanager
    def get_connection(self):
        yield self._conn


@pytest.fixture
def read_only_export(tmp_path):
    """The shape refresh_factory_export.py writes, mounted the way the hub mounts it."""
    root = tmp_path / "hub-catalog"
    (root / "state").mkdir(parents=True)
    (root / "state" / "pipeline.json").write_text('{"products": {}}')
    os.chmod(root / "state", 0o555)
    os.chmod(root, 0o555)
    yield root
    os.chmod(root, 0o755)
    os.chmod(root / "state", 0o755)


@pytest.fixture
def postgres_hub(monkeypatch, read_only_export):
    import aimarket_hub.acex_audit as audit_mod
    import aimarket_hub.acex_ipo as ipo_mod
    import aimarket_hub.db_backend as backend_mod

    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(read_only_export))
    monkeypatch.setenv("AIMARKET_ACEX_IPO_DATABASE_URL", PG_URL)
    monkeypatch.setenv("AIMARKET_ACEX_AUDIT_DATABASE_URL", PG_URL)
    # The defaults a hub gets when no ACEX_*_DB_PATH is set (other tests reload the
    # modules with temp paths, so pin them here).
    monkeypatch.setattr(ipo_mod, "_DB_PATH", "data/acex_ipo.db")
    monkeypatch.setattr(audit_mod, "_DB_PATH", "data/acex_audit.db")
    urls = []

    def _create_backend(database_url="", db_path=None):
        urls.append(database_url)
        return _FakePostgres()

    monkeypatch.setattr(backend_mod, "create_backend", _create_backend)
    ipo_mod._reset_for_tests()
    audit_mod._reset_for_tests()
    yield {"root": read_only_export, "urls": urls, "ipo": ipo_mod, "audit": audit_mod}
    ipo_mod._reset_for_tests()
    audit_mod._reset_for_tests()


def test_resolving_the_sqlite_path_creates_nothing(tmp_path, monkeypatch):
    from aimarket_hub.acex_storage import resolve_sqlite_path

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    path = resolve_sqlite_path("data/acex_ipo.db", label="IPO")
    assert path == (tmp_path / "data" / "acex_ipo.db").resolve()
    assert not (tmp_path / "data").exists()


def test_postgres_ledgers_start_on_the_read_only_export(postgres_hub):
    ipo = postgres_hub["ipo"].AcexIpoLedger()
    audit = postgres_hub["audit"].AcexAuditLedger()
    assert postgres_hub["urls"] == [PG_URL, PG_URL]
    assert ipo._backend.backend_type == audit._backend.backend_type == "postgresql"
    assert sorted(os.listdir(postgres_hub["root"])) == ["state"]


def test_paid_invoke_accrual_reaches_the_pools(postgres_hub):
    """The two calls a paid invoke makes (api.py and verified_settlement._accrue_acex)."""
    ipo, audit = postgres_hub["ipo"], postgres_hub["audit"]
    floated = ipo.float_product("prod-export", name="Export", audit_score_bps=8000)
    assert floated.get("error") is None

    accrued = ipo.accrue_revenue("prod-export", 2.0)
    assert accrued["ok"] is True
    assert accrued["to_pool_usd"] > 0
    # No insuring auditor yet is an answer from the ledger; the failure was an exception.
    rewards = audit.accrue_audit_rewards("prod-export", 2.0)
    assert rewards.get("ok") or rewards.get("error") == "no_insuring_coverage"
    state = ipo.revenue_state("prod-export")
    assert state["gross_revenue_usd"] == 2.0
    assert state["accrued_undistributed_usd"] == accrued["to_pool_usd"]


def test_sqlite_fallback_still_creates_its_own_directory(tmp_path, monkeypatch):
    """Dropping the mkdir from path resolution must not break the dev/test SQLite path."""
    import aimarket_hub.acex_ipo as ipo_mod

    for key in ("AIFACTORY_PROD", "DATABASE_URL", "AIMARKET_ACEX_IPO_DATABASE_URL",
                "ACEX_IPO_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    ledger = ipo_mod.AcexIpoLedger(db_path="data/acex_ipo.db")
    assert ledger.float_product("prod-dev", audit_score_bps=8000).get("error") is None
    assert (tmp_path / "data" / "acex_ipo.db").is_file()
