"""Apply the owner's title correction to only the three newly scheduled posts."""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("scheduler", Path(__file__).with_name("schedule.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PLAN = (
    ("reviewer-advisory-2026-11-07", 4993690,
     "A privacy warning became bad advice in an AI reviewer's draft"),
    ("warden-own-market-2026-11-07", 4993722,
     "Healthy containers hid a blocked MCP marketplace connection"),
    ("ard-six-hubs-2026-11-07", 4993724,
     "A missing version broke verification of signed ARD search results"),
)

assert m.api.request("/api/users/me")["username"] == "alexar76"
rows = m.owned()
prepared = []
for pack, ident, title in PLAN:
    path = m.PROMO / pack
    receipt = json.loads((path / "publication-receipt.json").read_text())
    found = next(row for row in rows if row["id"] == ident)
    assert found["user"]["username"] == "alexar76"
    assert found["title"] in (receipt["title"], title)
    assert m.timestamp(found["published_at"]) == m.timestamp(receipt["scheduledAt"])
    assert m.timestamp(found["published_at"]) > datetime.now(timezone.utc)
    assert sha256(found["body_markdown"].encode()).hexdigest() == receipt["bodySha256"]
    assert not any(row["title"] == title and row["id"] != ident for row in rows)
    prepared.append((path, ident, title, receipt, found))

for path, ident, title, receipt, before in prepared:
    response = path / "devto-retitle-response.json"
    if before["title"] == title:
        assert response.exists(), "Reconcile unrecorded external title change"
        changed = json.loads(response.read_text())
    else:
        assert not response.exists(), "Do not replay a recorded title update"
        m.save(path / "devto-retitle-pending.json", {
            "id": ident, "before": before["title"], "after": title,
            "scheduledAt": receipt["scheduledAt"], "bodySha256": receipt["bodySha256"],
            "attemptedAt": datetime.now(timezone.utc).isoformat(),
        })
        changed = m.api.request(f"/api/articles/{ident}", method="PUT", payload={"article": {
            "title": title, "published": True,
            "published_at": receipt["scheduledAt"], "ai_disclosure_level": "not_disclosed",
        }})
        m.save(response, changed)
    assert changed["id"] == ident and changed["title"] == title
    assert changed["user"]["username"] == "alexar76"
    assert changed["body_markdown"] == before["body_markdown"]
    assert changed["ai_disclosure_level"] == "not_disclosed"
    assert m.timestamp(changed["published_at"]) == m.timestamp(receipt["scheduledAt"])
    receipt.update(title=title, url=changed["url"], titleUpdatedAt=datetime.now(timezone.utc).isoformat(),
                   aiDisclosureVerifiedAgainst="title update response")
    m.save(path / "publication-receipt.json", receipt)
    article = path / "article.md"
    text = article.read_text()
    lines = text.splitlines()
    assert lines[1].startswith("title: ")
    lines[1] = "title: " + json.dumps(title)
    article.write_text("\n".join(lines) + "\n")
    (path / "devto-rendered.html").write_text(changed["body_html"])
    readme = path / "README.md"
    if readme.exists():
        readme.write_text(readme.read_text().replace(before["title"], title))
    pending = path / "devto-retitle-pending.json"
    if pending.exists():
        pending.unlink()
    print(json.dumps({"id": ident, "title": title, "at": receipt["scheduledAt"], "bodyUnchanged": True}))

after = m.owned()
for path, ident, title, receipt, before in prepared:
    found = next(row for row in after if row["id"] == ident)
    assert found["title"] == title and found["body_markdown"] == before["body_markdown"]
    assert m.timestamp(found["published_at"]) == m.timestamp(receipt["scheduledAt"])
for target in (m.PROMO / "ecosystem-articles-2026-11-07.json", Path(__file__).with_name("final-queue-verification.json")):
    summary = json.loads(target.read_text())
    updates = {ident: json.loads((path / "publication-receipt.json").read_text())
               for path, ident, *_ in prepared}
    summary["articles"] = [updates.get(article["id"], article)
                           for article in summary["articles"]]
    summary["titlesUpdatedAt"] = datetime.now(timezone.utc).isoformat()
    m.save(target, summary)
print("All three title changes read back; bodies and scheduled times preserved.")
