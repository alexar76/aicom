"""Port the apex-only HISTOR/WARDEN line (aicom terminal-home.html on this branch) onto the production variant.

Usage: python3 patch.py PROD_FILE MAIN_EDITED_FILE OUT_FILE
Takes the two inserted blocks from the edited main file and puts them at the same anchors in the
production file. Each anchor must occur exactly once, and nothing else may change.
"""
import sys

prod = open(sys.argv[1], encoding="utf-8").read()
edited = open(sys.argv[2], encoding="utf-8").read()

CSS_ANCHOR = "  .hero .trust-line { font-size: clamp(16px, 2.2vw, 20px); max-width: 680px; margin: 0 auto 8px; }"
CSS_START = "  /* modelmarket.dev only (pages.py drops the block on every other hub)"
HTML_ANCHOR = '  <header class="hero">\n    <div class="eyebrow">'
HTML_START = "    <!-- apex-only -->"
HTML_END = "    <!-- /apex-only -->\n"

css_block = edited[edited.index(CSS_START):edited.index(CSS_ANCHOR)]
html_block = edited[edited.index(HTML_START):edited.index(HTML_END) + len(HTML_END)]
for anchor in (CSS_ANCHOR, HTML_ANCHOR):
    assert prod.count(anchor) == 1, anchor
assert "apex-tools" not in prod
new = prod.replace(CSS_ANCHOR, css_block + CSS_ANCHOR, 1)
new = new.replace(HTML_ANCHOR, '  <header class="hero">\n' + html_block + '    <div class="eyebrow">', 1)
assert len(new) == len(prod) + len(css_block) + len(html_block)
open(sys.argv[3], "w", encoding="utf-8").write(new)
print("ok", len(css_block), len(html_block))
