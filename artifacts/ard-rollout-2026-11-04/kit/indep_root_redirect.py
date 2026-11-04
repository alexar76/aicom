"""indep_root_redirect.py NGINX_FILE — the ARD well-known URI at independentai.network's origin.

The hub lives under /hub, so its manifest is /hub/.well-known/ard.json; draft-jimenez-dawn-ard-initial-contact-00
4.3.1 has clients fetch https://<origin>/.well-known/ard.json and follow at most one redirect. One exact location
answers that with a single 302 to the hub's manifest. Refuses to run twice or on an unexpected file.
"""
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
anchor = "  location = /hub { return 301 /hub/; }\n"
if text.count(anchor) != 1:
    sys.exit(f"anchor found {text.count(anchor)} times — stop")
if "/.well-known/ard.json" in text:
    sys.exit("an ARD location already exists — stop")
block = (
    "  # Agent Resource Discovery (aimarket-hub docs/ard.md, 2026-11-04): the hub's ARD manifest is under /hub; an ARD\n"
    "  # client asks the origin and follows one redirect (draft-jimenez-dawn-ard-initial-contact-00 4.3.1).\n"
    "  location = /.well-known/ard.json { return 302 https://independentai.network/hub/.well-known/ard.json; }\n"
)
open(path, "w", encoding="utf-8").write(text.replace(anchor, anchor + block))
print("inserted")
