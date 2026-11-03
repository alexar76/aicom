"""Where subcontracting meets routing and delegation (mandates.md §5.4, §6), end to end.

The SUB/1 and AMD/1 suites pin each mechanism on its own: a grant-funded child routed to a
peer, one delegated mandate paying for a local child, the allowance proxy's routing-fee debit
as a unit. What they leave open is where the mechanisms meet. Each property below is driven
through the HTTP app with real signed mandates, real job tokens and a fake peer on the
outbound transport, and each would fail if the line it names were removed or inverted:

* nothing that ties a call to this hub's job crosses to a peer — not the job token, the
  grant (a bearer secret for the buyer's allowance), the job and node ids, nor a mandate's
  agent and principal — whether the routed call is a root or a child, however this hub bills
  the peer and over either transport it can reach it by, while the same kind of call executed
  locally does receive them, so none of these checks passes vacuously;
* a job paid under a two-mandate chain counts its root, its children and their routing fees
  against BOTH mandates, and whichever mandate has less room left bounds the whole job;
* the routing-fee paths out of an allowance the existing tests never drive: a fee the
  allowance cannot cover, a routed child that fails and must have its price AND fee back in
  the allowance in time for a retry, and a brokered peer's fee debited after the fact.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import httpx
import pytest
from aimarket_hub import mandates, subcontract

from tests._mandate_kit import (
    HUB,
    balance,
    funded_account,
    issue,
    key,
    list_provider,
    list_static,
    mandated_invoke,
    setup_mandate,
)
from tests.test_subcontract import (
    BRIEF,
    FED_AIR,
    FED_CONFIGS,
    FED_PRICE,
    FED_WEATHER,
    PEER,
    PEER_INVOKE,
    WEATHER,
    _Resp,
    federated_world,
    gaia_envelope,
    job_headers,
)

INVOKE = "/ai-market/v2/invoke"
BRIEF_URL = "https://brief.test/invoke"
MID_URL = "https://mid.test/invoke"
MID = {"product_id": "mid", "capability_id": "mid.step@v1", "input": {"q": 1}, "source_hub": "local"}
PRO = {"product_id": "wx-pro", "capability_id": "wx.pro@v1", "input": {"q": 1}, "source_hub": "local"}
MEMO = {"product_id": "memo", "capability_id": "memo.write@v1", "input": {"q": 1}, "source_hub": "local"}

FEE_BPS = 1000                                   # 10 %, so the fee is legible in the numbers
FEE = round(FED_PRICE * FEE_BPS / 10_000, 6)     # $0.0001 on a $0.001 reading
RESALE = {**FED_CONFIGS["resale"][0], "AIMARKET_ROUTING_FEE_BPS": str(FEE_BPS)}
SELLER_OF_RECORD = FED_CONFIGS["seller_of_record"][0]

# Everything the hub sends only to a provider it executes itself (§5.4, §6.1-6.2).
LOCAL_ONLY = {h.lower() for h in (subcontract.JOB_HEADER, subcontract.GRANT_HEADER, subcontract.HUB_HEADER,
                                  mandates.AGENT_HEADER, mandates.PRINCIPAL_HEADER)}

# The two transports a routed call can cross by (api.py, "Transport"): a peer whose
# well-known advertises `mcp_endpoint` is sent the {capability_id, input} envelope there, one
# that advertises none the bare input on the legacy per-capability path. The headers are
# built once above both, but each transport is its own call, so a leak added to one is
# invisible from the other: the linkage checks run over both.
TRANSPORTS = ("mcp_endpoint", "legacy")


def legacy_url(cap: dict) -> str:
    return f"{PEER}/capabilities/{cap['product_id']}/{cap['capability_id']}/invoke"


PEER_URLS = {"mcp_endpoint": {PEER_INVOKE}, "legacy": {legacy_url(FED_WEATHER), legacy_url(FED_AIR)}}


@contextmanager
def routed_world(monkeypatch, tmp_path, transport: str, **env):
    """`federated_world`, with its peer reached over ``transport``.

    The legacy peer is the same peer with a well-known that advertises no endpoint, so the
    hub's transport lookup answers None. It replaces the fixture's well-known before the
    first routed call, and the per-peer transport cache is emptied again so the decision is
    made from this one and not from anything cached.
    """
    with federated_world(monkeypatch, tmp_path, **env) as (client, db, providers):
        if transport == "legacy":
            import aimarket_hub.api as api_mod
            import aimarket_hub.peer_routing as peer_routing
            import aimarket_hub.outbound_http as outbound

            async def well_known(url, *, timeout=10.0):
                assert url == f"{PEER}/.well-known/ai-market.json", url
                return _Resp(200, {"name": "gaia"})

            monkeypatch.setattr(outbound, "safe_get", well_known)
            monkeypatch.setattr(peer_routing, "_peer_endpoint_cache", {})
        yield client, db, providers


def hub_key_at_peer(env: dict) -> str | None:
    """The X-API-Key a configuration pays the peer with: this hub's own account there, if any."""
    return env.get("AIMARKET_PEER_API_KEYS", "").partition("=")[2] or None


async def _ok(body, headers, p):
    return 200, {"result": {"ok": True}}


def peer_answers(providers, *modes: str, transport: str = "mcp_endpoint") -> list[dict]:
    """Answer the peer's calls with ``modes`` in order, then succeed; record every body sent."""
    bodies: list[dict] = []
    queue = list(modes)

    def answer(capability_id: str) -> tuple[int, dict]:
        mode = queue.pop(0) if queue else "ok"
        if mode == "unreachable":
            raise httpx.ConnectError("peer is down")
        if mode == "server_error":
            return 500, {"error": "internal"}
        if mode == "refused":
            return 200, gaia_envelope(capability_id, ok=False)
        if mode == "cheaper":
            # Charged under its own catalogue price: the fee basis drops with it.
            return 200, {**gaia_envelope(capability_id), "price_usd": FED_PRICE / 2}
        return 200, gaia_envelope(capability_id)

    async def gaia(body, headers, p):
        bodies.append(body)
        return answer(body["capability_id"])

    def legacy(capability_id: str):
        # The bare input arrives here, so the capability is the path's, not the body's. The
        # hub normalizes no envelope on this transport, so the answer states `success` itself,
        # as a legacy factory-product peer's does.
        async def gaia_legacy(body, headers, p):
            bodies.append(body)
            status, out = answer(capability_id)
            return status, ({"success": out.get("ok", True) is not False, **out} if status == 200 else out)
        return gaia_legacy

    if transport == "legacy":
        for cap in (FED_WEATHER, FED_AIR):
            providers.add(legacy_url(cap), legacy(cap["capability_id"]))
    else:
        providers.add(PEER_INVOKE, gaia)
    return bodies


def assert_the_peer_learned_none_of(providers, bodies: list[dict], secrets: list[str], *,
                                    transport: str = "mcp_endpoint") -> list[dict]:
    """No local-only header by name, and no secret by value, in anything the peer received.

    Every URL on the peer is scanned, and all of them must belong to ``transport``: a run
    that quietly took the other transport would be scanning the wrong call. Returns the
    headers the peer received, for the caller's own checks.
    """
    reached = {url for url in providers.seen if url.startswith(PEER + "/")}
    assert reached and reached <= PEER_URLS[transport], (transport, reached)
    sent = [headers for url in sorted(reached) for headers in providers.seen[url]]
    assert sent, "the peer was never called, so nothing was proven"
    for headers in sent:
        assert not {name.lower() for name in headers} & LOCAL_ONLY, headers
    # By value too: a grant forwarded under any other name, or in the body, is the same leak.
    wire = json.dumps([sent, bodies])
    for secret in secrets:
        assert secret and secret not in wire
    return sent


def _claims(token: str) -> dict:
    return json.loads(subcontract._b64url_decode(token.split(".", 1)[0]))


def _held(db) -> tuple[int, int]:
    """Credit holds and mandate reservations still open: money or limit in limbo."""
    credit = db._conn.execute("SELECT COUNT(*) AS n FROM credit_holds WHERE status = 'held'").fetchone()["n"]
    limit = db._conn.execute("SELECT COUNT(*) AS n FROM mandate_holds WHERE status = 'held'").fetchone()["n"]
    return int(credit), int(limit)


# ── 1. linkage and money stay on this hub ─────────────────────────────────────

class TestRoutedCallsCarryNoJob:
    @pytest.mark.parametrize("transport", TRANSPORTS)
    @pytest.mark.parametrize("config", sorted(FED_CONFIGS))
    @pytest.mark.parametrize("payer", ["api_key", "mandate"])
    def test_a_root_routed_to_a_peer_carries_no_job_context(self, monkeypatch, tmp_path, payer, config, transport):
        env, fee = FED_CONFIGS[config]
        with routed_world(monkeypatch, tmp_path, transport, **env) as (client, db, providers):
            bodies = peer_answers(providers, transport=transport)
            providers.add(BRIEF_URL, _ok)
            m = setup_mandate(client, db)

            def call(payload):
                if payer == "mandate":
                    return mandated_invoke(client, m, payload)
                return client.post(INVOKE, headers={"X-API-Key": m["api_key"]}, json=payload)

            routed = call(FED_WEATHER)
            # A routed root opens no job at all, so nothing tying it to this hub can leak
            # under ANY header name — not only under the names scanned below.
            jobs_after_routing = [db._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                                  for table in ("job_nodes", "job_grants")]
            local = call(BRIEF)
            left = balance(db, m["account"])
        assert routed.status_code == 200 and routed.json()["success"], routed.text
        assert jobs_after_routing == [0, 0]
        assert local.status_code == 200, local.text
        # The same payer's call executed HERE: its provider is told the job and, for a
        # mandated call, who is behind it...
        at_provider = providers.seen[BRIEF_URL][0]
        assert subcontract.JOB_HEADER in at_provider and at_provider[subcontract.HUB_HEADER] == HUB
        secrets = [m["api_key"]]
        if payer == "mandate":
            assert at_provider[mandates.AGENT_HEADER] == m["agent"].did
            assert at_provider[mandates.PRINCIPAL_HEADER] == m["owner"].did
            secrets += [m["digest"], m["agent"].did, m["owner"].did]
        # ...and the peer, for the routed one, none of it (§5.4: it did not verify the mandate).
        sent = assert_the_peer_learned_none_of(providers, bodies, secrets, transport=transport)
        # Each configuration took its own billing branch, so neither run is the other in
        # disguise: a resale pays the peer from this hub's account there and holds a routing
        # fee on top, a seller of record does neither.
        assert [h.get("X-API-Key") for h in sent] == [hub_key_at_peer(env)]
        assert left == pytest.approx(1.0 - FED_PRICE - fee - 0.010)

    def test_a_root_routed_to_a_peer_cannot_open_an_allowance(self, monkeypatch, tmp_path):
        """§6.2: the hub passes through only money it meters, so no grant is ever minted for
        a call it routes — there is none a peer could be handed."""
        with federated_world(monkeypatch, tmp_path, **SELLER_OF_RECORD) as (client, db, providers):
            account, api_key = funded_account(client, db, 1.0)
            r = client.post(INVOKE, headers={"X-API-Key": api_key},
                            json={**FED_WEATHER, "subcontract": {"allowance_usd": 0.005}})
            grants = db._conn.execute("SELECT COUNT(*) AS n FROM job_grants").fetchone()["n"]
            left = balance(db, account)
            held = _held(db)
        assert r.status_code == 400 and r.json()["error"] == "subcontract_unsupported", r.text
        assert grants == 0 and held == (0, 0)
        assert left == pytest.approx(1.0)
        assert PEER_INVOKE not in providers.seen

    @pytest.mark.parametrize("transport", TRANSPORTS)
    @pytest.mark.parametrize("config", sorted(FED_CONFIGS))
    @pytest.mark.parametrize("funding", ["allowance", "own"])
    def test_a_child_routed_to_a_peer_forwards_neither_its_token_nor_its_grant(
            self, monkeypatch, tmp_path, config, funding, transport):
        env, _ = FED_CONFIGS[config]
        with routed_world(monkeypatch, tmp_path, transport, **env) as (client, db, providers):
            list_provider(db, "mid.step@v1", "mid", 0.002, url=MID_URL)
            bodies = peer_answers(providers, transport=transport)
            providers.add(MID_URL, _ok)
            _, provider_key = funded_account(client, db, 1.0)
            children: dict[str, dict] = {}

            async def brief(body, headers, p):
                sent = job_headers(headers, with_grant=funding == "allowance")
                if funding == "own":
                    sent["X-API-Key"] = provider_key      # fixed-price: it pays its own way
                # The same purchase twice over: once routed to the peer, once executed here.
                for name, child in (("routed", FED_WEATHER), ("local", MID)):
                    r = await p.buy(child, sent)
                    assert r.status_code == 200, r.text
                    children[name] = r.json()["job"]
                return 200, {"result": {"ok": True}}

            providers.add(BRIEF_URL, brief)
            _, api_key = funded_account(client, db, 1.0)
            extra = {"subcontract": {"allowance_usd": 0.01}} if funding == "allowance" else {}
            r = client.post(INVOKE, headers={"X-API-Key": api_key}, json={**BRIEF, **extra})
            assert r.status_code == 200, r.text

        at_brief = providers.seen[BRIEF_URL][0]
        at_mid = providers.seen[MID_URL][0]
        token, grant = at_brief[subcontract.JOB_HEADER], at_brief.get(subcontract.GRANT_HEADER, "")
        assert bool(grant) == (funding == "allowance")      # there was a grant to leak, or not
        assert {c["funded_by"] for c in children.values()} == {funding}
        # Executed here, the child's provider gets a token naming the child's own node, and
        # the job's grant so it can subcontract in turn...
        assert _claims(at_mid[subcontract.JOB_HEADER])["node"] == children["local"]["node"]
        assert at_mid.get(subcontract.GRANT_HEADER, "") == grant
        # ...routed, the peer gets none of it: not the tokens, not the grant, not the job id
        # (a bearer read capability for GET /jobs), not the buyer's or the provider's key.
        routed = children["routed"]
        secrets = [token, at_mid[subcontract.JOB_HEADER], api_key, provider_key,
                   routed["job_id"], routed["node"], routed["parent"]]
        sent = assert_the_peer_learned_none_of(providers, bodies, secrets + ([grant] if grant else []),
                                               transport=transport)
        # The one key the peer may see is this hub's own account there, and only on a resale.
        assert [h.get("X-API-Key") for h in sent] == [hub_key_at_peer(env)]


# ── 2. a job under a two-mandate chain ────────────────────────────────────────

def _redelegate(client, m: dict, *, per_day: int, allowance: int = 10_000, seed: int = 3):
    """M2: agent A (M1's subject) hands a narrower mandate to agent B."""
    doc = issue(m["agent"], key(seed).did, parent=m["digest"], per_day=per_day,
                subcontract={"perCallAllowance": allowance, "maxDepth": 1})
    r = client.post("/ai-market/v2/mandates", json=doc)
    assert r.status_code == 200, r.text
    return key(seed), r.json()["digest"]


def _usage(client, m: dict, digest: str) -> dict:
    """What the owner reads back for any mandate of its chain, by its funding key."""
    r = client.get(f"/ai-market/v2/mandates/{digest}", headers={"X-API-Key": m["api_key"]})
    assert r.status_code == 200, r.text
    return r.json()["usage"]


class TestTwoMandateChain:
    def test_every_mandate_in_the_chain_counts_the_root_its_children_and_their_fees(self, monkeypatch, tmp_path):
        with federated_world(monkeypatch, tmp_path, **RESALE) as (client, db, providers):
            peer_answers(providers)
            m1 = setup_mandate(client, db, per_day=100_000, subcontract={"perCallAllowance": 10_000, "maxDepth": 1})
            b, m2 = _redelegate(client, m1, per_day=50_000, allowance=5_000)

            async def brief(body, headers, p):
                for child in (FED_WEATHER, FED_AIR):
                    r = await p.buy(child, job_headers(headers))
                    assert r.status_code == 200, r.text
                return 200, {"result": {"ok": True}}

            providers.add(BRIEF_URL, brief)
            r = mandated_invoke(client, m1, {**BRIEF, "subcontract": {"allowance_usd": 0.005}}, agent=b, leaf=m2)
            assert r.status_code == 200, r.text
            usage = {"M1": _usage(client, m1, m1["digest"]), "M2": _usage(client, m1, m2)}
            held = _held(db)
            left = balance(db, m1["account"])

        body = r.json()
        children = 2 * (FED_PRICE + FEE)
        assert body["mandate"]["digest"] == m2 and body["mandate"]["depth"] == 1
        assert body["subcontracting"]["spent_usd"] == pytest.approx(children)
        # The brief, both routed readings and both routing fees — against each mandate, both
        # as today's counter and as the settled reservations the total is summed from.
        for name, u in usage.items():
            assert u["spent_today_usd"] == pytest.approx(0.010 + children), name
            assert u["spent_total_usd"] == pytest.approx(0.010 + children), name
        assert held == (0, 0)
        assert left == pytest.approx(1.0 - 0.010 - children)

    @pytest.mark.parametrize("binding", ["parent", "leaf"])
    def test_whichever_mandate_has_less_room_bounds_the_whole_job(self, monkeypatch, tmp_path, binding):
        """M2 can never allow more than M1 (a child that raises a limit is refused when it
        is registered), so M1 is the tighter one when something else has spent from it
        already — here agent A itself. Either way the tight mandate has $0.018 of its day left."""
        with federated_world(monkeypatch, tmp_path, **RESALE) as (client, db, providers):
            list_static(db, capability_id=PRO["capability_id"], product_id=PRO["product_id"], price=0.003)
            list_static(db, capability_id=MEMO["capability_id"], product_id=MEMO["product_id"], price=0.012)
            if binding == "parent":
                m1 = setup_mandate(client, db, per_day=30_000, subcontract={"perCallAllowance": 10_000, "maxDepth": 1})
                b, m2 = _redelegate(client, m1, per_day=30_000)
                assert mandated_invoke(client, m1, MEMO).status_code == 200   # A spends $0.012 under M1
                before = 0.012
            else:
                m1 = setup_mandate(client, db, per_day=100_000, subcontract={"perCallAllowance": 10_000, "maxDepth": 1})
                b, m2 = _redelegate(client, m1, per_day=18_000)
                before = 0.0
            tight = m1["digest"] if binding == "parent" else m2
            outcomes: list[tuple[int, str | None]] = []

            async def brief(body, headers, p):
                for _ in range(3):
                    r = await p.buy(PRO, job_headers(headers))
                    outcomes.append((r.status_code, r.json().get("error")))
                return 200, {"result": {"ok": True}}

            providers.add(BRIEF_URL, brief)

            def job(allowance_usd: float):
                return mandated_invoke(client, m1, {**BRIEF, "subcontract": {"allowance_usd": allowance_usd}},
                                       agent=b, leaf=m2)

            # $0.010 for the brief plus a $0.010 allowance: over the tight mandate's $0.018.
            over = job(0.010)
            refused = {"left": balance(db, m1["account"]), "held": _held(db),
                       "M1": _usage(client, m1, m1["digest"])["spent_today_usd"],
                       "M2": _usage(client, m1, m2)["spent_today_usd"],
                       "provider_ran": BRIEF_URL in providers.seen}
            # $0.008 fits it exactly — and then the children can spend no more than that.
            fits = job(0.008)
            assert fits.status_code == 200, fits.text
            usage = {"M1": _usage(client, m1, m1["digest"]), "M2": _usage(client, m1, m2)}
            held = _held(db)
            left = balance(db, m1["account"])

        assert over.status_code == 402, over.text
        assert (over.json()["error"], over.json()["limit"], over.json()["mandate"]) == ("mandate_limit", "perDay", tight)
        # Refused before anything ran, and nothing of it stays counted or held on either mandate.
        assert refused == {"left": pytest.approx(1.0 - before), "held": (0, 0), "M1": pytest.approx(before),
                           "M2": 0, "provider_ran": False}
        # The third $0.003 child would take the job past the tight mandate: refused, and free.
        assert outcomes == [(200, None), (200, None), (402, "allowance_exhausted")]
        sub = fits.json()["subcontracting"]
        assert sub["spent_usd"] == pytest.approx(0.006) and sub["released_usd"] == pytest.approx(0.002)
        assert usage["M1"]["spent_today_usd"] == pytest.approx(before + 0.016)
        assert usage["M2"]["spent_today_usd"] == pytest.approx(0.016)
        assert usage["M1" if binding == "parent" else "M2"]["remaining_today_usd"] == pytest.approx(0.002)
        assert held == (0, 0)
        assert left == pytest.approx(1.0 - before - 0.016)


# ── 3. the routing fee of a routed child, from the allowance ─────────────────

class TestRoutingFeeFromAnAllowance:
    def test_a_fee_the_allowance_cannot_cover_refuses_the_child_before_the_peer_is_asked(self, monkeypatch, tmp_path):
        with federated_world(monkeypatch, tmp_path, **RESALE) as (client, db, providers):
            list_static(db, capability_id=WEATHER["capability_id"], product_id=WEATHER["product_id"], price=FED_PRICE)
            peer_answers(providers)
            seen: list[tuple[int, str | None]] = []

            async def brief(body, headers, p):
                # The routed reading's price fits the allowance; its price plus fee does not.
                # Then a local reading at the same price, from what should be the same allowance.
                for child in (FED_WEATHER, WEATHER):
                    r = await p.buy(child, job_headers(headers))
                    seen.append((r.status_code, r.json().get("error")))
                return 200, {"result": {"ok": True}}

            providers.add(BRIEF_URL, brief)
            account, api_key = funded_account(client, db, 1.0)
            r = client.post(INVOKE, headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": FED_PRICE}})
            assert r.status_code == 200, r.text
            held = _held(db)
            left = balance(db, account)

        assert seen == [(402, "allowance_exhausted"), (200, None)]
        assert PEER_INVOKE not in providers.seen
        sub = r.json()["subcontracting"]
        # The refused child's price went back into the allowance: the local reading was paid from it.
        assert {n["capability_id"]: (n["status"], n["price_usd"]) for n in sub["nodes"]} == {
            FED_WEATHER["capability_id"]: ("failed", 0.0), WEATHER["capability_id"]: ("captured", FED_PRICE)}
        assert sub["spent_usd"] == pytest.approx(FED_PRICE) and sub["released_usd"] == 0
        assert held == (0, 0)
        assert left == pytest.approx(1.0 - 0.010 - FED_PRICE)

    @pytest.mark.parametrize("failure", ["refused", "server_error", "unreachable"])
    def test_a_routed_child_that_fails_hands_price_and_fee_back_in_time_for_a_retry(self, monkeypatch, tmp_path, failure):
        """Three different exits of the federated branch (a refusal settled in its tail, a
        peer 5xx and a transport error unwound by its `finally`). The allowance holds exactly
        one reading and its fee, so the retry is paid only if BOTH came back to it."""
        with federated_world(monkeypatch, tmp_path, **RESALE) as (client, db, providers):
            peer_answers(providers, failure)
            codes: list[tuple[int, bool | None]] = []

            async def brief(body, headers, p):
                for _ in range(2):
                    r = await p.buy(FED_WEATHER, job_headers(headers))
                    codes.append((r.status_code, r.json().get("success")))
                return 200, {"result": {"ok": True}}

            providers.add(BRIEF_URL, brief)
            account, api_key = funded_account(client, db, 1.0)
            r = client.post(INVOKE, headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": FED_PRICE + FEE}})
            assert r.status_code == 200, r.text
            held = _held(db)
            left = balance(db, account)

        assert codes[0][0] == (200 if failure == "refused" else 502) and codes[0][1] is not True
        assert codes[1] == (200, True)
        assert len(providers.seen[PEER_INVOKE]) == 2
        sub = r.json()["subcontracting"]
        assert sorted((n["status"], n["price_usd"]) for n in sub["nodes"]) == [
            ("captured", pytest.approx(FED_PRICE + FEE)), ("failed", 0.0)]
        assert sub["spent_usd"] == pytest.approx(FED_PRICE + FEE) and sub["released_usd"] == 0
        assert held == (0, 0)
        assert left == pytest.approx(1.0 - 0.010 - FED_PRICE - FEE)

    def test_a_brokered_childs_after_the_fact_fee_is_carved_from_the_allowance(self, monkeypatch, tmp_path):
        """A peer this hub neither sells for nor resells bills its buyer itself; this hub
        reserves its fee on the catalogued price and, when the peer charges less, releases it
        and debits the smaller fee after the fact. With a grant that debit is carved from the
        allowance too — end to end, where the proxy test pins only the proxy."""
        allowance = 0.002
        with federated_world(monkeypatch, tmp_path, AIMARKET_ROUTING_FEE_BPS=str(FEE_BPS)) as (client, db, providers):
            peer_answers(providers, "cheaper")
            children: list[tuple[int, dict]] = []

            async def brief(body, headers, p):
                r = await p.buy(FED_WEATHER, job_headers(headers))
                children.append((r.status_code, r.json()))
                return 200, {"result": {"ok": True}}

            providers.add(BRIEF_URL, brief)
            # Just the brief and the allowance: with both held the buyer's free balance is
            # zero, so a fee debited from it instead of the allowance could not be paid at all.
            account, api_key = funded_account(client, db, 0.010 + allowance)
            r = client.post(INVOKE, headers={"X-API-Key": api_key},
                            json={**BRIEF, "subcontract": {"allowance_usd": allowance}})
            assert r.status_code == 200, r.text
            held = _held(db)
            left = balance(db, account)

        fee = round(FED_PRICE / 2 * FEE_BPS / 10_000, 6)     # on what the peer charged, not the catalogue
        status, child = children[0]
        assert status == 200 and child["success"] and child["job"]["funded_by"] == "allowance", child
        sub = r.json()["subcontracting"]
        assert [(n["status"], n["price_usd"]) for n in sub["nodes"]] == [("captured", pytest.approx(fee))]
        assert sub["spent_usd"] == pytest.approx(fee) and sub["released_usd"] == pytest.approx(allowance - fee)
        assert held == (0, 0)
        assert left == pytest.approx(allowance - fee)
