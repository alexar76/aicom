"""Patch terminal-home.html so the unapproved-hub rail follows the hub, not the moment the tab was opened.

ensurePeers() answered from its cache for the life of the page, so a peer approved elsewhere stayed under
"Unapproved hubs" until a reload (modelmarket.dev, 2026-11-02). Now the cache is good for a minute: poll() (every
3 s) asks again after that, also after a failed request, and the rail is redrawn only when the queue changed,
so an open preview or a typed search survives. Two variants are in production; both get the same change.
Usage: python3 patch.py IN OUT
"""
import sys

src = open(sys.argv[1], encoding="utf-8").read()
DECL = """  let peersCache = null;
"""
NEW_DECL = """  let peersCache = null;
  // A tab left open kept its first answer: a peer approved elsewhere stayed under "Unapproved hubs" until a reload.
  // poll() asks again once the list is a minute old (after a failed try too, not every 3 s); the rail is redrawn
  // only when the queue changed, so an open preview or a typed search survives the refresh.
  const PEERS_TTL_MS = 60000;
  let peersTriedAt = 0;
  let pendingKey = '';
"""
assert src.count(DECL) == 1, "peersCache declaration"
src = src.replace(DECL, NEW_DECL, 1)

GUARD = "    if (peersCache) return peersCache;\n"
assert src.count(GUARD) == 1, "cache guard"
if "    if (peersRequest) return peersRequest;\n" in src:          # variant with a shared in-flight request
    old = GUARD + "    if (peersRequest) return peersRequest;\n"
    new = ("    if (peersCache && Date.now() - peersTriedAt < PEERS_TTL_MS) return peersCache;\n"
           "    if (peersRequest) return peersRequest;\n"
           "    peersTriedAt = Date.now();\n")
    assert src.count(old) == 1
    src = src.replace(old, new, 1)
    render_old = "      peersForFed = peersCache;\n      renderKnockRail();\n"
    render_new = ("      peersForFed = peersCache;\n"
                  "      const key = JSON.stringify(pendingCache);\n"
                  "      if (key !== pendingKey) { pendingKey = key; renderKnockRail(); }\n")
else:                                                            # older variant: one fetch, no shared request
    new = ("    if (peersCache && Date.now() - peersTriedAt < PEERS_TTL_MS) return peersCache;\n"
           "    peersTriedAt = Date.now();\n")
    src = src.replace(GUARD, new, 1)
    render_old = "    peersForFed = peersCache;\n    renderKnockRail();\n"
    render_new = ("    peersForFed = peersCache;\n"
                  "    const key = JSON.stringify(pendingCache);\n"
                  "    if (key !== pendingKey) { pendingKey = key; renderKnockRail(); }\n")
assert src.count(render_old) == 1, "render call"
src = src.replace(render_old, render_new, 1)
open(sys.argv[2], "w", encoding="utf-8").write(src)
print("patched", sys.argv[2])
