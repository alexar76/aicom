# HEPHAESTUS: counterparty scenario, local verification

Date: 2026-10-28. Changes are local; no deployment or publishing was performed.

The new Studio scenario invokes current EMPORION catalogue offers and builds a report
from each returned step, keeping original source evidence and receipts. Independent
checks can continue on source failures. Raw results are not added to public trace bills;
signed per-step digests bind the returned results to the bill.

## Verification

- `cd hephaestus && npm run check`: core type check and 99 tests, including counterparty planning,
  identity ambiguity/adverse statuses, receipt selection, missing evidence and freshness.
- `cd hephaestus/studio && npm run build`: Studio type check and production bundle.
- 227 targeted backend tests: pipeline/API, Studio route/paid execution and paid provider/client.
  These include signed result commitments, receipt retention, response privacy and independent continuation.
- `node scripts/check_hephaestus_counterparty.mjs`: offline Playwright regression with synthetic
  catalogue and source responses, including a fully simulated wallet. No remote source requests,
  real signatures or real payments are used by this browser test.

The browser script records its actual assertions in [browser-check.json](browser-check.json).
It checks the Russian form, explicit inputs without example defaults, sources/freshness,
JSON receipt export, partial failures, paid-result report attribution and mobile layout.
Screenshots named `fixture-*` show synthetic test data; they are not production verification.

Backend commands (test stores and network mocks are configured by the suites):

```sh
# aicom root, .venv Python 3.12.13: 110 tests
.venv/bin/python -m pytest tests/test_pipeline_evidence.py tests/test_pipeline_blame.py tests/test_pipeline_data_flow.py tests/test_pipeline_references.py tests/test_pipeline_federated.py tests/test_pipeline_trace_read.py tests/test_ai_market_protocol_v1.py -q
# aimarket-hub, its .venv Python 3.11.15: 63 + 54 tests
.venv/bin/python -m pytest tests/test_studio_run.py tests/test_studio_paid.py -q
.venv/bin/python -m pytest tests/test_pipeline_provider.py tests/test_pipeline_client.py -q
```

Usage: [Russian scenario guide](https://github.com/alexar76/hephaestus/blob/main/docs/counterparty.ru.md).
Trademark research is separate: [EMPORION search](../emporion-trademarks-2026-10-28.md).
