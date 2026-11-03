"""Per-capability verifier routes (AIMARKET_VERIFY_ROUTES) for Pay-on-Verified.

One capability is routed to its own verifier ("GAIA", answering with the structural
`delivery_verdict` the way gaia/verifier.py does); every other capability stays with the
default verifier ("Metis", a judge answering in free text). Both are faked by URL behind
the `httpx` name inside verified_settlement, the same move the main settlement suite
makes, and every call records the URL, the Authorization header and the payload.

What has to hold:

  * the routed capability is judged ONLY by its route, with ONLY the route's token, and
    the signed envelope names the verifier that actually judged;
  * an unmatched capability is exactly the default verifier's business, as before;
  * every guard of the money gate still applies to a routed verdict: the threshold echo,
    the indeterminate policy, retries, appeals (to a court that is NOT the routed
    verifier), reputation and the slash ladder;
  * a table that cannot be used refuses to verify — before any work at plan time, and by
    waiting (hold kept) for a settlement already registered — and NEVER hands the
    capability to the default verifier instead;
  * a route's token never reaches a log, a reply, the well-known document or another
    verifier.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx as real_httpx
import pytest
from fastapi.testclient import TestClient

import aimarket_hub.api as api_mod
import aimarket_hub.channels as channels_mod
import aimarket_hub.verified_settlement as vs_mod
from aimarket_hub.api import create_app
from aimarket_hub.api_models import VerifyBlock
from aimarket_hub.channels import ChannelLedger
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer

ROUTED = {"product_id": "prod-translate", "capability_id": "translate.multi@v2"}   # $0.40
PLAIN = {"product_id": "prod-summarize", "capability_id": "summarize@v1"}          # $0.25
METIS_URL = "http://metis.test"
GAIA_URL = "http://gaia.test"
COURT_URL = "http://court.test"
GAIA_ID = "gaia.verify@v1"
GAIA_KEY_ENV = "AIMARKET_VERIFY_GAIA_TOKEN"
# Distinctive values so a leak anywhere is a substring match away.
GAIA_TOKEN = "gaia-route-token-7f3e9c"
METIS_TOKEN = "metis-default-token-41aa0b"
COURT_TOKEN = "court-token-0c55d2"
# A bounded wait, so a regression that leaves a verdict hanging fails in seconds instead of
# sitting out the 300 s default.
VERIFY = {"requested": True, "intent": "Translate 'paid' to Spanish", "mode": "fast", "wait": True,
          "wait_timeout_s": 8}
DEPOSIT = 5.0
T0 = 1_900_000_000.0
WINDOW = 3600.0


def _route_table(**over):
    entry = {"url": GAIA_URL, "verifier_id": GAIA_ID, "key_env": GAIA_KEY_ENV}
    entry.update(over)
    return json.dumps({ROUTED["capability_id"]: entry})


# ── Fake verifiers ───────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"<<<UNTRUSTED-DELIVERY-([0-9a-f]{8,})>>>")


class _Verifier:
    """Scripted /v1/verify for one service. The LAST step repeats forever."""

    def __init__(self, name, steps, *, trace="tr"):
        self.name = name
        self.steps = list(steps)
        self.trace = trace
        self.calls: list[dict] = []

    def next_step(self):
        return self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]


class _Resp:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _metis_judged(aid, fulfils, score, trace):
    return {
        "answer": json.dumps({"audit_id": aid, "fulfils": fulfils, "score": score,
                              "reasons": ["metis: judged in prose"]}),
        "status": "success", "verified": True, "verify_score": 0.95,
        "verify_performed": True, "threshold": 0.7, "route": "fast", "trace_id": trace,
    }


def _gaia_judged(fulfils, score, trace, threshold=0.7):
    """gaia/verifier.py's actuation envelope: the verdict is structural."""
    return {
        "answer": "actuation effect observed" if fulfils else "no effect observed",
        "status": "success", "verified": fulfils and score >= threshold,
        "verify_score": score, "verify_performed": True,
        "threshold": threshold, "threshold_source": "request",
        "delivery_verdict": {"fulfils": fulfils, "score": score,
                             "reasons": ["actuation:effect" if fulfils else "actuation:no_effect"]},
        "route": "fast", "trace_id": trace,
    }


def _client_cls(services: dict):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            import asyncio

            svc = next((s for base, s in services.items() if url.startswith(base + "/")), None)
            if svc is None:
                raise AssertionError(f"verify call to an unexpected URL: {url}")
            svc.calls.append({"url": url, "headers": dict(headers or {}), "payload": dict(json or {})})
            step = svc.next_step()
            kind = step[0]
            if kind == "gate":
                released = await asyncio.get_running_loop().run_in_executor(None, step[1].wait, 10.0)
                if not released:
                    raise AssertionError(f"{svc.name} gate timed out")
                step = step[2]
                kind = step[0]
            if kind == "transport":
                raise real_httpx.ConnectError("boom")
            if kind == "http":
                return _Resp({"detail": "x"}, status_code=step[1])
            if kind == "engine":
                return _Resp({"answer": "", "status": "error", "verify_performed": False,
                              "verify_score": 0.0, "error": "unparseable_input"})
            aid = _FENCE_RE.search((json or {}).get("input", "")).group(1)
            if kind == "metis":
                return _Resp(_metis_judged(aid, step[1], step[2], svc.trace))
            if kind == "gaia":
                return _Resp(_gaia_judged(step[1], step[2], svc.trace,
                                          *(step[3:4] if len(step) > 3 else ())))
            raise AssertionError(f"unknown step {step}")

    return _Client


class _FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {"output": {"translated": "pagado"}}


class _FakeFactoryClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _FakeResp()


# ── Fixture ──────────────────────────────────────────────────────────────────


class _Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _build(tmp_path: Path, monkeypatch, *, metis=None, gaia=None, court=None,
           routes: str | None = None, window: float = 0.0):
    metis = metis or _Verifier("metis", [("metis", True, 0.95)], trace="tr_metis")
    gaia = gaia or _Verifier("gaia", [("gaia", True, 1.0)], trace="tr_gaia")
    court = court or _Verifier("court", [("metis", False, 0.1)], trace="tr_court")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    monkeypatch.setenv("AIMARKET_VERIFY_RETRY_BACKOFF_S", "0.01")
    monkeypatch.setenv("AIMARKET_VERIFY_METIS_URL", METIS_URL)
    monkeypatch.setenv("AIMARKET_VERIFY_METIS_KEY", METIS_TOKEN)
    monkeypatch.delenv("AIMARKET_VERIFY_VERIFIER_ID", raising=False)
    monkeypatch.setenv(GAIA_KEY_ENV, GAIA_TOKEN)
    monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", _route_table() if routes is None else routes)
    monkeypatch.setenv("AIMARKET_APPEAL_WINDOW_S", str(window))
    monkeypatch.setenv("AIMARKET_APPEAL_METIS_URL", COURT_URL)
    monkeypatch.setenv("AIMARKET_APPEAL_METIS_KEY", COURT_TOKEN)
    monkeypatch.setenv("AIMARKET_APPEAL_SWEEP_S", "3600")      # tests drive the sweep
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    clock = _Clock(T0)
    monkeypatch.setattr(vs_mod, "_now_s", clock)
    monkeypatch.setattr(channels_mod, "_ledger", ChannelLedger(db_path=str(tmp_path / "channels.db")))
    monkeypatch.setattr(vs_mod, "httpx", SimpleNamespace(
        AsyncClient=_client_cls({METIS_URL: metis, GAIA_URL: gaia, COURT_URL: court}),
        RequestError=real_httpx.RequestError,
    ))
    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _FakeFactoryClient)
    # Misconfiguration warnings are once per process; each test starts with a clean slate.
    monkeypatch.setattr(vs_mod, "_warned_knobs", set())

    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    signer = Signer(config.signing_key_path)
    app = create_app(config=config, db=db, signer=signer)
    for cap, publisher in ((ROUTED, "pub-translate"), (PLAIN, "pub-summarize")):
        db._conn.execute("UPDATE capabilities SET publisher_id = ? WHERE capability_id = ?",
                         (publisher, cap["capability_id"]))
    db._conn.commit()
    hook = MagicMock()
    app.state.verify_svc.attach_supply_security(hook)
    return SimpleNamespace(app=app, db=db, signer=signer, clock=clock, hook=hook,
                           svc=app.state.verify_svc, metis=metis, gaia=gaia, court=court)


def _open(client, deposit=DEPOSIT):
    ch = client.post("/ai-market/v2/channel/open", json={"deposit_usd": deposit}).json()
    return ch["channel"]["channel_id"], ch["channel"]["channel_secret"]


def _invoke(client, cap, channel_id, secret, verify=None):
    return client.post(
        "/ai-market/v2/invoke",
        headers={"X-Payment-Channel": channel_id, "X-Payment-Channel-Secret": secret},
        json={**cap, "source_hub": "local", "input": {"text": "paid"},
              "verify": VERIFY if verify is None else verify},
    )


def _lookup(client, nonce):
    r = client.get(f"/ai-market/v2/verification/{nonce}")
    assert r.status_code == 200, r.text
    return r.json()


def _await_status(client, nonce, statuses, timeout_s=8.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rec = _lookup(client, nonce)
        if rec["verification"]["status"] in statuses:
            return rec
        time.sleep(0.02)
    raise AssertionError(f"{nonce} never reached {statuses}: {_lookup(client, nonce)['verification']}")


def _reputation(db):
    return [r["event_type"] for r in db._conn.execute("SELECT event_type FROM reputation_events")]


def _bearers(svc):
    return [c["headers"].get("Authorization") for c in svc.calls]


# ── Resolving a route (pure) ─────────────────────────────────────────────────


def _env(monkeypatch, routes, **extra):
    monkeypatch.setenv("AIMARKET_VERIFY_METIS_URL", METIS_URL)
    monkeypatch.delenv("AIMARKET_VERIFY_VERIFIER_ID", raising=False)
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    if routes is None:
        monkeypatch.delenv("AIMARKET_VERIFY_ROUTES", raising=False)
    else:
        monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", routes)
    for name, value in extra.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("routes", [None, "", "   "])
def test_no_table_means_the_default_verifier(monkeypatch, routes):
    _env(monkeypatch, routes)
    assert vs_mod.route_table() == ()
    route = vs_mod.verifier_route(ROUTED["capability_id"])
    assert route == vs_mod.default_route()
    assert (route.url, route.verifier_id, route.routed) == (METIS_URL, "metis.verify@v1", False)


def test_an_exact_id_beats_any_prefix_and_the_longest_prefix_wins(monkeypatch):
    def entry(n):
        return {"url": f"http://v{n}.test", "verifier_id": f"v{n}@v1", "key_env": f"AIMARKET_VERIFY_K{n}"}

    _env(monkeypatch, json.dumps({
        "gaia.*": entry(1), "gaia.actuate*": entry(2), "gaia.actuate@v1": entry(3),
    }), AIMARKET_VERIFY_K1="a", AIMARKET_VERIFY_K2="b", AIMARKET_VERIFY_K3="c")
    assert vs_mod.verifier_route("gaia.actuate@v1").verifier_id == "v3@v1"
    assert vs_mod.verifier_route("gaia.actuate@v2").verifier_id == "v2@v1"
    assert vs_mod.verifier_route("gaia.weather.read@v1").verifier_id == "v1@v1"
    # A key without '*' is an exact id, never a prefix; anything else is the default's.
    assert vs_mod.verifier_route("gaia").routed is False
    assert vs_mod.verifier_route("translate.multi@v2") == vs_mod.default_route()
    route = vs_mod.verifier_route("gaia.actuate@v1")
    assert (route.match, route.url, route.key_env, route.gate) == (
        "gaia.actuate@v1", "http://v3.test", "AIMARKET_VERIFY_K3", "v3@v1")
    assert route.key() == "c"


def test_an_exact_key_is_never_a_prefix(monkeypatch):
    _env(monkeypatch, json.dumps({"gaia.actuate@v1": {
        "url": GAIA_URL, "verifier_id": GAIA_ID, "key_env": GAIA_KEY_ENV}}), **{GAIA_KEY_ENV: GAIA_TOKEN})
    assert vs_mod.verifier_route("gaia.actuate@v1").verifier_id == GAIA_ID
    for other in ("gaia.actuate@v10", "gaia.actuate@v1.evil", "gaia.actuate@v"):
        assert vs_mod.verifier_route(other) == vs_mod.default_route(), other


def _gaia_entry(**over):
    e = {"url": GAIA_URL, "verifier_id": GAIA_ID, "key_env": GAIA_KEY_ENV}
    e.update(over)
    return e


@pytest.mark.parametrize("raw,why", [
    ("{not json", "not valid JSON"),
    ('["gaia.actuate@v1"]', "must be a JSON object"),
    ('{"gaia.actuate@v1": "https://gaia.test"}', "must be an object"),
    ('{"a@v1": {"url": "http://a.test", "verifier_id": "a@v1", "key_env": "AIMARKET_VERIFY_A"},'
     ' "a@v1": {"url": "http://b.test", "verifier_id": "b@v1", "key_env": "AIMARKET_VERIFY_B"}}',
     "repeats the key"),
    (json.dumps({"gaia.actuate@v1": {**_gaia_entry(), "keyenv": "X"}}), "unknown"),
    (json.dumps({"gaia.actuate@v1": {"url": GAIA_URL, "verifier_id": GAIA_ID}}), "missing"),
    (json.dumps({"*": _gaia_entry()}), "not '*'"),
    (json.dumps({"gaia.*.read": _gaia_entry()}), "prefix ending in '*'"),
    (json.dumps({"": _gaia_entry()}), "prefix ending in '*'"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(url="ftp://gaia.test")}), "http(s)"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(url="")}), "non-empty"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(url="https://user:pw@gaia.test")}), "credentials"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(url="https://gaia.test/?k=1")}), "query"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(verifier_id="gaia verify")}), "verifier_id"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(verifier_id="")}), "verifier_id"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(key_env="GAIA_VERIFY_TOKEN")}), "key_env"),
    # The value of key_env goes to a remote host: it may not name the hub's own secrets.
    (json.dumps({"gaia.actuate@v1": _gaia_entry(key_env="AIMARKET_ADMIN_TOKEN")}), "key_env"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(key_env="AIMARKET_VERIFY_ROUTES")}), "key_env"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(key_env=None)}), "key_env"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(),
                 "gaia.relay@v1": _gaia_entry(url="http://elsewhere.test")}), "two different URLs"),
    (json.dumps({"gaia.actuate@v1": _gaia_entry(),
                 "gaia.relay@v1": _gaia_entry(verifier_id="gaia.other@v1")}), "another verifier id"),
])
def test_an_unusable_table_refuses_every_capability(monkeypatch, raw, why):
    _env(monkeypatch, raw, **{GAIA_KEY_ENV: GAIA_TOKEN})
    for cap in ("gaia.actuate@v1", "translate.multi@v2", ""):
        with pytest.raises(vs_mod.RouteUnavailable, match=re.escape(why)):
            vs_mod.verifier_route(cap)
    # …and is never mistaken for "no table".
    assert vs_mod.routes_configured() is True


def test_production_requires_https_except_on_loopback(monkeypatch):
    _env(monkeypatch, json.dumps({"gaia.actuate@v1": _gaia_entry(url="http://gaia.test")}),
         **{GAIA_KEY_ENV: GAIA_TOKEN})
    assert vs_mod.verifier_route("gaia.actuate@v1").url == "http://gaia.test"
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    with pytest.raises(vs_mod.RouteUnavailable, match="https in production"):
        vs_mod.verifier_route("gaia.actuate@v1")
    for url in ("https://iot.modelmarket.dev/", "http://127.0.0.1:9320", "http://localhost:9320"):
        monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", json.dumps({"gaia.actuate@v1": _gaia_entry(url=url)}))
        assert vs_mod.verifier_route("gaia.actuate@v1").url == url.rstrip("/")


def test_an_unset_key_env_refuses_only_the_routes_it_matches(monkeypatch):
    _env(monkeypatch, _route_table())
    monkeypatch.delenv(GAIA_KEY_ENV, raising=False)
    with pytest.raises(vs_mod.RouteUnavailable, match=f"{GAIA_KEY_ENV} is not set"):
        vs_mod.verifier_route(ROUTED["capability_id"])
    monkeypatch.setenv(GAIA_KEY_ENV, "   ")
    with pytest.raises(vs_mod.RouteUnavailable):
        vs_mod.verifier_route(ROUTED["capability_id"])
    # Every other capability still has its verifier.
    assert vs_mod.verifier_route(PLAIN["capability_id"]) == vs_mod.default_route()


def test_a_route_may_not_sign_as_the_default_verifier_from_another_url(monkeypatch):
    _env(monkeypatch, _route_table(verifier_id="metis.verify@v1"), **{GAIA_KEY_ENV: GAIA_TOKEN})
    with pytest.raises(vs_mod.RouteUnavailable, match="signs as the default verifier"):
        vs_mod.verifier_route(ROUTED["capability_id"])
    # One service, two names: the default verifier's URL under another id.
    monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", _route_table(url=METIS_URL))
    with pytest.raises(vs_mod.RouteUnavailable, match="default verifier's URL under another id"):
        vs_mod.verifier_route(ROUTED["capability_id"])
    # The same id at the default's own URL is the same service: allowed.
    monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", _route_table(url=METIS_URL, verifier_id="metis.verify@v1"))
    assert vs_mod.verifier_route(ROUTED["capability_id"]).routed is True
    # With no default verifier named there is nobody to be confused with.
    monkeypatch.delenv("AIMARKET_VERIFY_METIS_URL")
    monkeypatch.delenv("METIS_URL", raising=False)
    monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", _route_table(verifier_id="metis.verify@v1"))
    assert vs_mod.verifier_route(ROUTED["capability_id"]).verifier_id == "metis.verify@v1"


def test_problems_name_settings_never_the_token(monkeypatch):
    _env(monkeypatch, _route_table(verifier_id="metis.verify@v1"), **{GAIA_KEY_ENV: GAIA_TOKEN})
    with pytest.raises(vs_mod.RouteUnavailable) as exc:
        vs_mod.verifier_route(ROUTED["capability_id"])
    route = vs_mod.route_table()[0]
    assert GAIA_TOKEN not in str(exc.value) and GAIA_TOKEN not in repr(route)
    assert route.key_env == GAIA_KEY_ENV


def test_plan_refuses_an_unroutable_capability_and_keeps_the_rest(monkeypatch):
    block = VerifyBlock(requested=True, intent="switch the heater on")
    kw = dict(list_price=1.0, crypto_on=True, sandbox_mode=False, channel_id="ch_1")
    _env(monkeypatch, _route_table())
    monkeypatch.delenv(GAIA_KEY_ENV, raising=False)
    routed = vs_mod.plan(block, capability_id=ROUTED["capability_id"], **kw)
    assert routed.error.startswith("verify_unavailable") and not routed.active
    assert GAIA_KEY_ENV not in routed.error          # the detail is for the operator's log
    assert vs_mod.plan(block, capability_id=PLAIN["capability_id"], **kw).active is True
    # With no default verifier named, a routed capability is still verifiable.
    monkeypatch.setenv(GAIA_KEY_ENV, GAIA_TOKEN)
    monkeypatch.delenv("AIMARKET_VERIFY_METIS_URL", raising=False)
    monkeypatch.delenv("METIS_URL", raising=False)
    assert vs_mod.plan(block, capability_id=ROUTED["capability_id"], **kw).active is True
    assert vs_mod.plan(block, capability_id=PLAIN["capability_id"], **kw).error.startswith(
        "verify_unavailable: this hub has no verifier configured")


def test_skipped_envelopes_name_the_routed_verifier(monkeypatch):
    _env(monkeypatch, _route_table(), **{GAIA_KEY_ENV: GAIA_TOKEN})
    block = VerifyBlock(requested=True, intent="x", mode="auto")
    assert vs_mod.skipped_envelope_for(block, reason="federated_unsupported",
                                       capability_id=ROUTED["capability_id"])["verifier"] == GAIA_ID
    assert vs_mod.skipped_envelope_for(block, reason="federated_unsupported",
                                       capability_id=PLAIN["capability_id"])["verifier"] == "metis.verify@v1"
    floor = vs_mod.plan(block, list_price=0.01, crypto_on=True, sandbox_mode=False,
                        channel_id="ch_1", capability_id=ROUTED["capability_id"])
    assert floor.skipped_envelope["reason"] == "below_price_floor"
    assert floor.skipped_envelope["verifier"] == GAIA_ID


def test_the_well_known_document_says_who_judges_what_and_nothing_secret(monkeypatch):
    _env(monkeypatch, _route_table(), **{GAIA_KEY_ENV: GAIA_TOKEN})
    ad = vs_mod.advertisement()
    assert ad["enabled"] is True and ad["verifier"] == "metis.verify@v1"
    assert ad["routes"] == [{"capabilities": ROUTED["capability_id"], "verifier": GAIA_ID}]
    blob = json.dumps(ad)
    assert GAIA_TOKEN not in blob and GAIA_KEY_ENV not in blob and GAIA_URL not in blob
    # No routes: the document is what it always was.
    monkeypatch.delenv("AIMARKET_VERIFY_ROUTES")
    assert "routes" not in vs_mod.advertisement()
    # An unusable table turns Pay-on-Verified off, and says so.
    monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", "{oops")
    ad = vs_mod.advertisement()
    assert ad["enabled"] is False and ad["reason"] == "the verifier routing table is invalid"


# ── Money paths through a route ──────────────────────────────────────────────


def test_a_routed_capability_is_judged_by_its_route_with_its_own_token(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    h = _build(tmp_path, monkeypatch)
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret).json()
        env = body["verification"]
        assert env["status"] == "settled" and env["verified"] is True and env["verdict"] == "passed"
        assert env["verifier"] == GAIA_ID and env["trace_id"] == "tr_gaia"
        assert h.signer.verify_verification_signature(env)
        assert channels_mod._ledger.get(channel_id)["used_usd"] == pytest.approx(0.40)
        assert _reputation(h.db) == ["verify_passed"]
        assert _bearers(h.gaia) == [f"Bearer {GAIA_TOKEN}"] and h.metis.calls == []
        sent = h.gaia.calls[0]
        assert sent["url"] == f"{GAIA_URL}/v1/verify"
        assert sent["payload"]["min_verify_score"] == pytest.approx(0.7)
        assert "audit_id" in sent["payload"] and _FENCE_RE.search(sent["payload"]["input"])

        # The capability no route matches: the default verifier, its own key, as before.
        body = _invoke(client, PLAIN, channel_id, secret).json()
        env = body["verification"]
        assert env["status"] == "settled" and env["verifier"] == "metis.verify@v1"
        assert env["trace_id"] == "tr_metis"
        assert _bearers(h.metis) == [f"Bearer {METIS_TOKEN}"] and len(h.gaia.calls) == 1
    assert GAIA_TOKEN not in caplog.text and METIS_TOKEN not in caplog.text


def test_with_a_table_an_unmatched_capability_sees_no_difference(tmp_path, monkeypatch):
    """Same request to the default verifier, same envelope, table or no table."""
    seen = {}
    for label, routes in (("none", ""), ("table", _route_table())):
        h = _build(tmp_path / label, monkeypatch, routes=routes)
        with TestClient(h.app) as client:
            channel_id, secret = _open(client)
            env = _invoke(client, PLAIN, channel_id, secret).json()["verification"]
        call = h.metis.calls[0]
        seen[label] = (
            call["url"], call["headers"], sorted(call["payload"]),
            {k: env[k] for k in ("status", "verifier", "verdict", "verified", "threshold", "mode",
                                 "reason", "verify_score", "audit_score")},
        )
    assert seen["none"] == seen["table"]


def test_a_routed_fail_refunds_and_blames_through_the_route(tmp_path, monkeypatch):
    h = _build(tmp_path, monkeypatch, gaia=_Verifier("gaia", [("gaia", False, 0.0)], trace="tr_gaia"))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret).json()
        env = body["verification"]
        assert env["status"] == "refunded" and env["verdict"] == "failed"
        assert env["verifier"] == GAIA_ID and env["delivery_reasons"] == ["actuation:no_effect"]
        assert h.signer.verify_verification_signature(env)
        assert body["rejection_receipt"]["trace_id"] == "tr_gaia"
        ch = channels_mod._ledger.get(channel_id)
        assert ch["used_usd"] == pytest.approx(0.0) and ch["balance_usd"] == pytest.approx(DEPOSIT)
        assert _reputation(h.db) == ["verify_failed"]
        h.hook.record_verified_failure.assert_called_once()
        assert h.hook.record_verified_failure.call_args.kwargs["publisher_id"] == "pub-translate"
        assert h.metis.calls == []


def test_a_routed_verifier_judging_at_another_bar_is_refused(tmp_path, monkeypatch):
    h = _build(tmp_path, monkeypatch,
               gaia=_Verifier("gaia", [("gaia", True, 1.0, 0.5)], trace="tr_gaia"))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        env = _invoke(client, ROUTED, channel_id, secret).json()["verification"]
        assert env["status"] == "refunded" and env["verdict"] == "indeterminate"
        assert env["reason"] == "threshold_mismatch" and env["verifier"] == GAIA_ID
        assert channels_mod._ledger.get(channel_id)["used_usd"] == pytest.approx(0.0)
        assert _reputation(h.db) == [] and not h.hook.record_verified_failure.called
        assert h.metis.calls == []


def test_routed_engine_errors_are_retried_then_settled_by_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_VERIFY_ENGINE_RETRIES", "2")
    h = _build(tmp_path, monkeypatch, gaia=_Verifier("gaia", [("engine",)]))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        env = _invoke(client, ROUTED, channel_id, secret).json()["verification"]
        assert env["status"] == "refunded" and env["reason"] == "metis_error_fail_closed"
        assert env["verifier"] == GAIA_ID
        assert len(h.gaia.calls) == 3 and h.metis.calls == []
        assert _reputation(h.db) == []


def test_routed_transport_failures_are_retried_at_the_route(tmp_path, monkeypatch):
    h = _build(tmp_path, monkeypatch, gaia=_Verifier(
        "gaia", [("transport",), ("http", 503), ("gaia", True, 1.0)], trace="tr_gaia"))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        env = _invoke(client, ROUTED, channel_id, secret).json()["verification"]
        assert env["status"] == "settled" and env["verifier"] == GAIA_ID
        assert len(h.gaia.calls) == 3 and h.metis.calls == []


def test_a_routed_verifier_refusing_the_token_settles_by_policy_not_by_metis(tmp_path, monkeypatch):
    """GAIA answers 401 to a wrong token: fatal, refunded under fail-closed, nobody blamed."""
    h = _build(tmp_path, monkeypatch, gaia=_Verifier("gaia", [("http", 401)]))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        env = _invoke(client, ROUTED, channel_id, secret).json()["verification"]
        assert env["status"] == "refunded" and env["verdict"] == "indeterminate"
        assert env["verifier"] == GAIA_ID
        assert channels_mod._ledger.get(channel_id)["used_usd"] == pytest.approx(0.0)
        assert h.metis.calls == [] and _reputation(h.db) == []


# ── Misconfiguration never falls back to the default verifier ───────────────


@pytest.mark.parametrize("break_it", ["bad_json", "unset_key"])
def test_an_unusable_route_refuses_the_opt_in_before_any_work(tmp_path, monkeypatch, break_it, caplog):
    caplog.set_level(logging.WARNING)
    h = _build(tmp_path, monkeypatch, routes="{oops" if break_it == "bad_json" else None)
    if break_it == "unset_key":
        monkeypatch.delenv(GAIA_KEY_ENV)
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        r = _invoke(client, ROUTED, channel_id, secret)
        assert r.status_code == 400, r.text
        assert r.json()["error"] == "verify_invalid"
        assert r.json()["detail"].startswith("verify_unavailable")
        assert GAIA_KEY_ENV not in r.text
        ch = channels_mod._ledger.get(channel_id)
        assert ch["used_usd"] == pytest.approx(0.0) and ch["balance_usd"] == pytest.approx(DEPOSIT)
        plain = _invoke(client, PLAIN, channel_id, secret)
        if break_it == "bad_json":
            # Which capabilities the table meant to route cannot be known: refuse them all.
            assert plain.status_code == 400
            assert "not valid JSON" in caplog.text
        else:
            assert plain.status_code == 200 and plain.json()["verification"]["status"] == "settled"
            assert f"{GAIA_KEY_ENV} is not set" in caplog.text
        assert h.gaia.calls == []
        assert len(h.metis.calls) == (0 if break_it == "bad_json" else 1)
    assert GAIA_TOKEN not in caplog.text


def test_a_route_that_breaks_while_a_settlement_waits_keeps_the_hold(tmp_path, monkeypatch):
    """Registered under a working route, then the route breaks: the worker waits (the hold
    is buyer-safe), never asks the default verifier, and settles at the route once fixed."""
    gate = threading.Event()
    h = _build(tmp_path, monkeypatch, gaia=_Verifier(
        "gaia", [("gate", gate, ("transport",)), ("gaia", True, 1.0)], trace="tr_gaia"))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret, verify={**VERIFY, "wait": False}).json()
        nonce = body["receipt"]["nonce"]
        assert body["verification"]["status"] == "pending"
        assert body["verification"]["verifier"] == GAIA_ID
        monkeypatch.delenv(GAIA_KEY_ENV)          # the operator's redeploy lost the token
        gate.set()                                # the in-flight attempt fails: transport
        deadline = time.time() + 0.6
        while time.time() < deadline:
            assert _lookup(client, nonce)["verification"]["status"] == "pending"
            time.sleep(0.05)
        assert h.metis.calls == [] and len(h.gaia.calls) == 1
        assert channels_mod._ledger.get(channel_id)["used_usd"] == pytest.approx(0.0)
        monkeypatch.setenv(GAIA_KEY_ENV, GAIA_TOKEN)   # fixed
        env = _await_status(client, nonce, ("settled", "refunded"))["verification"]
        assert env["status"] == "settled" and env["verifier"] == GAIA_ID
        assert h.metis.calls == [] and _bearers(h.gaia)[-1] == f"Bearer {GAIA_TOKEN}"


def test_a_broken_route_that_outlives_max_wait_refunds_and_still_never_asks_metis(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_VERIFY_MAX_WAIT_S", "0.3")
    gate = threading.Event()
    h = _build(tmp_path, monkeypatch, gaia=_Verifier("gaia", [("gate", gate, ("transport",))]))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret, verify={**VERIFY, "wait": False}).json()
        monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", "{broken")
        gate.set()
        env = _await_status(client, body["receipt"]["nonce"], ("settled", "refunded"))["verification"]
        assert env["status"] == "refunded" and env["verdict"] == "indeterminate"
        assert channels_mod._ledger.get(channel_id)["used_usd"] == pytest.approx(0.0)
        assert h.metis.calls == [] and _reputation(h.db) == []


def test_the_route_is_attributed_after_the_table_changes_under_a_pending_row(tmp_path, monkeypatch):
    """Pending under Metis, then a route appears: the verdict names the verifier that judged."""
    gate = threading.Event()
    h = _build(tmp_path, monkeypatch, routes="",
               metis=_Verifier("metis", [("gate", gate, ("transport",)), ("metis", True, 0.95)]))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret, verify={**VERIFY, "wait": False}).json()
        assert body["verification"]["verifier"] == "metis.verify@v1"
        monkeypatch.setenv("AIMARKET_VERIFY_ROUTES", _route_table())
        gate.set()
        env = _await_status(client, body["receipt"]["nonce"], ("settled", "refunded"))["verification"]
        assert env["status"] == "settled" and env["verifier"] == GAIA_ID
        assert h.signer.verify_verification_signature(env)
        assert len(h.metis.calls) == 1 and len(h.gaia.calls) == 1


def test_a_crash_between_the_decision_and_the_money_replays_the_same_attribution(tmp_path, monkeypatch):
    h = _build(tmp_path, monkeypatch)
    real_capture = vs_mod.capture_hold
    failures = {"n": 0}

    def flaky_capture(receipt_id):
        if failures["n"] == 0:
            failures["n"] += 1
            return {"error": "ledger unavailable"}
        return real_capture(receipt_id)

    monkeypatch.setattr(vs_mod, "capture_hold", flaky_capture)
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret, verify={**VERIFY, "wait": False}).json()
        nonce = body["receipt"]["nonce"]
        deadline = time.time() + 5
        while time.time() < deadline and failures["n"] == 0:
            time.sleep(0.02)
        row = h.svc._row(nonce)
        assert row["status"] == "finalizing"
        assert json.loads(row["final_json"])["verdict"]["judged_by"] == GAIA_ID
        client.portal.call(h.svc.sweep_appeals)
        env = _lookup(client, nonce)["verification"]
        assert env["status"] == "settled" and env["verifier"] == GAIA_ID
        assert channels_mod._ledger.get(channel_id)["used_usd"] == pytest.approx(0.40)
        assert _reputation(h.db) == ["verify_passed"]


# ── Per-verifier concurrency ─────────────────────────────────────────────────


def test_a_fast_route_never_queues_behind_a_slow_default_verifier(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_VERIFY_MAX_CONCURRENCY", "1")
    gate = threading.Event()
    h = _build(tmp_path, monkeypatch,
               metis=_Verifier("metis", [("gate", gate, ("metis", True, 0.95))]))
    try:
        with TestClient(h.app) as client:
            channel_id, secret = _open(client)
            slow = _invoke(client, PLAIN, channel_id, secret, verify={**VERIFY, "wait": False}).json()
            deadline = time.time() + 5
            while time.time() < deadline and not h.metis.calls:
                time.sleep(0.02)
            assert h.metis.calls, "the slow verifier never got the call"
            # Metis holds the only default slot; the routed capability settles anyway.
            env = _invoke(client, ROUTED, channel_id, secret).json()["verification"]
            assert env["status"] == "settled" and env["verifier"] == GAIA_ID
            assert _lookup(client, slow["receipt"]["nonce"])["verification"]["status"] == "pending"
            gate.set()
            _await_status(client, slow["receipt"]["nonce"], ("settled",))
    finally:
        gate.set()


# ── Appeals against a routed verdict ─────────────────────────────────────────


def test_a_routed_verdict_is_appealed_to_a_court_that_is_not_the_route(tmp_path, monkeypatch):
    h = _build(tmp_path, monkeypatch, window=WINDOW,
               court=_Verifier("court", [("metis", False, 0.1)], trace="tr_court"))
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret).json()
        nonce, env = body["receipt"]["nonce"], body["verification"]
        assert env["status"] == "provisional" and env["verifier"] == GAIA_ID
        assert env["appeal"]["verifier"] == "metis.appeal@v1"
        assert h.signer.verify_verification_signature(env)
        r = client.post(f"/ai-market/v2/verification/{nonce}/appeal",
                        headers={"X-Payment-Channel-Secret": secret}, json={"statement": "it never switched"})
        assert r.status_code == 202, r.text
        env = _await_status(client, nonce, ("settled", "refunded"))["verification"]
        assert env["status"] == "refunded" and env["appeal"]["outcome"] == "overturned"
        assert env["appeal"]["first_verifier"] == GAIA_ID
        assert h.signer.verify_verification_signature(env)
        rec = json.loads(h.svc._row(nonce)["appeal_json"])
        assert rec["first_verifier"] == GAIA_ID and rec["appeal_verifier"] == "metis.appeal@v1"
        # Each service got its own credential and nobody else's.
        assert _bearers(h.gaia) == [f"Bearer {GAIA_TOKEN}"]
        assert _bearers(h.court) == [f"Bearer {COURT_TOKEN}"]
        assert h.metis.calls == []
        ch = channels_mod._ledger.get(channel_id)
        assert ch["used_usd"] == pytest.approx(0.0) and ch["balance_usd"] == pytest.approx(DEPOSIT)


def test_a_court_at_the_routed_verifier_is_no_court_for_its_verdicts(tmp_path, monkeypatch):
    h = _build(tmp_path, monkeypatch, window=WINDOW)
    monkeypatch.setenv("AIMARKET_APPEAL_METIS_URL", GAIA_URL)
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        env = _invoke(client, ROUTED, channel_id, secret).json()["verification"]
        assert env["status"] == "settled" and "appeal" not in env      # settles at once
        # The default verifier's verdicts still have a court distinct from Metis.
        env = _invoke(client, PLAIN, channel_id, secret).json()["verification"]
        assert env["status"] == "provisional" and env["verifier"] == "metis.verify@v1"


def test_a_routed_verdict_can_be_appealed_to_the_default_verifier_as_court(tmp_path, monkeypatch):
    """The court is checked against the verifier that ruled, not against the default."""
    h = _build(tmp_path, monkeypatch, window=WINDOW,
               metis=_Verifier("metis", [("metis", True, 0.95)]))
    monkeypatch.setenv("AIMARKET_APPEAL_METIS_URL", METIS_URL)
    with TestClient(h.app) as client:
        channel_id, secret = _open(client)
        body = _invoke(client, ROUTED, channel_id, secret).json()
        nonce = body["receipt"]["nonce"]
        assert body["verification"]["status"] == "provisional"
        r = client.post(f"/ai-market/v2/verification/{nonce}/appeal",
                        headers={"X-Payment-Channel-Secret": secret})
        assert r.status_code == 202, r.text
        env = _await_status(client, nonce, ("settled", "refunded"))["verification"]
        assert env["appeal"]["outcome"] == "upheld" and env["status"] == "settled"
        # The Metis-as-court call carried the court's key, never the route's.
        assert _bearers(h.metis) == [f"Bearer {COURT_TOKEN}"]
        # …while a default-verifier verdict on this hub has no court at all.
        env = _invoke(client, PLAIN, channel_id, secret).json()["verification"]
        assert env["status"] == "settled" and "appeal" not in env
