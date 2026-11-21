"""histor.changed_since@v1: what changed in an MCP server's tools since the set you approved.

Give the server (`endpoint`, `name` or `package`) and the set you approved: `approved_digest` (its
MTL/1 digest, sha256-…) or `approved_tools` (the tools/list array then; HISTOR computes the digest).
HISTOR, which reads public MCP servers every day, answers whether that set is still what the server
serves. When it is not, the agent lists every change HISTOR recorded since the server last served
your set — tools added, removed and modified, with the fields that moved — and what the tool list
now costs a model in tokens against what it cost then (o200k_base, as HISTOR counts it).

Verdicts: unchanged, changed, approved_set_never_observed (HISTOR never saw your set at this server:
it cannot say what changed since), not_recorded (HISTOR does not read this server, or has no digest).
HISTOR's own signed answer is returned as `histor_check` (verify it under HISTOR's did:key). Only
histor.modelmarket.dev is reached.
"""
# ruff: noqa: E501 — pinned witness keys and answer texts are kept whole

from urllib.parse import quote

HISTOR = "https://histor.modelmarket.dev"
MAX_LISTED = 20


def _get(path):
    reply = fetch(HISTOR + path, headers={"accept": "application/json"})  # noqa: F821 — the sandbox provides fetch()
    if reply.status == 404:
        return None
    if not reply.ok:
        raise RuntimeError("HISTOR answered " + str(reply.status) + " for " + path.split("?")[0])
    return reply.json()


def _selector(payload):
    for key in ("endpoint", "package", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            if len(value) > 500:
                raise ValueError(key + " is too long")
            return key, value.strip()
    raise ValueError(
        "name the server: endpoint (a URL), package (npm:… or pypi:…) or name (registry name)"
    )


def _check(payload):
    key, value = _selector(payload)
    tools, digest = payload.get("approved_tools"), payload.get("approved_digest")
    if isinstance(tools, list) and tools:
        reply = fetch(HISTOR + "/api/v1/check", method="POST", json={key: value, "tools": tools})  # noqa: F821
        if not reply.ok:
            raise RuntimeError("HISTOR's check answered " + str(reply.status))
        return reply.json()
    if not isinstance(digest, str) or not digest.startswith("sha256-") or len(digest) > 60:
        raise ValueError(
            "send approved_digest (the MTL/1 digest, sha256-…) or approved_tools (the tools/list array)"
        )
    return _get(
        "/api/v1/check?"
        + key
        + "="
        + quote(value, safe="")
        + "&toolSetDigest="
        + quote(digest, safe="")
    )


def _fields(modified):
    out = []
    for item in modified or []:
        if isinstance(item, dict):
            out.append(
                {"tool": item.get("tool"), "fields": sorted((item.get("fields") or {}).keys())}
            )
    return out


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError(
            "send an object: endpoint, package or name, and approved_digest or approved_tools"
        )
    check = _check(payload)
    if not check:
        raise RuntimeError("HISTOR gave no answer for that server")
    approved = (check.get("query") or {}).get("toolSetDigest") or payload.get("approved_digest")
    target = check.get("target") or {}
    observed = check.get("observed") or {}
    match = check.get("match")
    out = {
        "approved_digest": approved,
        "current_digest": observed.get("toolSetDigest"),
        "server": {k: target.get(k) for k in ("id", "name", "endpoint", "page")},
        "histor_match": match,
        "histor_note": check.get("note"),
        "last_observed": observed.get("lastObserved"),
        "histor_check": check,
    }
    if match == "same":
        out.update(
            verdict="unchanged",
            unchanged_since=observed.get("unchangedSince"),
            detail="the server still serves the set you approved, as of HISTOR's last read",
        )
        return out
    if match == "different":
        out.update(
            verdict="approved_set_never_observed",
            detail="HISTOR never saw the set you approved at this server, so it cannot say what "
            "changed since; the current set is current_digest",
        )
        return out
    if match != "previously-observed" or not target.get("id"):
        out.update(
            verdict="not_recorded",
            detail=check.get("note") or "HISTOR has no observation to compare",
        )
        return out
    # The compact change feed (the full server record can pass the 256 KiB a fetch may bring back).
    feed = _get("/api/v1/changes?watch=" + target["id"] + "&limit=50") or {}
    cost = _get("/api/v1/servers/" + target["id"] + "/cost?limit=50") or {}
    changes = feed.get("changes") or []  # newest first
    since = None
    for i, change in enumerate(changes):
        if change.get("from_toolset") == approved:
            since = i  # the newest move away from your set
            break
    window = changes if since is None else changes[: since + 1]
    costs = {c.get("id"): c for c in cost.get("changes") or []}
    listed = []
    added, removed, modified = set(), set(), set()
    for change in window[:MAX_LISTED]:
        summary = change.get("summary") if isinstance(change.get("summary"), dict) else {}
        moved = _fields(summary.get("modified"))
        added.update(summary.get("added") or [])
        removed.update(summary.get("removed") or [])
        modified.update(m["tool"] for m in moved if m["tool"])
        delta = ((costs.get(change.get("id")) or {}).get("totals") or {}).get("sent") or {}
        listed.append(
            {
                "observed_at": change.get("observed_at"),
                "added": summary.get("added") or [],
                "removed": summary.get("removed") or [],
                "modified": moved,
                "tokens_delta": delta.get("delta"),
                "from": change.get("from_toolset"),
                "to": change.get("to_toolset"),
            }
        )
    first = costs.get(window[-1].get("id")) if since is not None and window else None
    then = (((first or {}).get("totals") or {}).get("sent") or {}).get("before")
    now = ((cost.get("current") or {}).get("totals") or {}).get("sent")
    out.update(
        verdict="changed",
        changed_at=window[-1].get("observed_at") if since is not None and window else None,
        seen_before=check.get("seenBefore"),
        changes_since=len(window) if since is not None else None,
        changes=listed,
        complete=since is not None and len(window) <= MAX_LISTED,
        tools={
            "added": sorted(added - removed),
            "removed": sorted(removed - added),
            "modified": sorted(modified),
        },
        tokens={
            "approved": then,
            "now": now,
            "delta": (now - then) if isinstance(now, int) and isinstance(then, int) else None,
            "tokenizer": (cost.get("current") or {}).get("tokenizer"),
        },
        scope="what HISTOR recorded between its daily reads; a server can serve other definitions to "
        "another client or between reads",
    )
    if since is None:
        out["detail"] = (
            "your set's last change is older than the " + str(len(changes)) + " changes HISTOR "
            "lists for this server: the newest ones are shown, the full history is at the page"
        )
    return out
