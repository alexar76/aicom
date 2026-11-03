"""Inside the new image, before it serves: the code imports, migration 018 is the last revision, demo closes
checkout whatever keys are set, the key rules hold, and change events carry an escaped chat line."""

from dataclasses import replace

import histor.__main__  # noqa: F401
import histor.app  # noqa: F401
from histor import watch_paid
from histor.config import load_settings
from histor.migrations import MIGRATIONS
from histor.security_events import _change_event

assert MIGRATIONS[-1][:2] == (18, "018_watch_subscriptions"), MIGRATIONS[-1][:2]
s = load_settings()
assert s.watch_demo and s.watch_price_cents == 2900 and s.watch_days == 30
plan = watch_paid.plan(replace(s, stripe_secret_key="rk_live_x", stripe_webhook_secret="whsec_x"))
assert plan["demo"] and not plan["card"]["enabled"] and plan["card"]["closedReason"].startswith("demo mode"), plan
open_ = replace(s, watch_demo=False, stripe_secret_key="rk_live_x", stripe_webhook_secret="whsec_x")
assert "live key" in watch_paid.closed_reason(open_)
assert watch_paid.closed_reason(replace(open_, profile="prod")) == ""
assert "test key" in watch_paid.closed_reason(replace(open_, profile="prod", stripe_secret_key="sk_test_x"))
row = {"id": 1, "target_id": "a" * 16, "name": "<!here>", "endpoint": "https://e.example/mcp", "observed_at": "2026-11-01T00:00:00Z",
       "label_id": None, "summary": {"added": [], "removed": [], "modified": [{"tool": "t"}], "newAddresses": []}}
assert "&lt;!here&gt;" in _change_event("https://histor.modelmarket.dev", row)[1]["text"]
print("smoke ok: imports, migration 018 last, demo closes checkout, key rules, escaped chat line")
