# New Runtime / histor — bounded recheck, 28 October 2026

Read 14:32 Europe/Moscow. This source was already in `docs/external-presence-2026-10-24.ru.md`; it is an updated counter, not a new mention.

- https://newruntime.com/readers/histor/ : HTTP 200, 49,372 bytes, SHA-256 `c27e666f8eb88e394c48f7a49f484f2f35b8da87b465de7bcad8ab6ed7898666`.
- https://newruntime.com/readers/histor.json : HTTP 200, dossier still identifies operator as unknown, confidence low, no documentation URL, researched 2026-10-23. Its only source link is the different `https://histor.dev/`, which it explicitly refuses to attribute. No direct modelmarket.dev/alexar76 attribution appears in the dossier.
- Baseline as of 2026-10-28 10:01:18.935 UTC: 183 requests, 32 active days, first seen 2026-09-26 11:12:56.808 UTC, last seen 2026-10-28 06:52:45.098 UTC. The complete observation window is 98 days, distinct from the 32 days on which this family appeared. Compared with the supplied 27 October baseline 171/31: +12 requests, +1 active day.
- Its https://newruntime.com/bot-traffic-history.json response generated at 2026-10-28 11:31:05.892 UTC independently sums to the same 183 family requests over 32 days. Sanitized labels include `histor/0.1.0`, later versions through `histor/0.4.2`, and read-only `initialize + tools/list`; URLs within labels are redacted.
- Identity method: family is assigned by the normalized client-supplied User-Agent token. It is not operator authentication; the site's identity note says a family label is a claim and anyone can claim it. The privacy page says its request/label counts do not prove a human reader, indexing, training, recommendation or intent.
- Local `histor/histor/mcpclient.py:48` supplies a `histor/{version}` UA with a public `histor.modelmarket.dev/#crawler` URL and read-only operations. Behaviour and versioned name are consistent with our crawler; public evidence redacts the URL, and New Runtime does not itself bind the operator. Conclusion: **probably related to our HISTOR, operator not publicly attributed**.

Only the dossier, its linked history, privacy and reader index were read. No contact or change was made. Short extracts, hash/status metadata and matching histor-only traffic records retained in `culture-evidence/newruntime-facts.json` and `newruntime-extra-facts.json`; unrelated complete traffic history was not retained.
