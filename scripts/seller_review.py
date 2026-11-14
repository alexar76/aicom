#!/usr/bin/env python3
"""Seller review before publication: nothing with a seller's numbers goes out before they have seen it.

Some sellers we list asked to see, before publication, every text of ours that carries numbers about
their services (scripts/seller_review_registry.json says who, since when and on what terms). This is
the check our publishing paths run. It finds every paragraph that names a registered seller and holds
a number, files those paragraphs on the seller's private review page (okx-a2mcp src/web/review.js,
https://modelmarket.dev/tools/review/<their link>/), and lets the publication through only when the
seller has answered OK (or, if they agreed to it, when their review window passed with no answer).
An objection, a missing answer, or a check that cannot reach the review service all block: it fails
closed.

    seller_review.py scan FILE...                 # list what would be filed; nothing leaves this machine
    seller_review.py check FILE...                # file and require answers (exit 0 = may publish)
    seller_review.py check-blog POSTS [--only SLUG] [--live-only]
    seller_review.py file --seller ID FILE        # file a whole text, e.g. an aggregate with no names in it

A changed number is a changed paragraph and so a new request: the seller always answers the final
text. The gate's token: $SELLER_REVIEW_ADMIN_TOKEN_FILE, else ~/.config/seller-review/admin_token.
Exit status: 0 publish, 2 blocked (waiting or objected), 3 the check itself failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REGISTRY = Path(__file__).with_name("seller_review_registry.json")
DIGIT = re.compile(r"\d")


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    reg = json.loads(path.read_text(encoding="utf-8"))
    for sid, s in reg["sellers"].items():
        s["id"] = sid
        s["_res"] = [re.compile(p) for p in s["patterns"]]
    return reg


def normalize(paragraph: str) -> str:
    return re.sub(r"\s+", " ", paragraph).strip()


def paragraphs(text: str) -> list[str]:
    return [p for p in (normalize(x) for x in re.split(r"\n\s*\n", text)) if p]


def review_id(seller: str, excerpt: str) -> str:
    """Same as okx-a2mcp src/web/review.js reviewId: sha256("<seller>\\n<excerpt>"), first 20 hex digits."""
    return hashlib.sha256(f"{seller}\n{excerpt}".encode("utf-8")).hexdigest()[:20]


def find(text: str, reg: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """(seller, excerpt) for every seller named next to a number: each paragraph that names the
    seller AND holds a digit, joined with a blank line, in document order."""
    out = []
    paras = paragraphs(text)
    for seller in reg["sellers"].values():
        hits = [p for p in paras if DIGIT.search(p) and any(r.search(p) for r in seller["_res"])]
        if hits:
            out.append((seller, "\n\n".join(hits)))
    return out


def _token() -> str:
    path = os.environ.get("SELLER_REVIEW_ADMIN_TOKEN_FILE") or str(Path.home() / ".config/seller-review/admin_token")
    return Path(path).read_text(encoding="utf-8").strip()


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {_token()}", "Content-Type": "application/json",
        "User-Agent": "modelmarket-seller-review/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def state(record: dict[str, Any], seller: dict[str, Any], now: datetime) -> str:
    if record.get("decision") == "ok":
        return "approved"
    if record.get("decision") == "object":
        return "objected"
    nb = record.get("not_before") or ""
    passed = bool(nb) and now >= datetime.fromisoformat(nb.replace("Z", "+00:00"))
    return "approved_by_silence" if seller.get("silence_is_consent") and passed else "waiting"


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def review(source: str, title: str, items: list[tuple[dict[str, Any], str]], reg: dict[str, Any], *,
           http: Callable[..., tuple[int, dict[str, Any]]] = _http,
           now: datetime | None = None, out=sys.stdout) -> int:
    """File each (seller, excerpt) and report. 0 = may publish, 2 = blocked, 3 = check failed."""
    now = now or datetime.now(timezone.utc)
    worst = 0
    for seller, excerpt in items:
        rid = review_id(seller["id"], excerpt)
        try:
            status, rec = http("GET", f"{reg['api']}/requests/{rid}")
            if status == 404:
                status, rec = http("POST", f"{reg['api']}/requests", {
                    "seller": seller["id"], "excerpt": excerpt, "title": title, "source": source,
                    "not_before": iso(now + timedelta(hours=seller["window_hours"]))})
            if status not in (200, 201) or rec.get("id") != rid:
                raise RuntimeError(f"review service answered {status}")
        except Exception as e:  # noqa: BLE001 - any failure here must block, never pass
            print(f"FAILED  {source}: could not reach the review service for {seller['name']} ({e}); not publishing",
                  file=out)
            worst = max(worst, 3)
            continue
        st = state(rec, seller, now)
        if st in ("approved", "approved_by_silence"):
            how = "answered OK" if st == "approved" else f"no answer by {rec['not_before']} (agreed: silence is OK)"
            print(f"ok      {source}: {seller['name']} {how} [{rid}]", file=out)
        elif st == "objected":
            print(f"BLOCKED {source}: {seller['name']} objected at {rec.get('decided_at')}: {rec.get('note') or '(no note)'}"
                  f" — change the text; the new paragraph is filed as a new request [{rid}]", file=out)
            worst = max(worst, 2)
        else:
            print(f"BLOCKED {source}: waiting for {seller['name']} (filed {rec.get('created_at')}, "
                  f"window to {rec.get('not_before')}) [{rid}]", file=out)
            worst = max(worst, 2)
    return worst


def _blog_posts(posts: Path, only: str | None, live_only: bool, now: datetime) -> list[tuple[str, str, str]]:
    out = []
    for d in sorted(p for p in posts.iterdir() if p.is_dir()):
        if only and d.name != only:
            continue
        body, meta = d / "body.md", d / "meta.json"
        if not body.is_file():
            continue
        m = json.loads(meta.read_text(encoding="utf-8")) if meta.is_file() else {}
        until = m.get("embargo_until")
        if live_only and until and datetime.fromisoformat(until.replace("Z", "+00:00")) > now:
            continue  # checked when it is scheduled (schedule_release.sh) and at the deploy after its moment
        out.append((f"blog/{d.name}", m.get("title") or d.name, body.read_text(encoding="utf-8")))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "check"):
        p = sub.add_parser(name)
        p.add_argument("files", nargs="+", type=Path)
        p.add_argument("--title", default="")
    b = sub.add_parser("check-blog")
    b.add_argument("posts", type=Path)
    b.add_argument("--only")
    b.add_argument("--live-only", action="store_true")
    f = sub.add_parser("file")
    f.add_argument("--seller", required=True)
    f.add_argument("file", type=Path)
    f.add_argument("--title", default="")
    args = ap.parse_args(argv)
    reg = load_registry()
    now = datetime.now(timezone.utc)

    if args.cmd == "file":
        if args.seller not in reg["sellers"]:
            print(f"unknown seller {args.seller}; registry: {', '.join(reg['sellers'])}", file=sys.stderr)
            return 3
        text = "\n\n".join(paragraphs(args.file.read_text(encoding="utf-8")))
        return review(str(args.file), args.title or args.file.name, [(reg["sellers"][args.seller], text)], reg, now=now)

    if args.cmd == "check-blog":
        docs = _blog_posts(args.posts, args.only, args.live_only, now)
    else:
        docs = [(str(p), args.title or p.name, p.read_text(encoding="utf-8")) for p in args.files]

    worst = 0
    for source, title, text in docs:
        items = find(text, reg)
        if args.cmd == "scan":
            for seller, excerpt in items:
                print(f"{source}: {seller['name']} [{review_id(seller['id'], excerpt)}]\n  " + excerpt.replace("\n", "\n  "))
            worst = max(worst, 2 if items else 0)
            continue
        worst = max(worst, review(source, title, items, reg, now=now))
    if args.cmd != "scan" and worst == 0:
        print(f"seller review: nothing blocks ({len(docs)} text(s) checked)")
    return worst


if __name__ == "__main__":
    sys.exit(main())
