"""Runs inside the new image with no network: the gateway imports, says 1.3.0, and a direct tool's definition
does not move with the price or the trial size."""
import os, re
for name in [n for n in os.environ if n.startswith("AIMARKET_")]:
    del os.environ[name]
from aimarket_hub import mcp_gateway as g
assert g.SERVER_VERSION == "1.3.0", g.SERVER_VERSION
class Cap:
    def __init__(self, price): self.price_per_call_usd = price
checks = 0
for spec in g.DIRECT_TOOLS:
    a = g._direct_tool_definition(spec, Cap(0.001))
    os.environ["AIMARKET_SANDBOX_MAX_PER_VISITOR"] = "9"
    b = g._direct_tool_definition(spec, Cap(0.05))
    del os.environ["AIMARKET_SANDBOX_MAX_PER_VISITOR"]
    assert a == b, spec["name"]
    assert "$" not in a["description"] and "market_search shows the current price" in a["description"], a["description"]
    assert not re.search(r"first \d+ priced", a["description"]), a["description"]
    assert g._direct_tool_definition(spec, Cap(0))["description"].endswith(" Free."), spec["name"]
    checks += 4
import aimarket_hub.api  # noqa: F401  the app module still imports with the new gateway
print(f"mcp description smoke ok: {checks + 2} checks over {len(g.DIRECT_TOOLS)} direct tools")
