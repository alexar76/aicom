# Cultural projects and public social mentions — 2026-10-28

Verification window: approximately 14:25–14:31 Europe/Moscow. Compared with `docs/growth/external-mentions-expanded-2026-10-27.ru.md` and `external-signals-2026-10-27.ru.md`.

## Result

No newly attributable independent review, discussion or repost was confirmed for Pantheon/Trace of Refusal, PingBlip, Independent AI/KOVA/AEGIS/CHARON, Emberline/Cite Desks, or Attested Memory in this pass. This is a result of the sources checked, not a claim that no mentions exist anywhere.

## Direct checks and changes

| URL / source | Verified result | Classification |
|---|---|---|
| https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game | Live HTTP 200, direct fetch 2026-10-28 11:29:42 UTC. Exactly one `community_post` (original PingBlip author), no replies. HTML shows 19 views; search cache had 11 then 14. Our own reads can increment views; do not infer audience growth. Original post dated 2026-10-20 07:57 UTC. | Existing first-party announcement on external site. |
| https://pingblip.itch.io/pingblip | HTTP 200. Public `community_post_list` empty, Leave a comment prompt. | Existing first-party game page. |
| https://alexar76.itch.io/the-weight-of-the-answer | HTTP 200. Public comments list empty, Leave a comment prompt. Web tool could not fetch this URL, but the direct read succeeded and is saved. | Existing first-party book page. |
| https://alexar76.itch.io/the-white-on-the-map | HTTP 200. Public comments list empty, Leave a comment prompt. Web tool cache miss; direct read succeeded. | Existing first-party book page. |
| https://alexar76.itch.io/the-right-to-a-shadow | HTTP 200. No public comment section in retrieved HTML. | Existing first-party book page. |
| https://hn.algolia.com/api/v1/search_by_date?query=modelmarket.dev&hitsPerPage=100 | Exactly one indexed hit: known HISTOR Show HN https://news.ycombinator.com/item?id=50193565 , title “Show HN: An open dataset of MCP tool definitions and every change to them”, author alex_artamokhov, 1 point, 2 comments, created 2026-10-22 10:38:35 UTC. | Existing author-submitted HN post; comment count unchanged versus yesterday. |
| HN Algolia exact searches (`typoTolerance=false`, body/title/URL attributes) | alexar76, independentai.network, attestedmemory.net, emberlinedesk.com, pantheon.modelmarket.dev, pingblip each returned 0 hits. “Trace of Refusal” split into terms and returned 26 irrelevant matches; these are excluded, not evidence of mentions. | Bounded public index checks. |
| https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=modelmarket.dev&limit=100&sort=latest and same for pingblip | Both direct GET 403 Forbidden. | Coverage limitation. |
| https://www.reddit.com/search.json?q=%22modelmarket.dev%22&sort=new&limit=100 | Direct GET 403 Blocked. | Coverage limitation. |

## Public web search

32 search queries covered exact names/domains and public indexed HN/Reddit/X/Bluesky, PingBlip press destinations, and culture/product families. No new independent source was confirmed. Known results include itch profiles/collection, automatic itch tag lists, Odel Attested Memory listing, and author DEV posts/DEV mirrors. Registry and analytical pages for modelmarket.dev were passed to the core-research agent rather than duplicated here.

Notable false positives:

- PingBlip Dominican startup covered by INTEC in 2012 and the 2014 ONAPI publication has a different product/operator and is excluded. See https://www.intec.edu.do/notas-de-prensa/item/startup-weekend-santo-domingo-una-empresa-creada-en-54-horas .
- `emberline.app` / Google Play `dev.uptrack.emberline` is Uptrack's parent check-in app, not our `emberlinedesk.com` Fire Evidence Desk.
- CiteNYC furniture “desks” results are unrelated to Cite Desks.
- DNS index neighbour lists containing independentai.network do not establish product coverage or a review.
- Initial HN search for alexar76 without typo suppression returned 290 fuzzy matches (e.g. alexalx666); these were explicitly discarded and exact queries rerun.
- `dev.clauneck.workers.dev/alexar76` is a DEV mirror, not a new independent author.

## Evidence

`culture-evidence/index.json`: 11 direct GET records with UTC timestamps, statuses, byte sizes and SHA-256 hashes; raw successful responses saved beside it. This final index records the successful network reads and 403s. An initial sandboxed attempt failed DNS for all targets, after which a read-only network escalation succeeded.

`culture-evidence/extra-index.json`: 7 extra HN queries. Raw JSON responses include exact parameters and complete results. `fetch.py` and `fetch-extra.py` are read-only public request scripts.

No submissions, publications, messages, account changes, GitHub writes or product mutations were performed.
