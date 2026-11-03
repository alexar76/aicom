"""Regression tests for the independent audit of mandates and subcontracting (2026-09-26).

Each test pins a property the earlier suites left open: a one-line regression in the code it
names turns it red. Several started life as the auditor's probes (a probe had to pass on the
fixed code and fail on the mutant it was paired with).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    ADMIN_TOKEN, ECHO, HUB, b64url, balance, digest, funded_account, hub, issue, key,
    list_provider, list_static, mandated_invoke, nonce, owner_change, owner_link_payload,
    request_proof, revoke_payload, setup_mandate,
)
from tests.test_subcontract import BRIEF, WEATHER, Providers, job_headers, world  # noqa: F401
from aimarket_hub import credits, mandates, subcontract
from aimarket_hub.models import Capability

OWNERS = "/ai-market/v2/mandates/owners"


# ── a mandate has one name ────────────────────────────────────────────────────

class TestOneMandateOneDigest:
    def test_an_unsigned_proof_context_cannot_mint_a_copy(self, monkeypatch, tmp_path):
        """proof.@context is replaced by the document's before hashing, so it is unsigned —
        and the digest covers it. Left free, the constrained agent could register copies
        with fresh counters that revoking the original does not touch."""
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            for mutate in (
                lambda p: p.__setitem__("@context", ["x"]),
                lambda p: p.__setitem__("@context", "x1"),
                lambda p: p.pop("@context"),
                lambda p: p.__setitem__("note", "extra"),
            ):
                copy = json.loads(json.dumps(m["doc"]))
                mutate(copy["proof"])
                assert digest(copy) != m["digest"]
                # refused as a document — not merely as a second registration of its id
                with pytest.raises(mandates.MandateError, match="proof"):
                    mandates.parse_mandate(copy)
                r = client.post("/ai-market/v2/mandates", json=copy)
                assert r.status_code == 403 and r.json()["error"] == "mandate_invalid", r.text

    def test_one_credential_id_names_one_mandate(self, monkeypatch, tmp_path):
        from awr.proof import sign_document

        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            twin = issue(m["owner"], m["agent"].did, per_day=2_000_000)
            unsigned = {k: v for k, v in twin.items() if k != "proof"}
            unsigned["id"] = m["doc"]["id"]
            twin = sign_document(unsigned, m["owner"], twin["proof"]["created"])
            r = client.post("/ai-market/v2/mandates", json=twin)
            assert r.status_code == 403 and "already registered" in r.json()["detail"], r.text

    def test_a_limit_past_ijson_is_refused(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = funded_account(client, db)
            client.post(OWNERS, headers={"X-API-Key": api_key}, json=owner_link_payload(key(1), account))
            # awr refuses to SIGN such a number, so no honest issuer produces one; the hub must
            # still refuse it before it reaches a counter or a sqlite binding.
            doc = issue(key(1), key(2).did)
            doc["credentialSubject"]["aimarketMandate"]["limits"]["perDay"] = 2**53
            r = client.post("/ai-market/v2/mandates", json=doc)
            assert r.status_code == 403 and "2^53" in r.json()["detail"], r.text


# ── a refusal before the provider runs gives everything back ─────────────────

def test_an_incomplete_input_releases_the_hold_and_the_mandate(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        db.upsert_capability(Capability(
            capability_id="needs.q@v1", product_id="needs-q", name="needs q", description="static",
            price_per_call_usd=0.004, source_hub="local", invoke_url="",
            prompt_template='{"ok": true}',
            input_schema={"type": "object", "required": ["q"], "properties": {"q": {"type": "string"}}},
        ))
        m = setup_mandate(client, db, per_day=10_000)   # room for two calls at $0.004
        payload = {"product_id": "needs-q", "capability_id": "needs.q@v1", "input": {}, "source_hub": "local"}
        for _ in range(3):
            r = mandated_invoke(client, m, payload)
            assert r.status_code == 400, r.text
        assert balance(db, m["account"]) == pytest.approx(1.0)
        store = mandates.MandateStore(db._conn, HUB)
        assert store.usage(m["digest"])["spent_today_usd"] == 0
        held = db._conn.execute("SELECT COUNT(*) AS n FROM mandate_holds WHERE status = 'held'").fetchone()
        assert held["n"] == 0


# ── an owner change needs an OWNER's signature (P3) ──────────────────────────

def _locked(client, db):
    account, api_key = funded_account(client, db)
    r = client.post(OWNERS, headers={"X-API-Key": api_key},
                    json=owner_link_payload(key(1), account, require_mandate=True))
    assert r.status_code == 200
    return account, api_key


class TestOwnerChangeForgeries:
    def test_a_signature_by_another_key_claiming_the_owner(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = _locked(client, db)
            attacker = key(66)
            payload = owner_link_payload(attacker, account)
            auth = owner_change(attacker, account, "link", attacker.did)
            auth["by"] = key(1).did
            payload["authorization"] = auth
            r = client.post(OWNERS, headers={"X-API-Key": api_key}, json=payload)
            assert r.status_code in (401, 403), r.text

    def test_an_authorization_by_a_non_owner(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = _locked(client, db)
            attacker = key(66)
            payload = owner_link_payload(attacker, account)
            payload["authorization"] = owner_change(attacker, account, "link", attacker.did)
            r = client.post(OWNERS, headers={"X-API-Key": api_key}, json=payload)
            assert r.status_code == 403, r.text

    def test_an_authorization_cannot_be_replayed(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = _locked(client, db)
            h = {"X-API-Key": api_key}
            link_auth = owner_change(key(1), account, "link", key(2).did)
            p = owner_link_payload(key(2), account)
            p["authorization"] = link_auth
            assert client.post(OWNERS, headers=h, json=p).status_code == 200
            r = client.post(OWNERS + "/unlink", headers=h, json={
                "did": key(2).did, "authorization": owner_change(key(1), account, "unlink", key(2).did)})
            assert r.status_code == 200
            p2 = owner_link_payload(key(2), account)
            p2["authorization"] = link_auth
            assert client.post(OWNERS, headers=h, json=p2).status_code == 401

    def test_a_stale_authorization(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = _locked(client, db)
            t, n = int(time.time()) - 3600, nonce()
            msg = mandates.owner_change_message(hub_origin=HUB, account_id=account, action="link",
                                                did=key(2).did, require_mandate=False, t=t, nonce=n)
            p = owner_link_payload(key(2), account)
            p["authorization"] = {"by": key(1).did, "t": t, "n": n, "s": b64url(key(1).sign(msg))}
            assert client.post(OWNERS, headers={"X-API-Key": api_key}, json=p).status_code == 401

    def test_a_wrong_admin_bearer_is_not_the_recovery_path(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = _locked(client, db)
            r = client.post(OWNERS, json=owner_link_payload(key(3), account),
                            headers={"X-API-Key": api_key, "Authorization": "Bearer not-the-admin-token"})
            assert r.status_code == 403, r.text
            ok = client.post(OWNERS, json=owner_link_payload(key(3), account),
                             headers={"X-API-Key": api_key, "Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert ok.status_code == 200, ok.text

    def test_a_locked_account_cannot_stake_on_its_key_alone(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = _locked(client, db)
            r = client.post("/ai-market/v2/supply/stake", headers={"X-API-Key": api_key},
                            json={"amount_usd": 0.5})
            assert r.status_code == 403 and "require_mandate" in r.json()["detail"], r.text
            assert balance(db, account) == pytest.approx(1.0)


# ── status and usage of a mandate AS A CHAIN (§3.5) ──────────────────────────

class TestMandateStatus:
    def _child(self, client, m):
        sub = key(3)
        child = issue(m["agent"], sub.did, per_call=10_000, per_day=500_000, parent=m["digest"])
        r = client.post("/ai-market/v2/mandates", json=child)
        assert r.status_code == 200, r.text
        return r.json()["digest"]

    def test_the_owner_reads_a_redelegations_usage_and_sees_it_die_with_its_parent(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            child = self._child(client, m)
            path = f"/ai-market/v2/mandates/{child}"
            proof = request_proof(m["owner"], child, b"", path=path, method="GET")
            r = client.get(path, headers={"X-AIMarket-Mandate-Proof": proof})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "active" and body["chain"] == [m["digest"], child]
            assert "usage" in body   # the ROOT owner's key, not the child's subject
            assert client.post("/ai-market/v2/mandates/revoke",
                               json=revoke_payload(m["owner"], m["digest"])).status_code == 200
            after = client.get(path).json()
            assert after["status"] == "revoked" and after["revoked_at"] is None   # its own row is clean
            assert "revoked" in after["status_reason"]

    def test_a_mandate_not_yet_valid_is_pending_not_expired(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            later = issue(m["owner"], key(4).did, valid_from=datetime.now(timezone.utc) + timedelta(days=1))
            d = client.post("/ai-market/v2/mandates", json=later).json()["digest"]
            assert client.get(f"/ai-market/v2/mandates/{d}").json()["status"] == "pending"

    def test_the_signed_path_is_relative_to_the_base_url(self):
        class _Req:
            class url:  # noqa: N801 - a stand-in for starlette's URL
                path = "/hub/ai-market/v2/invoke"

            scope = {"root_path": "/hub"}

        assert mandates.signed_path(_Req()) == "/ai-market/v2/invoke"
        _Req.scope = {}
        _Req.url.path = "/ai-market/v2/invoke"
        assert mandates.signed_path(_Req()) == "/ai-market/v2/invoke"


# ── money paths the suites never drove ───────────────────────────────────────

def test_concurrent_children_never_overdraw_an_allowance(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 5.0)
        ledger = credits.CreditsLedger(db._conn)
        # A read-then-write regression loses the race only sometimes: several rounds push the
        # chance of missing it toward nothing.
        for round_ in range(5):
            assert not ledger.hold(account, 0.010, f"alw_race_{round_}").get("error")
            wins: list[int] = []
            barrier = threading.Barrier(40)

            def draw(i: int) -> None:
                barrier.wait()
                if not ledger.transfer_hold(f"alw_race_{round_}", f"child_{round_}_{i}", 0.001).get("error"):
                    wins.append(i)

            threads = [threading.Thread(target=draw, args=(i,)) for i in range(40)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            assert len(wins) == 10, (round_, len(wins))


def test_a_routing_fee_paid_from_an_allowance_stays_inside_it(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 1.0)
        ledger = credits.CreditsLedger(db._conn)
        ledger.hold(account, 0.002, "alw_fee")
        proxy = subcontract.AllowanceCredits(ledger, "alw_fee")
        assert proxy.debit(account, 0.005, "fee_big").get("error")
        assert not proxy.debit(account, 0.001, "fee_ok").get("error")
        assert proxy.allowance_left_usd() == pytest.approx(0.001)
        assert balance(db, account) == pytest.approx(0.998)


def test_a_routing_fee_debit_counts_against_the_mandate(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        m = setup_mandate(client, db)
        store = mandates.MandateStore(db._conn, HUB)
        adm = mandates.Admission(chain=store.chain(m["digest"]), account_id=m["account"],
                                 product_id="p", store=store)
        proxy = mandates.MandatedCredits(credits.CreditsLedger(db._conn), adm)
        assert not proxy.debit(m["account"], 0.003, receipt_id="fee_1", note="routing").get("error")
        assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.003)


def test_a_child_refunded_between_release_and_settle_is_not_counted(monkeypatch, tmp_path):
    """The window a multi-worker hub has: the root's ledger release has happened, so a
    failing child is refunded to the BALANCE, but the root's mandate settle has not."""
    with hub(monkeypatch, tmp_path) as (client, db):
        m = setup_mandate(client, db)
        store = mandates.MandateStore(db._conn, HUB)
        chain = store.chain(m["digest"])
        store.reserve(chain, receipt_id="alw_w", amount_micro=10_000, product_id="p", check_per_call=False)
        # children drew 4000 by the time of the ledger release; one of those (1000) is then
        # refunded to the balance before settle() runs
        store.give_back("alw_w", 1_000)
        store.settle("alw_w", 4_000)
        assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.003)
        # and after the settle the ordinary path still works
        store.give_back("alw_w", 500)
        assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.0025)


def test_finish_gives_a_late_refund_back_to_the_root_mandate(monkeypatch, tmp_path):
    """The wiring, not the primitive: finish() on a grant-funded child whose holds went back
    to the buyer's balance takes their sum back off the root mandate's counters."""
    from aimarket_hub import invoke_funding

    with hub(monkeypatch, tmp_path) as (client, db):
        m = setup_mandate(client, db)
        store = mandates.MandateStore(db._conn, HUB)
        store.reserve(store.chain(m["digest"]), receipt_id="alw_late", amount_micro=10_000,
                      product_id="p", check_per_call=False)
        store.settle("alw_late", 4_000)            # the root settled: 4000 counted as spent
        ledger = credits.CreditsLedger(db._conn)
        proxy = subcontract.AllowanceCredits(ledger, "alw_late")
        proxy.released_micro = 3_000    # price + fee of a child refunded afterwards
        funding = invoke_funding.InvokeFunding(product_id="wx", capability_id="wx.read@v1")
        funding.job = subcontract.JobContext(
            job_id="job_late", node="node_late", depth=1, max_depth=1, path=["a@v1", "wx.read@v1"],
            parent="node_root", funded_by="allowance",
            grant={"mandate_digest": m["digest"], "allowance_receipt": "alw_late"})
        funding._proxies.append(proxy)
        from aimarket_hub.signing import Signer

        invoke_funding.finish(funding, {"success": False}, credits_ledger=ledger, store=store,
                              jobs=subcontract.JobStore(db._conn, Signer(tmp_path / "k"), HUB))
        assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.001)


def test_a_federated_childs_two_refunds_are_both_counted(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 1.0)
        ledger = credits.CreditsLedger(db._conn)
        ledger.hold(account, 0.010, "alw_fed")
        proxy = subcontract.AllowanceCredits(ledger, "alw_fed")
        proxy.hold(account, 0.003, "fed_price")
        proxy.hold(account, 0.001, "fed_fee")
        ledger.release_hold("alw_fed")          # the root closed its allowance
        proxy.release_hold("fed_price")         # both of the child's holds now go to the balance
        proxy.release_hold("fed_fee")
        assert proxy.released_micro == 4_000


# ── the job tree (§6) ─────────────────────────────────────────────────────────

class TestJobTree:
    def test_a_late_child_cannot_join_a_finished_root(self, world):
        client, db, providers = world
        stash: dict = {}

        async def brief(body, headers, p):
            stash.update(headers)
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        _, buyer_key = funded_account(client, db, 1.0)
        _, provider_key = funded_account(client, db, 1.0)
        for extra in ({"subcontract": {"allowance_usd": 0.005}}, {}):   # allowance root, then linkage-only
            stash.clear()
            r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": buyer_key}, json={**BRIEF, **extra})
            assert r.status_code == 200, r.text
            late = client.post("/ai-market/v2/invoke", json=WEATHER, headers={
                subcontract.JOB_HEADER: stash[subcontract.JOB_HEADER], "X-API-Key": provider_key})
            assert late.status_code == 403 and late.json()["error"] == "job_invalid", late.text
            assert "finished" in late.json()["detail"]
            # The refusal leaves no write pending. On PostgreSQL one did: the request's
            # connection stayed "idle in transaction", and the next write to the row hung.
            raw = getattr(db._conn, "_conn", None)
            if raw is not None and hasattr(raw, "in_transaction"):
                assert not raw.in_transaction

    def test_a_child_refused_after_joining_gives_its_slots_back(self, world):
        client, db, providers = world
        list_static(db, capability_id="other.tool@v1", product_id="other", price=0.001)
        seen: dict = {}

        async def brief(body, headers, p):
            r = await p.buy({**WEATHER, "product_id": "other", "capability_id": "other.tool@v1"}, job_headers(headers))
            seen["status"], seen["body"] = r.status_code, r.json()
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        m = setup_mandate(client, db, scope=("brief.*", "wx.*"),
                          subcontract={"perCallAllowance": 10_000, "maxDepth": 1})
        r = mandated_invoke(client, m, {**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 200, r.text
        assert seen["status"] == 403 and seen["body"]["error"] == "mandate_scope"
        job_id = r.json()["subcontracting"]["job_id"]
        tree = client.get(f"/ai-market/v2/jobs/{job_id}").json()
        assert [n["status"] for n in tree["nodes"] if n["depth"] == 1] == ["refused"]
        n = db._conn.execute("SELECT n FROM job_counters WHERE counter = ?", (f"nodes:{job_id}",)).fetchone()
        assert n["n"] == 0

    def test_sixty_four_nodes_is_the_whole_job_root_included(self, monkeypatch, tmp_path):
        from aimarket_hub.signing import Signer

        with hub(monkeypatch, tmp_path) as (client, db):
            store = subcontract.JobStore(db._conn, Signer(tmp_path / "k"), HUB)
            root = store.open_root(product_id="r", capability_id="root@v1", max_depth=subcontract.HUB_MAX_DEPTH)
            children = [store.join(token=store.issue_token(root), grant_secret="", product_id=f"c{i}",
                                   capability_id=f"c{i}@v1") for i in range(16)]
            joined = 16
            for i in range(47):
                parent = children[i % 16]
                store.join(token=store.issue_token(parent), grant_secret="", product_id=f"g{i}",
                           capability_id=f"g{i}@v1")
                joined += 1
            assert joined + 1 == subcontract.MAX_NODES_PER_JOB
            with pytest.raises(subcontract.SubcontractError) as refused:
                store.join(token=store.issue_token(children[0]), grant_secret="", product_id="x",
                           capability_id="x@v1")
            assert refused.value.error == "job_limit" and refused.value.extra.get("limit") == "nodes"
            assert len(store.tree(root.job_id)["nodes"]) == 64

    def test_a_linkage_only_job_goes_as_deep_as_the_hub_allows(self, world):
        client, db, providers = world
        list_provider(db, "mid.step@v1", "mid", 0.002, url="https://mid.test/invoke")
        _, own_key = funded_account(client, db, 1.0)   # each hop pays for itself
        seen: dict = {}

        async def brief(body, headers, p):
            r = await p.buy({**WEATHER, "product_id": "mid", "capability_id": "mid.step@v1"},
                            {**job_headers(headers, with_grant=False), "X-API-Key": own_key})
            seen["mid"] = r.status_code
            return 200, {"result": {"ok": True}}

        async def mid(body, headers, p):
            r = await p.buy(WEATHER, {**job_headers(headers, with_grant=False), "X-API-Key": own_key})
            seen["leaf"] = (r.status_code, r.json().get("job", {}).get("depth"))
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        providers.add("https://mid.test/invoke", mid)
        _, api_key = funded_account(client, db, 1.0)
        assert client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=BRIEF).status_code == 200
        assert seen == {"mid": 200, "leaf": (200, 2)}

    def test_each_receipt_commits_to_its_own_children_by_their_receipt_ids(self, world):
        import awr

        client, db, providers = world
        list_provider(db, "mid.step@v1", "mid", 0.002, url="https://mid.test/invoke")
        seen: dict = {}

        async def brief(body, headers, p):
            r = await p.buy({**WEATHER, "product_id": "mid", "capability_id": "mid.step@v1"}, job_headers(headers))
            assert r.status_code == 200, r.text
            seen["mid"] = r.json()["provenance_receipt"]
            return 200, {"result": {"ok": True}}

        async def mid(body, headers, p):
            r = await p.buy(WEATHER, job_headers(headers))
            assert r.status_code == 200, r.text
            seen["leaf"] = r.json()["provenance_receipt"]
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        providers.add("https://mid.test/invoke", mid)
        _, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.01, "max_depth": 2}})
        assert r.status_code == 200, r.text

        def doc(url):
            d = client.get(url).json()
            return d.get("receipt", d)

        root, mid_doc, leaf = (doc(r.json()["provenance_receipt"]["receipt_url"]),
                               doc(seen["mid"]["receipt_url"]), doc(seen["leaf"]["receipt_url"]))
        assert root["credentialSubject"]["parents"] == [
            {"id": seen["mid"]["receipt_id"], "digestSRI": seen["mid"]["digest_sri"]}]
        assert mid_doc["credentialSubject"]["parents"] == [
            {"id": seen["leaf"]["receipt_id"], "digestSRI": seen["leaf"]["digest_sri"]}]
        # and an outsider holding the three documents resolves the whole chain
        result = awr.verify(root, supporting=[mid_doc, leaf])
        assert result["valid"], result["reasons"]
        assert result["chain"]["resolved"] == 2 and result["chain"]["unresolved"] == 0

    def test_get_jobs_reports_the_same_bill_as_the_answer(self, world):
        client, db, providers = world

        async def brief(body, headers, p):
            await p.buy(WEATHER, job_headers(headers))
            return 200, {"result": {"ok": True}}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        sub = r.json()["subcontracting"]
        tree = client.get(f"/ai-market/v2/jobs/{sub['job_id']}").json()
        assert (tree["spent_usd"], tree["released_usd"]) == (sub["spent_usd"], sub["released_usd"])
        assert sub["spent_usd"] == pytest.approx(0.001) and sub["released_usd"] == pytest.approx(0.004)
        # the answer's balance is the balance AFTER the rest of the allowance came back
        assert r.json()["remaining_balance"] == pytest.approx(balance(db, account))

    def test_a_root_that_fails_after_its_children_delivered_still_shows_the_bill(self, world):
        client, db, providers = world

        async def brief(body, headers, p):
            for _ in range(2):
                assert (await p.buy(WEATHER, job_headers(headers))).status_code == 200
            return 500, {"error": "upstream offline"}

        providers.add("https://brief.test/invoke", brief)
        account, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.004}})
        assert r.status_code >= 400
        sub = r.json()["subcontracting"]
        assert sub["job_id"] and [n["status"] for n in sub["nodes"]] == ["captured", "captured"]
        assert sub["spent_usd"] == pytest.approx(0.002)
        # cost-plus: the materials are paid for, the failed brief is not
        assert balance(db, account) == pytest.approx(1.0 - 0.002)

    def test_an_expired_grant_pays_nothing(self, monkeypatch, tmp_path):
        from aimarket_hub.signing import Signer

        with hub(monkeypatch, tmp_path) as (client, db):
            store = subcontract.JobStore(db._conn, Signer(tmp_path / "k"), HUB)
            root = store.open_root(product_id="brief", capability_id="brief.make@v1", allowance_micro=5_000,
                                   account_id="acct", allowance_receipt="alw_e", now=time.time() - 3600)
            with pytest.raises(subcontract.SubcontractError) as e:
                store.join(token=store.issue_token(root), grant_secret=root.grant_secret,
                           product_id="wx", capability_id="wx.read@v1")
            assert e.value.error == "allowance_exhausted"

    def test_the_hub_caps_an_allowance(self, world):
        client, db, providers = world
        _, api_key = funded_account(client, db, 5.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 2.0}})
        assert r.status_code == 400 and r.json()["error"] == "subcontract_unsupported", r.text

    def test_a_mandate_bounds_the_depth_of_the_job_it_opens(self, world):
        client, db, providers = world
        m = setup_mandate(client, db, subcontract={"perCallAllowance": 10_000, "maxDepth": 1})
        r = mandated_invoke(client, m, {**BRIEF, "subcontract": {"allowance_usd": 0.005, "max_depth": 2}})
        assert r.status_code == 403 and "maxDepth" in r.json()["detail"], r.text

    def test_a_job_token_is_domain_separated(self, monkeypatch, tmp_path):
        from aimarket_hub.signing import Signer

        signer = Signer(tmp_path / "k")
        store = subcontract.JobStore(None, signer, HUB)
        ctx = subcontract.JobContext(job_id="job_x", node="node_x", depth=0, max_depth=1, path=["a@v1"])
        token = store.issue_token(ctx)
        assert store.verify_token(token)["job"] == "job_x"
        # the same claims signed bare — as anything else this key signs would be — do not verify
        payload_b64 = token.split(".", 1)[0]
        bare = f"{payload_b64}.{b64url(signer.sign(subcontract._b64url_decode(payload_b64)))}"
        with pytest.raises(subcontract.SubcontractError):
            store.verify_token(bare)


def test_a_stranded_allowance_is_settled_when_the_hub_starts(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.signing import Signer

    with hub(monkeypatch, tmp_path) as (client, db):
        account, _ = funded_account(client, db, 1.0)
        ledger = credits.CreditsLedger(db._conn)
        ledger.hold(account, 0.005, "alw_stranded")
        subcontract.JobStore(db._conn, None, HUB).open_root(
            product_id="brief", capability_id="brief.make@v1", allowance_micro=5_000,
            account_id=account, allowance_receipt="alw_stranded", now=0)
        assert balance(db, account) == pytest.approx(0.995)
        # the process that held it "crashed"; a new one starts on the same database
        config = HubConfig()
        config.hub_url = HUB
        config.db_path = str(tmp_path / "restarted.db")
        config.signing_key_path = str(tmp_path / "restarted.key")
        restarted = create_app(config=config, db=db, signer=Signer(tmp_path / "restarted.key"))
        with TestClient(restarted, base_url=HUB):
            pass
        assert balance(db, account) == pytest.approx(1.0)
        grant = db._conn.execute("SELECT status, settled_at FROM job_grants WHERE allowance_receipt = ?",
                                 ("alw_stranded",)).fetchone()
        assert grant["status"] == "closed" and grant["settled_at"]


def test_the_well_known_advertises_mandates_and_subcontracting(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        wk = client.get("/.well-known/ai-market.json").json()
        assert wk["mandates"]["version"] == "AMD/1" and wk["mandates"]["enabled"] is True
        assert wk["mandates"]["audience"] == HUB
        assert wk["subcontracting"]["version"] == "SUB/1"
        assert wk["subcontracting"]["max_nodes_per_job"] == subcontract.MAX_NODES_PER_JOB
