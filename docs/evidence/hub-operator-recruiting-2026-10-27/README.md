# Hub operator recruitment checks

Initial observation: 27 October 2026 at 21:43 MSK (18:43 UTC). The accompanying check script made nine unauthenticated public HTTP GET requests. All nine returned HTTP 200. During that initial check, no messages, announcements, invokes, payments or approvals were submitted.

`public-entrypoints.json` preserves response hashes and selected metadata, plus public live-stat, demand and peer responses. These are observations at the stated time; they are not evidence of independent operator ownership or customer revenue.

## Entry points

- Published EN and RU operator quickstart pages and their raw Markdown returned 200. Both raw documents contain quickstart, add and doctor commands.
- PyPI metadata reports `aimarket-hub` 3.16.0, Python >=3.11, Apache-2.0. The live main hub also advertises 3.16.0.
- The peer response lists 20 accepted peers and two pending records. A peer count is not a count of independent operators.
- Stats report 20 invocations and $0.026 invocation volume in the preceding 24-hour window. That volume is not proof of settlement or independent paid demand. `settled_only_volume_usd` is $0.04 and is not scoped to that day.
- Demand export generated at 18:34:28 UTC reports admitted=1, pending=2, crawled_us=3 under its own filtering policy. These counters do not identify beneficial owners and do not override the peer list's semantics.

## Existing integration candidates

The public peer assay for agent-exec dated 15:26:28 UTC reports missing `input_schema` and a string `signature`. The queued origin is `https://agent-exec.448c.org`. Its public [llms.txt](https://agent-exec.448c.org/llms.txt), read through the web tool on the same date, documents free feedback via POST `/feedback`. No POST was performed during the initial review. It describes the service as accountless pay-per-use execution and provides several API operations; advertised capabilities were not invoked in this review.

The Machina dossier at `https://mach402.dev` reports failed discovery and manifest fetches. Its diagnostic contains IP-address URLs, so the observation does not establish whether an ordinary hostname request fails identically. No contact or cross-project identity was inferred from its name.

Local source context:

- `aimarket-hub/aimarket_hub/signing.py:72` records agent-exec and Machina as outside implementations observed in October, and explains the signature object shape.
- `aimarket-hub/aimarket_hub/federation_transport.py:80` supports same-origin POST per-tool x402 endpoints for their manifest shape. Neither should be asked to install the full reference hub or invent a hub-level invoke route merely to address these findings.
- `aimarket-hub/docs/operator-quickstart.md` documents small external demand and distinguishes local startup from public production hosting.
- `aimarket-hub/docs/money-rails.md` documents optional MarketSplitter fees, which are off by default.

## Campaign handoff

Promotional content belongs in sibling `PromoMaterials` under workspace rules. The recruitment pack lives at `../PromoMaterials/outreach/hub-operators-2026-10-27/`, with a DEV draft in `devto/hub-operators-2026-10-27/` and X drafts in `twitter/ready/POST-hub-operators-2026-10-27.txt`. Their initial trackers recorded no contacts or publications. The current tracker records the subsequent authorized feedback described below.

Candidate fit and interest are separate. Official sources used to verify candidate products/contact routes are cited next to each entry in `prospects.ru.md`. Actual integrations, responses, independently controlled hubs and retention remain to be established by the proposed pilot.

## Authorized feedback sent

The user subsequently explicitly instructed us to send the prepared agent-exec message through feedback. A fresh GET of `/feedback` confirmed the request schema and free, unauthenticated POST route. `send_agent_exec_feedback.py` sent the approved file unchanged once, with no redirects or automatic retries; its SHA-256 matched `fbd7816b84c9c3cec1ea3ea7d9500de318dee5bb2107f2e2d669a2a32e66df0f`.

At 22:55:34 MSK on 27 October 2026 (19:55:34 UTC), the service responded HTTP 201 with `received: true`, ID `fb_3f4fdfc4f97aa13a`, and kind `other`. Its acknowledgement says reports are read and analysed daily and that there is no individual reply. This confirms receipt by the service, not operator interest, an operator reply, admission or activation.

The full request and response receipt is stored in `PromoMaterials/outreach/hub-operators-2026-10-27/agent-exec-feedback-receipt.json`. Local attempt metadata is in `agent-exec-send-attempt.json`. Other candidate contacts, public posts, paid invokes and GitHub writes were not performed. `campaign-validation.json` remains the initial validation snapshot; `post-send-validation.json` records the current files and sent status.

## Machina follow up

At 22:59–23:00 MSK (19:59–20:00 UTC), a fresh public queue GET still listed Machina and agent-exec as the two pending peers. Ordinary hostname GETs to Machina's AIMarket discovery and fallback manifest returned 404, matching the primary failure in its saved assay. This confirms that the IP-address URLs in the earlier HTTPX diagnostic were not sufficient evidence of a local virtual-host routing bug.

Machina's `/health`, `/docs`, `/openapi.json` and `/docs/buyer-guide` returned HTTP 200. OpenAPI names the service Machina Agent Services and explicitly advertises `GET /.well-known/x402`; that route also returned an nginx 404. This narrows the actionable question to discovery availability and routing, while leaving the actual server configuration unknown. API operations were not invoked.

The buyer guide publishes `ceo@difftechstore.com` as its support email. A targeted email draft is saved in `PromoMaterials/outreach/hub-operators-2026-10-27/machina-email.txt`. It has not been sent. The prior user authorization named agent-exec feedback only.

Static review found that `outbound_http.py` preserves the original Host and SNI while pinning an approved IP, and `crawler.py` passes them into HTTPX. In `federation_assay.py`, a discovery-fetch failure leaves an empty document, which can generate subsequent missing-key and missing-manifest diagnostics. Those messages should not be presented as independently verified defects in Machina's current documents.

Raw checks: `pending-hubs-recheck.json`, `machina-api-recheck.json` and `machina-discovery-recheck.json`. All requests in this follow-up were public HTTP GETs; no admission state, external message or paid operation was changed.
