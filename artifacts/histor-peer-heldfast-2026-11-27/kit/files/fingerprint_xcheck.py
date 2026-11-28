"""Compare another observer's per-tool fingerprints with HISTOR's record, server by server.

Some observers keep no tool-set digest. They pin every tool on its own, in their own format. heldfast does this
(github.com/rufat325/heldfast, docs/LOCK.md): SHA-256 of RFC 8785 over name, title, description, input_schema,
annotations, output_schema (omitted when empty) and icons (omitted when empty). Its public feed
(github.com/rufat325/heldfast-feed) holds one state file per server, `state/remote__<registry name>.json` for a
hosted server (`/` in the name written `__`):

    {"package": "remote/<registry name>", "url": "<endpoint>", "published": "<RFC 3339>", "version": "...",
     "tools": {"<tool name>": "<fingerprint>", ...},
     "attempted": {"at": "<RFC 3339>", "why": "HTTP 401", ...}}

`published` is the time of the read that produced this tool list, which is the read compared here (an npm package's
file says `checked_at` instead). `attempted` is a later read that failed; a server never read has only `attempted`.

HISTOR computes the same fingerprints from what it stored (GET /api/v1/servers/<id>/fingerprints?format=heldfast,
histor/fingerprints.py), so the comparison is tool by tool, with no conversion on either side. <id> is the first
16 hex of sha256(name + "\\n" + endpoint).

That route answers with HISTOR's current tool set (`unchangedSince` .. `lastObserved`). A fingerprint also covers
the title and annotations, which can change while the tool set stays. So a server whose fingerprints differ is looked
up once more (GET /api/v1/servers/<id>) for the time of its newest title/annotation change. Verdicts per server:

    agree              every tool both sides fingerprint is the same, and both list the same tools
    disagree           different, although HISTOR read this tool set (titles and annotations included) both
                       before and after the other observer's read
    changed_after      different, and HISTOR's current tool set or its titles/annotations date from after the other
                       observer's read: the server changed in between, which this route cannot judge
    read_after         different, and the other observer read after HISTOR's last read: the server may have changed
                       since HISTOR read it. The row carries HISTOR's status now (`histor_last_status`): on 2026-11-27,
                       31 of 37 such servers had `robots-disallowed`, and HISTOR does not read an endpoint its
                       robots.txt disallows (RFC 9309)
    histor_no_extras   HISTOR read this tool set before it kept titles and annotations, so it cannot fingerprint it
    histor_no_toolset  HISTOR lists the server but has no tool set for it (not readable without credentials, ...)
    not_listed         HISTOR does not list this name and endpoint
    theirs_no_tools    the other observer's file lists no tools (with its `attempted.why` when there is one)
    bad_row            the file is missing a field or cannot be read

Tools whose titles or annotations HISTOR could not keep (over its size caps) are left out on both sides and
counted. Standard library only, so histor/peers.py runs it in a container with no database.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

try:  # inside the package, and when mounted next to it into an older image
    from histor import digest_xcheck as dx
except ImportError:  # pragma: no cover - a copy of both files run by path
    import digest_xcheck as dx  # type: ignore[no-redef]

FORMATS = ("heldfast",)
VERDICTS = ("agree", "disagree", "changed_after", "read_after", "histor_no_extras", "histor_no_toolset",
            "not_listed", "theirs_no_tools", "bad_row")
LISTED = 20  # tool names kept per list in a row of the report


class NoToolSet(Exception):
    """HISTOR lists the server but has no tool set for it."""


def fetch_json(url: str, timeout: float = 30) -> Any:
    """GET a JSON document. 404 becomes NotListed, or NoToolSet when HISTOR says it lists the server."""
    req = urllib.request.Request(url, headers={"User-Agent": dx.UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            try:
                detail = str(json.loads(exc.read().decode("utf-8") or "{}").get("detail") or "")
            except (ValueError, UnicodeDecodeError):
                detail = ""
            if "no tool set" in detail:
                raise NoToolSet(url) from exc
            raise dx.NotListed(url) from exc
        raise


def github_listing(repo: str, ref: str, folder: str, prefix: str, get_json: Callable[[str], Any]) -> dict:
    """The files of FOLDER at the commit REF names now: {"commit", "committed_at", "files": [names with PREFIX],
    "files_in_folder"}. Three GitHub API requests: the commit, its root tree, the folder's tree."""
    api = f"https://api.github.com/repos/{repo}"
    commit = get_json(f"{api}/commits/{urllib.parse.quote(ref, safe='')}")
    root = get_json(f"{api}/git/trees/{commit['commit']['tree']['sha']}")
    sub = next((t for t in root.get("tree", []) if t.get("path") == folder and t.get("type") == "tree"), None)
    if sub is None:
        raise ValueError(f"no folder {folder!r} at {repo}@{commit['sha'][:12]}")
    tree = get_json(f"{api}/git/trees/{sub['sha']}")
    if tree.get("truncated"):
        raise ValueError(f"the listing of {folder!r} is truncated")
    names = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    return {"commit": commit["sha"], "committed_at": commit["commit"]["committer"]["date"],
            "files_in_folder": len(names), "files": sorted(n for n in names if n.startswith(prefix))}


def raw_url(repo: str, commit: str, folder: str, name: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{commit}/{folder}/{urllib.parse.quote(name)}"


def read_state(text: str) -> dict:
    """One heldfast state file as a row: name, endpoint, read_at (`published`, else `checked_at`), tools
    ({name: fingerprint}) and `attempted` (a later read that failed: "<why> at <at>"); bad fields → None."""
    try:
        d = json.loads(text)
    except ValueError:
        d = None
    if not isinstance(d, dict):
        return {"name": None, "endpoint": None, "read_at": None, "tools": None}
    package = d.get("package")
    name = package[len("remote/"):] if isinstance(package, str) and package.startswith("remote/") else None
    tools = d.get("tools")
    tools = {str(k): v for k, v in tools.items() if isinstance(v, str)} if isinstance(tools, dict) else None
    row = {"name": name or None, "endpoint": d.get("url") or None,
           "read_at": d.get("published") or d.get("checked_at") or None, "tools": tools}
    tried = d.get("attempted")
    if isinstance(tried, dict) and (tried.get("why") or tried.get("at")):
        row["attempted"] = f"{str(tried.get('why') or '?')[:80]} at {str(tried.get('at') or '?')[:40]}"
    return row


def _latest_extras_change(record: dict) -> datetime | None:
    times = [dx.parse_time(c.get("observedAt") or c.get("observed_at")) for c in record.get("extrasChanges") or []]
    times = [t for t in times if t]
    return max(times) if times else None


def judge(theirs: dict[str, str], answer: dict, read_at: datetime,
          extras_changed: Callable[[], datetime | None]) -> dict:
    """One server's verdict and the details the report keeps."""
    if not answer.get("extrasRecorded"):
        return {"verdict": "histor_no_extras"}
    skipped = set(answer.get("incomplete") or [])
    ours = {k: v for k, v in (answer.get("fingerprints") or {}).items() if k not in skipped}
    them = {k: v for k, v in theirs.items() if k not in skipped}
    out: dict[str, Any] = {"tools_compared": len(set(ours) | set(them))}
    if skipped:
        out["tools_skipped"] = sorted(skipped)[:LISTED]
    if ours == them:
        return {"verdict": "agree", **out}
    only_theirs = sorted(set(them) - set(ours))
    only_histor = sorted(set(ours) - set(them))
    different = sorted(k for k in set(ours) & set(them) if ours[k] != them[k])
    out |= {"only_theirs": only_theirs[:LISTED], "only_histor": only_histor[:LISTED], "different": different[:LISTED],
            "counts": {"only_theirs": len(only_theirs), "only_histor": len(only_histor), "different": len(different)}}
    since, last = dx.parse_time(answer.get("unchangedSince")), dx.parse_time(answer.get("lastObserved"))
    out |= {"histor_unchanged_since": answer.get("unchangedSince"), "histor_last_observed": answer.get("lastObserved")}
    if since and since > read_at:
        return {"verdict": "changed_after", **out}
    extras_at = extras_changed()
    if extras_at:
        out["histor_extras_changed_at"] = extras_at.isoformat().replace("+00:00", "Z")
    if extras_at and extras_at > read_at:
        return {"verdict": "changed_after", **out}
    if last and last < read_at:
        return {"verdict": "read_after", **out}
    return {"verdict": "disagree", **out}


def xcheck(rows: list[dict], fetch: Callable[[str], Any], histor: str, fmt: str = "heldfast",
           pause: float = 0.0) -> dict:
    """ROWS from read_state (plus "file"), each judged against HISTOR's record."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    base = histor.rstrip("/")
    out = []
    for raw in rows:
        entry = {k: raw.get(k) for k in ("file", "name", "endpoint", "read_at") if k in raw}
        if raw.get("attempted"):
            entry["their_last_attempt"] = raw["attempted"]
        read_at = dx.parse_time(raw.get("read_at"))
        if raw.get("name") and raw.get("tools") is not None and not raw["tools"]:
            out.append({**entry, "verdict": "theirs_no_tools", **({"note": raw["attempted"]} if raw.get("attempted") else {})})
            continue
        missing = [k for k, v in (("name", raw.get("name")), ("endpoint", raw.get("endpoint")), ("read_at", read_at),
                                  ("tools", raw.get("tools") is not None)) if not v]
        if missing:
            note = "missing or unreadable: " + ", ".join(missing)
            out.append({**entry, "verdict": "bad_row", "note": raw.get("fetch_error") or note})
            continue
        tid = dx.target_id(str(raw["name"]), str(raw["endpoint"]))
        try:
            answer = fetch(f"{base}/api/v1/servers/{tid}/fingerprints?format={fmt}")
        except NoToolSet:
            out.append({**entry, "id": tid, "verdict": "histor_no_toolset"})
            continue
        except dx.NotListed:
            out.append({**entry, "id": tid, "verdict": "not_listed"})
            continue
        finally:
            if pause:
                time.sleep(pause)

        record: dict[str, Any] = {}

        def extras_changed(tid: str = tid, record: dict[str, Any] = record) -> datetime | None:
            record.update(fetch(f"{base}/api/v1/servers/{tid}") or {})
            if pause:
                time.sleep(pause)
            return _latest_extras_change(record)

        row = {**entry, "id": tid, "tools_theirs": len(raw["tools"]), **judge(raw["tools"], answer, read_at, extras_changed)}
        status = (record.get("server") or {}).get("lastStatus")
        if status:
            # Why HISTOR's last successful read can be old: a server whose robots.txt disallows the endpoint is not
            # read again (RFC 9309), one that now asks for credentials cannot be.
            row["histor_last_status"] = status
        out.append(row)
    counts = {v: sum(1 for r in out if r["verdict"] == v) for v in VERDICTS}
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "histor": histor, "format": fmt, "rows_in": len(rows), "counts": counts, "rows": out,
    }


def markdown(report: dict) -> str:
    c = report["counts"]
    src = report.get("source") or {}
    lines = [f"# Per-tool fingerprint cross-check with HISTOR, {report['generated_at']}", "",
             f"{report['rows_in']} servers; fingerprints in the {report['format']} format, compared tool by tool.", ""]
    if src.get("commit"):
        lines += [f"Source: {src.get('repo')}@{src['commit']} ({src.get('committed_at')}), folder "
                  f"{src.get('folder')}/, {src.get('files_in_folder')} files, {src.get('files_with_prefix')} with "
                  f"the prefix {src.get('prefix')}.", ""]
    if report.get("sample"):
        s = report["sample"]
        lines += [f"Today's share: part {s['part'] + 1} of {s['parts']} ({report['rows_in']} of {s['rows_in_source']} "
                  f"files; rule: {s['rule']}).", ""]
    lines += ["| verdict | servers |", "|---|---|"] + [f"| {v} | {c[v]} |" for v in VERDICTS]
    odd = [r for r in report["rows"] if r["verdict"] in ("disagree", "changed_after", "read_after", "bad_row")]
    if odd:
        lines += ["", "| verdict | server | endpoint | their read | HISTOR unchanged since | HISTOR's last read | HISTOR's "
                  "status now | tools: only theirs / only HISTOR's / different |", "|---|---|---|---|---|---|---|---|"]
        for r in odd:
            k = r.get("counts") or {}
            tools = (f"{k.get('only_theirs', 0)} / {k.get('only_histor', 0)} / {k.get('different', 0)}"
                     if k else r.get("note") or "")
            lines.append(f"| {r['verdict']} | {r.get('name') or ''} | {r.get('endpoint') or ''} | {r.get('read_at') or ''} "
                         f"| {r.get('histor_unchanged_since') or ''} | {r.get('histor_last_observed') or ''} "
                         f"| {r.get('histor_last_status') or ''} | {tools} |")
    return "\n".join(lines) + "\n"
