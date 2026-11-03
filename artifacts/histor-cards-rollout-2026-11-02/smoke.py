"""Inside the new image, before it serves: server-card support imports and judges, migration 020 is last, the
crawler has the card pass, registry syncs leave card sets alone, and the API and /check know the card."""

import inspect

import histor.__main__  # noqa: F401
import histor.app  # noqa: F401
from histor import cards
from histor.crawler import Crawler
from histor.migrations import MIGRATIONS
from histor.store import Store

assert MIGRATIONS[-1][:2] == (20, "020_server_cards"), MIGRATIONS[-1][:2]
tools = [{"name": "t", "description": "x", "inputSchema": {"type": "object"}}]
v = cards.judge("https://h.example/mcp", {"https://h.example/mcp/server-card": cards.Read("ok", doc={"tools": tools})}, 2)
assert v.status == cards.DECLARED and v.tools == tools
assert cards.judge("https://h.example/mcp", {"https://h.example/.well-known/mcp/server-card.json":
                                              cards.Read("ok", doc={"tools": tools})}, 2).status == cards.AMBIGUOUS
assert hasattr(Crawler, "refresh_cards") and hasattr(Store, "apply_cards") and hasattr(Store, "server_card")
assert 'src != "card"' in inspect.getsource(Store._apply_declaration)
assert "serverCard" in inspect.getsource(histor.app)
print("smoke ok: migration 020 last, card judging, card pass, syncs leave card sets alone, API field")
