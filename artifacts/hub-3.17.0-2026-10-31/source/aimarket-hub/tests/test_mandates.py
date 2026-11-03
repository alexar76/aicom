"""Agent mandates (aimarket-protocol/mandates.md §3-5), end to end.

The property that matters most is at the bottom of each section: a mandate's limit cannot be
overrun — not by one call, not by a day of calls, not by siblings in a delegation chain and
not by concurrent requests.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    ECHO, HUB, balance, digest, funded_account, hub, issue, key, list_static,
    mandated_invoke, owner_link_payload, request_proof, revoke_payload, setup_mandate,
)
from aimarket_hub import mandates
from aimarket_hub.mandates import MandateError, check_link, parse_mandate


# ── the document (§3.2) ───────────────────────────────────────────────────

class TestDocument:
    def test_a_signed_mandate_verifies_and_is_named_by_its_digest(self):
        doc = issue(key(1), key(2).did)
        m = parse_mandate(doc)
        assert m.digest == digest(doc)
        assert m.issuer == key(1).did and m.subject == key(2).did
        assert m.limits == {"perCall": 20_000, "perDay": 1_000_000}

    def test_changing_a_limit_after_signing_breaks_the_proof(self):
        doc = issue(key(1), key(2).did)
        doc["credentialSubject"]["aimarketMandate"]["limits"]["perDay"] = 999_999_999
        with pytest.raises(MandateError) as e:
            parse_mandate(doc)
        assert e.value.error == "mandate_invalid" and "proof" in e.value.detail

    @pytest.mark.parametrize("mutate, needle", [
        (lambda d: d["credentialSubject"]["aimarketMandate"]["limits"].__setitem__("perCall", 1.5), "integers"),
        (lambda d: d["credentialSubject"]["aimarketMandate"]["limits"].__setitem__("perCall", True), "integer"),
        (lambda d: d["credentialSubject"]["aimarketMandate"]["limits"].pop("perDay"), "perDay"),
        (lambda d: d["credentialSubject"]["aimarketMandate"].__setitem__("scope", ["gaia.**"]), "scope"),
        (lambda d: d["credentialSubject"]["aimarketMandate"].__setitem__("audience", ["https://h.test/"]), "audience"),
        (lambda d: d["credentialSubject"]["aimarketMandate"].__setitem__("audience", ["ftp://h.test"]), "audience"),
        (lambda d: d.__setitem__("@context", ["https://example.com"]), "@context"),
    ])
    def test_field_rules_refuse_before_the_signature_matters(self, mutate, needle):
        doc = issue(key(1), key(2).did)
        mutate(doc)
        with pytest.raises(MandateError) as e:
            parse_mandate(doc)
        assert needle in e.value.detail

    def test_a_mandate_to_oneself_and_a_year_plus_span_are_refused(self):
        with pytest.raises(MandateError, match="own issuer"):
            parse_mandate(issue(key(1), key(1).did))
        with pytest.raises(MandateError, match="366 days"):
            parse_mandate(issue(key(1), key(2).did, days=400))


# ── delegation (§3.4) ─────────────────────────────────────────────────────

class TestChainRules:
    def _pair(self, **child):
        parent = parse_mandate(issue(key(1), key(2).did, scope=("gaia.*",), per_day=1000, per_call=100,
                                     subcontract={"perCallAllowance": 50, "maxDepth": 2}))
        fields = dict(scope=("gaia.weather.read@v1",), per_day=500, per_call=100, parent=parent.digest)
        fields.update(child)
        issuer = fields.pop("issuer", key(2))
        return parent, parse_mandate(issue(issuer, key(3).did, **fields))

    def test_a_narrower_child_is_a_valid_link(self):
        parent, child = self._pair()
        check_link(child, parent)

    @pytest.mark.parametrize("change, needle", [
        ({"scope": ("atlas.*",)}, "widens scope"),
        ({"scope": ("*",)}, "widens scope"),
        ({"per_day": 5000}, "raises limit perDay"),
        ({"issuer": key(9)}, "not issued by the parent's subject"),
        ({"days": 60}, "outlives"),
        ({"subcontract": {"perCallAllowance": 99, "maxDepth": 1}}, "subcontract.perCallAllowance"),
        ({"audience": (HUB, "https://other.test")}, "names a hub"),
    ])
    def test_a_child_can_never_widen_what_its_parent_allows(self, change, needle):
        parent, child = self._pair(**change)
        with pytest.raises(MandateError) as e:
            check_link(child, parent)
        assert needle in e.value.detail

    def test_dropping_a_limit_the_parent_sets_is_widening_too(self):
        parent = parse_mandate(issue(key(1), key(2).did, total=5000))
        child = parse_mandate(issue(key(2), key(3).did, parent=parent.digest))
        with pytest.raises(MandateError, match="drops the parent's limit total"):
            check_link(child, parent)


# ── the owner link (§4) ───────────────────────────────────────────────────

class TestOwnerLink:
    def test_registration_needs_a_funded_root(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            r = client.post("/ai-market/v2/mandates", json=issue(key(1), key(2).did))
            assert r.status_code == 402 and r.json()["error"] == "mandate_unfunded"

    def test_a_link_needs_both_the_api_key_and_the_owner_signature(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = funded_account(client, db)
            payload = owner_link_payload(key(1), account)
            assert client.post("/ai-market/v2/mandates/owners", json=payload).status_code == 401
            forged = owner_link_payload(key(1), account)
            forged["proof"]["s"] = owner_link_payload(key(7), account)["proof"]["s"]
            r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key}, json=forged)
            assert r.status_code == 401 and r.json()["error"] == "mandate_proof_invalid"
            r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key}, json=payload)
            assert r.status_code == 200 and r.json()["account_id"] == account
            # the same signed link cannot be replayed
            r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key}, json=payload)
            assert r.status_code == 401

    def test_one_did_cannot_be_claimed_by_two_accounts(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            a1, k1 = funded_account(client, db)
            a2, k2 = funded_account(client, db)
            assert client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": k1},
                               json=owner_link_payload(key(1), a1)).status_code == 200
            r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": k2},
                            json=owner_link_payload(key(1), a2))
            assert r.status_code == 409


# ── presenting a mandate (§5) ─────────────────────────────────────────────

class TestMandatedInvoke:
    def test_an_agent_without_the_api_key_pays_from_the_owner_account(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, usd=1.0)
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["price_usd"] == pytest.approx(0.004)
            assert body["mandate"] == {"digest": m["digest"], "agent": m["agent"].did,
                                       "principal": m["owner"].did, "depth": 0}
            assert balance(db, m["account"]) == pytest.approx(0.996)

    def test_the_proof_binds_key_body_and_nonce(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db)
            # wrong key
            r = mandated_invoke(client, m, ECHO, agent=key(8))
            assert r.status_code == 401 and r.json()["error"] == "mandate_proof_invalid"
            # proof over a different body
            body = json.dumps(ECHO).encode()
            proof = request_proof(m["agent"], m["digest"], b'{"other": 1}')
            r = client.post("/ai-market/v2/invoke", content=body, headers={
                "Content-Type": "application/json", "X-AIMarket-Mandate": m["digest"],
                "X-AIMarket-Mandate-Proof": proof})
            assert r.status_code == 401
            # a replayed nonce
            proof = request_proof(m["agent"], m["digest"], body, n="replayed-nonce-0001")
            headers = {"Content-Type": "application/json", "X-AIMarket-Mandate": m["digest"],
                       "X-AIMarket-Mandate-Proof": proof}
            assert client.post("/ai-market/v2/invoke", content=body, headers=headers).status_code == 200
            r = client.post("/ai-market/v2/invoke", content=body, headers=headers)
            assert r.status_code == 401 and "already used" in r.json()["detail"]
            # a stale timestamp
            stale = request_proof(m["agent"], m["digest"], body, t=int(time.time()) - 3600)
            r = client.post("/ai-market/v2/invoke", content=body, headers={
                "Content-Type": "application/json", "X-AIMarket-Mandate": m["digest"],
                "X-AIMarket-Mandate-Proof": stale})
            assert r.status_code == 401
            assert balance(db, m["account"]) == pytest.approx(1.0 - 0.004)

    def test_scope_and_audience(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, scope=("gaia.*",))
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 403 and r.json()["error"] == "mandate_scope"
        with hub(monkeypatch, tmp_path) as (client, db):
            # §3.2: a hub refuses to REGISTER a mandate that does not name it, so the
            # audience check at invoke is reached only by a mandate stored before that rule.
            account, api_key = funded_account(client, db)
            owner = key(1)
            client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                        json=owner_link_payload(owner, account))
            r = client.post("/ai-market/v2/mandates",
                            json=issue(owner, key(2).did, audience=("https://elsewhere.test",)))
            assert r.status_code == 403 and "not addressed" in r.json()["detail"]

    def test_a_mandate_does_not_ride_along_with_another_rail(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db)
            r = mandated_invoke(client, m, ECHO, extra_headers={"X-Payment-Channel": "ch_x"})
            assert r.status_code == 400 and r.json()["error"] == "mandate_rail_unsupported"

    def test_require_mandate_closes_the_raw_api_key(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            account, api_key = funded_account(client, db)
            client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                        json=owner_link_payload(key(1), account, require_mandate=True))
            r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=ECHO)
            assert r.status_code == 402 and r.json()["error"] == "mandate_required"
            assert balance(db, account) == pytest.approx(1.0)


# ── the limits (§5.3) ─────────────────────────────────────────────────────

class TestLimits:
    def test_per_call(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, per_call=3_000)
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 402
            assert r.json()["error"] == "mandate_limit" and r.json()["limit"] == "perCall"
            assert balance(db, m["account"]) == pytest.approx(1.0)

    def test_per_day_stops_exactly_at_the_limit(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, per_day=10_000)   # room for two calls, not three
            assert mandated_invoke(client, m, ECHO).status_code == 200
            assert mandated_invoke(client, m, ECHO).status_code == 200
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 402 and r.json()["limit"] == "perDay"
            assert balance(db, m["account"]) == pytest.approx(1.0 - 0.008)
            usage = client.get(f"/ai-market/v2/mandates/{m['digest']}",
                               headers={"X-API-Key": m["api_key"]}).json()["usage"]
            assert usage["spent_today_usd"] == pytest.approx(0.008)

    def test_siblings_share_their_parent_limit(self, monkeypatch, tmp_path):
        """Two re-delegations each allowed the parent's whole day can still only spend it
        once between them: spend is recorded against every mandate in the chain."""
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, per_day=10_000)
            children = []
            for seed in (3, 4):
                child = issue(m["agent"], key(seed).did, per_day=10_000, parent=m["digest"])
                assert client.post("/ai-market/v2/mandates", json=child).status_code == 200
                children.append((key(seed), digest(child)))
            ok = 0
            for agent, leaf in children * 2:
                r = mandated_invoke(client, m, ECHO, agent=agent, leaf=leaf)
                ok += r.status_code == 200
            assert ok == 2
            assert balance(db, m["account"]) == pytest.approx(1.0 - 0.008)

    def test_concurrent_reservations_never_overrun_a_counter(self, monkeypatch, tmp_path):
        """Forty threads race for a limit with room for ten. The counter is moved by one
        conditional statement, so exactly ten win however the threads interleave."""
        # A read-then-write regression loses this race only most of the time; five rounds,
        # each on a fresh mandate, make a miss vanishingly unlikely.
        with hub(monkeypatch, tmp_path) as (client, db):
            store = mandates.MandateStore(db._conn, HUB)
            for round_ in range(5):
                m = setup_mandate(client, db, per_day=40_000, owner_seed=100 + round_, agent_seed=200 + round_)
                chain = store.chain(m["digest"])
                wins, refusals = [], []
                barrier = threading.Barrier(40)

                def race(i: int) -> None:
                    barrier.wait()
                    try:
                        store.reserve(chain, receipt_id=f"r{round_}_{i}", amount_micro=4_000, product_id="p")
                        wins.append(i)
                    except MandateError:
                        refusals.append(i)

                threads = [threading.Thread(target=race, args=(i,)) for i in range(40)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                assert len(wins) == 10 and len(refusals) == 30, round_
                assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.04)

    def test_a_failed_call_gives_its_reservation_back(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            db.upsert_capability(__import__("aimarket_hub.models", fromlist=["Capability"]).Capability(
                capability_id="broken@v1", product_id="broken", name="broken", description="x",
                price_per_call_usd=0.004, source_hub="local", invoke_url="",
                prompt_template='{"ok": false, "error": "upstream down"}',
            ))
            m = setup_mandate(client, db, per_day=10_000)
            r = mandated_invoke(client, m, {**ECHO, "product_id": "broken", "capability_id": "broken@v1"})
            assert r.status_code == 502
            store = mandates.MandateStore(db._conn, HUB)
            assert store.usage(m["digest"])["spent_today_usd"] == 0
            assert balance(db, m["account"]) == pytest.approx(1.0)


# ── revocation (§5.5) ─────────────────────────────────────────────────────

class TestRevocation:
    def test_revoking_a_parent_revokes_the_child(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db)
            child = issue(m["agent"], key(3).did, parent=m["digest"])
            client.post("/ai-market/v2/mandates", json=child)
            leaf = digest(child)
            assert mandated_invoke(client, m, ECHO, agent=key(3), leaf=leaf).status_code == 200
            r = client.post("/ai-market/v2/mandates/revoke", json=revoke_payload(m["owner"], m["digest"]))
            assert r.status_code == 200 and r.json()["status"] == "revoked"
            r = mandated_invoke(client, m, ECHO, agent=key(3), leaf=leaf)
            assert r.status_code == 403 and "revoked" in r.json()["detail"]

    def test_only_an_issuer_in_the_chain_may_revoke(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            r = client.post("/ai-market/v2/mandates/revoke", json=revoke_payload(key(9), m["digest"]))
            assert r.status_code == 403

    def test_the_funding_account_is_the_kill_switch(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db)
            r = client.post("/ai-market/v2/mandates/revoke", headers={"X-API-Key": m["api_key"]},
                            json={"digest": m["digest"]})
            assert r.status_code == 200
            assert mandated_invoke(client, m, ECHO).status_code == 403


# ── the normative vectors (mandates.md §9) ────────────────────────────────

_VECTOR_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "aimarket-protocol" / "test-vectors"


@pytest.fixture(scope="module")
def vectors():
    path = _VECTOR_DIR / "mandate-signed.json"
    if not path.exists():
        pytest.skip("mandate vectors live in the monorepo's aimarket-protocol/")
    return json.loads(path.read_text())


class TestProtocolVectors:
    def test_the_generator_reproduces_the_committed_file(self, tmp_path):
        """The vectors are normative only if they are what the generator says they are."""
        generator = _VECTOR_DIR / "generate_mandates.py"
        if not generator.exists():
            pytest.skip("mandate vectors live in the monorepo's aimarket-protocol/")
        code = compile(generator.read_text(), str(generator), "exec")
        exec(code, {"__file__": str(tmp_path / "generate_mandates.py"), "__name__": "__main__"})  # noqa: S102
        assert (tmp_path / "mandate-signed.json").read_bytes() == (_VECTOR_DIR / "mandate-signed.json").read_bytes()

    def test_the_hub_accepts_the_owner_change_and_revocation_signatures(self, vectors):
        change, revoke = vectors["owner_change"], vectors["revoke"]
        message = mandates.owner_change_message(
            hub_origin=vectors["hub_origin"], account_id=change["account_id"], action=change["action"],
            did=change["did"], require_mandate=bool(change["require_mandate"]), t=change["t"], nonce=change["n"],
        )
        assert message.decode() == change["message"]
        assert mandates.verify_did_signature(change["by"], message, mandates.b64url_decode(change["signature"]))
        message = mandates.revoke_message(hub_origin=vectors["hub_origin"], digest=revoke["digest"],
                                          t=revoke["t"], nonce=revoke["n"])
        assert message.decode() == revoke["message"]
        assert mandates.verify_did_signature(revoke["by"], message, mandates.b64url_decode(revoke["signature"]))

    def test_the_hub_reproduces_both_digests_and_the_chain(self, vectors):
        root = parse_mandate(vectors["root"]["document"])
        child = parse_mandate(vectors["child"]["document"])
        assert root.digest == vectors["root"]["digest"]
        assert child.digest == vectors["child"]["digest"]
        check_link(child, root)

    def test_the_hub_accepts_the_request_and_owner_link_signatures(self, vectors):
        p, link = vectors["request_proof"], vectors["owner_link"]
        message = mandates.request_message(
            hub_origin=vectors["hub_origin"], method=p["method"], path=p["path"], digest=p["leaf"],
            t=p["t"], nonce=p["n"], body=p["body"].encode(),
        )
        assert message.decode() == p["message"]
        assert mandates.verify_did_signature(vectors["keys"]["delegate"]["did"], message,
                                             mandates.b64url_decode(p["signature"]))
        message = mandates.owner_link_message(
            hub_origin=vectors["hub_origin"], account_id=link["account_id"], did=link["did"],
            t=link["t"], nonce=link["n"],
        )
        assert message.decode() == link["message"]
        assert mandates.verify_did_signature(link["did"], message, mandates.b64url_decode(link["signature"]))


# ── what an independent review of the money path found (each pinned) ────

class TestOwnerChangesNeedAnOwner:
    """A leaked API key must not get around require_mandate (§4)."""

    def _locked_account(self, client, db):
        from tests._mandate_kit import owner_link_payload
        account, api_key = funded_account(client, db)
        r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                        json=owner_link_payload(key(1), account, require_mandate=True))
        assert r.status_code == 200
        return account, api_key

    def test_the_key_alone_cannot_link_an_attackers_did(self, monkeypatch, tmp_path):
        from tests._mandate_kit import owner_change
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = self._locked_account(client, db)
            attacker = key(66)
            r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                            json=owner_link_payload(attacker, account))
            assert r.status_code == 403 and r.json()["error"] == "owner_authorization_required"
            # the same link, authorized by the real owner, goes through
            payload = owner_link_payload(key(2), account)
            payload["authorization"] = owner_change(key(1), account, "link", key(2).did)
            assert client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                               json=payload).status_code == 200

    def test_the_key_alone_cannot_unlink_or_relax_the_policy(self, monkeypatch, tmp_path):
        from tests._mandate_kit import owner_change
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            account, api_key = self._locked_account(client, db)
            r = client.post("/ai-market/v2/mandates/owners/unlink", headers={"X-API-Key": api_key},
                            json={"did": key(1).did})
            assert r.status_code == 403
            r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                            json=owner_link_payload(key(1), account, require_mandate=False))
            assert r.status_code == 403
            # still locked: the bare key does not pay
            assert client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json=ECHO).status_code == 402
            # the owner itself may unlink
            r = client.post("/ai-market/v2/mandates/owners/unlink", headers={"X-API-Key": api_key},
                            json={"did": key(1).did, "authorization": owner_change(key(1), account, "unlink", key(1).did)})
            assert r.status_code == 200

    def test_the_operator_can_recover_an_owner_who_lost_every_key(self, monkeypatch, tmp_path):
        from tests._mandate_kit import ADMIN_TOKEN
        with hub(monkeypatch, tmp_path) as (client, db):
            account, api_key = self._locked_account(client, db)
            r = client.post("/ai-market/v2/mandates/owners", json=owner_link_payload(key(3), account),
                            headers={"X-API-Key": api_key, "Authorization": f"Bearer {ADMIN_TOKEN}"})
            assert r.status_code == 200


class TestLimitsCannotBeDodged:
    def test_a_fresh_product_id_does_not_open_a_fresh_per_product_counter(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db, price=0.004)
            m = setup_mandate(client, db, per_product=8_000)
            codes = [mandated_invoke(client, m, {**ECHO, "product_id": f"zz{i}"}).status_code for i in range(4)]
            assert codes[:2] == [200, 200] and codes[2:] == [402, 402]
            assert balance(db, m["account"]) == pytest.approx(1.0 - 0.008)

    def test_per_call_covers_every_hold_of_the_call(self, monkeypatch, tmp_path):
        """A federated call reserves its price and then the routing fee; perCall is their sum."""
        from aimarket_hub import credits

        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db, per_call=5_000)
            store = mandates.MandateStore(db._conn, HUB)
            adm = mandates.Admission(chain=store.chain(m["digest"]), account_id=m["account"],
                                     product_id="p", store=store)
            proxy = mandates.MandatedCredits(credits.CreditsLedger(db._conn), adm)
            assert not proxy.hold(m["account"], 0.004, "price-1").get("error")
            refused = proxy.hold(m["account"], 0.002, "fee-1")
            assert refused.get("error") and adm.last_refusal.extra["limit"] == "perCall"
            # an allowance is bounded by perCallAllowance, not perCall
            assert not proxy.hold_allowance(m["account"], 0.008, "alw-1").get("error")

    def test_release_after_capture_keeps_the_money_counted(self, monkeypatch, tmp_path):
        from aimarket_hub import credits

        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            ledger = credits.CreditsLedger(db._conn)
            store = mandates.MandateStore(db._conn, HUB)
            adm = mandates.Admission(chain=store.chain(m["digest"]), account_id=m["account"],
                                     product_id="p", store=store)
            proxy = mandates.MandatedCredits(ledger, adm)
            proxy.hold(m["account"], 0.004, "r1")
            ledger.capture_hold("r1")        # the capture committed; the mandate step did not
            proxy.release_hold("r1")          # the handler's `finally` then runs
            assert store.usage(m["digest"])["spent_today_usd"] == pytest.approx(0.004)

    def test_a_hold_that_raises_does_not_strand_the_limit(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db)
            store = mandates.MandateStore(db._conn, HUB)
            adm = mandates.Admission(chain=store.chain(m["digest"]), account_id=m["account"],
                                     product_id="p", store=store)

            class Boom:
                def hold(self, *a):
                    raise RuntimeError("database is locked")

            with pytest.raises(RuntimeError):
                mandates.MandatedCredits(Boom(), adm).hold(m["account"], 0.004, "r1")
            assert store.usage(m["digest"])["spent_today_usd"] == 0

    def test_limits_count_what_the_ledger_actually_holds(self):
        # the credits ledger counts millicents (10 µUSD): $0.000006 is held as 10 µUSD
        assert mandates.MandatedCredits._micro(0.000006) == 10
        assert mandates.MandatedCredits._micro(0.004) == 4_000


def test_a_hub_under_a_path_can_be_named_in_audience():
    doc = issue(key(1), key(2).did, audience=("https://independentai.network/hub",))
    assert parse_mandate(doc).audience == ("https://independentai.network/hub",)
