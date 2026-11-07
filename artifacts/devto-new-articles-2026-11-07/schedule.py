"""Schedule a reviewed DEV.to pack as alexar76; no GitHub or blog writes.

Dry run by default. Never repeat POST after an uncertain result: a pending marker
forces reconciliation through the author's article list first.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import urllib.error


AICOM = Path(__file__).resolve().parents[2]
PROMO = AICOM.parent / "PromoMaterials" / "devto"
spec = importlib.util.spec_from_file_location(
    "devto_client", AICOM / "docs/growth/publication-2026-10-25/devto_publish.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def owned():
    result = []
    for page in range(1, 21):
        batch = api.request(f"/api/articles/me/all?per_page=100&page={page}")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("Author list pagination incomplete")


class RenderCheck(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = 0
        self.code = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tables += tag == "table"
        self.code += tag == "pre"
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("pack")
    parser.add_argument("--at", required=True)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    pack = (PROMO / args.pack).resolve()
    assert pack.parent == PROMO.resolve(), "Only a DEV.to pack in PromoMaterials is allowed"
    text = (pack / "article.md").read_text()
    assert text.startswith("---\n")
    _, front, body = text.split("---", 2)
    fields = {}
    for line in front.strip().splitlines():
        if ":" in line and not line.startswith("#"):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
    body = body.lstrip("\n")
    tags = [value.strip() for value in fields["tags"].split(",")]
    assert 0 < len(tags) <= 4 and len(fields["title"]) <= 128
    assert len(fields["description"]) <= 160
    assert "AI assistance" in body.rstrip().splitlines()[-1]
    assert "/Users/" not in body and "[INSERT" not in body and "ARTICLE_URL" not in body
    assert not body.startswith("# ")
    assert body.count("```") % 2 == 0
    assert not re.search(r"\]\((?:file:|/|\.\.)", body)
    when = timestamp(args.at)
    assert when > datetime.now(timezone.utc), "A future native schedule is required"
    assert api.request("/api/users/me")["username"] == "alexar76"
    mine = owned()
    matches = [row for row in mine if row["title"] == fields["title"]]
    assert len(matches) <= 1, "Ambiguous matching title"
    receipt = pack / "devto-schedule-response.json"
    pending = pack / "devto-schedule-pending.json"
    body_hash = sha256(body.encode()).hexdigest()
    payload = {
        "title": fields["title"],
        "description": fields["description"],
        "body_markdown": body,
        "published": True,
        "published_at": args.at,
        "tags": tags,
        "ai_disclosure_level": "not_disclosed",
    }
    if not args.send:
        assert not matches and not receipt.exists() and not pending.exists(), "Reconcile existing article first"
        assert not any(row.get("published_at") and timestamp(row["published_at"]) == when for row in mine), "Slot occupied"
        print(json.dumps({"action": "dry_run", "title": fields["title"], "at": args.at,
                          "words": len(body.split()), "sha256": body_hash, "tags": tags}))
        return
    if receipt.exists():
        created = json.loads(receipt.read_text())
        assert matches and matches[0]["id"] == created["id"], "Receipt missing from author list"
    elif pending.exists():
        assert matches, "Uncertain prior write; inspect before sending anything again"
        created = matches[0]
    else:
        assert not matches, "An article with this title already exists"
        assert not any(row.get("published_at") and timestamp(row["published_at"]) == when for row in mine), "Slot occupied"
        save(pending, {"title": fields["title"], "at": args.at, "bodySha256": body_hash,
                       "attemptedAt": datetime.now(timezone.utc).isoformat()})
        created = api.request("/api/articles", method="POST", payload={"article": payload})
        save(receipt, created)
    assert created.get("user", {}).get("username") == "alexar76"
    assert timestamp(created["published_at"]) == when
    assert created.get("ai_disclosure_level") == "not_disclosed"
    mine = owned()
    rows = [row for row in mine if row["id"] == created["id"]]
    assert len(rows) == 1 and rows[0]["title"] == fields["title"]
    assert timestamp(rows[0]["published_at"]) == when
    try:
        found = api.request(f'/api/articles/{created["id"]}')
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        found = rows[0]
    if "body_markdown" not in found:
        found = created
    assert found.get("user", {}).get("username") == "alexar76"
    assert found["body_markdown"] == body
    # Author-list records omit this field on scheduled posts. The create response
    # explicitly returns it; check any later response that does include it too.
    if found.get("ai_disclosure_level") is not None:
        assert found["ai_disclosure_level"] == "not_disclosed"
    check = RenderCheck()
    rendered = found.get("body_html") or created.get("body_html")
    assert rendered, "Missing rendered article"
    check.feed(rendered)
    assert not re.search(r"\[(?:INSERT|TODO)", rendered)
    assert all(url.startswith(("https://", "#")) for url in check.links)
    if "| ---" in body:
        assert check.tables >= 1, "Markdown table did not render"
    if "```" in body:
        assert check.code >= 1, "Code block did not render"
    (pack / "devto-rendered.html").write_text(rendered)
    verified = {
        "id": created["id"], "title": fields["title"], "url": created["url"],
        "author": "alexar76", "scheduledAt": args.at,
        "aiDisclosureLevel": "not_disclosed", "bodySha256": body_hash,
        "aiDisclosureVerifiedAgainst": "create response",
        "words": len(body.split()), "renderedTables": check.tables,
        "renderedCodeBlocks": check.code,
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "nativeSchedule": True,
        "authorListVerified": True,
        "bodyVerifiedAgainst": "authenticated article or create response",
    }
    save(pack / "publication-receipt.json", verified)
    if pending.exists():
        pending.unlink()
    print(json.dumps(verified, ensure_ascii=False))


if __name__ == "__main__":
    main()
