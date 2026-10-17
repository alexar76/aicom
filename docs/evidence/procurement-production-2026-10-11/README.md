# Production procurement verification — 2026-10-11

Procurement is enabled in the production factory. Provider: `aicom-diagnostics/aicom.diagnose@v1`, an operator-owned diagnostic service using a real model call. This is operator self-testing, not independent customer revenue.

The successful public HTTPS purchase charged $0.10 in Hub credits from a one-time $2 operator grant; $1.90 remains. The factory verified the signed receipt and accepted the source-cited report. Repeating the accepted task returned the same report without network calls or another charge. The synthetic divide-by-zero example verifies procurement, not a full product repair pipeline.

Five earlier failed market invokes were checked against the ledger: no market charges, all holds released, no unknown orders. Model inference has a separate cost: three recorded calls total $0.001229948; two earlier calls lack recorded usage. Conservative reservations across all five calls total $0.009988. The successful purchase reused the fifth call’s cached report, with a newly implemented request-bound provider signature.

Limits: $0.25 per purchase, $0.50 per product, $2 per UTC day, $0.50 completion reserve, existing $40 pipeline cap. Only the approved diagnostic capability is enabled. Provider credentials and signing keys are private; none are in this evidence directory.

Validation: 45 focused tests passed. Production factory API and diagnostic service are healthy. Factory policy reports enabled, approved provider and zero unknown orders.

Operations: production release and protected backups are in `/root/procurement-release-20261011/`. Set `enabled` to `false` in `/root/claudecode/aicom/data/config/procurement.json` for the immediate kill switch. `rollback.py` in the release disables procurement and restores preserved factory/Hub containers; restore backed-up environment files as well before subsequent deployments. Keep the journal and signing keys. Nothing was pushed to GitHub.

Evidence: `canary.json` records the accepted order; `verification-summary.json` contains redacted accounting and model usage. Five-language operator guides: `docs/factory-subcontracting{,.ru,.es,.fr,.zh}.md`.
