"""mcp.money_tools.changes@v1: which public MCP servers changed tools that move value or hold keys.

HISTOR reads public MCP servers every day and records every change of their tool lists, about 6,000 a
day. Its money-tool feed (histor/money_changes.py, rules money-tools/v1) keeps the few that matter to
an agent that can pay: a server added a tool that sends, swaps or withdraws; a value-moving tool
changed its description or schema; a tool's description gained a wallet address or replaced one; a
description began to mention private keys or seed phrases. This agent reads that feed (one request
to histor.modelmarket.dev) and answers a question about it:

  - `since`: an ISO time (2026-11-22T00:00:00Z) or a change id; only later changes. A poller passes
    the `cursor` of its last answer as `since` and so sees each change once.
  - `min_severity`: low (default), medium or high. High: an address added or replaced, a key tool added.
  - `server`: part of a server's name, endpoint or website, e.g. "swaptitan" or "onv.codes".
  - `flags`: only changes with one of these flags (address_added, address_replaced, added_moves_value,
    added_creates_or_imports_wallet, added_handles_keys, modified_moves_value, mentions_keys, …).
  - `limit`: 1 to 100 (default 25), newest first.

Each item names the server and its HISTOR page, the tools and what changed. A flag says what changed,
not that the server is malicious. The answer carries the feed's time, cursor and SHA-256, so it can be
matched to the feed it was read from. The feed covers the last seven days and is rebuilt every hour.
"""
# ruff: noqa: E501 — the answer texts are kept whole

import hashlib
import json

FEED = "https://histor.modelmarket.dev/datasets/feeds/money-tool-changes.json"
SCHEMA = "histor.money-tool-changes/v1"
LEVELS = {"low": 1, "medium": 2, "high": 3}
MAX_LIMIT = 100


def _since(value):
    if value is None:
        return None, None
    if isinstance(value, bool):
        raise ValueError("since is an ISO time (2026-11-22T00:00:00Z) or a change id")
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        return int(value), None
    text = str(value).strip()
    if len(text) == 20 and text[4] == "-" and text[10] == "T" and text.endswith("Z"):
        return None, text
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return None, text + "T00:00:00Z"
    raise ValueError(
        "since is an ISO time in UTC (2026-11-22T00:00:00Z or 2026-11-22) or a change id"
    )


def _strings(payload, key, limit):
    value = payload.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(
        isinstance(v, str) and 0 < len(v) <= limit for v in value
    ):
        raise ValueError(key + " must be a string or a list of strings")
    return [v.strip().lower() for v in value][:20]


def handle(payload):
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("send an object: since, min_severity, server, flags, limit (all optional)")
    since_id, since_at = _since(payload.get("since"))
    level = str(payload.get("min_severity") or "low").lower()
    if level not in LEVELS:
        raise ValueError("min_severity is low, medium or high")
    servers = _strings(payload, "server", 200)
    flags = set(_strings(payload, "flags", 60))
    limit = payload.get("limit", 25)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("limit must be a whole number from 1 to 100")

    reply = fetch(FEED, headers={"accept": "application/json"})  # noqa: F821 — the sandbox provides fetch()
    if not reply.ok:
        raise RuntimeError("HISTOR's money-tool feed answered " + str(reply.status))
    raw = reply.text
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise RuntimeError("the feed is not " + SCHEMA)

    picked = []
    for item in doc.get("items") or []:
        if not isinstance(item, dict):
            continue
        if since_id is not None and int(item.get("change_id") or 0) <= since_id:
            continue
        if since_at is not None and str(item.get("observed_at") or "") <= since_at:
            continue
        if LEVELS.get(item.get("severity"), 0) < LEVELS[level]:
            continue
        if flags and not flags & set(item.get("flags") or []):
            continue
        if servers:
            where = " ".join(
                str(item.get(k) or "") for k in ("name", "endpoint", "website")
            ).lower()
            if not any(s in where for s in servers):
                continue
        picked.append(item)
    picked.sort(key=lambda i: -int(i.get("change_id") or 0))
    counts = {
        k: sum(1 for i in picked if i.get("severity") == k) for k in ("high", "medium", "low")
    }
    return {
        "matched": len(picked),
        "counts": counts,
        "items": picked[:limit],
        "truncated": len(picked) > limit,
        "cursor": doc.get("cursor"),
        "feed": {
            "url": FEED,
            "generated_at": doc.get("generated_at"),
            "window_days": doc.get("window_days"),
            "rules": doc.get("rules"),
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        },
        "note": "A flag says what changed in a tool list, not that the server is malicious. "
        "Open the page for the full change in HISTOR's log.",
    }
