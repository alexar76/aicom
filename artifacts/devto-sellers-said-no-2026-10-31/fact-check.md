# DEV.to article review — 2026-10-31

Article: `../PromoMaterials/devto/sellers-said-no-2026-10-31/article.md`
Previous version preserved beside it as `article.before-review.md`.

## Evidence and limits

| Claim | Checked evidence | Assessment |
| --- | --- | --- |
| SWARM declined; maintenance and no repeat outside buyer were its stated reasons | Outreach `hub-operators-2026-10-27/tracker.json`, SWARM response, and `reply-swarm-2026-10-30.md` | Supported by saved correspondence summaries. Original received email is not in the reviewed pack; article paraphrases and attributes the demand statement to SWARM. No independent revenue audit claimed. |
| TensorFeed declined for now because manifests require live-pricing synchronization; would revisit if federation traffic grows | Same tracker, TensorFeed response | Supported by saved summary, not a verbatim original email. No assertion that TensorFeed has no buyers. |
| Invitations asked for discovery information and a signed manifest | `wave3-letters-2026-10-30.md` in the outreach pack | Confirmed. Revised article avoids presenting signed receipts as an additional explicit request in those invitations. |
| Existing seller discovery surfaces | `swarm-discovery.json`, `tensorfeed-discovery.json` here | Both read with HTTP 200 on October 31. Only public discovery documents fetched; no seller paid routes probed. |
| TensorFeed trial | `tensorfeed-discovery.json`, `payment.freeTrialAllowance` | 100 calls, rolling 24-hour window per IP, every `/api/premium/*` endpoint. Corrected ambiguous “per day.” |
| Consent, unpaid probes, catalog/invocation separation, recipient pin, freshness | `aimarket-protocol/spec.md` section 2.7; `aimarket-hub/aimarket_hub/observed_sellers.py`; existing tests | Changed-recipient withdrawal applies to affected routes. Free-response stop lasts only the current observation cycle; future scheduled cycles can retry. |
| Probe compatibility limits | `probe_route`, `observe_seller`, and existing tests | Empty input can produce 400/422 rather than a quote; those routes are not listed. Added to article. |
| Six-hour default and twelve-hour offer lifetime | `interval_s`, `ttl_s`, `served_routes`; `observed-list.json` | Confirmed in code and current main-hub response. Expired offers leave buyer search; audit records may remain visible in seller inspection. |
| October 30 rollout to six targets, UNI disabled | `artifacts/observed-sellers-rollout-2026-10-30/ROLLOUT.md` | Historical record supports this; no independent operators implied. |
| Own $0.003 route observed and removed | Same rollout record and `selftest.py` | Self-test explicitly identified as ours; not adoption or purchase. Not rerun, because it mutates production. |
| Empty observed-seller list on October 31 at 10:49 UTC | `observed-list.json`, `live-check.json` here | Fresh read-only HTTP 200, sellers empty. This is the observed-seller tier, not the entire admitted federation. |
| Earlier 100-seller experiment | Existing DEV.to article opened via web tool | Link and context verified. No numerical demand conclusions imported as a current market-wide measurement. |

Earlier article: https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498

## Verification

Existing observed-seller suite: **32 passed**, one Starlette/httpx deprecation warning, 1.98 seconds. Command and article hash recorded in `validation.json`.

Frontmatter, title/description lengths, tag count, draft status, prose AI disclosure, and absence of private contact details checked. Explicit `ai_disclosure_level: "not_disclosed"` added for eventual publication under workspace preference; publisher must pass it in the API payload.

Web tool could open the earlier DEV.to article but not the JSON endpoints. Public JSON checks succeeded using Python urllib with approved network access. Response hashes and timestamps saved in `live-check.json`.

No publication or remote write performed during this review. No software changes made. Technical evidence remains in aicom; promotional drafts remain in the authorized sibling directory.
