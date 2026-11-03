"""Publish only the reviewed article as alexar76, without an AI disclosure badge."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


WORKSPACE = Path(__file__).resolve().parents[2]
PROMO = WORKSPACE.parent / "PromoMaterials" / "devto"
PACK = PROMO / "sellers-said-no-2026-10-31"
EXPECTED_HASH = "8fdcd46bf514ebc15980c252abd9c064fa417d5fe55aa4e38aa2e3321551e6d6"
BASE = "https://dev.to/api"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(name, data):
    path = PACK / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


spec = importlib.util.spec_from_file_location("existing_devto_publisher", PROMO / "publish_article.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
helper.load_dotenv(PROMO / ".env")
KEY = os.environ.get("DEVTO_API_KEY")
if not KEY:
    raise SystemExit("No existing DEV.to API credential available.")


def request(path, payload=None, method="GET", authenticated=True):
    headers = {
        "Accept": "application/vnd.forem.api-v1+json",
        "User-Agent": "AIMarket-editorial-publication/1.0",
    }
    if authenticated:
        headers["api-key"] = KEY
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"DEV.to returned HTTP {exc.code} for {method} {path}.") from None


def same_article(article, metadata, body, require_disclosure=True):
    assert article.get("user", {}).get("username") == "alexar76", "Wrong article identity"
    assert article.get("title") == metadata["title"], "Title differs"
    assert article.get("body_markdown", "").strip() == body.strip(), "Body differs"
    if require_disclosure or "ai_disclosure_level" in article:
        assert article.get("ai_disclosure_level") == "not_disclosed", "Unexpected AI badge setting"


def owned_article(article_id):
    # The public single-article endpoint returns 404 for drafts even with the key.
    for page in range(1, 21):
        articles = request(f"/articles/me/all?per_page=100&page={page}")
        for article in articles:
            if article["id"] == article_id:
                return article
        if len(articles) < 100:
            break
    raise SystemExit("Article not found among the authenticated user's articles.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["stage", "publish", "verify"])
    args = parser.parse_args()
    text = (PACK / "article.md").read_text()
    assert hashlib.sha256(text.encode()).hexdigest() == EXPECTED_HASH, "Reviewed article changed"
    metadata, body = helper.parse_frontmatter(text)
    assert metadata["ai_disclosure_level"] == "not_disclosed"
    assert "Disclosure: I used AI assistance" in body
    user = request("/users/me")
    assert user.get("username") == "alexar76", "Authenticated user is not alexar76"
    save("devto-author-check.json", {"username": user["username"], "id": user["id"], "checkedAt": now()})

    if args.mode == "stage":
        matches = []
        for page in range(1, 21):
            articles = request(f"/articles/me/all?per_page=100&page={page}")
            assert isinstance(articles, list)
            matches.extend(a for a in articles if a.get("title") == metadata["title"])
            if len(articles) < 100:
                break
        else:
            raise SystemExit("Article scan incomplete; creation refused.")
        assert len(matches) <= 1, "Multiple matching articles; creation refused"
        if matches:
            article = owned_article(matches[0]["id"])
            same_article(article, metadata, body, require_disclosure=False)
            article = request(f"/articles/{article['id']}", {"article": {"ai_disclosure_level": "not_disclosed"}}, method="PUT")
            same_article(article, metadata, body)
            save("devto-draft-response.json", article)
        else:
            assert not (PACK / "devto-create-attempt.json").exists(), "Previous create attempt needs reconciliation"
            payload = {"article": {
                "title": metadata["title"],
                "description": metadata["description"],
                "body_markdown": body,
                "tags": [tag.strip() for tag in metadata["tags"].split(",")],
                "published": False,
                "ai_disclosure_level": "not_disclosed",
            }}
            save("devto-request.json", payload)
            save("devto-create-attempt.json", {"at": now(), "bodySha256": hashlib.sha256(body.encode()).hexdigest()})
            article = request("/articles", payload, method="POST")
            save("devto-draft-response.json", article)
            same_article(article, metadata, body)
        print(json.dumps({"id": article["id"], "author": article["user"]["username"], "ai_disclosure_level": article["ai_disclosure_level"], "published_at": article.get("published_at")}))
        return

    draft = json.loads((PACK / "devto-draft-response.json").read_text())
    article_id = draft["id"]
    same_article(draft, metadata, body)
    before = owned_article(article_id)
    same_article(before, metadata, body, require_disclosure=False)
    if args.mode == "publish" and not before.get("published_at"):
        result = request(f"/articles/{article_id}", {"article": {"published": True, "ai_disclosure_level": "not_disclosed"}}, method="PUT")
        save("devto-publish-response.json", result)
        same_article(result, metadata, body)
        assert result.get("published_at"), "API did not confirm publication"

    public = request(f"/articles/alexar76/{before['slug']}", authenticated=False)
    save("devto-public.json", public)
    same_article(public, metadata, body)
    assert public.get("published_at"), "Public API does not confirm publication"
    published_text = text.replace("published: false", "published: true", 1)
    (PACK / "article.published.md").write_text(published_text)
    receipt = {
        "id": article_id,
        "url": public["url"],
        "title": public["title"],
        "author": public["user"]["username"],
        "aiDisclosureLevel": public["ai_disclosure_level"],
        "publishedAt": public["published_at"],
        "publiclyVerifiedAt": now(),
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "reviewedFileSha256": EXPECTED_HASH,
        "exactBodyVerified": True,
        "detailedAiDisclosureRetained": True,
        "githubWrites": False,
    }
    save("devto-publication.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
