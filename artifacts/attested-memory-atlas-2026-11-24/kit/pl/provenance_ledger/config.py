from __future__ import annotations

import os
from dataclasses import dataclass


def production_mode() -> bool:
    """Fail CLOSED: production unless the operator says otherwise.

    Every gate here used to switch on ``AIFACTORY_PROD`` being SET, so a deployment that
    forgot the variable — or copied an ``.env.example`` carrying ``AIFACTORY_PROD=0`` —
    ran with no actor verification and no capability authentication, silently. Now an
    explicit ``AIFACTORY_PROD=1`` always wins, and only an explicit ``AIFACTORY_DEV=1``
    turns the checks off. Unset means production.
    """
    if os.getenv("AIFACTORY_PROD", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return os.getenv("AIFACTORY_DEV", "").strip().lower() not in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    db_path: str
    key_file: str
    admin_token: str


def get_settings() -> Settings:
    settings = Settings(
        db_path=os.getenv("PROVENANCE_LEDGER_DB", "./data/provenance-ledger.sqlite3"),
        key_file=os.getenv("PROVENANCE_KEY_FILE", "./data/signing-key.pem"),
        admin_token=os.getenv("PROVENANCE_ADMIN_TOKEN", "change-me"),
    )
    if production_mode():
        if settings.admin_token in {"", "change-me"} or len(settings.admin_token) < 32:
            raise RuntimeError("PROVENANCE_ADMIN_TOKEN must be a random 32+ character secret in production")
        if len(os.getenv("AIMARKET_CAPABILITY_TOKEN", "")) < 32:
            raise RuntimeError("AIMARKET_CAPABILITY_TOKEN must be configured in production")
        if os.getenv("ATTESTED_PQC_ENABLED", "1").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError("ATTESTED_PQC_ENABLED cannot be disabled in production")
        if os.getenv("ATTESTED_PQC_REQUIRE", "1").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError("ATTESTED_PQC_REQUIRE cannot be disabled in production")
        if not (os.getenv("PROVENANCE_LEDGER_DATABASE_URL") or os.getenv("DATABASE_URL")):
            raise RuntimeError("PostgreSQL DSN is required in production")
    return settings
