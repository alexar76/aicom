"""The subcontracting example provider (examples/subcontract-capability) against the real hub.

`server.py` is loaded as it ships and wired to the hub app in-process: the hub executes it
exactly as it would over HTTPS (the envelope, the job token, the grant, a signature it
verifies — AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG=1), and the provider buys its two GAIA
readings back through the SAME app over the same request path a deployed one would use.
Only the network is replaced: the hub's outbound calls go to the provider and to a fake GAIA
peer, and the provider's go to the app. It is published through /supply/register from its
own capability.json, so the manifest the operator will publish is the one under test.

The root buyer is scripts/subcontract_canary.py, run against the same app, so the checks
the live canary will make are proven against the shape the hub really answers with.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests._mandate_kit import ADMIN_TOKEN, HUB, balance, funded_account, hub
from aimarket_hub import subcontract
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "subcontract-capability"
CANARY_PATH = Path(__file__).resolve().parents[2] / "scripts" / "subcontract_canary.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module      # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


witness_server = _load("weather_witness_server", EXAMPLE_DIR / "server.py")

PEER = "https://iot.gaia.test"
PEER_INVOKE = f"{PEER}/ai-market/v2/invoke"
WITNESS_URL = "http://127.0.0.1:9475/invoke"      # the UNI-rehearsal shape: a loopback provider
PUBLISHER = "aicom-weather-witness"
READING_PRICE = 0.001
WITNESS = {"product_id": "weather-witness", "capability_id": "weather.witness@v1", "input": {"city": "Helsinki"}}


def gaia_answer(body: dict, *, offline: tuple[str, ...] = ()) -> dict:
    """What GAIA's oracle_core answers for a place, trimmed to the fields that matter."""
    cap = body["capability_id"]
    if cap in offline:
        return {"ok": False, "error": "upstream relay offline", "refuse_reason": "upstream relay offline"}
    if cap == "gaia.weather.read@v1":
        output = {
            "reading": {"device_id": "om-wx-helsinki", "seq": 7, "ts": "2026-09-26T10:00:00Z",
                        "values": {"temperature_c": 11.2, "humidity_pct": 81.0},
                        "units": {"temperature_c": "°C", "humidity_pct": "%"}},
            "attestation": {"alg": "ed25519", "device_pubkey": "d2VhdGhlcg==", "signature": "c2ln"},
            "resolved": {"requested": "Helsinki", "matched_place": "Helsinki", "device_id": "om-wx-helsinki",
                         "relay_latitude": 60.1699, "relay_longitude": 24.9384, "distance_km": 0.0},
        }
    else:
        output = {
            "reading": {"device_id": "om-aq-helsinki", "seq": 3, "ts": "2026-09-26T09:30:00Z",
                        "values": {"pm2_5": 4.1, "european_aqi": 12}, "units": {"pm2_5": "µg/m³"}},
            "attestation": {"alg": "ed25519", "device_pubkey": "YWly", "signature": "c2ln"},
            "resolved": {"requested": "Helsinki", "matched_place": "Helsinki", "device_id": "om-aq-helsinki",
                         "latitude": 60.1699, "longitude": 24.9384},
        }
    return {"capability_id": cap, "output": output, "price_usd": READING_PRICE,
            "receipt": {"nonce": f"gaia-{cap}", "latency_ms": 9, "price_usd": READING_PRICE}}


class _Resp:
    def __init__(self, status: int, headers: dict[str, str], body: bytes):
        self.status_code = status
        self.headers = httpx.Headers(headers)
        self.content = body
        self.text = body.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.content)


@dataclass
class World:
    client: Any
    db: Any
    witness: Any
    provider_calls: list[tuple[str, str, dict]] = field(default_factory=list)   # the provider's outbound
    hub_to_provider: list[dict] = field(default_factory=list)                   # headers the hub sent it
    gaia_calls: list[dict] = field(default_factory=list)                        # headers GAIA received

    def purchases(self) -> list[tuple[str, dict]]:
        return [(url, h) for method, url, h in self.provider_calls if method == "POST"]


@contextmanager
def witness_world(monkeypatch, tmp_path, *, offline: tuple[str, ...] = (), **env):
    env = {
        # The apex's own configuration for GAIA: the hub is seller of record, no routing fee.
        "AIMARKET_SELLS_FOR": PEER,
        # The hub checks the provider's signature, as it does in production.
        "AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG": "1",
        # The runbook's collateral exemption — every other publish gate still applies.
        "AIMARKET_SUPPLY_OPERATOR_PUBLISHERS": PUBLISHER,
        "AIMARKET_ALLOW_LOCAL_PUBLISH": "1",
        "AIMARKET_ORACLE_FAMILY_URL": "off",
        "AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE": "off",
        **env,
    }
    with hub(monkeypatch, tmp_path, **env) as (client, db):
        import aimarket_hub.api as api_mod
        import aimarket_hub.peer_routing as peer_routing
        import aimarket_hub.outbound_http as outbound

        world = World(client, db, None)

        def transport(method, url, headers, body, timeout):
            # Called from the provider's worker threads, exactly like urllib would be; the
            # TestClient hands each request to the running app's event loop.
            world.provider_calls.append((method, url, dict(headers)))
            r = client.request(method, url, headers=dict(headers), content=body)
            return r.status_code, dict(r.headers), r.content

        cfg = witness_server.Config(hub_url=HUB, key_path=tmp_path / "witness" / "provider_key",
                                    state_path=tmp_path / "witness" / "daily_spend.json",
                                    child_source_hub=PEER)
        world.witness = witness_server.Witness(cfg, transport=transport)

        async def safe_post(url, *, json=None, headers=None, timeout=30.0, invoke=False, oracle_paid=False):
            sent = {k: v for k, v in (headers or {}).items() if v}
            if url == WITNESS_URL:
                world.hub_to_provider.append(sent)
                raw = __import__("json").dumps(json or {}).encode()
                status, out_headers, out = await asyncio.to_thread(world.witness.handle, sent, raw)
                return _Resp(status, out_headers, out)
            if url == PEER_INVOKE:
                world.gaia_calls.append(sent)
                answer = gaia_answer(json or {}, offline=offline)
                return _Resp(200, {"content-type": "application/json"}, __import__("json").dumps(answer).encode())
            raise AssertionError(f"unexpected outbound POST {url}")

        async def safe_get(url, *, timeout=10.0):
            assert url == f"{PEER}/.well-known/ai-market.json", url
            return _Resp(200, {}, b'{"name": "gaia", "mcp_endpoint": "%s"}' % PEER_INVOKE.encode())

        monkeypatch.setattr(outbound, "safe_post", safe_post)
        monkeypatch.setattr(outbound, "safe_get", safe_get)
        monkeypatch.setattr(peer_routing, "_peer_endpoint_cache", {})
        db.upsert_peer(Peer(url=PEER, name="gaia", capabilities_count=2,
                            well_known_url=f"{PEER}/.well-known/ai-market.json", trusted=True))
        for cap in ("gaia.weather.read@v1", "gaia.air.read@v1"):
            db.upsert_capability(Capability(
                capability_id=cap, product_id="gaia.gateway", name=cap, price_per_call_usd=READING_PRICE,
                source_hub=PEER, source_hub_name=PEER, trust_score=0.5,
            ))

        # Published from the example's own manifest, through the operator's door.
        manifest = json.loads((EXAMPLE_DIR / "capability.json").read_text(encoding="utf-8"))
        manifest.update(invoke_url=WITNESS_URL, provider_pubkey=world.witness.pubkey_b64)
        r = client.post("/ai-market/v2/supply/register", json=manifest,
                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        assert r.status_code == 200, r.text
        yield world


def _root_call(world: World, api_key: str, *, allowance: float | None = 0.01):
    payload = dict(WITNESS)
    if allowance is not None:
        payload["subcontract"] = {"allowance_usd": allowance, "max_depth": 1}
    return world.client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=payload)


# ── the provider, bought through the hub ────────────────────────────────


class TestCostPlus:
    def test_the_witness_is_paid_from_the_buyers_allowance(self, monkeypatch, tmp_path):
        with witness_world(monkeypatch, tmp_path) as world:
            account, api_key = funded_account(world.client, world.db, 1.0)
            r = _root_call(world, api_key)
            assert r.status_code == 200, r.text
            body = r.json()
            buyer_left = balance(world.db, account)

        result, sub = body["result"], body["subcontracting"]
        assert result["witness"] == "weather-witness/1" and result["funding"] == "cost-plus"
        assert result["agreement"]["agree"] is True
        assert result["agreement"]["location_km"] == 0.0 and result["agreement"]["time_apart_s"] == 1800
        assert result["weather"]["reading"]["values"]["temperature_c"] == 11.2
        assert result["air"]["attestation"]["signature"] == "c2ln"      # GAIA's own proof, verbatim
        # Two readings, bought inside the buyer's job, paid from the allowance.
        assert sorted((n["capability_id"], n["status"], n["funded_by"]) for n in sub["nodes"]) == [
            ("gaia.air.read@v1", "captured", "allowance"), ("gaia.weather.read@v1", "captured", "allowance")]
        assert sub["spent_usd"] == pytest.approx(2 * READING_PRICE)
        assert sub["spent_usd"] + sub["released_usd"] == pytest.approx(0.01)
        assert {c["node"] for c in result["children"]} == {n["node"] for n in sub["nodes"]}
        assert result["job"]["job_id"] == sub["job_id"]
        # The buyer paid the witness and its two readings — nothing else.
        assert buyer_left == pytest.approx(1.0 - 0.002 - 2 * READING_PRICE)

        # What crossed each hop: the hub sent the token and the grant; the provider sent them
        # back and NO other payment; GAIA, a peer, saw neither.
        assert subcontract.JOB_HEADER in world.hub_to_provider[0]
        assert subcontract.GRANT_HEADER in world.hub_to_provider[0]
        purchases = world.purchases()
        assert len(purchases) == 2
        for url, headers in purchases:
            assert url == f"{HUB}/ai-market/v2/invoke"
            assert headers[subcontract.JOB_HEADER] == world.hub_to_provider[0][subcontract.JOB_HEADER]
            assert headers[subcontract.GRANT_HEADER] == world.hub_to_provider[0][subcontract.GRANT_HEADER]
            assert "X-API-Key" not in headers and "X-Payment-Channel" not in headers
        for sent in world.gaia_calls:
            assert subcontract.JOB_HEADER not in sent and subcontract.GRANT_HEADER not in sent

    def test_the_hub_key_is_read_once_from_the_well_known(self, monkeypatch, tmp_path):
        with witness_world(monkeypatch, tmp_path) as world:
            _, api_key = funded_account(world.client, world.db, 1.0)
            assert _root_call(world, api_key).status_code == 200
            assert _root_call(world, api_key).status_code == 200
            gets = [url for method, url, _ in world.provider_calls if method == "GET"]
            hub_key = world.client.get("/.well-known/ai-market.json").json()["signer_public_key"]
        assert gets == [f"{HUB}/.well-known/ai-market.json"]
        assert world.witness.hub_key.b64 == hub_key

    def test_the_hub_refuses_a_reply_signed_with_another_key(self, monkeypatch, tmp_path):
        """The signature is really checked: a provider answering under a key that is not the
        published provider_pubkey is a 502, and the buyer pays only the readings it consumed."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        with witness_world(monkeypatch, tmp_path) as world:
            world.witness.key = Ed25519PrivateKey.generate()
            account, api_key = funded_account(world.client, world.db, 1.0)
            r = _root_call(world, api_key)
            buyer_left = balance(world.db, account)
        assert r.status_code == 502 and "signature" in r.text
        # Cost-plus, §6.3: materials consumed are paid for; the failing provider is not.
        assert buyer_left == pytest.approx(1.0 - 2 * READING_PRICE)

    def test_a_root_over_a2a_opens_the_same_job(self, monkeypatch, tmp_path):
        """The root buyer speaks A2A 1.0 (the SDK's A2AClient); only the root changes
        protocol. The witness still buys at /invoke with the token and the grant, the two
        readings are carved out of the same allowance, and the Task carries the bill."""
        from aimarket_agent.a2a import A2AClient, task_result, task_state

        with witness_world(monkeypatch, tmp_path) as world:
            account, api_key = funded_account(world.client, world.db, 1.0)
            a2a = A2AClient(HUB, api_key=api_key)
            a2a.session = world.client       # TestClient is an httpx.Client: the real app
            task = a2a.invoke(WITNESS["product_id"], WITNESS["capability_id"], WITNESS["input"],
                              subcontract={"allowance_usd": 0.01, "max_depth": 1})
            buyer_left = balance(world.db, account)
            sub = task["metadata"]["aimarket"]["subcontracting"]
            tree = world.client.get(f"/ai-market/v2/jobs/{sub['job_id']}").json()

        assert task_state(task) == "TASK_STATE_COMPLETED"
        assert task_result(task)["funding"] == "cost-plus"
        assert sorted((n["capability_id"], n["status"], n["funded_by"]) for n in sub["nodes"]) == [
            ("gaia.air.read@v1", "captured", "allowance"), ("gaia.weather.read@v1", "captured", "allowance")]
        assert sub["spent_usd"] == pytest.approx(2 * READING_PRICE)
        assert sub["spent_usd"] + sub["released_usd"] == pytest.approx(0.01)
        assert buyer_left == pytest.approx(1.0 - 0.002 - 2 * READING_PRICE)
        assert tree["allowance_status"] == "closed" and len(tree["nodes"]) == 3
        assert subcontract.GRANT_HEADER in world.hub_to_provider[0]
        purchases = world.purchases()
        assert [url for url, _ in purchases] == [f"{HUB}/ai-market/v2/invoke"] * 2

    def test_a_root_that_fails_over_a2a_still_shows_the_bill_it_paid(self, monkeypatch, tmp_path):
        """§6.3/§6.4: the weather reading was delivered, so it is paid for although the
        witness then fails. The REST answer explains that charge with its bill; the Task used
        to keep only the error, so an A2A buyer was charged with nothing to say for what."""
        from aimarket_agent.a2a import A2AClient, task_state

        with witness_world(monkeypatch, tmp_path, offline=("gaia.air.read@v1",)) as world:
            account, api_key = funded_account(world.client, world.db, 1.0)
            a2a = A2AClient(HUB, api_key=api_key)
            a2a.session = world.client
            task = a2a.invoke(WITNESS["product_id"], WITNESS["capability_id"], WITNESS["input"],
                              subcontract={"allowance_usd": 0.01, "max_depth": 1})
            buyer_left = balance(world.db, account)
            again = world.client.post("/a2a", headers={"A2A-Version": "1.0", "X-API-Key": api_key}, json={
                "jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task["id"]}}).json()["result"]

        assert task_state(task) == "TASK_STATE_FAILED"
        assert buyer_left == pytest.approx(1.0 - READING_PRICE)
        for seen in (task, again):
            sub = seen["metadata"]["aimarket"]["subcontracting"]
            assert sorted((n["capability_id"], n["status"]) for n in sub["nodes"]) == [
                ("gaia.air.read@v1", "failed"), ("gaia.weather.read@v1", "captured")]
            assert sub["spent_usd"] == pytest.approx(READING_PRICE)
            assert sub["spent_usd"] + sub["released_usd"] == pytest.approx(0.01)

    def test_a_provider_cannot_buy_inside_the_job_over_a2a(self, monkeypatch, tmp_path):
        """/a2a refuses job headers rather than dropping them: dropped, an allowance-funded
        purchase would silently become a stranger's, paid by nobody or by the wrong key."""
        with witness_world(monkeypatch, tmp_path) as world:
            r = world.client.post("/a2a", headers={
                "A2A-Version": "1.0", subcontract.JOB_HEADER: "token", subcontract.GRANT_HEADER: "grant",
            }, json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": {
                "messageId": "m", "role": "ROLE_USER", "parts": [{"data": {"invoke": {
                    "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
                    "source_hub": PEER, "input": {"city": "Helsinki"}}}}]}}})
        assert r.json()["error"]["code"] == -32602
        assert "/ai-market/v2/invoke" in r.json()["error"]["message"]
        assert world.gaia_calls == []

    def test_one_reading_is_not_a_witness(self, monkeypatch, tmp_path):
        with witness_world(monkeypatch, tmp_path, offline=("gaia.air.read@v1",)) as world:
            account, api_key = funded_account(world.client, world.db, 1.0)
            r = _root_call(world, api_key)
            buyer_left = balance(world.db, account)
        assert r.status_code == 502
        # GAIA's refusal of the air reading cost nothing; the weather reading was delivered.
        assert buyer_left == pytest.approx(1.0 - READING_PRICE)


class TestFixedPrice:
    def test_it_pays_its_own_way_within_its_daily_cap(self, monkeypatch, tmp_path):
        with witness_world(monkeypatch, tmp_path) as world:
            provider_account, provider_key = funded_account(world.client, world.db, 0.10)
            world.witness.cfg.api_key = provider_key
            # One call in flight reserves two ceilings ($0.02); settled, it counts what the
            # readings cost plus the fee rate the hub reports ($0.00202). $0.021 is one call.
            world.witness.cap = witness_server.DailyCap(world.witness.cfg.state_path, 0.021)
            account, api_key = funded_account(world.client, world.db, 1.0)
            first = _root_call(world, api_key, allowance=None)
            assert first.status_code == 200, first.text
            second = _root_call(world, api_key, allowance=None)
            buyer_left = balance(world.db, account)
            provider_left = balance(world.db, provider_account)
            used = world.witness.cap.used_micro()

        body = first.json()
        assert body["result"]["funding"] == "fixed-price"
        assert sorted((n["status"], n["funded_by"]) for n in body["subcontracting"]["nodes"]) == [
            ("captured", "own"), ("captured", "own")]
        assert "allowance_usd" not in body["subcontracting"]
        # The provider paid the readings; the buyer paid the witness, once.
        assert provider_left == pytest.approx(0.10 - 2 * READING_PRICE)
        assert buyer_left == pytest.approx(1.0 - 0.002)
        assert used == 2 * 1_010
        # The second call would have taken the cap over: refused before anything was bought.
        assert second.status_code == 502 and "daily_cap_reached" in second.text
        assert len(world.purchases()) == 2
        for _, headers in world.purchases():
            assert headers["X-API-Key"] == provider_key and subcontract.GRANT_HEADER not in headers

    def test_without_an_allowance_or_a_key_of_its_own_it_spends_nothing(self, monkeypatch, tmp_path):
        with witness_world(monkeypatch, tmp_path) as world:
            account, api_key = funded_account(world.client, world.db, 1.0)
            r = _root_call(world, api_key, allowance=None)
            buyer_left = balance(world.db, account)
        assert r.status_code == 502 and "allowance_required" in r.text
        assert world.purchases() == []
        assert buyer_left == pytest.approx(1.0)


# ── nobody but the hub can make it spend ────────────────────────────────


def _token(signer: Signer, *, iss: str = HUB, path=("weather.witness@v1",), depth: int = 0,
           max_depth: int = 1, now: float | None = None, product_id: str = "weather-witness") -> str:
    ctx = subcontract.JobContext(job_id="job_" + "ab" * 12, node="node_" + hashlib.sha256(
        f"{time.time_ns()}".encode()).hexdigest()[:24], depth=depth, max_depth=max_depth, path=list(path),
        product_id=product_id)
    return subcontract.JobStore(None, signer, iss).issue_token(ctx, now=now)


@pytest.fixture
def lone_witness(tmp_path):
    """The provider with the hub's key pinned and a transport that records every attempt."""
    hub_signer = Signer(tmp_path / "hub_key")
    calls: list[tuple[str, str]] = []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url))
        return 599, {}, b"{}"

    cfg = witness_server.Config(hub_url=HUB, key_path=tmp_path / "w" / "key", state_path=tmp_path / "w" / "cap.json",
                                hub_signer_pubkey=hub_signer.public_key_b64, api_key="aimk_providers_own")
    return witness_server.Witness(cfg, transport=transport), hub_signer, calls


def _call(witness, token: str | None, *, grant: str = "") -> tuple[int, dict]:
    headers = {}
    if token is not None:
        headers[subcontract.JOB_HEADER] = token
    if grant:
        headers[subcontract.GRANT_HEADER] = grant
    status, _, body = witness.handle(headers, json.dumps(WITNESS).encode())
    return status, json.loads(body)


class TestTokenGate:
    def test_no_token_no_purchase(self, lone_witness):
        witness, _, calls = lone_witness
        status, body = _call(witness, None)
        assert (status, body["error"]) == (403, "job_required")
        assert calls == []

    @pytest.mark.parametrize("case, error, why", [
        ("forged", "job_invalid", "not signed by the hub"),
        ("expired", "job_invalid", "expired"),
        ("other_hub", "job_invalid", "another hub"),
        ("other_capability", "job_invalid", "uni.answer@v1"),
        ("no_depth_left", "job_limit", "no deeper"),
        ("garbage", "job_invalid", "not a job token"),
    ])
    def test_a_token_the_hub_did_not_issue_for_this_call_is_refused(self, lone_witness, tmp_path, case, error, why):
        witness, hub_signer, calls = lone_witness
        token = {
            "forged": lambda: _token(Signer(tmp_path / "someone_else")),
            "expired": lambda: _token(hub_signer, now=time.time() - 120),
            "other_hub": lambda: _token(hub_signer, iss="https://other-hub.test"),
            "other_capability": lambda: _token(hub_signer, path=("uni.answer@v1",)),
            "other_product": lambda: _token(hub_signer, product_id="mallory-witness"),
            "no_depth_left": lambda: _token(hub_signer, depth=1, max_depth=1),
            "garbage": lambda: "not-a-token-at-all",
        }[case]()
        status, body = _call(witness, token, grant="a-leaked-grant")
        assert (status, body["error"]) == (403, error) and why in body["detail"]
        assert calls == [], "the provider bought something for a token it should have refused"

    def test_a_token_is_served_once(self, lone_witness):
        witness, hub_signer, calls = lone_witness
        token = _token(hub_signer)
        first, _ = _call(witness, token)
        assert first == 502 and len(calls) == 2           # verified, bought (the fake hub failed)
        again, body = _call(witness, token)
        assert (again, body["error"]) == (403, "job_replayed") and len(calls) == 2

    def test_a_real_hub_token_does_not_work_a_second_time(self, monkeypatch, tmp_path):
        """A token captured on the way to the provider and replayed at its public URL."""
        with witness_world(monkeypatch, tmp_path) as world:
            _, api_key = funded_account(world.client, world.db, 1.0)
            assert _root_call(world, api_key).status_code == 200
            seen = world.hub_to_provider[0]
            status, _, body = world.witness.handle(seen, json.dumps(WITNESS).encode())
        assert status == 403 and json.loads(body)["error"] == "job_replayed"
        assert len(world.purchases()) == 2

    def test_bad_input_is_refused_before_anything_is_bought(self, lone_witness):
        witness, hub_signer, calls = lone_witness
        status, _, body = witness.handle({subcontract.JOB_HEADER: _token(hub_signer)},
                                         json.dumps({**WITNESS, "input": {"latitude": 91, "longitude": 0}}).encode())
        assert status == 400 and json.loads(body)["error"] == "input_invalid" and calls == []


# ── the parts, on their own ─────────────────────────────────────────────


class TestParts:
    def test_the_signature_canonical_is_the_hubs(self):
        from aimarket_hub.supply_security import _bound_response_canonical

        result = {"t": 11.2, "place": "Хельсинки", "nested": {"b": [1, 2.5], "a": None}}
        for args in (("weather.witness@v1", "weather-witness", {"city": "Tōkyō"}, result),
                     ("weather.witness@v1", "typed-by-buyer", None, result)):
            assert witness_server.bound_canonical(*args) == _bound_response_canonical(*args)

    def test_readings_far_apart_or_stale_do_not_agree(self):
        weather = gaia_answer({"capability_id": "gaia.weather.read@v1"})
        air = gaia_answer({"capability_id": "gaia.air.read@v1"})
        air["output"]["resolved"].update(latitude=59.33, longitude=18.07)       # Stockholm
        air["output"]["reading"]["ts"] = "2026-09-26T05:00:00Z"
        verdict = witness_server.agreement(weather, air)
        assert verdict["agree"] is False and verdict["location_km"] > 350
        assert len(verdict["reasons"]) == 2
        unknown = witness_server.agreement({"output": {}}, air)
        assert unknown["agree"] is False and unknown["location_km"] is None

    def test_the_cap_counts_upward_and_resets_by_utc_day(self, tmp_path):
        now = [1_790_000_000.0]
        cap = witness_server.DailyCap(tmp_path / "cap.json", 0.03, now=lambda: now[0])
        reservation = cap.reserve(20_000)
        assert reservation and not cap.reserve(20_000)
        cap.settle(reservation, 2_020)
        assert cap.used_micro() == 2_020 and cap.reserve(20_000)
        now[0] += 86_400
        assert cap.used_micro() == 0

    def test_what_a_purchase_may_have_cost(self):
        ceiling = 10_000
        assert witness_server.cost_bound(200, {"success": True, "price_usd": 0.001, "routing_fee_bps": 100}, ceiling) == 1_010
        assert witness_server.cost_bound(200, {"success": True, "price_usd": "lots"}, ceiling) == ceiling
        assert witness_server.cost_bound(200, {"success": True, "price_usd": 50}, ceiling) == ceiling
        assert witness_server.cost_bound(0, {}, ceiling) == ceiling            # timed out: unknown
        assert witness_server.cost_bound(502, {}, ceiling) == ceiling
        assert witness_server.cost_bound(402, {}, ceiling) == 0
        assert witness_server.cost_bound(200, {"success": False}, ceiling) == 0

    def test_yesterdays_refund_cannot_release_todays_reservations(self, tmp_path):
        now = [1_790_000_000.0]
        cap = witness_server.DailyCap(tmp_path / "cap.json", 0.05, now=lambda: now[0])
        yesterday = cap.reserve(20_000)
        now[0] += 86_400
        assert cap.reserve(20_000) and cap.reserve(20_000)
        cap.settle(yesterday, 2_020)
        assert cap.used_micro() == 40_000
        assert cap.reserve(20_000) is None

    def test_corrupt_daily_ledger_does_not_reset_the_budget(self, tmp_path):
        path = tmp_path / "cap.json"
        path.write_text("broken")
        cap = witness_server.DailyCap(path, 0.05)
        with pytest.raises(witness_server.Refusal, match="spending ledger"):
            cap.reserve(20_000)

    def test_an_unreadable_hub_key_refuses_and_is_not_refetched_per_call(self, tmp_path):
        """Otherwise every forged call a stranger sends is one more outbound request."""
        gets = []

        def transport(method, url, headers, body, timeout):
            gets.append(url)
            return 500, {}, b"{}"

        now = [1_790_000_000.0]
        cfg = witness_server.Config(hub_url=HUB, key_path=tmp_path / "k", state_path=tmp_path / "c.json")
        witness = witness_server.Witness(cfg, transport=transport, now=lambda: now[0])
        forged = _token(Signer(tmp_path / "x"))
        for _ in range(3):
            status, body = _call(witness, forged)
            assert (status, body["error"]) == (503, "hub_key_unavailable")
        assert len(gets) == 1
        now[0] += witness_server.HubKey.RETRY_AFTER_S + 1
        _call(witness, forged)
        assert len(gets) == 2

    def test_the_http_layer(self, tmp_path):
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer

        cfg = witness_server.Config(hub_url=HUB, key_path=tmp_path / "k", state_path=tmp_path / "c.json",
                                    hub_signer_pubkey=Signer(tmp_path / "h").public_key_b64)
        witness = witness_server.Witness(cfg, transport=lambda *a: (599, {}, b"{}"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), witness_server.make_handler(witness))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def fetch(path, data=None, headers=None):
            req = urllib.request.Request(base + path, data=data, headers=headers or {},
                                         method="POST" if data is not None else "GET")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read() or b"{}")

        try:
            status, health = fetch("/healthz")
            assert status == 200 and health["provider_pubkey"] == witness.pubkey_b64
            assert health["capability_id"] == "weather.witness@v1" and "api_key" not in json.dumps(health)
            assert fetch("/invoke", json.dumps(WITNESS).encode())[0] == 403
            assert fetch("/elsewhere", b"{}")[0] == 404
            too_big = json.dumps({**WITNESS, "pad": "x" * (witness_server.MAX_BODY_BYTES + 1)}).encode()
            assert fetch("/invoke", too_big)[0] == 413
        finally:
            server.shutdown()
            server.server_close()

    def test_a_key_is_created_private(self, tmp_path):
        path = tmp_path / "k" / "provider_key"
        key = witness_server.load_or_create_key(path)
        assert path.stat().st_mode & 0o777 == 0o600
        assert witness_server.public_key_b64(witness_server.load_or_create_key(path)) == \
            witness_server.public_key_b64(key)
        assert len(base64.b64decode(witness_server.public_key_b64(key))) == 32


# ── the root buyer: scripts/subcontract_canary.py ───────────────────────


@pytest.fixture
def canary():
    if not CANARY_PATH.exists():
        pytest.skip("scripts/subcontract_canary.py is not in this checkout")
    return _load("subcontract_canary", CANARY_PATH)


class _ClientHttp:
    def __init__(self, client):
        self.client = client

    @staticmethod
    def _out(r) -> tuple[int, Any]:
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None

    def get(self, url):
        return self._out(self.client.get(url))

    def post(self, url, payload, headers):
        return self._out(self.client.post(url, json=payload, headers=headers))


class TestCanary:
    @pytest.mark.parametrize("a2a", [False, True], ids=["invoke", "a2a"])
    @pytest.mark.parametrize("fixed_price", [False, True], ids=["cost-plus", "fixed-price"])
    def test_every_check_passes_against_the_real_flow(self, monkeypatch, tmp_path, canary, fixed_price, a2a):
        pytest.importorskip("aimarket_provenance")
        with witness_world(monkeypatch, tmp_path) as world:
            if fixed_price:
                _, world.witness.cfg.api_key = funded_account(world.client, world.db, 0.10)
            _, api_key = funded_account(world.client, world.db, 1.0)
            seen = canary.observe(HUB, api_key, city="Helsinki", allowance_usd=0.01,
                                  fixed_price=fixed_price, http=_ClientHttp(world.client), a2a=a2a)
        checks = canary.evaluate(seen, allowance_usd=0.01, fixed_price=fixed_price)
        failed = [(c.name, c.detail) for c in checks if not c.ok]
        assert failed == []
        expected = {"root_delivered", "two_children_captured", "witness_matches_bill",
                    "job_tree_readable", "receipt_commits_children"}
        assert {c.name for c in checks} >= (expected | {"a2a_task_completed"} if a2a else expected)

    def test_an_a2a_task_that_did_not_complete_is_not_a_delivery(self, canary):
        rejected = {"id": "a2at_x", "status": {"state": "TASK_STATE_REJECTED", "message": {
            "metadata": {"aimarket": {"error": "allowance_exhausted", "detail": "closed"}}}},
            "metadata": {"aimarket": {"subcontracting": {"job_id": "job_x", "nodes": []}}}}
        status, body = canary.task_as_invoke(rejected)
        assert status != 200 and body["success"] is False and body["error"] == "allowance_exhausted"
        seen = {"status": status, "body": body, "a2a": {"task_id": "a2at_x", "state": "TASK_STATE_REJECTED",
                                                        "reread_state": "TASK_STATE_REJECTED", "reread_same": True}}
        assert {c.name for c in canary.evaluate(seen, allowance_usd=0.01, fixed_price=False)
                if not c.ok} == {"a2a_task_completed", "root_delivered"}

    def test_it_fails_on_the_shapes_it_exists_to_catch(self, monkeypatch, tmp_path, canary):
        pytest.importorskip("aimarket_provenance")
        with witness_world(monkeypatch, tmp_path) as world:
            _, api_key = funded_account(world.client, world.db, 1.0)
            good = canary.observe(HUB, api_key, city="Helsinki", allowance_usd=0.01,
                                  fixed_price=False, http=_ClientHttp(world.client))

        def failing(mutate) -> set[str]:
            seen = json.loads(json.dumps(good))
            mutate(seen)
            return {c.name for c in canary.evaluate(seen, allowance_usd=0.01, fixed_price=False)
                    if not c.ok and c.critical}

        def one_child(s):
            s["body"]["subcontracting"]["nodes"] = s["body"]["subcontracting"]["nodes"][:1]

        def money_leaked(s):
            s["body"]["subcontracting"]["released_usd"] -= 0.001

        def unpriced_fee(s):
            s["body"]["subcontracting"]["spent_usd"] += 0.00002
            s["body"]["subcontracting"]["released_usd"] -= 0.00002

        def receipt_forgets(s):
            s["receipt"]["credentialSubject"]["parents"] = []

        def paid_by_itself(s):
            for n in s["body"]["subcontracting"]["nodes"]:
                n["funded_by"] = "own"

        assert "two_children_captured" in failing(one_child)
        assert failing(money_leaked) == {"allowance_accounted"}
        assert failing(unpriced_fee) == {"bill_adds_up"}
        assert failing(receipt_forgets) == {"receipt_commits_children"}
        assert "two_children_captured" in failing(paid_by_itself)
        assert failing(lambda s: s.update(status=502)) == {"root_delivered"}


def test_a_token_issued_to_another_product_with_the_same_capability_id_is_refused(monkeypatch, tmp_path):
    """Only (capability_id, product_id, source_hub) is unique, so another publisher can list
    its own product under weather.witness@v1. The hub hands that provider a job token whose
    path ends in weather.witness@v1 — replayed at the witness's public URL, the witness used
    to accept it and buy readings with its OWN key for a caller who never paid it. The token
    now names the product, and the witness checks it."""
    import aimarket_hub.outbound_http as outbound

    attacker_url = "http://127.0.0.1:9999/invoke"
    with witness_world(monkeypatch, tmp_path) as world:
        provider_account, provider_key = funded_account(world.client, world.db, 0.10)
        world.witness.cfg.api_key = provider_key          # fixed-price mode: its own money
        world.db.upsert_capability(Capability(
            capability_id="weather.witness@v1", product_id="mallory-witness", name="mallory",
            price_per_call_usd=0.0, source_hub="local", invoke_url=attacker_url,
            publisher_id="mallory", provider_pubkey="",
        ))
        replay: dict = {}
        inner_post = outbound.safe_post

        async def safe_post(url, *, json=None, headers=None, timeout=30.0, invoke=False, oracle_paid=False):
            if url == attacker_url:
                token = {k: v for k, v in (headers or {}).items() if v}[subcontract.JOB_HEADER]
                status, _, body = await asyncio.to_thread(
                    world.witness.handle, {subcontract.JOB_HEADER: token}, __import__("json").dumps(WITNESS).encode())
                replay["status"], replay["body"] = status, __import__("json").loads(body)
                return _Resp(200, {"content-type": "application/json"}, b'{"result": {"ok": true}}')
            return await inner_post(url, json=json, headers=headers, timeout=timeout, invoke=invoke)

        monkeypatch.setattr(outbound, "safe_post", safe_post)
        _, attacker_key = funded_account(world.client, world.db, 1.0)
        world.client.post("/ai-market/v2/invoke", headers={"X-API-Key": attacker_key},
                          json={"product_id": "mallory-witness", "capability_id": "weather.witness@v1",
                                "input": {"city": "Helsinki"}})
        assert replay["status"] == 403 and replay["body"]["error"] == "job_invalid", replay
        assert balance(world.db, provider_account) == pytest.approx(0.10)   # spent nothing
        assert world.witness.cap.used_micro() == 0
