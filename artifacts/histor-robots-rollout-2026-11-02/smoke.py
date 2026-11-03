"""Inside the new image, before it serves: robots.txt support imports and decides, nothing reaches the network,
migration 019 is last, the crawler's reader carries the policy, and the check note names robots.txt."""

import histor.__main__  # noqa: F401
import histor.app  # noqa: F401
from histor import check
from histor.mcpclient import McpReader
from histor.migrations import MIGRATIONS
from histor.robots import OK, Fetched, Policy, decide_path

assert MIGRATIONS[-1][:2] == (19, "019_robots_txt"), MIGRATIONS[-1][:2]
assert decide_path("User-agent: *\nAllow: /\nDisallow: /api/\n", "https://h/api/mcp")[0] is False
assert decide_path("User-agent: *\nDisallow: /\nUser-agent: histor\nAllow: /mcp\n", "https://h/mcp")[0] is True
policy = Policy(fetch=lambda origin: Fetched(OK, 200, "User-agent: *\nDisallow: /mcp\n"))
decision = policy.decide("https://93.184.216.34/mcp")
assert not decision.allowed and decision.status == "robots-disallowed" and "User-agent: histor" in decision.detail
assert "robots" in McpReader.__init__.__code__.co_varnames
assert "robots.txt does not allow HISTOR" in check.NOTE_ROBOTS_SINCE
print("smoke ok: migration 019 last, RFC 9309 decisions, reader takes the policy, check note")
