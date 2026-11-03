"""Inside the new image, before it serves: the mcp.json card path and its endpoint shapes, migration 021 last,
402 answers classified without paying, the day-long back-off, /check's note, and the page strings."""

import inspect
from pathlib import Path

import httpx

import histor.__main__  # noqa: F401
import histor.app  # noqa: F401
from histor import cards, check, remote_schedule
from histor.mcpclient import PAY_PER_CRAWL, PAYMENT_REQUIRED, USER_AGENT, McpReader
from histor.migrations import MIGRATIONS

assert MIGRATIONS[-1][:2] == (21, "021_card_path_mcp_json"), MIGRATIONS[-1][:2]
assert cards.candidates("https://h.example/mcp")[-1] == "https://h.example/.well-known/mcp.json"
tools = [{"name": "t", "description": "x", "inputSchema": {"type": "object"}}]
v = cards.judge("https://h.example/mcp", {"https://h.example/.well-known/mcp.json":
                                          cards.Read("ok", doc={"mcpUrl": "https://h.example/mcp", "tools": tools})}, 3)
assert v.status == cards.DECLARED, v

seen = []
def site(request):
    seen.append(request.headers)
    return httpx.Response(402, json={"error": "Pay per crawl. $0.01 a page.", "price": "USD 0.01"})
obs = McpReader(timeout=5, allow_private=True, transport=httpx.MockTransport(site)).list_tools("https://127.0.0.1/mcp")
assert obs.status == PAY_PER_CRAWL and "USD 0.01" in obs.detail and len(seen) == 1
assert seen[0]["user-agent"] == USER_AGENT and "crawler" in USER_AGENT and "x-payment" not in seen[0]
obs = McpReader(timeout=5, allow_private=True, transport=httpx.MockTransport(
    lambda r: httpx.Response(402, json={"x402Version": 1, "accepts": []}))).list_tools("https://127.0.0.1/mcp")
assert obs.status == PAYMENT_REQUIRED
assert '"pay-per-crawl", "payment-required"' in inspect.getsource(remote_schedule.RemoteSchedule.record)
assert "charges crawlers for each read" in check.NOTE_PAYCRAWL_SINCE

landing = Path("/app/docs/landing")
assert 'id="checks"' in (landing / "index.html").read_text()
for lang in ("ru", "es", "fr", "zh"):
    text = (landing / "assets/i18n" / f"{lang}.js").read_text()
    assert "chk2p:" in text and "js_paycrawl_note:" in text, lang
assert "pay-per-crawl" in (landing / "assets/desk.js").read_text()
print("smoke ok: migration 021 last, mcp.json cards, 402 reasons without paying, back-off, notes, page strings")
