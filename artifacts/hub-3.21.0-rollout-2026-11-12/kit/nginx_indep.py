#!/usr/bin/env python3
"""independentai.network: the hub is under /hub, so the origin's /.well-known/ai-catalog.json redirects there,
as the ARD manifest already does. Keeps a dated copy outside sites-enabled; the caller runs `nginx -t` and reloads.
Running it twice changes nothing."""
import os
import shutil
import sys

PATH = os.path.realpath("/etc/nginx/sites-enabled/independentai.network")
text = open(PATH, encoding="utf-8").read()
if "ai-catalog" in text:
    print("already has the AI Catalog redirect")
    sys.exit(0)
anchor = "  location = /.well-known/ard.json { return 302 https://independentai.network/hub/.well-known/ard.json; }\n"
assert text.count(anchor) == 1, "the ARD redirect is not where it was"
line = ("  # AI Catalog (aimarket-hub docs/ai-catalog.md, 2026-11-12): the hub's catalogue is under /hub; a client that asks\n"
        "  # the origin's well-known URI follows one redirect.\n"
        "  location = /.well-known/ai-catalog.json { return 302 https://independentai.network/hub/.well-known/ai-catalog.json; }\n")
os.makedirs("/root/nginx-backups", exist_ok=True)
shutil.copy2(PATH, "/root/nginx-backups/independentai.network.bak-20261112-aicatalog")
open(PATH, "w", encoding="utf-8").write(text.replace(anchor, anchor + line))
print("patched", PATH, "; copy at /root/nginx-backups/independentai.network.bak-20261112-aicatalog")
