# Why 131 endpoints answered HISTOR 402, and what robots.txt content signals say (2026-11-02)

Owner: «делаем все честно и безопасно». HISTOR pays for no read and keeps its user agent; this only asked why.

**One honest read each** (`count_402.py`). HISTOR's own reader from the worktree, with its own user agent
`histor/0.5.3 (+https://histor.modelmarket.dev/#crawler; ...)`. robots.txt was consulted first, nothing was paid,
and reads ran one at a time per host. The endpoints were the 131 remote ones whose last read in the 2 Nov snapshot
was 402.

| Now | Endpoints |
|---|---:|
| `http-402`, another reason | 78 |
| `robots-disallowed` (their robots.txt now keeps HISTOR out) | 27 |
| `payment-required`: an x402 endpoint, every call paid | 21 |
| `ok`: readable again | 4 |
| `pay-per-crawl`: the site charges crawlers per read | 1 (api.groundtruths.xyz, "USD 0.01") |

A dozen of the 78 were looked at with one more request each:
- **Their host's billing** ("Payment required"), on 6 hosts.
- **base44 apps:** "Functions are blocked - app owner lacks backend functions capability", on 4.
- **A free tier's daily cap:** "Free tier allows 1 hit per endpoint per UTC day", on 1.

None of these charges for reading. HISTOR now keeps such a message as the detail of `http-402`.

**Content signals** (`content_signal.py`, a read of the stored `robots_txt` rows).
- **Use.** 2,985 of the 16,413 robots.txt files HISTOR has read use Cloudflare's `Content-Signal`.
- **Opt-outs.** 1,369 say `ai-train=no`, 28 `ai-input=no` and 20 `search=no`.
- **HISTOR's position.** It does none of the three: it records tool definitions as a public log. It does publish them
  as datasets that others may train on. What to do about that is the owner's decision.
