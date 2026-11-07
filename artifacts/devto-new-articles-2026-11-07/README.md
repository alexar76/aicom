# DEV.to scheduling evidence 2026-11-07

User requested writing and DEV.to scheduling of the proposed topics. The user explicitly confirmed all three. The third topic was completed first while that clarification was pending.

## Completed third topic

- Pack: `../PromoMaterials/devto/reviewer-advisory-2026-11-07/` relative to the workspace root's parent arrangement; absolute path `/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/devto/reviewer-advisory-2026-11-07/`.
- DEV.to id: 4993690, author `alexar76` (verified through `/api/users/me`).
- Native publication time: 2026-11-08T14:00:00Z, 15:00 Europe/Amsterdam.
- Body: 1098 words; SHA-256 `222d13012c12f7b4366a4044e6db9bf3b3cd5419a023bfd44a868ef2dad2be9c`.
- Independent editorial review checked original and fixed adapter, tests, November 4 and 6 rollout records. Title was changed to explicitly say drafted advice, avoiding implication that letters were sent.
- Create response confirms `ai_disclosure_level: not_disclosed`; prose discloses AI assistance.
- Author list confirms id, title, body and future time. The author-list API omits AI disclosure fields on this scheduled post; those are verified from the saved create response.
- Public article API returned 404 before the future publication time, as expected.
- DEV.to render has one table and one code block. HTTPS and anchor links verified.

The first verification stopped on an assertion because the author-list response omitted `ai_disclosure_level`. The article had already been created successfully. The verifier was corrected and resumed against saved id 4993690. No duplicate POST and no content update were sent.

No GitHub writes, own-blog deployment or messages to other people were performed. All article text and publication receipts stay in PromoMaterials; this directory contains the technical scheduler and evidence only.

`schedule.py` supports dry run and `--send`, verifies identity, future time, duplicate titles and occupied slots, saves a pending marker before POST, and reconciles existing receipts before any subsequent invocation.

## Completed remaining topics

- WARDEN own marketplace article: DEV.to 4993722, 2026-11-09T14:00:00Z,1053 words,one table and one code block. Independent editorial review passed.
- ARD six-hub article: DEV.to 4993724,2026-11-10T14:00:00Z,939 words,five code blocks. Independent editorial review passed. All four literal Bash blocks executed successfully with curl and jq against public endpoints. No paid capability invoked.
- Final owner-queue readback checked all three unique ids,titles,times,author and exact body hashes. The three create responses confirm not_disclosed; prose AI disclosure retained. All publication receipts remain in PromoMaterials; compact technical summary is final-queue-verification.json.

## Follow-up today article and title correction

The owner asked for an article today and pointed out repeated Our openings in the dashboard. Only the three newly scheduled titles were updated. Bodies and dates were guarded by hashes and reread; older published titles were untouched. The third PUT initially received429; later owner-list reconciliation and a single remaining PUT completed it. No duplicate articles were created. Retitle response receipts stay in each PromoMaterials pack.

A separate HISTOR article, An MCP tool set can gain a digest without changing, is scheduled today2026-11-07at16:00UTC/17:00Amsterdam. DEV.to4993771,1041words,one table,one code block. Independent review confirmed1.1vs1.2chronology and missing-toolset-digest scopes. Two public HISTOR GET filters returned200withcorrectreasons. The avp9-nexus source comment was verified via unauthenticated GitHub API GET and credited; no GitHub write.

Final queue verifies all four ids,titles,exact body hashes and times. Today16UTC; original three remainNov8/9/10at14UTC. All four prose disclosures and not_disclosed response fields retained.

## Full body edit and blog publication requested on November 7 evening

The owner requested a review of all four article bodies for formulaic prose and addition to the blog. Three independent editors rewrote separate articles; the parent rewrote HISTOR. A fourth reading across all four confirmed distinct openings/structures and preservation of material factual limits. Body word counts changed1041→801,1098→752,1053→739,939→866 (973words removed).

Original article bodies remain in each PromoMaterials pack as article.before-editorial-2026-11-07.md. The final English bodies are the single reviewed source copied into modelmarket-blog/posts. Existing DEV.to titles and publication times are preserved. Blog copies are published now; future DEV.to discussion links are withheld until those posts actually publish, using the blog's existing optional-discussion behavior.

The standard blog builder produced70posts. Browser QA covered all4desktop pages plus ARD and HISTOR at390pxmobile: no viewport overflow, broken images or missing resources; code scrolls internally and table fits. Evidence is blog-qa/. After withholding unavailable discussion links, targeted HTML checks confirmed correct CTA presence and a fresh build passed.

Deployment cloned the existing release and overlaid only the four new post directories plus index/feed/sitemap. It verified312existing files unchanged and kept the prior release. Public checks found all4HTML pages byte-identical to the checked build, four valid WebP covers, all4index/feed entries and71sitemap URLs. See editorial-blog-deployment.json and editorial-blog-public-check.json. No GitHub write, authentication change, external message or service restart.

DEV.to updates use existing ids only, preserving published_at and not_disclosed, and set blog canonical+cover URLs after public blog verification. Updates are paced21seconds to respect the observed write limit. Raw editorial responses and final receipts stay in PromoMaterials.
