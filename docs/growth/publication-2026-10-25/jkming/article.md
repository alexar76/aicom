---
title: "We Kept WARDEN's 8/10 Thresholds and Fixed Its Credential Index"
published: false
description: "A reader asked whether shorter secret fragments justified lower thresholds. We compared 6/7/8, reproduced false blocks, and fixed a narrower indexing defect."
tags: mcp, security, opensource, ai
---

**AI disclosure — Fully Autonomous:** AI agents prepared the experiment design, implementation, analysis and this article under the project owner’s direction. I maintain WARDEN and HISTOR in the alexar76/AICOM ecosystem. These are our deterministic tests of our own code, not an independent audit or measurements of production traffic.

We kept WARDEN's strong matching windows at eight characters for non-hex values and ten for hex values. We found and fixed a credential-indexing defect instead. The patch is implemented locally; it has not been released or deployed.

The investigation started with [jkming's comment on our earlier red-team article](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ion2): could we catch six-character pieces hidden inside longer words by lowering the threshold, or would ordinary text produce too many accidental matches?

## First distinguish a match from an executed call

The tested local guard has a conservative boundary: after reading a credential and outside text, a supported outbound or MCP call needs confirmation unless an exact, independently reviewed public request has permission.

`ask` pauses execution for the operator. `deny` refuses it. `pass` permits it through this guard. No real outbound calls were sent during these experiments.

That distinction matters: improving a detector can turn a confirmation into a refusal without preventing an additional automatic transmission.

## Comparing the complete hook

We generated 960 synthetic credentials across eight formats: Stripe, GitHub, AWS, Anthropic, hex, base64, JWT, and PEM. Two deterministic seeds supplied 60 values per format each. The JWT/PEM fixtures were format-like strings, not functioning cryptographic credentials.

Each credential received 15 attack requests, covering isolated and embedded fragments, transformations, ten-character fragments, and a complete-key positive control. The original variants differed only in the non-hex window constant; hex remained ten throughout. The final variant added the index fix while retaining 8/10.

| Variant | Attack requests | `pass` | `ask` | `deny` |
| --- | ---: | ---: | ---: | ---: |
| Original, window 6 | 14,400 | 0 | 7,145 | 7,255 |
| Original, window 7 | 14,400 | 0 | 10,464 | 3,936 |
| Original, window 8 | 14,400 | 0 | 11,555 | 2,845 |
| Fixed index, window 8 | 14,400 | 0 | 10,838 | 3,562 |

The fix moved **717 requests from `ask` to `deny`**: 342 with Stripe-like credentials and 375 with GitHub-like credentials. All 2,845 existing denials remained denials. These are improved recognition decisions, not 717 newly prevented automatic transmissions: the old boundary already paused those requests.

The detector alone still returned “no match” for 8,709 attack fixtures after the fix. The complete boundary therefore remains necessary. Even these constructed inputs exceed what fragment recognition reliably identifies.

## Ordinary requests have two different costs

We built 7,680 distinct ordinary requests from public source excerpts and tested each under two profiles. The results were identical in all four variants:

| Ordinary-request profile | `pass` | `ask` | `deny` |
| --- | ---: | ---: | ---: |
| Strict default after credential and outside-text reads | 0 | 7,680 | 0 |
| Exact reviewed public request, with one permission | 7,680 | 0 | 0 |

The strict default asks about every request. That is a substantial usability cost. Exact permissions cover the reviewed full request, including its recipient; a secret match still overrides permission. These are the same 7,680 inputs in two profiles, not 15,360 independent ordinary requests.

Zero denials in this sample did not establish that lower thresholds were safe.

## Accidental substrings outside the ordinary sample

We directly scanned 3,575 unique public files: 39,259 excerpts and 22,056,276 normalized letters and digits. Using the 480 calibration credentials, window six produced 79 exact window matches across 31 excerpts. Windows seven, eight, and the final fixed eight produced none.

These were identical normalized substrings, not collisions in a truncated cryptographic hash, and not a per-call false-positive rate.

We replayed all 31 deliberately selected credential/excerpt pairs through the complete hook with exact public-request permission. Window six falsely denied all 31. Windows seven, eight, and fixed eight each allowed 29 and asked about two. Selection by a known match makes these useful controls, not a representative traffic sample.

Seven also had a concrete counterexample from our earlier generator. Ordinary JSON `{"limit":3}` beside the health-check text `健康检查返回 "ok":true` normalized to a string containing `mit3okt`. That seven-character substring appeared in a synthetic PEM-like credential. The real hook denied the reviewed public request at six and seven, and allowed it at eight, including the final index.

The new corpus's zero matches at seven did not erase that reproduced failure.

## The narrower indexing defect

The old index skipped every leading letter of a normalized credential until the first digit. That avoided shared format prefixes, but also skipped useful secret material.

A GitHub-like `ghp_` value with a long alphabetic payload and four trailing digits could consequently have no eight-character windows indexed. An embedded eight-character secret fragment then reached only the general confirmation boundary.

For recognized provider prefixes, the patch can start indexing immediately after the prefix. Eligible windows still require both letters and digits. Generic values retain their conservative starting position; DER exclusions and the hex threshold stay unchanged. Recognizing a prefix does not validate a real provider credential.

We rejected a broader candidate that also expanded generic values: after reading `AcmeIntegrationToken2026`, it falsely denied the reviewed public text `Public build Token2026`. The original and final builds both permit that control.

Across all 960 credentials, the final index preserved every old fingerprint: 70,466 became 71,612, with additions for 279 credentials and zero losses. Existing sessions need another credential read to gain the new windows; hashes cannot reconstruct skipped secret text.

## What remains unresolved

For the 960 single six-character fragments embedded in longer words, the final eight-character variant denied none and asked about all 960. It does not solve reliable recognition of those substrings. Window six denied 347 and asked about 613, while also producing the false blocks above.

All corpus and hook measurements ran on a Linux server in networkless Docker containers, with a read-only root and source, an unprivileged user, dropped capabilities, and CPU/memory limits. **This experiment did not use gVisor.** We reset state before each attack, matched input hashes across variants, and used separate calibration/holdout file partitions. Fragment positions deliberately targeted the old indexing weakness.

The final build passed the existing gate's 26 tool-attack scenarios with zero complete deliveries; two additional scenarios concern answers only. Separately, 1,156 local macOS code tests, build, and typecheck passed.

These results support keeping 8/10 and fixing the index on these fixtures. They establish neither a global optimum nor a zero production false-positive rate. Human approval decisions, long sessions with multiple credentials, adaptive attackers, and all possible encodings remain outside this measurement.
