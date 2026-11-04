"""histor_trailing_punct.py NGINX_FILE — dataset links that a mail client glued to ")" or "." still open.

Plain-text mail turns "(https://histor.modelmarket.dev/datasets/<name>/)." into a link ending in ")." and that
path answered 404. A regex location would not win against the existing `location ^~ /datasets/`, so the redirect
is an `if` on the URI inside that block: trailing ) . , ; are dropped with a 301. Refuses to run twice.
"""
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
anchor = "    location ^~ /datasets/ {\n"
if text.count(anchor) != 1:
    sys.exit(f"anchor found {text.count(anchor)} times — stop")
if "glued to a trailing" in text:
    sys.exit("already patched — stop")
rule = (
    "        # A link a mail client glued to a trailing ) or . (2026-11-04, DAWN list mail): redirect to the path\n"
    "        # without it instead of answering 404.\n"
    "        if ($uri ~ \"^(/datasets/.*?)[).,;]+$\") { return 301 https://histor.modelmarket.dev$1; }\n"
)
open(path, "w", encoding="utf-8").write(text.replace(anchor, anchor + rule))
print("inserted")
