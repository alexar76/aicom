"""Real, signed mandates for the hub's tests — no mocks of the cryptography.

Every mandate here is a genuine eddsa-jcs-2022 document produced with the awr reference
package, so a test that passes has exercised the same verification path production runs.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

awr = pytest.importorskip("awr")
from awr.didkey import SigningKey  # noqa: E402
from awr.proof import sign_document  # noqa: E402
from awr.digest import canonical_sri  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.models import Capability  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

HUB = "https://hub.test"
ADMIN_TOKEN = "test-admin-token-not-for-production"


def key(n: int) -> SigningKey:
    return SigningKey.from_seed(hashlib.sha256(f"mandate-test-{n}".encode()).digest())


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# One start for every mandate a test run issues. Computed per call, a parent and the child
# issued a second later got windows one second apart, and the child "outlived" its parent
# whenever the clock ticked between them.
_START = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)


def issue(issuer: SigningKey, subject: str, *, scope=("*",), audience=(HUB,), per_call=20_000,
          per_day=1_000_000, total=None, per_product=None, subcontract=None, parent="",
          valid_from: datetime | None = None, days: int = 30, extra: dict | None = None,
          approval_above: int | None = None) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = valid_from or _START
    limits: dict[str, int] = {"perCall": per_call, "perDay": per_day}
    if total is not None:
        limits["total"] = total
    if per_product is not None:
        limits["perProductPerDay"] = per_product
    if approval_above is not None:
        limits["approvalAbove"] = approval_above
    body: dict[str, Any] = {"version": 1, "audience": list(audience), "scope": list(scope), "limits": limits}
    if subcontract is not None:
        body["subcontract"] = subcontract
    if parent:
        body["parent"] = parent
    if extra:
        body.update(extra)
    document = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "type": ["VerifiableCredential", "AIMarketMandate"],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "issuer": issuer.did,
        "validFrom": _ts(start),
        "validUntil": _ts(start + timedelta(days=days)),
        "credentialSubject": {"id": subject, "aimarketMandate": body},
    }
    return sign_document(document, issuer, _ts(now))


def digest(document: dict) -> str:
    return canonical_sri(document)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def nonce() -> str:
    return secrets.token_urlsafe(18)


def request_proof(agent: SigningKey, leaf_digest: str, body: bytes, *, path: str = "/ai-market/v2/invoke",
                  method: str = "POST", t: int | None = None, n: str | None = None, hub: str = HUB) -> str:
    t = int(time.time()) if t is None else t
    n = n or nonce()
    message = "\n".join([
        "aimarket-mandate-request/1", hub, f"{method} {path}", leaf_digest, str(t), n,
        hashlib.sha256(body).hexdigest(),
    ]).encode()
    return f"t={t};n={n};s={b64url(agent.sign(message))}"


def owner_link_payload(owner: SigningKey, account_id: str, *, require_mandate: bool = False,
                       t: int | None = None, n: str | None = None) -> dict:
    t = int(time.time()) if t is None else t
    n = n or nonce()
    message = "\n".join(["aimarket-owner-link/1", HUB, account_id, owner.did, str(t), n]).encode()
    return {"did": owner.did, "require_mandate": require_mandate,
            "proof": {"t": t, "n": n, "s": b64url(owner.sign(message))}}


def revoke_payload(by: SigningKey, target: str) -> dict:
    t, n = int(time.time()), nonce()
    message = "\n".join(["aimarket-mandate-revoke/1", HUB, target, str(t), n]).encode()
    return {"digest": target, "by": by.did, "t": t, "n": n, "s": b64url(by.sign(message))}


# Set AIMARKET_TEST_DATABASE_URL to run every kit-based test on PostgreSQL instead of SQLite:
# three production hubs (hunt, attested, independent) run on Postgres, and the mandate
# counters, the allowance holds and the RETURNING claims must hold there too. Each test gets a
# fresh schema.
PG_URL = os.environ.get("AIMARKET_TEST_DATABASE_URL", "").strip()


def _reset_postgres(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


@contextmanager
def hub(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_HUB_URL", HUB)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_INVOKE_RATE_PER_MIN", "100000")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.hub_url = HUB
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    if PG_URL:
        _reset_postgres(PG_URL)
        config.database_url = PG_URL
    db = HubDatabase(root / "hub.db", database_url=PG_URL)
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    try:
        with TestClient(app, base_url=HUB) as client:
            client.app_ref = app  # the ASGI app, for providers that call back into the hub
            yield client, db
    finally:
        # A PostgreSQL connection per test hub adds up: without this a full run hits the
        # server's max_connections ("sorry, too many clients") a hundred tests in.
        with contextlib.suppress(Exception):
            db.close()


def list_static(db: HubDatabase, capability_id: str = "demo.echo@v1", product_id: str = "demo-echo",
                price: float = 0.004) -> None:
    db.upsert_capability(Capability(
        capability_id=capability_id, product_id=product_id, name=capability_id,
        description="static pack", price_per_call_usd=price, source_hub="local",
        invoke_url="", prompt_template='{"answer": "echo", "ok": true}',
    ))


def list_provider(db: HubDatabase, capability_id: str, product_id: str, price: float,
                  url: str = "https://provider.test/invoke") -> None:
    db.upsert_capability(Capability(
        capability_id=capability_id, product_id=product_id, name=capability_id,
        description="provider", price_per_call_usd=price, source_hub="local", invoke_url=url,
        # A trusted provider: the invoke trust gate is not what these tests are about.
        trust_score=0.9,
    ))


def funded_account(client: TestClient, db: HubDatabase, usd: float = 1.0) -> tuple[str, str]:
    from aimarket_hub import credits

    ledger = credits.CreditsLedger(db._conn)
    made = ledger.create_account("owner", grant_usd=usd, grant_note=credits.OPERATOR_GRANT_NOTE)
    return made["account_id"], made["api_key"]


def balance(db: HubDatabase, account_id: str) -> float:
    from aimarket_hub import credits

    return credits.CreditsLedger(db._conn).balance(account_id)


def setup_mandate(client: TestClient, db: HubDatabase, *, owner_seed: int = 1, agent_seed: int = 2,
                  usd: float = 1.0, **mandate_fields) -> dict:
    """A funded owner, a linked DID, and a registered mandate for an agent key."""
    account, api_key = funded_account(client, db, usd)
    owner, agent = key(owner_seed), key(agent_seed)
    r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                    json=owner_link_payload(owner, account))
    assert r.status_code == 200, r.text
    doc = issue(owner, agent.did, **mandate_fields)
    r = client.post("/ai-market/v2/mandates", json=doc)
    assert r.status_code == 200, r.text
    return {"account": account, "api_key": api_key, "owner": owner, "agent": agent,
            "doc": doc, "digest": r.json()["digest"]}


def mandated_invoke(client: TestClient, m: dict, payload: dict, *, agent: SigningKey | None = None,
                    leaf: str | None = None, extra_headers: dict | None = None):
    body = json.dumps(payload).encode()
    agent = agent or m["agent"]
    leaf = leaf or m["digest"]
    headers = {
        "Content-Type": "application/json",
        "X-AIMarket-Mandate": leaf,
        "X-AIMarket-Mandate-Proof": request_proof(agent, leaf, body),
        **(extra_headers or {}),
    }
    return client.post("/ai-market/v2/invoke", content=body, headers=headers)


ECHO = {"product_id": "demo-echo", "capability_id": "demo.echo@v1", "input": {"text": "hi"}, "source_hub": "local"}


def approval_payload(by: SigningKey, approval: dict, decision: str = "approve", *,
                     max_micro: int | None = None, n: str | None = None) -> dict:
    """An owner's signed answer to an approval request (mandates.md §5.6)."""
    t, n = int(time.time()), n or nonce()
    message = "\n".join([
        "aimarket-mandate-approval/1", HUB, approval["approval_id"], decision, approval["mandate"],
        approval["body_sha256"], str(approval["max_micro"] if max_micro is None else max_micro), str(t), n,
    ]).encode()
    return {"decision": decision, "by": by.did, "t": t, "n": n, "s": b64url(by.sign(message))}


def owner_change(by: SigningKey, account_id: str, action: str, did: str, require_mandate: bool = False) -> dict:
    """An existing owner's authorization for a change of owners (mandates.md §4)."""
    t, n = int(time.time()), nonce()
    message = "\n".join(["aimarket-owner-change/1", HUB, account_id, action, did,
                         "1" if require_mandate else "0", str(t), n]).encode()
    return {"by": by.did, "t": t, "n": n, "s": b64url(by.sign(message))}
