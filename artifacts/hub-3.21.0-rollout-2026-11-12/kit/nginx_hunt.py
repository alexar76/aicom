#!/usr/bin/env python3
"""hunt.modelmarket.dev: send the AI Catalog paths to the hub (the site's `location /` is the game).

Adds exact locations for /.well-known/ai-catalog.json and ^~ /ai-catalog/ after the ARD registry block, and the
ai-catalog Link relation beside the ARD one on `location = /`. Keeps a dated copy of the file; the caller runs
`nginx -t` and reloads. Running it twice changes nothing.
"""
import shutil
import sys

PATH = "/etc/nginx/sites-available/hunt.modelmarket.dev"
text = open(PATH, encoding="utf-8").read()
if "ai-catalog" in text:
    print("already has the AI Catalog locations")
    sys.exit(0)
PROXY = """        proxy_pass http://signal_hunt_hub;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
"""
anchor = "    location ^~ /ard/ {\n" + PROXY
assert text.count(anchor) == 1, "the ARD registry block is not where it was"
block = ("    # AI Catalog (aimarket-hub docs/ai-catalog.md, 2026-11-12): the catalogue MCP Server Cards point at, the\n"
         "    # nested catalogue of capabilities, the identifiers of peers' capabilities and the signer profiles.\n"
         "    location = /.well-known/ai-catalog.json {\n" + PROXY +
         "    location ^~ /ai-catalog/ {\n" + PROXY)
link = """        add_header Link '<https://hunt.modelmarket.dev/.well-known/ard.json>; rel="ard"' always;\n"""
assert text.count(link) == 1, "the Link header line is not where it was"
new_link = link + """        add_header Link '<https://hunt.modelmarket.dev/.well-known/ai-catalog.json>; rel="ai-catalog"' always;\n"""
shutil.copy2(PATH, PATH + ".bak-20261112-aicatalog")
open(PATH, "w", encoding="utf-8").write(text.replace(anchor, anchor + block).replace(link, new_link))
print("patched; copy at", PATH + ".bak-20261112-aicatalog")
