# WARDEN threshold study: keep 8/10, repair credential indexing

**Disclosure:** I maintain WARDEN in the alexar76 ecosystem. This experiment, analysis and report were prepared with substantial generative-AI assistance. This is a maintainer's evaluation of our own code with constructed fixtures, not an independent audit or a measurement of production traffic.

Date: 2026-10-25. **Status: the final source change is local and unreleased.**

## Question and decision

[jkming asked](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ion2) whether WARDEN should recognize shorter secret fragments embedded inside other words. We compared non-hexadecimal windows of 6, 7 and 8 characters; the hexadecimal window remained 10 throughout.

We retained 8/10 and fixed a narrower indexing defect. This improved recognition without changing the decisions on the ordinary request sample. It does **not** make an embedded 6-character fragment reliably detectable.

## Full guard results

`ask` pauses execution for operator approval; `deny` rejects it; `pass` allows it through this guard. After a credential and external text have been read, the evaluated guard requires approval for supported outbound/MCP calls unless an exact, independently reviewed public-request rule applies. No real requests were sent.

| Variant | Attack requests | `pass` | `ask` | `deny` |
| --- | ---: | ---: | ---: | ---: |
| Original, 6 | 14,400 | 0 | 7,145 | 7,255 |
| Original, 7 | 14,400 | 0 | 10,464 | 3,936 |
| Original, 8 | 14,400 | 0 | 11,555 | 2,845 |
| Final, 8 | 14,400 | 0 | 10,838 | 3,562 |

The fix moved 717 requests from `ask` to `deny`: 342 Stripe-like and 375 GitHub-like cases. These were **not 717 newly prevented automatic transmissions**: approval already stopped them. All previous hard denials remained.

Without the general credential boundary, the final leak/fragment detector alone returned no match on 8,709 attack requests. Fingerprint recognition cannot replace that boundary.

## Ordinary requests and collision controls

There were 7,680 distinct ordinary requests, each tested in both profiles. Every variant asked about all 7,680 in the strict default profile. With exact reviewed public-request rules, all 7,680 passed, with no additional questions or hard denials. These are the same inputs in two profiles, not independent samples. The default profile still imposes substantial review work.

Direct scanning with 480 calibration credentials covered 3,575 unique public files, 39,259 excerpts and 22,056,276 normalized letters and digits. Window 6 produced 79 exact substring matches in 31 excerpts; windows 7, 8 and final 8 produced none. These are substring matches, not truncated-hash collisions or a call-level false-positive rate.

We replayed the 31 matching credential/excerpt pairs through the actual hook with exact public-request rules. Window 6 falsely denied all 31; the other variants allowed 29 and asked about 2. These controls were deliberately selected because they collided; their proportions do not estimate population rates.

A separate known counterexample reproduced a false denial at 7: ordinary JSON/health text normalized to include `mit3okt`, matching a synthetic PEM-like credential. Windows 6 and 7 denied it; original and final 8 allowed it. A zero count in the new corpus therefore does not establish that 7 is safe to deploy.

## The indexing repair

The old index skipped every initial letter until the first digit. A provider-prefixed key with digits near its end could consequently have no eligible 8-character windows. The final change starts earlier after recognized provider prefixes, retaining the mixed-letter/digit condition and existing DER and generic-value exclusions.

We rejected a broader candidate: after reading `AcmeIntegrationToken2026`, it falsely denied the reviewed public text `Public build Token2026`. The final version preserves the original decision on this control.

All old fingerprints remained for all 960 credentials: 0 lost, 70,466 → 71,612 entries, with expansion for 279 credentials. Existing sessions need a credential reread to acquire new windows. For 960 embedded-6 fixtures, final 8 still produced 960 requests for approval and 0 hard denials.

## Method and limits

We used 960 synthetic credentials across eight formats and two deterministic seeds, with 15 attacks per credential. Corpus partitions did not overlap between seeds. Attack positions deliberately exercised the indexing defect; observed proportions are fixture-dependent.

All empirical corpus and guard measurements ran in networkless, restricted Linux Docker containers, **without gVisor**. Separately, 1,156 code tests passed locally on macOS. The existing gate had 26 tool attacks with 0 fully delivered, plus 2 answer-only scenarios. These checks support the narrower repair and retained thresholds; they do not establish universal safety or a production false-positive rate.
