"""Owner approval above a threshold (aimarket-protocol/mandates.md §5.6).

What must hold: a mandated call that costs more than ``approvalAbove`` spends nothing until
an owner of the funding account signs THAT call; the signature cannot be stretched to another
call, a higher amount or a second run; and a refusal is not turned into a nag.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

import pytest

from tests._mandate_kit import (  # noqa: E402  (importorskip awr first)
    ECHO, approval_payload, balance, funded_account, hub, issue, key, list_static, mandated_invoke,
    owner_link_payload, setup_mandate,
)
from aimarket_hub import mandates
from aimarket_hub.mandates import MandateError, check_link, parse_mandate

PRICE = 0.004
# 3000 µUSD: under the static pack's 4000 µUSD price, so every ECHO call needs an approval.
THRESHOLD = 3_000


def _approve(client, m, approval, decision="approve", **kw):
    return client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                       json=approval_payload(m["owner"], approval, decision, **kw))


class TestDocument:
    def test_approval_above_is_a_limit_a_child_keeps_and_may_only_lower(self):
        parent = parse_mandate(issue(key(1), key(2).did, approval_above=5_000))
        assert parent.limits["approvalAbove"] == 5_000
        lower = parse_mandate(issue(key(2), key(3).did, parent=parent.digest, approval_above=1_000))
        check_link(lower, parent)
        dropped = parse_mandate(issue(key(2), key(3).did, parent=parent.digest))
        with pytest.raises(MandateError, match="drops the parent's limit approvalAbove"):
            check_link(dropped, parent)
        raised = parse_mandate(issue(key(2), key(3).did, parent=parent.digest, approval_above=9_000))
        with pytest.raises(MandateError, match="raises limit approvalAbove"):
            check_link(raised, parent)

    def test_the_strictest_threshold_in_the_chain_applies(self):
        parent = parse_mandate(issue(key(1), key(2).did, approval_above=5_000))
        child = parse_mandate(issue(key(2), key(3).did, parent=parent.digest, approval_above=2_000))
        assert mandates.approval_threshold([parent, child]) == 2_000
        assert mandates.approval_threshold([parse_mandate(issue(key(1), key(2).did))]) is None


class TestFlow:
    def test_under_the_threshold_nothing_is_asked(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=10_000)
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 200, r.text
            assert balance(db, m["account"]) == pytest.approx(1.0 - PRICE)

    def test_over_the_threshold_the_call_waits_for_a_signed_approval(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 402, r.text
            body = r.json()
            assert body["error"] == "approval_required" and body["limit"] == "approvalAbove"
            approval = body["approval"]
            assert approval["status"] == "pending"
            assert approval["capability_id"] == "demo.echo@v1"
            assert approval["amount_usd"] == pytest.approx(PRICE)
            assert approval["max_micro"] == 4_000          # a local call: no routing fee to cover
            assert approval["body_sha256"] == hashlib.sha256(json.dumps(ECHO).encode()).hexdigest()
            assert approval["url"].endswith(f"/mandates/approvals/{approval['approval_id']}")
            assert "account_id" not in approval
            assert balance(db, m["account"]) == pytest.approx(1.0), "nothing is spent while waiting"

            # Asking again before the owner answers is the same request, not a second one.
            again = mandated_invoke(client, m, ECHO).json()["approval"]
            assert again["approval_id"] == approval["approval_id"]
            listed = client.get("/ai-market/v2/mandates/approvals?status=pending",
                                headers={"X-API-Key": m["api_key"]}).json()["approvals"]
            assert [a["approval_id"] for a in listed] == [approval["approval_id"]]

            r = _approve(client, m, approval)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "approved" and r.json()["decided_by"] == m["owner"].did

            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 200, r.text
            assert balance(db, m["account"]) == pytest.approx(1.0 - PRICE)
            state = client.get(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}").json()
            assert state["status"] == "used"

            # One approval, one call: the identical call again is a new request.
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 402 and r.json()["error"] == "approval_required"
            assert r.json()["approval"]["approval_id"] != approval["approval_id"]
            assert balance(db, m["account"]) == pytest.approx(1.0 - PRICE)

    def test_an_approval_covers_only_the_bytes_it_names(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            assert _approve(client, m, approval).status_code == 200
            other = {**ECHO, "input": {"text": "something else"}}
            r = mandated_invoke(client, m, other)
            assert r.status_code == 402 and r.json()["error"] == "approval_required"
            assert r.json()["approval"]["approval_id"] != approval["approval_id"]
            assert balance(db, m["account"]) == pytest.approx(1.0)

    def test_approving_needs_an_owner_signature_over_this_request(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            url = f"/ai-market/v2/mandates/approvals/{approval['approval_id']}"
            # the API key alone may not approve: it is what leaks
            r = client.post(url, headers={"X-API-Key": m["api_key"]}, json={"decision": "approve"})
            assert r.status_code == 403 and r.json()["error"] == "owner_authorization_required"
            # the agent cannot approve its own call
            r = client.post(url, json=approval_payload(m["agent"], approval))
            assert r.status_code == 403
            # a signature over a different ceiling does not verify
            r = client.post(url, json=approval_payload(m["owner"], approval, max_micro=999_999))
            assert r.status_code == 401 and r.json()["error"] == "mandate_proof_invalid"
            # a signed "deny" cannot be replayed as "approve"
            denial = approval_payload(m["owner"], approval, "deny")
            r = client.post(url, json={**denial, "decision": "approve"})
            assert r.status_code == 401
            # nobody answered: still pending, still nothing spent
            assert client.get(url).json()["status"] == "pending"
            assert balance(db, m["account"]) == pytest.approx(1.0)
            # the owner's real signature, once — its nonce cannot be used twice
            payload = approval_payload(m["owner"], approval)
            assert client.post(url, json=payload).status_code == 200
            r = client.post(url, json=payload)
            assert r.status_code == 200 and r.json().get("unchanged") is True

    def test_a_second_owner_of_the_account_may_approve(self, monkeypatch, tmp_path):
        from tests._mandate_kit import owner_change

        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            cfo = key(40)
            link = owner_link_payload(cfo, m["account"])
            link["authorization"] = owner_change(m["owner"], m["account"], "link", cfo.did)
            assert client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": m["api_key"]},
                               json=link).status_code == 200
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            r = client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                            json=approval_payload(cfo, approval))
            assert r.status_code == 200 and r.json()["decided_by"] == cfo.did
            assert mandated_invoke(client, m, ECHO).status_code == 200

    def test_a_denial_stands_and_is_not_asked_again(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            # deny with the API key: denying moves no money, like the revoke kill switch
            r = client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                            headers={"X-API-Key": m["api_key"]}, json={"decision": "deny"})
            assert r.status_code == 200 and r.json()["status"] == "denied"
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 402 and r.json()["error"] == "approval_denied"
            assert r.json()["approval"]["approval_id"] == approval["approval_id"]
            # an answered request is closed
            r = _approve(client, m, approval)
            assert r.status_code == 409 and r.json()["error"] == "approval_closed"
            assert client.get("/ai-market/v2/mandates/approvals?status=pending",
                              headers={"X-API-Key": m["api_key"]}).json()["approvals"] == []
            assert balance(db, m["account"]) == pytest.approx(1.0)

    def test_another_account_cannot_answer(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            _, stranger_key = funded_account(client, db)
            r = client.post(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}",
                            headers={"X-API-Key": stranger_key}, json={"decision": "deny"})
            assert r.status_code == 403
            assert client.get("/ai-market/v2/mandates/approvals",
                              headers={"X-API-Key": stranger_key}).json()["approvals"] == []

    def test_unknown_and_malformed_ids(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            assert client.get("/ai-market/v2/mandates/approvals/apr_" + "0" * 24).status_code == 404
            assert client.get("/ai-market/v2/mandates/approvals/../../etc").status_code == 404
            assert client.get("/ai-market/v2/mandates/approvals").status_code == 401

    def test_an_agent_cannot_bury_its_owner_in_requests(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            for i in range(mandates.MAX_PENDING_APPROVALS):
                r = mandated_invoke(client, m, {**ECHO, "input": {"text": f"call {i}"}})
                assert r.json()["error"] == "approval_required"
            r = mandated_invoke(client, m, {**ECHO, "input": {"text": "one too many"}})
            assert r.status_code == 429 and r.json()["error"] == "approval_queue_full"

    def test_an_expired_request_is_asked_again(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            first = mandated_invoke(client, m, ECHO).json()["approval"]
            assert _approve(client, m, first).status_code == 200
            db._conn.execute("UPDATE mandate_approvals SET expires_at = ? WHERE approval_id = ?",
                             (time.time() - 1, first["approval_id"]))
            db._conn.commit()
            assert client.get(f"/ai-market/v2/mandates/approvals/{first['approval_id']}").json()["status"] == "expired"
            r = mandated_invoke(client, m, ECHO)
            assert r.json()["error"] == "approval_required"
            assert r.json()["approval"]["approval_id"] != first["approval_id"]
            assert balance(db, m["account"]) == pytest.approx(1.0)

    @pytest.mark.parametrize("limits, name", [
        ({"per_call": 3_500}, "perCall"),
        ({"per_day": 3_500}, "perDay"),
        ({"total": 3_500}, "total"),
        ({"per_product": 3_500}, "perProductPerDay"),
    ])
    def test_the_owner_is_not_asked_for_a_call_the_mandate_refuses(self, monkeypatch, tmp_path, limits, name):
        """A yes would change nothing: perCall and the period limits are checked first."""
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD, **limits)
            r = mandated_invoke(client, m, ECHO)
            assert r.status_code == 402 and r.json()["error"] == "mandate_limit", r.text
            assert r.json()["limit"] == name
            assert db._conn.execute("SELECT COUNT(*) AS n FROM mandate_approvals").fetchone()["n"] == 0

    def test_one_approval_pays_for_one_routed_call(self, monkeypatch, tmp_path):
        """A peer that answers below its catalogue price makes the hub release the fee hold and
        debit the smaller fee. The release gave the approval back, although the call ran and
        was charged: one signature then paid for any number of identical calls."""
        import aimarket_hub.outbound_http as ohttp
        from tests.test_federated_invoke import (
            MCP_ENDPOINT, ORACLE_PEER, _add_federated_capability, _add_peer, _oracle_envelope, _Outbound, _Resp,
        )

        routed = {"product_id": "prod-x", "capability_id": "cap.x@v1", "source_hub": ORACLE_PEER,
                  "input": {"q": "hi"}}
        with hub(monkeypatch, tmp_path) as (client, db):
            _add_peer(db, ORACLE_PEER, categories=["oracle"])
            _add_federated_capability(db, ORACLE_PEER, price=0.01)   # the hub holds its 100 µUSD fee
            outbound = _Outbound(_Resp(200, _oracle_envelope(price=0.008)), well_known={"mcp_endpoint": MCP_ENDPOINT})
            monkeypatch.setattr(ohttp, "safe_get", outbound.safe_get)
            monkeypatch.setattr(ohttp, "safe_post", outbound.safe_post)
            m = setup_mandate(client, db, approval_above=50)
            approval = mandated_invoke(client, m, routed).json()["approval"]
            assert _approve(client, m, approval).status_code == 200
            codes = [mandated_invoke(client, m, routed).status_code for _ in range(3)]
            assert codes == [200, 402, 402]
            assert len(outbound.posts) == 1
            spent = client.get(f"/ai-market/v2/mandates/approvals/{approval['approval_id']}").json()
            assert spent["status"] == "used"

    def test_usage_reports_the_threshold(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            r = client.get(f"/ai-market/v2/mandates/{m['digest']}", headers={"X-API-Key": m["api_key"]})
            assert r.json()["usage"]["approval_above_usd"] == pytest.approx(0.003)


class TestStore:
    """The approval follows the money: used by a hold, given back when that hold is released."""

    @pytest.fixture
    def approved(self, monkeypatch, tmp_path):
        with hub(monkeypatch, tmp_path) as (client, db):
            list_static(db)
            m = setup_mandate(client, db, approval_above=THRESHOLD)
            approval = mandated_invoke(client, m, ECHO).json()["approval"]
            assert _approve(client, m, approval).status_code == 200
            yield mandates.MandateStore(db._conn, "https://hub.test"), approval

    @staticmethod
    def _hold(store, approval, receipt):
        chain = store.chain(approval["mandate"])
        store.reserve(chain, receipt_id=receipt, amount_micro=4_000, product_id="demo-echo")

    def test_a_released_hold_gives_the_approval_back(self, approved):
        store, approval = approved
        self._hold(store, approval, "r1")
        assert store.claim_approval(approval["approval_id"], receipt_id="r1", need_micro=4_000)
        assert store.approval(approval["approval_id"])["status"] == "used"
        store.release("r1")
        assert store.approval(approval["approval_id"])["status"] == "approved"
        self._hold(store, approval, "r2")
        assert store.claim_approval(approval["approval_id"], receipt_id="r2", need_micro=4_000)
        store.capture("r2")
        store.release("r2")   # late: the hold was captured, so the approval stays spent
        assert store.approval(approval["approval_id"])["status"] == "used"

    def test_an_approval_cannot_cover_more_than_its_ceiling(self, approved):
        store, approval = approved
        assert not store.claim_approval(approval["approval_id"], receipt_id="r1", need_micro=4_010)
        assert store.claim_approval(approval["approval_id"], receipt_id="r1", need_micro=4_000)

    def test_concurrent_claims_have_one_winner(self, approved):
        store, approval = approved
        for _ in range(5):
            wins: list[bool] = []
            barrier = threading.Barrier(8)

            def claim(i: int) -> None:
                barrier.wait(timeout=10)
                wins.append(store.claim_approval(approval["approval_id"], receipt_id=f"race-{i}",
                                                 need_micro=4_000))

            threads = [threading.Thread(target=claim, args=(i,)) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)
            assert wins.count(True) == 1
            store.unclaim_approval(store.approval(approval["approval_id"])["receipt_id"])


def test_a_routed_calls_ceiling_covers_the_routing_fee():
    """The request is opened at the price hold; the fee hold comes right after it (§5.3). The
    ceiling the owner signs must cover both, or the same call would need a second approval."""
    from types import SimpleNamespace

    def ceiling(source_hub: str, bps: int, total: int) -> int:
        admission = SimpleNamespace(source_hub=source_hub, routing_fee_bps=bps)
        return mandates.MandatedCredits(None, admission)._ceiling(total)

    assert ceiling("local", 100, 4_000) == 4_000                      # no fee on a local call
    assert ceiling("https://peer.test", 0, 4_000) == 4_000            # a hub that charges none
    assert ceiling("https://peer.test", 100, 4_000) == 4_050          # 40 µUSD fee + one millicent
    assert ceiling("https://peer.test", 100, 4_001) == 4_061          # rounded up, never down
