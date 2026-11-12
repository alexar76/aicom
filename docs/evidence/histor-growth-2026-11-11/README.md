# HISTOR growth entry and measurement

The local version puts the record, check or Watch desk before the generic hero when a reader opens a direct link. On an observed record, follow Atom, inspect the change and proof, or replay a recorded set. Watch offers a pilot contact alongside its existing purchase flow. A contact click opens the reader's mail client; it sends nothing by itself.

## Reproduce the first visitor path

From the repository root, run with the HISTOR development environment installed:

```sh
histor/.venv/bin/python docs/evidence/histor-growth-2026-11-11/replay_check.py
```

The replay loads two preserved AI Applyd tool sets into a temporary SQLite database. The actual `/check` handler classifies the older digest as `previously-observed`, verifies the response with the test log's Ed25519 key and opens the server's Atom feed. It does not contact AI Applyd. See the [replay result](replay-result.json) and [archived comparison](../../../artifacts/histor-legion-case-2026-11-03/README.md).

For browser QA, pass `--serve 9497` to the replay. With Playwright and Chrome installed, run `node docs/evidence/histor-growth-2026-11-11/browser_check.mjs /tmp/histor-growth-screenshots` from the repository root. The [browser results](browser-result.json) cover 1280×720 and 390×640, a verified reply, Atom and pilot clicks, and preservation of the pilot action when the plan API is unavailable. Screenshots: [server on mobile](screenshots/card-390.png) · [Watch on desktop](screenshots/watch-1280.png).

## Compare channels and actions

Tag the destination with `utm_source=devto`, `blog`, `x` or `bluesky` as appropriate. Use `utm_source=qa` for internal browser walkthroughs. Keep the two X drafts in [PromoMaterials](../../../../PromoMaterials/twitter/ready/POST-histor-case-and-unity-2026-11-11.txt) until the public deep links are checked after release. The technical sources are the [AI Applyd replay](../../../artifacts/histor-legion-case-2026-11-03/README.md) and [Unity baseline](../unity-mcp-tool-cost-2026-11-11/README.md).

The same-origin collector accepts empty requests with one source and one event from fixed lists. It does not receive `tools/list`, an endpoint, a full referring URL, a cookie, or a browser ID. The client skips known browser automation unless tagged as QA and respects GPC and DNT. To detect a repeat, it keeps only the last date of a successful own-input check in that browser's local storage. It reports a repeat once per page when a prior check was 1–30 days earlier. Demos and QA never count as repeats.

Run a weekly report on the HISTOR host's combined access logs. Supply only non-overlapping files; `AICOM_OWN_IPS` can exclude known operator and fleet addresses without copying them into the output. For example:

```sh
cd histor
.venv/bin/python scripts/journey_report.py \
  --from 2026-11-11T00:00:00Z --until 2026-11-18T00:00:00Z \
  /var/log/nginx/access.log.1 /var/log/nginx/access.log
```

The existing operator logs still contain ordinary request metadata such as address and User-Agent. The report publishes no addresses or identifiers. `check_succeeded` means a browser verified a signed reply to its own input, including an honest result that no matching record exists. `sample_succeeded` measures the guided example separately. `watch_feed_clicked` and `pilot_contact_clicked` are clicks; actual subscriptions and received inquiries need separate confirmation. These are counts of events from browser-like requests, with known bots and QA filtered; they cannot be divided to infer a per-person conversion rate. Compare sources over equal observation windows, and watch for repeat checks and received pilot inquiries.

## Small team pilot

Agree on which tool lists the team is authorized to share and what counts as a change worth reviewing. Capture a baseline for the agreed endpoints and observe for 30 days. The deliverable is a short report: endpoint and capture conditions, old and new digests, changed fields, reference to the signed event or label, and disposition. Start with the AI Applyd report as an example: the Oct 19 archive and LEGION agreed on 23 sets of name, description and input schema; on Oct 24 HISTOR saw all 23 names change. Treat changes as review items, not proof of malicious behavior.

Before distributing links, deploy the app and landing assets as one version and recheck clean desktop and mobile sessions, a signed sample response, Atom and the pilot affordance. In particular, the 11 November production nginx overlay serves older desk assets separately. Check that it does not shadow the new release; deploying only the Python route or only the JS is insufficient. No production baseline exists for the new events before release.
