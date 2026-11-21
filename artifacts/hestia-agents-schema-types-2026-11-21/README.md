# HESTIA agents: input types for three fields — 2026-11-21

The daily supplier review (Multica, 10:00 UTC on attested) flagged three input fields as `untyped_properties`
(low): `key` of http.signature.verify@v1, `tools` of warden.scan@v1, `amount` of x402.settlement.check@v1.
Each now has the type its handler already accepts (`hestia_agents/manifests.py`, `deploy.json` regenerated with
`cli build`; main 8c4ed0be8):

- `key`: `["object", "string"]` — a JWK, a PEM string or `{alg, key}`.
- `tools`: `["array", "object"]` — the tools/list array or the result object holding it.
- `amount`: `["integer", "string"]`, pattern `^[0-9]+$` — USDC smallest unit, a whole number or its digits.

No handler changed. Tests: hestia-agents suite 1012 passed, 1 failed (`test_cli` payment-redeem, which fails the
same way without this change).

## Deploy

Owner 21.11: «выкатывай, возьми ключи с прода». `HESTIA_DEPLOY_TOKEN` read from the running `hestia-hestia-1`
on competing-lab into the deploying shell's environment (never printed), then
`hestia_agents.cli deploy --hearth https://hestia.modelmarket.dev --only http-signature --only warden-scan
--only x402-settlement` at 18:35Z (server time): all three `running`.

`cli verify`: http-signature ok, warden-scan ok (signatures repeat). x402-settlement reports "NOT DETERMINISTIC":
two calls of its probe differ only in `confirmations` (the agent reads the chain head; Base adds a block every
2 s), both `paid`. Expected for this agent, not a fault.

The review's next run (22.11 10:00Z) should no longer list the three `untyped_properties` findings.

Rollback: deploy the previous `deploy.json` files (main before 8c4ed0be8) the same way.
