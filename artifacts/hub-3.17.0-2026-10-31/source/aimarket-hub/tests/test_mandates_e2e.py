"""Across component boundaries: the SDK against the hub, and the job tree in AWR receipts.

The unit and HTTP suites prove each side on its own. These prove they meet: a mandate
issued by `aimarket-agent` (its own canonicalizer, no awr) is accepted and enforced by the
hub; and a subcontracting job is committed to in the root's AWR/2 work receipt by the digests
of its children's receipts, not merely listed in a JSON answer.
"""
from __future__ import annotations

import pytest

pytest.importorskip("aimarket_agent")

from aimarket_agent import AIMarketAgent, AgentKey, Mandate, issue_mandate, owner_link_payload  # noqa: E402

from tests._mandate_kit import HUB, balance, funded_account, hub, list_provider, list_static  # noqa: E402
from tests.test_subcontract import BRIEF, WEATHER, Providers, job_headers  # noqa: E402


def test_a_mandate_issued_by_the_sdk_is_accepted_and_enforced(monkeypatch, tmp_path):
    with hub(monkeypatch, tmp_path) as (client, db):
        list_static(db, price=0.004)
        account, api_key = funded_account(client, db, 1.0)
        owner, agent_key = AgentKey.generate(), AgentKey.generate()
        r = client.post("/ai-market/v2/mandates/owners", headers={"X-API-Key": api_key},
                        json=owner_link_payload(owner, hub_origin=HUB, account_id=account))
        assert r.status_code == 200, r.text
        doc = issue_mandate(owner, agent_key.did, audience=[HUB], scope=["demo.*"],
                            per_call_usd=0.01, per_day_usd=0.008)
        assert client.post("/ai-market/v2/mandates", json=doc).status_code == 200

        agent = AIMarketAgent(HUB, verify_receipts=False,
                              mandate=Mandate(document=doc, key=agent_key, hub_origin=HUB))
        agent.session = client   # TestClient is an httpx.Client: the SDK talks to the real app
        first = agent.invoke_single("demo-echo", "demo.echo@v1", {"text": "hi"})
        second = agent.invoke_single("demo-echo", "demo.echo@v1", {"text": "hi"})
        third = agent.invoke_single("demo-echo", "demo.echo@v1", {"text": "hi"})
        assert first["success"] and second["success"]
        assert third["error"] == "mandate_limit" and third["limit"] == "perDay"
        assert first["mandate"]["principal"] == owner.did
        assert balance(db, account) == pytest.approx(1.0 - 0.008)


def test_the_root_work_receipt_commits_to_its_subcontractors(monkeypatch, tmp_path):
    pytest.importorskip("aimarket_provenance")
    with hub(monkeypatch, tmp_path) as (client, db):
        providers = Providers(client.app_ref)
        import aimarket_hub.outbound_http as outbound

        monkeypatch.setattr(outbound, "safe_post", providers.post)
        list_static(db, capability_id="wx.read@v1", product_id="wx", price=0.001)
        list_provider(db, "brief.make@v1", "brief", 0.010, url="https://brief.test/invoke")
        child_digests: list[str] = []

        async def brief(body, headers, p):
            for _ in range(2):
                r = await p.buy(WEATHER, job_headers(headers))
                assert r.status_code == 200, r.text
                child_digests.append(r.json()["provenance_receipt"]["digest_sri"])
            return 200, {"result": {"brief": "ok"}}

        providers.add("https://brief.test/invoke", brief)
        _, api_key = funded_account(client, db, 1.0)
        r = client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key},
                        json={**BRIEF, "subcontract": {"allowance_usd": 0.005}})
        assert r.status_code == 200, r.text
        body = r.json()
        nodes = body["subcontracting"]["nodes"]
        assert sorted(n["receipt_digest"] for n in nodes) == sorted(child_digests)

        url = body["provenance_receipt"]["receipt_url"]
        document = client.get(url).json()
        document = document.get("receipt", document)
        parents = document["credentialSubject"]["parents"]
        assert sorted(p["digestSRI"] for p in parents) == sorted(child_digests)


def test_the_sdk_changes_owners_only_with_an_owners_signature(monkeypatch, tmp_path):
    from aimarket_agent import owner_unlink_payload

    with hub(monkeypatch, tmp_path) as (client, db):
        account, api_key = funded_account(client, db, 1.0)
        first, second = AgentKey.generate(), AgentKey.generate()
        headers = {"X-API-Key": api_key}
        assert client.post("/ai-market/v2/mandates/owners", headers=headers, json=owner_link_payload(
            first, hub_origin=HUB, account_id=account, require_mandate=True)).status_code == 200
        # a second DID with the key alone: refused; authorized by the first owner: linked
        assert client.post("/ai-market/v2/mandates/owners", headers=headers, json=owner_link_payload(
            second, hub_origin=HUB, account_id=account)).status_code == 403
        assert client.post("/ai-market/v2/mandates/owners", headers=headers, json=owner_link_payload(
            second, hub_origin=HUB, account_id=account, authorized_by=first)).status_code == 200
        r = client.post("/ai-market/v2/mandates/owners/unlink", headers=headers, json=owner_unlink_payload(
            second.did, hub_origin=HUB, account_id=account, authorized_by=first))
        assert r.status_code == 200 and r.json()["unlinked"] is True
