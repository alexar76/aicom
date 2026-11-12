# Драфт-ответ на кросс-чек alexar76 в #3431 (2026-10-26)

Куда: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3431
Якорь: обычный комментарий (уведомление через @alexar76).
Постить ПОСЛЕ пуша исправленных пинов (ссылки должны резолвиться на main).

---

## Текст (EN)

Verified on our side, and the three rows you flagged were real: the 2026-10-24 automation re-pin wrote those snapshots over dirty stands, so the 1.16/1.17 shopify pins carried `validate_component_codeblocks`/`validate_graphql_codeblocks` from the 1.14.4 install, the currents 2.6.1/2.7.0 pins carried `currents-get-affected-executions` (whose 2.3.3-era entry matches your hash), and the netlify 1.18.0/1.20.0 `netlify-coding-rules` entries were byte-identical to 1.14.0. All six re-pinned from clean stands today; corrected state: shopify 1.16.0 and 1.17.0 serve exactly 5 tools (the two validators correctly GONE), currents 2.6.1/2.7.0 = 39/43 tools without the phantom, netlify 1.18.0/1.20.0 carry coding-rules with the `reference` property. Per-server corrections and a census erratum are up: https://github.com/Paraphern/rugsnare/blob/main/docs/servers/shopify.md

Same artifact class as our supabase correction of 13 Oct (stale entries surviving a re-pin), and your field-level detail was precise enough to reproduce the diagnosis without guessing — that is the cross-check working exactly as intended. 25 of 34 identical field-by-field plus 318/318 annotations agreeing is the number we'll cite for "two independent captures, one contract".

Two of your explained rows deserve a wider audience than this thread:

- **mongodb (launch leg):** the same tarball serves 9 more write tools when launched bare than with our `--readOnly` entry, and describes `connect`/`disconnect` differently. What a server serves is a function of (version, launch args, network reachability) — a pin that records only the version verifies one leg of three. Our pins carry the launch entry (`command`, `args`, `env`) for exactly this reason.
- **netlify (network leg):** `netlify-coding-rules` registers only when the startup topic fetch succeeds — your no-network sandbox and our scan saw *different servers* from the same version, both honestly.

Both argue for one clause beyond the docs sentence under discussion: whatever you record, record how you launched it.

The MTL/1 correction is accepted and folded into the comparison doc verbatim in substance (toolExtrasDigest covers annotations, `_meta`, title, icons, execution and vendor fields; SHA-256 over sorted-key JSON, not JCS; `extras_changes` with the destructive-direction escalation): https://github.com/Paraphern/rugsnare/blob/main/audits/drift-watch/comparison-dominion-captures.md

And thank you for closing the version-attribution gap on your side — `package_observations.jsonl.gz` makes the next join cheaper than this one was.
