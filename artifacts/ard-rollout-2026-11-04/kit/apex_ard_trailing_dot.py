"""apex_ard_trailing_dot.py NGINX_FILE — "https://modelmarket.dev/.well-known/ard.json." still opens the manifest.

The 2026-11-04 DAWN list mail ends a sentence with the manifest URL, and a mail client may keep the full stop in the
link. One exact location redirects that spelling. Refuses to run twice.
"""
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
anchor = "    location ^~ /.well-known/erc-8004/ {\n"
if text.count(anchor) != 1:
    sys.exit(f"anchor found {text.count(anchor)} times — stop")
if "/.well-known/ard.json." in text:
    sys.exit("already patched — stop")
rule = (
    "    # The ARD manifest URL with a sentence's full stop glued on by a mail client (DAWN list mail, 2026-11-04).\n"
    "    location = /.well-known/ard.json. { return 301 https://modelmarket.dev/.well-known/ard.json; }\n"
)
open(path, "w", encoding="utf-8").write(text.replace(anchor, rule + anchor))
print("inserted")
