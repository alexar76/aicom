"""Add the two prepared images to the existing DEV.to article, keeping prose intact."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import unquote

spec = importlib.util.spec_from_file_location("publication", Path(__file__).with_name("publish.py"))
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)

assert pub.request("/users/me")["username"] == "alexar76"
receipt = json.loads((pub.PACK / "devto-publication.json").read_text())
assert receipt["id"] == 4951998
original_text = (pub.PACK / "article.md").read_text()
assert hashlib.sha256(original_text.encode()).hexdigest() == pub.EXPECTED_HASH
metadata, original_body = pub.helper.parse_frontmatter(original_text)
current = pub.owned_article(receipt["id"])
assert current.get("published") is True
if not (pub.PACK / "devto-before-images.json").exists():
    pub.save("devto-before-images.json", current)

urls = json.loads((pub.PACK / "_image_urls.json").read_text())
cover = urls["01-cover.png"]
diagram = urls["02-who-does-the-work.png"]
anchor = "The seller doesn't maintain an AIMarket manifest for this path. A buyer calls the seller's URL and pays the seller directly. The hub is outside that payment path."
assert original_body.count(anchor) == 1
image = f"![Diagram comparing seller-maintained signed manifests with hub-maintained observed listings. Observed offers require consent; buyers call and pay the seller directly. A price quote does not prove delivery.]({diagram})"
body = original_body.replace(anchor, anchor + "\n\n" + image)
body = body.replace("Seller replies are paraphrased; our own probes are identified as tests.", "Seller replies are paraphrased; our own probes are identified as tests. The cover illustration was generated with AI; the explanatory diagram was drawn from the implementation.")
assert "Disclosure: I used AI assistance" in body
frontmatter = original_text.split("---", 2)[1].strip()
frontmatter += f"\ncover_image: {cover}"
source = "---\n" + frontmatter + "\n---\n\n" + body
(pub.PACK / "article.before-images.md").write_text(original_text)
(pub.PACK / "article.with-images.md").write_text(source)
payload = {"article": {"body_markdown": body, "main_image": cover, "ai_disclosure_level": "not_disclosed"}}
pub.save("devto-images-request.json", payload)
if current.get("body_markdown", "").strip() == original_body.strip():
    pub.same_article(current, metadata, original_body, require_disclosure=False)
    result = pub.request(f"/articles/{receipt['id']}", payload, method="PUT")
    pub.save("devto-images-response.json", result)
else:
    pub.same_article(current, metadata, body, require_disclosure=False)
    result = json.loads((pub.PACK / "devto-images-response.json").read_text())
pub.same_article(result, metadata, body)
assert result.get("published_at")
public = pub.request(f"/articles/alexar76/{result['slug']}", authenticated=False)
pub.save("devto-public.json", public)
pub.same_article(public, metadata, body)
assert diagram in public["body_markdown"]
assert cover in unquote(public.get("cover_image", ""))
(pub.PACK / "article.md").write_text(source)
(pub.PACK / "article.published.md").write_text(source.replace("published: false", "published: true", 1))
receipt.update({
    "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
    "publiclyVerifiedAt": pub.now(),
    "imagesAddedAt": pub.now(),
    "coverImage": cover,
    "inlineImages": [diagram],
    "imagePrompts": "cover-prompts.txt",
    "imageGenerationMode": "built-in image_gen for cover; deterministic Pillow drawing for diagram",
    "aiDisclosureLevel": public["ai_disclosure_level"],
    "visibleAiBadgeAbsent": None,
    "exactBodyVerified": True,
})
pub.save("devto-publication.json", receipt)
print(json.dumps({"url": receipt["url"], "cover": cover, "diagram": diagram, "ai_disclosure_level": public["ai_disclosure_level"], "bodyVerified": True}))
