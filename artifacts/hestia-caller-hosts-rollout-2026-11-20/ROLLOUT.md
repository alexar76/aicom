# HESTIA: hosts the caller names, a per-call nonce, aid.discover@v1 — rollout 2026-11-20

Owner 20.11: «Хост из запроса» (from the capability list), «документацию на 5 языках не забудь».
Code: aicom main 4579785a6, plus the `lookup_failed` verdict of aid.discover (agent only, no image).

## What changed

- `egress_input_fields` (≤3 top-level input fields): the host a call's input names there may be
  fetched in that call, under every egress rule; 20/min per such host across the hearth; operator and
  operator-admitted owners only; shown on the roster.
- Egress passes `accept-signature`, `aid-domain`, `cache-control` (request) and `signature`,
  `signature-input`, `link` (response).
- `CALL_NONCE`: 32 random bytes (hex), the same in every fetch round of one call, both languages.
- Python handlers in the sandbox up to 200 000 characters (stub: 32 000).
- Runner probe reads the whole health answer (no BrokenPipeError).
- hestia-agents `aid.discover@v1`, generated from aid-record + aid-proof.

## Checks before

hestia 843 passed (coverage 90 %); hestia-agents 934 passed, 1 failed (test_cli payment-redeem, fails on
main too). Open alerts: only `host_disk[attested]`. Candidate runner offline (`--network none`, read-only,
from /app): python + javascript, the provider key unreadable from JS, warden.scan blocks the probe,
CALL_NONCE reaches handlers in both languages.

## Switch (overlays FROM the images of the JavaScript rollout an hour earlier)

| container | switched (UTC) | new image | previous (rollback) |
|---|---|---|---|
| hestia-hestia-runner-1 | 18:10:05–18:10:45 | `aicom-security:hestia-runner-callerhosts-20261120` = a6e92a87b097 | `hestia-hestia-runner-1-security-prev-…` (2013a3fa719f) |
| hestia-hestia-1 | 18:10:45–18:10:48 | `aicom-security:hestia-hearth-callerhosts-20261120` = 73770388103e | `hestia-hestia-1-security-prev-…` (0ef2660285c2) |

Ledger dump: `/root/hestia-backups/hestia-pg-pre-callerhosts-20261120T181005Z.sql.gz`. Rollback, hearth first:

    cd /root/hestia-callerhosts-rollout-20261120
    python3 rollout_container.py hestia-hestia-1 --rollback
    python3 rollout_container.py hestia-hestia-runner-1 --rollback

## After

- No restarts, no tracebacks in either log for the first 5 minutes.
- aid.discover live from skopos-vps: modelmarket.dev → `proven_bound` (also with
  `require_domain_binding`), ~1.9 s, signed; agentcommunity.org, aid.agentcommunity.org, ietf.org →
  no `_agent` record (1000). Roster: egress_hosts the two resolvers, egress_input_fields domain, endpoint.
- 23 calls in 18 s at one domain: 16 proven, then the agent's own budget (60 fetches/min; each call
  makes three) refused the resolvers. They were reported as `no_valid_record`, which was wrong:
  aid.discover now answers `lookup_failed` (1004) then, redeployed 18:12Z (handler byte-equal to the repo,
  sha256 f2c926a0…). The per-target budget (20/min) is proven by tests; live, the agent budget came first.
- warden-scan, aid-record, base-gas answer as before. Host tree synced to main; guard copy refreshed.
