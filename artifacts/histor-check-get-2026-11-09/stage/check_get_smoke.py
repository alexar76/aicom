"""Candidate smoke for GET /check (aicom 16fcc741c): a disposable HISTOR (SQLite) over ASGI, no network."""
import asyncio

import httpx


async def smoke():
    import os

    import histor
    if not os.environ.get("SMOKE_LOCAL"):  # SMOKE_LOCAL=1 runs it against a checkout to test the smoke itself
        assert histor.__file__.startswith("/app/histor/"), histor.__file__  # the overlay, as production imports it
    from histor.app import create_app
    from histor.check import CHECK_TYPE
    from histor.config import load_settings
    from histor.logbook import verify_document
    from histor.service import build

    services = build(load_settings())
    did = services.key.did
    store = services.store
    transport = httpx.ASGITransport(app=create_app(services))
    async with httpx.AsyncClient(transport=transport, base_url="https://histor.modelmarket.dev") as c:
        for params in ({"url": "https://mcp.smoke-linked.dev/mcp"}, {"endpoint": "https://mcp.smoke-linked.dev/mcp"}):
            r = await c.get("/api/v1/check", params=params)
            assert r.status_code == 200, (r.status_code, r.text[:300])
            answer = r.json()
            assert answer["type"] == CHECK_TYPE and answer["match"] == "not-listed", answer
            assert answer["query"] == {"endpoint": "https://mcp.smoke-linked.dev/mcp"}, answer["query"]
            assert verify_document(answer, did, CHECK_TYPE), "GET answer is not signed by the log key"
            assert r.headers["cache-control"] == "no-store"
        assert store.unlisted_queries("2000-01-01") == [], "a GET wrote an unlisted host"

        r = await c.get("/api/v1/check", headers={"accept": "text/html"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/check", (r.status_code, r.headers)
        r = await c.get("/api/v1/check")
        assert r.status_code == 400 and "for example" in r.json()["detail"], r.text[:300]

        r = await c.post("/api/v1/check", json={"url": "https://mcp.smoke-linked.dev/mcp"})
        assert r.status_code == 200 and r.json()["query"] == {"endpoint": "https://mcp.smoke-linked.dev/mcp"}, r.text[:300]
        assert [h["host"] for h in store.unlisted_queries("2000-01-01")] == ["mcp.smoke-linked.dev"]

        assert "GET" in (await c.options("/api/v1/check")).headers["access-control-allow-methods"]
        assert (await c.get("/health")).status_code == 200
        assert (await c.get("/api/v1/stats")).status_code == 200  # an empty log has no head, so no /log/checkpoint
        page = await c.get("/check")
        assert page.status_code == 200 and "api/v1/check?endpoint=" in page.text, page.status_code
    print("check-get smoke ok")


asyncio.run(smoke())
