"""patch_api.py LIVE_API OUT_API — register the ARD door in a live api.py (aicom 48502f8d3).

The live hubs run two api.py variants (apex ccd534b4f320, the other five a344cb9f4760), neither equal to main, so the
patch is applied to the live file at two anchors instead of copying main's file. Refuses an unknown variant or a
missing anchor rather than guessing.
"""
import hashlib
import sys

KNOWN = {"ccd534b4f320", "a344cb9f4760"}
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
if sha not in KNOWN:
    sys.exit(f"api.py {sha} is not a variant this patch was checked against ({sorted(KNOWN)}) — stop")
imp = "from aimarket_hub.hub_routes import agents as _agents_routes\n"
reg = "        search=search,\n        wellknown_router=wellknown_router,\n    )\n    app.include_router(wellknown_router)\n"
for anchor in (imp, reg):
    if text.count(anchor) != 1:
        sys.exit(f"anchor found {text.count(anchor)} times, expected once: {anchor!r} — stop")
text = text.replace(imp, imp + "from aimarket_hub.hub_routes import ard as _ard_routes\n")
text = text.replace(reg, (
    "        search=search,\n        wellknown_router=wellknown_router,\n    )\n"
    "    # Agent Resource Discovery (IETF DAWN drafts): the catalogue in ARD formats, read-only.\n"
    "    _ard_routes.register(\n"
    "        app=app,\n        config=config,\n        db=db,\n        search=search,\n"
    "        signer=signer,\n        wellknown_router=wellknown_router,\n    )\n"
    "    app.include_router(wellknown_router)\n"))
open(dst, "w", encoding="utf-8").write(text)
print(f"api.py {sha} -> {hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}")
