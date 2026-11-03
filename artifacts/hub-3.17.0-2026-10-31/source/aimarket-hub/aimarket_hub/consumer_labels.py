"""Who a live-feed consumer label is, for the PUBLIC feed: one implementation.

The /stats/live feed (api.py) and the server-rendered home page (terminal_ssr.py) both publish
recent invocations. They used to carry separate copies of these rules, and when the feed learned
`account:` / `mcp:` labels and AIMARKET_OPERATOR_ACCOUNTS, the home page kept publishing raw
account ids and counting the operator's own accounts as customers.

Which labels are the operator's own ecosystem (SELF) and which are everybody else (EXT) is
NOT decided here any more: that rule reads ecosystem.json and what the write site knew about
the caller, and lives in one place, aimarket_hub/ecosystem.py.
"""
from __future__ import annotations

import hashlib

OPERATOR_SELF = "operator_self"


def public_consumer_label(raw: str) -> str:
    """Pseudonymize a consumer label before it goes out on a public page.

    `channel:<id>` (a paid invoke) and `sandbox:<id>` (a trial) are credential-adjacent ids;
    `account:<id>` says which accounts exist; an `mcp:` suffix is whatever the caller's header
    said. Keep the prefix — paid vs trial vs anonymous is what the feed is for — and replace
    the id with a stable digest: the same grouping key across events, not a usable id.
    """
    for prefix in ("channel:", "sandbox:", "account:", "mcp:"):
        if raw.startswith(prefix):
            ident = raw[len(prefix):]
            if not ident:
                return raw
            return prefix + hashlib.sha256(ident.encode("utf-8")).hexdigest()[:12]
    return raw
