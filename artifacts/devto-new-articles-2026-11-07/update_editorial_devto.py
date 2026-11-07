"""Update only these four articles, preserving their DEV.to publication dates."""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import time
import urllib.request

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scheduler", HERE / "schedule.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
plan = json.loads((HERE / "editorial-blog-plan.json").read_text())
assert (HERE / "editorial-blog-deployment.json").exists()
assert m.api.request("/api/users/me")["username"] == "alexar76"
mine = {row["id"]: row for row in m.owned()}
prepared = []
for post in plan:
    pack = m.PROMO / post["pack"]
    receipt = json.loads((pack / "publication-receipt.json").read_text())
    _, front, body = (pack / "article.md").read_text().split("---", 2)
    body = body.lstrip("\n")
    fields = {key.strip(): json.loads(value.strip()) if value.strip().startswith('"') else value.strip()
              for key, value in (line.split(":", 1) for line in front.strip().splitlines())}
    existing = mine[post["id"]]
    assert existing["user"]["username"] == "alexar76"
    assert existing["title"] == fields["title"] == post["title"]
    assert m.timestamp(existing["published_at"]) == m.timestamp(post["devtoAt"])
    response_path = pack / "devto-editorial-response.json"
    if not response_path.exists():
        assert sha256(existing["body_markdown"].encode()).hexdigest() == receipt["bodySha256"], "Concurrent DEV.to edit"
    assert (m.AICOM / "modelmarket-blog/posts" / post["slug"] / "body.md").read_text() == body
    assert "AI assistance" in body.rstrip().splitlines()[-1]
    with urllib.request.urlopen(post["blogUrl"], timeout=30) as response:
        rendered = response.read().decode()
        assert response.status == 200 and "AI assistance" in rendered
    prepared.append((post, pack, receipt, body, fields, response_path))

for index, (post, pack, receipt, body, fields, response_path) in enumerate(prepared):
    if response_path.exists():
        changed = json.loads(response_path.read_text())
        assert changed["body_markdown"] == body, "Recorded update differs from local revision"
    else:
        if index:
            time.sleep(21)  # DEV.to permits few article updates per short window.
        live = next(row for row in m.owned() if row["id"] == post["id"])
        assert sha256(live["body_markdown"].encode()).hexdigest() == receipt["bodySha256"], "DEV.to changed during this pass"
        payload = {"article": {
            "title": fields["title"], "description": fields["description"],
            "body_markdown": body, "tags": [tag.strip() for tag in fields["tags"].split(",")],
            "published": True, "published_at": post["devtoAt"],
            "canonical_url": post["blogUrl"], "main_image": post["blogUrl"] + "cover.webp",
            "ai_disclosure_level": "not_disclosed",
        }}
        m.save(pack / "devto-editorial-pending.json", {"id": post["id"], "bodySha256": sha256(body.encode()).hexdigest(),
                                                     "at": datetime.now(timezone.utc).isoformat()})
        changed = m.api.request(f'/api/articles/{post["id"]}', method="PUT", payload=payload)
        m.save(response_path, changed)
    assert changed["id"] == post["id"] and changed["user"]["username"] == "alexar76"
    assert changed["body_markdown"] == body and changed["canonical_url"] == post["blogUrl"]
    assert changed["ai_disclosure_level"] == "not_disclosed"
    assert m.timestamp(changed["published_at"]) == m.timestamp(post["devtoAt"])
    (pack / "devto-rendered.html").write_text(changed["body_html"])
    check = m.RenderCheck()
    check.feed(changed["body_html"])
    receipt.update(bodySha256=sha256(body.encode()).hexdigest(), words=len(body.split()), canonicalUrl=post["blogUrl"],
                   blogPublishedAt=post["blogAt"], editorialUpdatedAt=datetime.now(timezone.utc).isoformat(),
                   renderedTables=check.tables, renderedCodeBlocks=check.code,
                   aiDisclosureVerifiedAgainst="editorial update response")
    m.save(pack / "publication-receipt.json", receipt)
    # Originals and editorial backups stay in PromoMaterials, with canonical links in the final frontmatter.
    article = pack / "article.md"
    _, front, _ = article.read_text().split("---", 2)
    lines = [line for line in front.strip().splitlines() if not line.startswith(("canonical_url:", "cover_image:"))]
    lines += ["canonical_url: " + post["blogUrl"], "cover_image: " + post["blogUrl"] + "cover.webp"]
    article.write_text("---\n" + "\n".join(lines) + "\n---\n\n" + body)
    pending = pack / "devto-editorial-pending.json"
    if pending.exists():
        pending.unlink()
    print(json.dumps({"id": post["id"], "title": fields["title"], "words": len(body.split()),
                      "canonical": changed["canonical_url"], "publicationTimePreserved": True}), flush=True)

after = {row["id"]: row for row in m.owned()}
receipts = []
for post, pack, receipt, body, fields, _ in prepared:
    row = after[post["id"]]
    assert row["body_markdown"] == body and row["canonical_url"] == post["blogUrl"]
    assert m.timestamp(row["published_at"]) == m.timestamp(post["devtoAt"])
    fresh = json.loads((pack / "publication-receipt.json").read_text())
    fresh["finalQueueVerifiedAt"] = datetime.now(timezone.utc).isoformat()
    m.save(pack / "publication-receipt.json", fresh)
    receipts.append(fresh)
summary = {"author": "alexar76", "articles": receipts, "bodiesEdited": True, "blogPublished": True,
           "devtoPublicationDatesPreserved": True, "githubWrites": False}
m.save(m.PROMO / "ecosystem-articles-2026-11-07.json", summary)
m.save(HERE / "final-queue-verification.json", summary)
print("All four editorial bodies and canonicals read back; DEV.to dates preserved.", flush=True)
