"""Candidate smoke for MTL/1.2: a disposable HISTOR (SQLite), labels and the server API over ASGI."""
import asyncio
import json

import httpx
from awr import SigningKey, verify_document


async def smoke():
    import histor
    assert histor.__file__.startswith("/app/histor/"), histor.__file__  # the overlay, as production imports it
    from histor.app import create_app
    from histor.config import load_settings
    from histor.crawler import PROFILE_REVISION as CRAWLER_REVISION
    from histor.labels import PROFILE_REVISION, LabelIssuer
    from histor.service import build
    from histor.subject import build_subject
    assert PROFILE_REVISION == CRAWLER_REVISION == "1.2.0"

    issuer = LabelIssuer(SigningKey.generate())
    ts = "2026-11-06T20:00:00Z"
    bad = build_subject(server_name="io.smoke/bad", registry="urn:awr:mtl:1:registry:smoke",
                        tools=[{"name": "p", "inputSchema": {"maximum": float("inf")}}],
                        transport="streamable-http", endpoint="https://bad.example/mcp")
    obs = issuer.observation(bad, observed_at=ts, issued_at=ts)
    body = obs["credentialSubject"]["mcpTrustLabel"]
    assert verify_document(obs)["valid"] and body["profileRevision"] == "1.2.0"
    assert body["toolSet"]["noDigest"] == {"reason": "not_digestible", "code": "MTL-NUM-001"}, body["toolSet"]
    failed = issuer.continuity(current=None, prior_label=obs, prior_subject_ref=bad.reference(), prior_tool_digest=None,
                               unchanged_since=None, observed_at=ts, issued_at=ts, failure={"status": "http-401"})
    assert failed["credentialSubject"]["mcpTrustLabel"]["noDigest"] == {"current": {"reason": "not_observed"}}

    services = build(load_settings())
    store = services.store
    states = store.package_states()
    assert isinstance(states, dict)
    with store.db.transaction() as tx:
        for tid, name, endpoint in (("t-bad", "io.smoke/bad", "https://bad.example/mcp"),
                                    ("t-down", "io.smoke/down", "https://down.example/mcp")):
            tx.execute("INSERT INTO targets(id, name, endpoint, transport, registry, title, description, version, "
                       "repository, website, first_listed, last_listed, delisted, skip_reason) "
                       "VALUES(?, ?, ?, 'streamable-http', 'urn:awr:mtl:1:registry:smoke', NULL, NULL, NULL, NULL, NULL, ?, ?, 0, NULL)",
                       (tid, name, endpoint, ts, ts))
        row = services.logbook.append(tx, obs, target_id="t-bad")
        tx.execute("UPDATE targets SET current_subject=?, current_toolset=NULL, chain_label=?, last_attempt=? WHERE id='t-bad'",
                   (bad.digest, row["id"], ts))
    services.logbook.publish_sth()  # a signed head, as production has, for /log/checkpoint
    transport = httpx.ASGITransport(app=create_app(services))
    async with httpx.AsyncClient(transport=transport, base_url="https://histor.modelmarket.dev") as c:
        listed = (await c.get("/api/v1/servers", params={"limit": 10})).json()["servers"]
        by = {s["name"]: s for s in listed}
        assert by["io.smoke/bad"]["noDigest"] == {"reason": "not_digestible"}, by["io.smoke/bad"]
        assert by["io.smoke/down"]["noDigest"] == {"reason": "not_observed"}, by["io.smoke/down"]
        page = (await c.get("/api/v1/servers/t-bad")).json()
        nd = page["server"]["noDigest"]
        assert nd == {"reason": "not_digestible", "code": "MTL-NUM-001", "profileRevision": "1.2.0",
                      "decidedAt": ts}, nd
        assert (await c.get("/health")).status_code == 200
        assert (await c.get("/log/checkpoint")).status_code == 200  # the tiles overlay is still there
        html = await c.get("/servers/t-bad")
        assert html.status_code in (200, 404), html.status_code
    print("mtl12 smoke ok")


asyncio.run(smoke())
