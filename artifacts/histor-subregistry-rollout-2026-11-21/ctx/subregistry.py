"""A subregistry: MCP registry entries served in the registry's own v0.1 API, with what HISTOR observed.

The MCP documentation (registry/registry-aggregators, "Acting as a Subregistry") describes it: an
aggregator that implements the registry's OpenAPI and adds its own data under a namespaced ``_meta``
key, so that a host application reads server metadata through one interface. A host that takes a
registry address (GitHub Copilot's organisation registry, for one) asks for three routes:

* ``GET /v0.1/servers`` — a page of entries (``cursor``, ``limit``, ``search``, ``updated_since``,
  ``version``, ``include_deleted``);
* ``GET /v0.1/servers/{serverName}/versions`` — the versions kept of one server, newest first;
* ``GET /v0.1/servers/{serverName}/versions/{version}`` — one entry, ``latest`` for the newest.

What is served is the upstream entry as it was read (``server`` unchanged, ``_meta`` as upstream sent
it) plus ``_meta["dev.modelmarket.histor/observed"]`` on the latest version of a server HISTOR lists:
per remote or package, the last read, the tool-set digest, since when it has not changed, and how
many times it did.

Entries are copied, never proxied: the upstream registry asks aggregators to keep their own copy and
gives no uptime promise. The copy holds the latest version of every server and each newer version as
it appears; a version superseded before the first sync is not in it. ``sync`` follows the documented
routine: one walk of ``version=latest``, then ``updated_since`` from a checkpoint that moves only
after every page was applied, with an overlap, and upserts by name and version.

With an allow list (``HISTOR_SUBREGISTRY_ALLOW``: one server name or ``namespace/*`` per line) the
copy holds only those servers: the list an organisation lets its hosts use. The upstream can be the
official registry or another subregistry, whose ``_meta`` is kept, so a private copy that observes
nothing itself still carries the public log's observations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
from fastapi import Request
from fastapi.responses import Response

from histor.mcpclient import USER_AGENT
from histor.registry import _get_page
from histor.subject import REGISTRY_OFFICIAL

log = logging.getLogger("histor.subregistry")

OFFICIAL_KEY = "io.modelcontextprotocol.registry/official"
OBSERVED_KEY = "dev.modelmarket.histor/observed"
OBSERVED_TYPE = "histor.observed/v1"

CHECKPOINT_META = "subregistry_checkpoint"      # start of the last sync whose every page was applied
FULL_META = "subregistry_full_at"               # start of the last full walk
ALLOW_META = "subregistry_allow_hash"           # the allow list the copy was built for
LAST_META = "subregistry_last_sync"             # what the last sync did, as JSON

PAGE = 100                  # the upstream's maximum page
DEFAULT_LIMIT = 30
MAX_LIMIT = 100
MAX_ENTRY_BYTES = 64 * 1024  # one entry with its _meta; the largest upstream entry seen is a few KB
MAX_PAGES = 100_000
OVERLAP_S = 600
# A full walk that returns far fewer servers than the copy holds is an upstream outage or a data reset
# (the registry is in preview and says so), not thousands of removals: nothing is marked deleted then.
SHRINK_GUARD = 0.5

# server.schema.json: reverse-DNS namespace, a slash, the server's name; 3 to 200 characters.
NAME_RE = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
_FRACTION = re.compile(r"(\.\d{1,6})\d*")
STATUSES = ("active", "deprecated", "deleted")

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
}


class BadRequest(ValueError):
    """A parameter the route cannot read; the message is safe to return."""


def valid_name(name: Any) -> bool:
    return isinstance(name, str) and 3 <= len(name) <= 200 and bool(NAME_RE.match(name))


def valid_version(version: Any) -> bool:
    return isinstance(version, str) and 0 < len(version) <= 255 and version.isprintable() and "/" not in version


def time_key(value: Any) -> str | None:
    """An RFC 3339 time as fixed-width UTC text, so text order is time order.

    The upstream writes microseconds ("…20.852269Z"); another registry may write none or nine digits.
    Compared as they come, "…20.8Z" sorts before "…20Z".
    """
    if not isinstance(value, str) or not 10 <= len(value) <= 64:
        return None
    text = _FRACTION.sub(r"\1", value.strip())
    if text[-1:] in "zZ":
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _now_key(clock: Callable[[], datetime]) -> str:
    return clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# -- the allow list --------------------------------------------------------------------------


@dataclass(frozen=True)
class Allow:
    names: frozenset[str]
    namespaces: tuple[str, ...]   # "io.github.acme/" for a line "io.github.acme/*"
    digest: str

    def matches(self, name: str) -> bool:
        return name in self.names or name.startswith(self.namespaces)

    @property
    def size(self) -> int:
        return len(self.names) + len(self.namespaces)


def parse_allow(text: str) -> Allow:
    names: set[str] = set()
    namespaces: set[str] = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.endswith("/*") and valid_name(line[:-1] + "x"):
            namespaces.add(line[:-1])
        elif valid_name(line):
            names.add(line)
        else:
            raise RuntimeError(f"allow list line {number}: not a server name or a namespace/* ({line[:80]!r})")
    if not names and not namespaces:
        raise RuntimeError("the allow list names no server; an empty registry is not what an empty file should mean")
    body = "\n".join(sorted(names) + sorted(n + "*" for n in namespaces))
    return Allow(frozenset(names), tuple(sorted(namespaces)), hashlib.sha256(body.encode()).hexdigest())


def load_allow(path: Path | None) -> Allow | None:
    if path is None:
        return None
    return parse_allow(path.read_text(encoding="utf-8"))


# -- reading the upstream ----------------------------------------------------------------------


def _record(item: Any) -> tuple[str, str, dict[str, Any], dict[str, Any]] | None:
    """(name, version, server, _meta) of one upstream record, or None when it is not an entry."""
    if not isinstance(item, dict):
        return None
    server, meta = item.get("server"), item.get("_meta")
    if not isinstance(server, dict):
        return None
    name, version = server.get("name"), server.get("version")
    if not valid_name(name) or not valid_version(version):
        return None
    return name, version, server, meta if isinstance(meta, dict) else {}


def _walk(client: httpx.Client, upstream: str, params: dict[str, Any], *, pause_s: float,
          retry_delay: float) -> Iterator[list[Any]]:
    """Pages of ``GET /v0.1/servers`` with the same filters kept on every cursor."""
    cursor: str | None = None
    seen: set[str] = set()
    for _ in range(MAX_PAGES):
        query = dict(params, limit=PAGE)
        if cursor:
            query["cursor"] = cursor
        page = _get_page(client, f"{upstream}/v0.1/servers", query, delay=retry_delay)
        servers = page.get("servers") if isinstance(page, dict) else None
        yield servers if isinstance(servers, list) else []
        nxt = (page.get("metadata") or {}).get("nextCursor") if isinstance(page, dict) else None
        if not nxt:
            return
        if not isinstance(nxt, str) or nxt in seen or nxt == cursor:
            raise RuntimeError("the upstream's pagination cursor did not advance (a cursor repeated)")
        seen.add(nxt)
        cursor = nxt
        time.sleep(pause_s)
    raise RuntimeError(f"the upstream's pagination did not end within {MAX_PAGES} pages")


def _store_page(tx: Any, records: list[Any], *, allow: Allow | None, seen_at: str, stats: dict[str, int]) -> None:
    for item in records:
        stats["read"] += 1
        record = _record(item)
        if record is None:
            stats["skipped"] += 1
            continue
        name, version, server, meta = record
        if allow is not None and not allow.matches(name):
            stats["filtered"] += 1
            continue
        official = meta.get(OFFICIAL_KEY) if isinstance(meta.get(OFFICIAL_KEY), dict) else {}
        status = official.get("status") if official.get("status") in STATUSES else "active"
        updated = time_key(official.get("updatedAt")) or seen_at
        published = time_key(official.get("publishedAt")) or updated
        try:
            # ASCII with escapes: an entry may carry a lone surrogate or a NUL, which neither UTF-8 nor a
            # Postgres text column takes as a character; as "\ud800" they are stored and served as sent.
            body = json.dumps(server, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            meta_text = json.dumps(meta, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        except (ValueError, RecursionError):
            stats["skipped"] += 1   # NaN or Infinity: not JSON, so not something to serve
            continue
        if len(body) + len(meta_text) > MAX_ENTRY_BYTES:
            stats["skipped"] += 1
            continue
        latest = 1 if official.get("isLatest") is True else 0
        tx.execute(
            "INSERT INTO registry_entries(name, version, body, meta, status, is_latest, published_key, updated_key, seen_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name, version) DO UPDATE SET body=excluded.body, "
            "meta=excluded.meta, status=excluded.status, is_latest=excluded.is_latest, "
            "published_key=excluded.published_key, updated_key=excluded.updated_key, seen_at=excluded.seen_at",
            (name, version, body, meta_text, status, latest, published, updated, seen_at),
        )
        if latest:
            # The upstream says so on the new version only; the one it supersedes is not sent again.
            tx.execute("UPDATE registry_entries SET is_latest=0 WHERE name=? AND version<>? AND is_latest=1", (name, version))
        stats["stored"] += 1


def sync(store: Any, upstream: str, *, allow: Allow | None = None, full: bool = False, full_every_s: int = 604800,
         transport: httpx.BaseTransport | None = None, timeout: float = 60.0, pause_s: float = 0.15,
         retry_delay: float = 2.0, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> dict[str, Any]:
    """Bring the copy up to date with ``upstream`` and say what was done.

    A full walk (the first sync, one a week after it, a changed allow list, or ``full=True``) reads the
    latest version of every server; the others read what changed since the checkpoint. With an allow
    list every sync asks for the listed servers only, one search each. Nothing here is atomic across
    pages and it need not be: a page applied twice is the same rows, and the checkpoint moves last.
    """
    upstream = upstream.rstrip("/")
    started = _now_key(clock)
    checkpoint = store.get_meta(CHECKPOINT_META)
    full_at = store.get_meta(FULL_META)
    allow_hash = allow.digest if allow else ""
    if store.get_meta(ALLOW_META) != allow_hash and (checkpoint or allow_hash):
        full = True   # another list: what the old one left out was never read
    if not checkpoint or not full_at:
        full = True
    elif full_every_s and started >= _shift(full_at, full_every_s):
        full = True
    stats = {"pages": 0, "read": 0, "stored": 0, "skipped": 0, "filtered": 0, "gone": 0}
    mode = "full" if full else "incremental"
    with httpx.Client(timeout=timeout, transport=transport,
                      headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
        if allow is not None:
            mode = "allow-list"
            searches = sorted(allow.names) + list(allow.namespaces)
            walks = [{"version": "latest", "search": term, "include_deleted": "true"} for term in searches]
        elif full:
            walks = [{"version": "latest"}]
        else:
            since = _shift(checkpoint, -OVERLAP_S)
            walks = [{"version": "latest", "updated_since": since[:19] + "Z"}]
        for params in walks:
            for records in _walk(client, upstream, params, pause_s=pause_s, retry_delay=retry_delay):
                stats["pages"] += 1
                with store.db.transaction() as tx:
                    _store_page(tx, records, allow=allow, seen_at=started, stats=stats)
    with store.db.transaction() as tx:
        if allow is not None:
            stats["gone"] = _drop_unlisted(tx, allow)
        if full or allow is not None:
            stats["gone"] += _mark_unseen(tx, started, guard=allow is None)
            store.set_meta(tx, FULL_META, started)
        store.set_meta(tx, CHECKPOINT_META, started)
        store.set_meta(tx, ALLOW_META, allow_hash)
        result = {"at": started[:19] + "Z", "mode": mode, "upstream": upstream, **stats}
        store.set_meta(tx, LAST_META, json.dumps(result))
    return result


def _shift(key: str, seconds: int) -> str:
    moved = datetime.strptime(key, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC) + timedelta(seconds=seconds)
    return moved.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _drop_unlisted(tx: Any, allow: Allow) -> int:
    gone = [r["name"] for r in tx.execute("SELECT DISTINCT name FROM registry_entries") if not allow.matches(r["name"])]
    for name in gone:
        tx.execute("DELETE FROM registry_entries WHERE name=?", (name,))
    return len(gone)


def _mark_unseen(tx: Any, started: str, *, guard: bool) -> int:
    """After a walk of every latest version: a latest entry it did not return is gone from the upstream's
    default list, which is how the upstream shows a deleted server (its moderation removes spam and
    malware that way). It is kept, marked deleted, and left out of a list unless deleted ones are asked for."""
    held = tx.one("SELECT COUNT(*) AS n FROM registry_entries WHERE is_latest=1 AND status<>'deleted'") or {}
    unseen = tx.one("SELECT COUNT(*) AS n FROM registry_entries WHERE is_latest=1 AND status<>'deleted' AND seen_at<?",
                    (started,)) or {}
    total, missing = int(held.get("n") or 0), int(unseen.get("n") or 0)
    if not missing:
        return 0
    if guard and total and (total - missing) < total * SHRINK_GUARD:
        log.warning("subregistry: the walk returned %d of %d servers; nothing marked deleted", total - missing, total)
        return 0
    tx.execute("UPDATE registry_entries SET status='deleted', updated_key=? WHERE is_latest=1 AND status<>'deleted' AND seen_at<?",
               (started, started))
    return missing


# -- serving -----------------------------------------------------------------------------------


def _observed(targets: list[dict[str, Any]], public_base: str) -> dict[str, Any] | None:
    rows = [t for t in targets if not t["delisted"]]
    if not rows:
        return None
    return {
        "type": OBSERVED_TYPE,
        "log": public_base,
        "targets": [{
            "id": t["id"], "endpoint": t["endpoint"], "page": f"{public_base}/s/{t['id']}",
            "notAttempted": t["skip_reason"], "lastStatus": t["last_status"], "lastObserved": t["last_ok"],
            "toolCount": t["current_count"], "toolSetDigest": t["current_toolset"],
            "toolExtrasDigest": t.get("current_extras"), "firstPinned": t["first_pinned"],
            "unchangedSince": t["unchanged_since"], "changes": t["changes"],
        } for t in rows],
    }


def _shape(rows: list[dict[str, Any]], store: Any, public_base: str) -> list[dict[str, Any]]:
    """Stored rows as ServerResponse objects. One query for the targets of every latest entry on the page."""
    names = sorted({r["name"] for r in rows if r["is_latest"]})
    by_name: dict[str, list[dict[str, Any]]] = {}
    if names:
        marks = ",".join("?" for _ in names)
        with store.db.read() as tx:
            for t in tx.execute(f"SELECT * FROM targets WHERE registry=? AND name IN ({marks}) ORDER BY name, endpoint",  # noqa: S608 - only "?" marks are formatted in
                                (REGISTRY_OFFICIAL, *names)):
                by_name.setdefault(t["name"], []).append(t)
    out = []
    for r in rows:
        meta = json.loads(r["meta"])
        official = dict(meta.get(OFFICIAL_KEY) or {})
        # The copy knows two things the stored block may not: a version superseded since it was read,
        # and a server the upstream stopped listing.
        official["isLatest"] = bool(r["is_latest"])
        official["status"] = r["status"]
        meta[OFFICIAL_KEY] = official
        observed = _observed(by_name.get(r["name"], []), public_base) if r["is_latest"] else None
        if observed is not None:
            meta[OBSERVED_KEY] = observed
        elif not r["is_latest"]:
            meta.pop(OBSERVED_KEY, None)   # an upstream's observation is of the latest version too
        out.append({"server": json.loads(r["body"]), "_meta": meta})
    return out


_COLUMNS = "name, version, body, meta, status, is_latest"


def list_page(store: Any, public_base: str, *, cursor: str | None = None, limit: int | None = None,
              search: str | None = None, updated_since: str | None = None, version: str | None = None,
              include_deleted: bool = False) -> dict[str, Any]:
    where: list[str] = []
    args: list[Any] = []
    if cursor:
        name, colon, after = cursor.partition(":")
        if not colon or not valid_name(name) or not valid_version(after):
            raise BadRequest("cursor: use the nextCursor value of the previous page")
        where.append("(name > ? OR (name = ? AND version > ?))")
        args += [name, name, after]
    if search:
        needle = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("LOWER(name) LIKE ? ESCAPE '\\'")
        args.append(f"%{needle}%")
    if updated_since:
        key = time_key(updated_since)
        if key is None:
            raise BadRequest("updated_since: an RFC 3339 date-time with a zone, for example 2026-11-01T00:00:00Z")
        where.append("updated_key >= ?")
        args.append(key)
        include_deleted = True   # as upstream: a client that syncs must hear about removals
    if version == "latest":
        where.append("is_latest = 1")
    elif version:
        if not valid_version(version):
            raise BadRequest("version: 'latest' or an exact version")
        where.append("version = ?")
        args.append(version)
    if not include_deleted:
        where.append("status <> 'deleted'")
    size = DEFAULT_LIMIT if limit is None else limit
    if not 1 <= size <= MAX_LIMIT:
        raise BadRequest(f"limit: 1 to {MAX_LIMIT}")
    sql = f"SELECT {_COLUMNS} FROM registry_entries"  # noqa: S608 - the conditions are fixed text, values are bound
    if where:
        sql += " WHERE " + " AND ".join(where)
    with store.db.read() as tx:
        rows = tx.execute(sql + " ORDER BY name, version LIMIT ?", (*args, size + 1))
    more = len(rows) > size
    rows = rows[:size]
    metadata: dict[str, Any] = {"count": len(rows)}
    if more:
        metadata["nextCursor"] = f"{rows[-1]['name']}:{rows[-1]['version']}"
    return {"servers": _shape(rows, store, public_base), "metadata": metadata}


def versions(store: Any, public_base: str, name: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    sql = f"SELECT {_COLUMNS} FROM registry_entries WHERE name=?"  # noqa: S608 - fixed text
    if not include_deleted:
        sql += " AND status <> 'deleted'"
    with store.db.read() as tx:
        rows = tx.execute(sql + " ORDER BY published_key DESC, version DESC", (name,))
    if not rows:
        return None
    return {"servers": _shape(rows, store, public_base), "metadata": {"count": len(rows)}}


def one(store: Any, public_base: str, name: str, version: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
    sql = f"SELECT {_COLUMNS} FROM registry_entries WHERE name=?"  # noqa: S608 - fixed text
    args: list[Any] = [name]
    if version == "latest":
        sql += " AND is_latest=1"
    else:
        sql += " AND version=?"
        args.append(version)
    if not include_deleted:
        sql += " AND status <> 'deleted'"
    with store.db.read() as tx:
        row = tx.one(sql, args)
    return _shape([row], store, public_base)[0] if row else None


def status(store: Any, *, upstream: str, allow: Allow | None, public_base: str) -> dict[str, Any]:
    with store.db.read() as tx:
        counts = tx.one("SELECT COUNT(*) AS entries, COALESCE(SUM(CASE WHEN is_latest=1 AND status<>'deleted' THEN 1 ELSE 0 END), 0) "
                        "AS servers FROM registry_entries") or {}
    last = store.get_meta(LAST_META)
    return {
        "type": "histor.subregistry/v1", "registry": public_base, "api": "v0.1", "upstream": upstream,
        "servers": int(counts.get("servers") or 0), "entries": int(counts.get("entries") or 0),
        "allowList": allow.size if allow else None, "observedKey": OBSERVED_KEY,
        "lastSync": json.loads(last) if last else None,
    }


def parse_path(raw_path: bytes | str, prefix: str = "/v0.1/servers/") -> tuple[str, str | None] | None:
    """(server name, version or None) from the undecoded request path, or None when it is neither route.

    A server name holds a slash and the specification wants it sent as ``%2F``; a decoded path cannot
    tell that slash from a separator, so the raw path is split first and each part decoded after. A
    client that sends the slash as it is gets the same answer.
    """
    text = (raw_path.decode("ascii", "replace") if isinstance(raw_path, bytes) else raw_path).split("?", 1)[0]
    if not text.startswith(prefix):
        return None
    parts = text[len(prefix):].split("/")
    candidates: list[tuple[list[str], str | None]] = []
    if len(parts) >= 3 and parts[-2] == "versions":
        candidates.append((parts[:-2], unquote(parts[-1])))
    if len(parts) >= 2 and parts[-1] == "versions":
        candidates.append((parts[:-1], None))
    for name_parts, version in candidates:
        name = unquote("/".join(name_parts))
        if valid_name(name) and (version is None or valid_version(version)):
            return name, version
    return None


def mount(app: Any, services: Any, *, allowed: Callable[[Any], bool]) -> None:
    """Add the routes to ``app``. ``allowed(request)`` is the instance's rate limit for this surface."""
    settings, store = services.settings, services.store
    upstream = settings.subregistry_upstream or settings.registry_url
    allow = load_allow(settings.subregistry_allow_path)

    def answer(payload: dict[str, Any], *, max_age: int = 300) -> Response:
        # Not JSONResponse: it writes UTF-8 and fails on the lone surrogate an entry may carry.
        return Response(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), media_type="application/json",
                        headers={**CORS, "Cache-Control": f"public, max-age={max_age}"})

    def problem(code: int, title: str, detail: str) -> Response:
        # The specification documents {"error": …}; the official registry answers RFC 9457 problem
        # details. Both are here, so a client written against either reads this.
        return Response(json.dumps({"title": title, "status": code, "detail": detail, "error": detail}),
                        status_code=code, media_type="application/problem+json", headers=CORS)

    def flag(request: Request, name: str) -> bool:
        return request.query_params.get(name, "").strip().lower() in {"1", "true"}

    def guarded(request: Request) -> Response | None:
        return None if allowed(request) else problem(429, "Too Many Requests", "too many requests")

    @app.options("/v0.1/servers", include_in_schema=False)
    @app.options("/v0.1/servers/{rest:path}", include_in_schema=False)
    def subregistry_preflight() -> Response:
        return Response(status_code=204, headers={**CORS, "Access-Control-Max-Age": "86400"})

    @app.api_route("/v0.1/servers", methods=["GET", "HEAD"])
    def subregistry_list(request: Request) -> Response:
        """Registry entries, one per server version, in the MCP registry's v0.1 form (histor.subregistry)."""
        if (refused := guarded(request)) is not None:
            return refused
        q = request.query_params
        try:
            limit = int(q["limit"]) if q.get("limit") else None
        except ValueError:
            return problem(400, "Bad Request", f"limit: 1 to {MAX_LIMIT}")
        try:
            page = list_page(store, settings.public_base, cursor=q.get("cursor") or None, limit=limit,
                             search=(q.get("search") or "").replace("\x00", "")[:200] or None,
                             updated_since=q.get("updated_since") or None, version=q.get("version") or None,
                             include_deleted=flag(request, "include_deleted"))
        except BadRequest as exc:
            return problem(400, "Bad Request", str(exc))
        return answer(page)

    @app.api_route("/v0.1/servers/{rest:path}", methods=["GET", "HEAD"])
    def subregistry_server(request: Request, rest: str) -> Response:
        """One entry (``…/versions/{version}``, ``latest`` for the newest) or a server's versions (``…/versions``)."""
        if (refused := guarded(request)) is not None:
            return refused
        raw = request.scope.get("raw_path") or request.url.path
        parsed = parse_path(raw) or parse_path(f"/v0.1/servers/{rest}")
        if parsed is None:
            return problem(404, "Not Found", "Server not found")
        name, version = parsed
        deleted = flag(request, "include_deleted")
        found = (versions(store, settings.public_base, name, include_deleted=deleted) if version is None
                 else one(store, settings.public_base, name, version, include_deleted=deleted))
        if found is None:
            return problem(404, "Not Found", "Server not found")
        return answer(found)

    @app.get("/api/v1/subregistry")
    def subregistry_status() -> Response:
        """What this subregistry holds and when it last read its upstream."""
        return answer(status(store, upstream=upstream, allow=allow, public_base=settings.public_base), max_age=60)


def sync_for(services: Any, *, full: bool = False) -> dict[str, Any]:
    settings = services.settings
    return sync(services.store, settings.subregistry_upstream or settings.registry_url,
                allow=load_allow(settings.subregistry_allow_path), full=full,
                full_every_s=settings.subregistry_full_s)


def main(argv: list[str] | None = None) -> int:
    """``python -m histor.subregistry sync [--full] | status``"""
    from histor.config import load_settings
    from histor.db import open_backend
    from histor.migrations import apply_migrations
    from histor.store import Store

    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "status"
    if command not in {"sync", "status"} or set(args[1:]) - {"--full"}:
        print(main.__doc__, file=sys.stderr)
        return 2
    settings = load_settings()
    backend = open_backend(settings.db_path, settings.database_url)
    try:
        apply_migrations(backend)
        store = Store(backend)
        upstream = settings.subregistry_upstream or settings.registry_url
        allow = load_allow(settings.subregistry_allow_path)
        if command == "sync":
            print(json.dumps(sync(store, upstream, allow=allow, full="--full" in args,
                                  full_every_s=settings.subregistry_full_s)))
        else:
            print(json.dumps(status(store, upstream=upstream, allow=allow, public_base=settings.public_base)))
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
