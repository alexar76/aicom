"""Read-only public verification of the deployed release; no payment calls."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
BASE = "https://modelmarket.dev"


def read(path, raw=False):
    with urlopen(BASE + path, timeout=45) as response:
        assert response.status == 200
        body = response.read()
    return body if raw else json.loads(body)


before = json.loads((ROOT / "public-before.json").read_text())
well_known = read("/.well-known/ai-market.json")
assert well_known["hub_version"] == "3.17.0", well_known.get("hub_version")
signer_fields = [k for k in before["well_known"]["body"] if "key" in k]
assert signer_fields, "The baseline must contain a public signing key"
for field in signer_fields:
    assert well_known.get(field) == before["well_known"]["body"][field], field

html = read("/", raw=True)
assert b"function searchEvidence(" in html and b"function renderObserved(" in html
dictionary = read("/hub-ui-i18n.json")
for language in ("en", "ru", "es", "fr", "zh"):
    assert dictionary["ui"][language]["search_observed"]
    assert dictionary["ui"][language]["evidence_signer"]

searches = {}
for intent in ("weather", "check an x402 payment route", ""):
    answer = read("/ai-market/v2/search?" + urlencode({"intent": intent, "limit": 0}))
    rows = answer["matches"]
    for row in rows:
        evidence = row["evidence"]
        assert evidence["kind"] in {"signed_catalogue", "local_catalogue", "catalogue_unrecorded"}
        if evidence["kind"] == "signed_catalogue":
            assert all(evidence.get(k) for k in ("signer", "signer_public_key", "checked_at", "checked_by"))
    searches[intent or "browse"] = answer
assert any(m["evidence"]["kind"] == "signed_catalogue" for m in searches["weather"]["matches"])

plugins = read("/ai-market/v2/plugins")
read("/mcp", raw=True)
for path in ("/operator", "/plugins/demo", "/studio/"):
    read(path, raw=True)
observed = read("/ai-market/v2/federation/observed-sellers")
receipt = {
    "checkedAt": datetime.now(timezone.utc).isoformat(),
    "version": well_known["hub_version"],
    "signingIdentityPreserved": True,
    "htmlSha256": hashlib.sha256(html).hexdigest(),
    "fiveLanguages": True,
    "searches": searches,
    "plugins": plugins,
    "observed": observed,
    "evidenceCounts": dict(Counter(m["evidence"]["kind"] for m in searches["browse"]["matches"])),
}
(ROOT / "public-after.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: receipt[k] for k in ("version", "signingIdentityPreserved", "fiveLanguages", "evidenceCounts")}, ensure_ascii=False))
