"""The provider a hub executes is never told the buyer's payment channel id.

`_invoke_core` used to forward the buyer's X-Payment-Channel verbatim to the provider — on
the local branch and on the factory branch alike. The channel id is the ledger's handle for
hold/debit/close, and before the fail-closed check it was a secretless channel's credential:
a provider that received it could invoke its own paid listing with that header and no
secret, and the hub would take the buyer's money for it. What the provider gets now is a
reference that is present exactly when a channel was (the oracles' paid tier reads only
presence), stable per channel (the attested apps key an actor on it), and not a channel.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

PRICE = 0.25


def _cap(**kw) -> Capability:
    base = dict(
        capability_id="prov.echo@v1",
        product_id="prod-prov",
        name="echo",
        version="v1",
        description="",
        input_schema={},
        output_schema={},
        price_per_call_usd=PRICE,
        source_hub="local",
        invoke_url="https://provider.example/invoke",
    )
    base.update(kw)
    return Capability(**base)


@contextmanager
def _hub(monkeypatch, tmp_path, *caps: Capability):
    import aimarket_hub.channels as channels_mod
    from aimarket_hub.channels import ChannelLedger

    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setattr(channels_mod, "_ledger", ChannelLedger(db_path=str(tmp_path / "channels.db")))
    root = tmp_path / "hub"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    database = HubDatabase(root / "hub.db")
    for cap in caps or (_cap(),):
        database.upsert_capability(cap)
    app = create_app(config=config, db=database, signer=Signer(root / "key"))
    with TestClient(app) as client:
        yield client


def _capture_provider(monkeypatch) -> list[dict[str, str]]:
    """Stand in for the provider on the local branch and record what the hub sent it."""
    import aimarket_hub.outbound_http as outbound

    seen: list[dict[str, str]] = []

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"success": true}'

        @staticmethod
        def json():
            return {"success": True, "result": {"ok": True}}

    async def _post(url, **kwargs):
        seen.append(dict(kwargs.get("headers") or {}))
        return _Resp()

    monkeypatch.setattr(outbound, "safe_post", _post)
    return seen


def _open(client) -> dict:
    return client.post("/ai-market/v2/channel/open", json={"deposit_usd": 5.0}).json()["channel"]


def _invoke(client, channel_id: str, secret: str = "", **body):
    headers = {"X-Payment-Channel": channel_id}
    if secret:
        headers["X-Payment-Channel-Secret"] = secret
    return client.post("/ai-market/v2/invoke", headers=headers, json={
        "product_id": "prod-prov", "capability_id": "prov.echo@v1",
        "source_hub": "local", "input": {}, **body,
    })


def _balance(channel_id: str) -> float:
    import aimarket_hub.channels as channels_mod

    return channels_mod._ledger.get(channel_id)["balance_usd"]


def test_the_provider_is_not_told_the_channel_id_or_its_secret(monkeypatch, tmp_path):
    seen = _capture_provider(monkeypatch)
    with _hub(monkeypatch, tmp_path) as client:
        ch = _open(client)
        r = _invoke(client, ch["channel_id"], ch["channel_secret"])
        assert r.status_code == 200, r.text

    assert len(seen) == 1
    forwarded = seen[0]["X-Payment-Channel"]
    # Still present: an oracle behind a trusted proxy lifts a call to its paid tier on a
    # non-empty X-Payment-Channel (oracle_core/tiers.py), and that must keep working.
    assert forwarded.strip()
    assert forwarded != ch["channel_id"]
    import aimarket_hub.channels as channels_mod

    assert channels_mod.hold_channel(forwarded, PRICE, receipt_id="provider-replay")["error"] == "channel not found"
    assert channels_mod.close_channel(forwarded)["error"] == "channel not found"
    for value in seen[0].values():
        assert ch["channel_id"] not in value
        assert ch["channel_secret"] not in value


def test_the_reference_is_stable_per_channel_and_distinct_across_channels(monkeypatch, tmp_path):
    seen = _capture_provider(monkeypatch)
    with _hub(monkeypatch, tmp_path) as client:
        first, second = _open(client), _open(client)
        for ch in (first, first, second):
            assert _invoke(client, ch["channel_id"], ch["channel_secret"]).status_code == 200

    refs = [h["X-Payment-Channel"] for h in seen]
    assert refs[0] == refs[1], "one buyer's channel must look like one buyer to the provider"
    assert refs[0] != refs[2], "two channels must not collapse into one buyer"


def test_no_channel_still_forwards_no_reference(monkeypatch, tmp_path):
    seen = _capture_provider(monkeypatch)
    free = _cap(price_per_call_usd=0.0)
    with _hub(monkeypatch, tmp_path, free) as client:
        r = client.post("/ai-market/v2/invoke", json={
            "product_id": "prod-prov", "capability_id": "prov.echo@v1",
            "source_hub": "local", "input": {},
        })
        assert r.status_code == 200, r.text

    assert seen[0]["X-Payment-Channel"] == ""


def test_secretless_channel_never_reaches_the_provider(monkeypatch, tmp_path):
    """Legacy channels fail closed even when a caller already knows the raw id."""
    import aimarket_hub.channels as channels_mod

    seen = _capture_provider(monkeypatch)
    with _hub(monkeypatch, tmp_path) as client:
        legacy = channels_mod._ledger.open(deposit_usd=5.0, with_secret=False)["channel"]
        assert "channel_secret" not in legacy
        response = _invoke(client, legacy["channel_id"])
        assert response.status_code == 402
        assert "balance" not in response.json()
        assert _balance(legacy["channel_id"]) == 5.0
        assert not seen
        assert channels_mod._ledger.get(legacy["channel_id"])["status"] == "open"


def test_the_factory_branch_forwards_the_reference_too(monkeypatch, tmp_path):
    import aimarket_hub.api as api_mod

    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    seen: list[dict[str, str]] = []

    class _Factory:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            seen.append(dict(kw.get("headers") or {}))
            return SimpleNamespace(status_code=200, text="{}", json=lambda: {"ok": True})

    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _Factory)
    with _hub(monkeypatch, tmp_path, _cap(invoke_url="")) as client:
        ch = _open(client)
        r = _invoke(client, ch["channel_id"], ch["channel_secret"])
        assert r.status_code == 200, r.text

    factory_calls = [h for h in seen if "X-Payment-Channel" in h]
    assert factory_calls, "the factory branch never ran"
    forwarded = factory_calls[0]["X-Payment-Channel"]
    assert forwarded.strip()
    assert forwarded != ch["channel_id"]
    assert ch["channel_id"] not in forwarded
