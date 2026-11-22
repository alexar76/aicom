"""Fix the capability search that froze the hub page (2026-11-22).

The catalogue panel loads 250 capabilities a page. Typing in its search box called drainCaps(), a loop
`while (capsHasMore) await loadCapsPage(false)`. loadCapsPage() returned at once when a page was already loading, so a
second keystroke (or a scroll) while the first page request was in flight turned the loop into an endless chain of
resolved promises: the tab froze, and the pending request could never finish. It showed once a hub listed more than
250 capabilities (modelmarket.dev 310, hub.modelmarket.dev 310, hunt 280, hub.attestedmemory.net 284).

Now one page request at a time is shared by every caller, drainCaps() stops when a page adds nothing, and only the
latest keystroke repaints. The three production variants carry the same code, so one patch fits all.
Usage: python3 patch.py IN OUT
"""
import sys

src = open(sys.argv[1], encoding="utf-8").read()

def swap(old: str, new: str, what: str) -> None:
    global src
    assert src.count(old) == 1, f"{what}: expected once, found {src.count(old)}"
    src = src.replace(old, new, 1)

swap("""  async function loadCapsPage(reset) {
    if (capsLoadingMore) return;
    if (!reset && capsCache && !capsHasMore) return;
    capsLoadingMore = true;
    try {
""", """  // One page request at a time, shared by every caller (a keystroke, a scroll, the drawer opening). Returning early
  // while a page was loading made drainCaps() spin on resolved promises and froze the tab (2026-11-22).
  let capsPageRequest = null;
  function loadCapsPage(reset) {
    if (capsPageRequest) return capsPageRequest;
    if (!reset && capsCache && !capsHasMore) return Promise.resolve();
    capsLoadingMore = true;
    capsPageRequest = loadCapsPageNow(reset).finally(() => { capsLoadingMore = false; capsPageRequest = null; });
    return capsPageRequest;
  }

  async function loadCapsPageNow(reset) {
    {
""", "loadCapsPage head")

swap("""      capsTotal = page.total;
      capsHasMore = page.has_more;
    } finally {
      capsLoadingMore = false;
    }
  }

  async function drainCaps() {
    while (capsHasMore) await loadCapsPage(false);
  }
""", """      capsTotal = page.total;
      capsHasMore = page.has_more;
    }
  }

  async function drainCaps() {
    // A page that adds nothing ends the loop: a hub that keeps answering has_more must not keep the tab busy.
    for (let pages = 0; capsHasMore && pages < 40; pages++) {
      const before = (capsCache || []).length;
      await loadCapsPage(false);
      if ((capsCache || []).length === before) break;
    }
  }
""", "loadCapsPage tail and drainCaps")

swap("""  catFind.addEventListener('input', async () => {
    if (catMode !== 'caps' || !capsCache) return;
    if ((catFind.value || '').trim() && capsHasMore) {
      try { await drainCaps(); } catch { /* keep whatever we have */ }
    }
    paintCaps();
  });""", """  let capsFindSeq = 0;
  catFind.addEventListener('input', async () => {
    if (catMode !== 'caps' || !capsCache) return;
    const seq = ++capsFindSeq;
    if ((catFind.value || '').trim() && capsHasMore) {
      paintCaps(); // matches among what is loaded now, at once
      try { await drainCaps(); } catch { /* keep whatever we have */ }
      if (seq !== capsFindSeq) return; // a later keystroke paints
    }
    paintCaps();
  });""", "search input handler")

open(sys.argv[2], "w", encoding="utf-8").write(src)
