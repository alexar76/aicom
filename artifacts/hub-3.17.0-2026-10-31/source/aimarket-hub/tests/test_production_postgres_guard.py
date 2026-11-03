"""Production storage cannot silently fall back from PostgreSQL to SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.sandbox_trials import SandboxTrialLedger


def _config(tmp_path: Path) -> HubConfig:
    config = HubConfig()
    config.db_path = str(tmp_path / "must-not-exist.db")
    config.signing_key_path = str(tmp_path / "key")
    config.database_url = ""
    return config


def test_production_app_refuses_missing_database_url(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="production Hub requires DATABASE_URL=postgresql"):
        create_app(config=_config(tmp_path))
    assert not (tmp_path / "must-not-exist.db").exists()


def test_production_app_refuses_non_postgres_database_url(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    config = _config(tmp_path)
    config.database_url = "sqlite:///tmp/not-production.db"
    with pytest.raises(RuntimeError, match="SQLite fallback is disabled"):
        create_app(config=config)


def test_production_trial_ledger_refuses_an_unnamed_relative_path(tmp_path, monkeypatch):
    """The ledger must be durable, and a relative path is durable only by accident.

    This used to demand PostgreSQL outright. It was relaxed deliberately: "not PostgreSQL"
    is not "not durable", and the rule as written refused modelmarket.dev — which runs on
    SQLite with its data directory on a Docker volume and has no PostgreSQL to point at —
    not at boot but inside the first free invoke, which answered 500 to the caller.

    What is still refused is the thing the rule was actually defending against: a path
    nobody chose, resolved against whatever the working directory happens to be, taking
    every visitor's spent allowance with it when the container is recreated.
    """
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_SANDBOX_DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_SANDBOX_DB_PATH", raising=False)
    with pytest.raises(RuntimeError, match="must be durable"):
        SandboxTrialLedger(db_path="data/sandbox_trials.db")


def test_production_trial_ledger_accepts_a_named_absolute_path(tmp_path, monkeypatch):
    """An absolute path on a volume is a decision, and it is the one the apex hub makes."""
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_SANDBOX_DATABASE_URL", raising=False)
    path = tmp_path / "trials.db"
    ledger = SandboxTrialLedger(db_path=str(path))
    assert ledger.quota("visitor-1")["remaining"] >= 0
    assert path.exists()


def test_the_per_service_url_is_read_before_the_shared_one(tmp_path, monkeypatch):
    """A hub told where to put THESE counters must be judged on that variable.

    The guard read only DATABASE_URL, so a deployment configured through
    AIMARKET_SANDBOX_DATABASE_URL — which is what the compose files in this repo set —
    was refused for a value it had never been given.
    """
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AIMARKET_SANDBOX_DATABASE_URL", "postgresql://u:p@db:5432/x")
    monkeypatch.delenv("AIMARKET_SANDBOX_DB_PATH", raising=False)
    import aimarket_hub.db_backend as backend_mod

    seen = {}
    real = backend_mod.create_backend

    def _fake(database_url="", db_path=None):
        seen["url"] = database_url
        return real(database_url="", db_path=tmp_path / "t.db")

    monkeypatch.setattr(backend_mod, "create_backend", _fake)
    SandboxTrialLedger(db_path="data/sandbox_trials.db")
    assert seen["url"] == "postgresql://u:p@db:5432/x"


def test_development_trial_ledger_keeps_zero_dependency_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "trials.db"
    ledger = SandboxTrialLedger(db_path=str(path))
    assert ledger.quota("visitor_12345")["remaining"] >= 0
    assert path.exists()


def test_production_acex_ipo_ledger_refuses_sqlite_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_ACEX_IPO_DATABASE_URL", raising=False)
    monkeypatch.delenv("ACEX_IPO_DATABASE_URL", raising=False)
    from aimarket_hub.acex_ipo import AcexIpoLedger

    with pytest.raises(RuntimeError, match="production ACEX ipo ledger requires"):
        AcexIpoLedger(db_path=str(tmp_path / "acex_ipo.db"))
    assert not (tmp_path / "acex_ipo.db").exists()


def test_production_acex_audit_ledger_refuses_sqlite_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_ACEX_AUDIT_DATABASE_URL", raising=False)
    monkeypatch.delenv("ACEX_AUDIT_DATABASE_URL", raising=False)
    from aimarket_hub.acex_audit import AcexAuditLedger

    with pytest.raises(RuntimeError, match="production ACEX audit ledger requires"):
        AcexAuditLedger(db_path=str(tmp_path / "acex_audit.db"))
    assert not (tmp_path / "acex_audit.db").exists()


def test_development_acex_ledgers_keep_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_ACEX_IPO_DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_ACEX_AUDIT_DATABASE_URL", raising=False)
    import aimarket_hub.acex_ipo as ipo_mod
    from aimarket_hub.acex_audit import AcexAuditLedger
    from aimarket_hub.acex_ipo import AcexIpoLedger

    ipo_path = tmp_path / "acex_ipo.db"
    audit_path = tmp_path / "acex_audit.db"
    ipo = AcexIpoLedger(db_path=str(ipo_path))
    ipo_mod._ledger = ipo  # audit bootstrap reads the module singleton
    audit = AcexAuditLedger(db_path=str(audit_path))
    floated = ipo.float_product("prod-dev", audit_score_bps=8000)
    assert floated.get("error") is None
    assert ipo_path.exists()
    assert audit_path.exists()
    assert audit.listing_audit_state("prod-dev")["enabled"] is True


def test_a_hub_that_cannot_keep_trials_fails_to_start(tmp_path, monkeypatch):
    """Not at the first visitor — at boot, where the deploy can see it.

    The ledger was built lazily, so modelmarket.dev started clean, reported healthy, and
    answered 500 to every sandbox-tier call. Nothing in any health endpoint said so.
    """
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIMARKET_SANDBOX_ENABLED", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AIMARKET_SANDBOX_DATABASE_URL", raising=False)
    monkeypatch.setenv("AIMARKET_SANDBOX_DB_PATH", "data/sandbox_trials.db")
    import aimarket_hub.sandbox_trials as trials

    monkeypatch.setattr(trials, "_ledger", None)
    monkeypatch.setattr(trials, "_ENABLED", True)
    with pytest.raises(RuntimeError, match="must be durable"):
        trials.ensure_trial_ledger()
