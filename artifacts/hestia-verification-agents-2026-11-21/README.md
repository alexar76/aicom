# HESTIA: seven verification agents — 2026-11-21/22 (LIVE since 2026-11-22 05:53Z)

Owner 21.11: «делай 1-6», then «и давай придумаем одного хайпового агента» → x402.preflight; «все это описываем в
документации по гестии и экосистеме на 5 языках»; «каталог агентов … по всем нашим стандартам транспарентности и
безопасности».

## What

| slug | capability | reaches | what it answers |
|---|---|---|---|
| registry-entry | `registry.entry.verify@v1` | registry, npm, PyPI, nuget.org, dns.google, + `domain` | do an MCP registry entry's packages and domain still name it (the registry's own rules, re-run now) |
| package-provenance | `package.provenance.verify@v1` | registry.npmjs.org, pypi.org | Sigstore provenance of an npm/PyPI release, verified from pinned roots |
| agent-card | `agent.card.verify@v1` | only `url` / `jwks` hosts | A2A 1.0 card structure and its JWS signatures |
| evm-signature | `evm.signature.verify@v1` | Base, Base Sepolia, Ethereum RPC | EIP-191/712 signatures by keys and smart wallets (ERC-1271, ERC-6492) |
| timestamp | `timestamp.verify@v1` | none | RFC 3161 tokens, chain to pinned Sigstore TSA / DigiCert G4 / FreeTSA roots |
| site-policy | `site.agent_policy@v1` | only `url` host | RFC 9309 per AI agent, Content-Signal lines with their groups, llms.txt |
| x402-preflight | `x402.preflight@v1` | `url` host, Base RPCs (publicnode), modelmarket.dev | should an agent pay this 402 (offer, asset/domain, budget, payee on chain, hub pin) |

All free, sandbox-only (WebAssembly), Python. Source: `hestia-agents/agents/<slug>/handler.py`; manifests in
`hestia-agents/hestia_agents/manifests.py`; catalogue text in `hestia-agents/docs/AGENTS*.md` (5 languages).

## How it was checked

- Each handler run against live hosts with `hestia-agents/scripts/record_fetches.py` (the hearth's limits: declared and
  caller-named hosts only, six requests a call, 256 KiB a reply, no redirects); every reply recorded under the sandbox's
  own request key into `tests/<slug>_vectors.json`.
- Every recorded case run again in HESTIA's own sandbox (`hestia.sandbox`, CPython 3.14.7 for WASI under wasmtime) with
  `hestia-agents/scripts/run_in_sandbox.py`: 44 recorded cases and the three TSA tokens, all "same as the
  in-process run", 0.13–1.7 s each.
- Tests (`tests/test_<slug>.py`), each negative case one changed byte or field: registry-entry 34, package-provenance 31,
  agent-card 40, evm-signature 28, timestamp 17, site-policy 18, x402-preflight 21. hestia-agents suite: all pass except
  the pre-existing `test_warden_scan` bundle-version test (bundle 0.35.0, main prepares 0.36.0) and the sandbox-lint
  tests when run without HESTIA's dependencies; with them (`PYTHONPATH=. uv run --project ../hestia --with pytest pytest
  tests/test_agents.py -o addopts=""`) 147/147.
- Independent references: EIP-712 spec "Mail" example (digest, separator, struct hash, signer); RFC 8037 A.4 EdDSA and
  A.3 thumbprint; RFC 9309 examples; the MCP registry's own `mcpname.go`, `npm.go`, `pypi.go`, `nuget.go`,
  `auth/dns.go`, `auth/http.go`; Sigstore `trusted_root.json` (sha256 6494e21e…); signed A2A fixtures made with the
  `cryptography` library (`tests/make_agent_card_fixtures.py`); three TSA tokens accepted by `openssl ts -verify`.
- Field data: 183 signed A2A cards on MCP-registry hosts (`artifacts/a2a-card-signatures-2026-11-21`): 109
  signed_verified, 4 self-asserted, 64 failed, 5 malformed, 1 gone. Two smart wallets that paid USDC on Base with a
  contract signature (proxy 0x5918…271d, EIP-7702 0x7112…7fe9) verify by ERC-1271 at the block before their payment.

Bugs found and fixed while building (each caught by a live case or a reference):
- npm keyids are OpenSSH fingerprints, not SHA-256 of the DER key;
- the signingCertificate OID ends in 0x0c, not 0x12;
- in registry-entry, DNS without a key is "not checked" unless HTTP was read too (HTTP auth is an alternative);
  deprecated, yanked and other-owner repositories are warnings, not a mismatch;
- in agent-card, key discovery beyond `jku` (did:web, did:key, did:jwk, embedded jwk, the conventional JWKS),
  ES256K and RFC 7797 were added after the field run showed them in use;
- in site-policy, the response Date was dropped so that `cli verify` sees the same signature twice.

## Catalogue

`hestia-agents/scripts/build_catalog.py` builds a public catalogue in five languages from the repository: per agent
the description, the hosts it can reach, the sandbox and egress limits read from the HESTIA source, the handler's
SHA-256 with a copy of the source, how to check the signature, the tests and recorded data. Output (not committed):
`index{,.ru,.es,.fr,.zh}.html`, `catalog.json`, `SHA256SUMS`, `src/`. Viewed at desktop and phone width; no horizontal
scroll; 29 agents. Not published.

## Deploy (owner 22.11: «Yes, deploy»)

- `HESTIA_DEPLOY_TOKEN` read from the running `hestia-hestia-1` on competing-lab into the deploying shell's
  environment (never printed), then `hestia_agents.cli deploy --hearth https://hestia.modelmarket.dev` with `--only`
  for the seven slugs, from main d31fad7e7: all seven `running` at server time 2026-11-22T05:53:07Z.
- `cli verify` for the seven: all `ok`, the signature repeats on each probe.
- Roster `/v1/hearth`: all seven listed, with the egress hosts and caller-named fields of the manifests; 33 tenants.
- Called from outside with real inputs (`live-calls-2026-11-22.json`), all HTTP 200, 0.6 to 3.7 s: registry-entry
  WARDEN 0.35.0 and com.notion/mcp verified; package-provenance @modelcontextprotocol/sdk 1.32.2 and sigstore 4.5.1
  (PyPI) verified; agent-card agoreum.xyz (JWKS on its host) and agent-guild-5d5r.onrender.com (did:web)
  signed_verified; evm-signature proxy wallet erc1271 valid at block 60530328; timestamp DigiCert verified;
  site-policy www.nytimes.com disallows GPTBot and ClaudeBot; x402-preflight textokit review_first (no payments to its
  payee in 24 h). The hearth's Ed25519 signature on all ten answers checked with signature.verify's `hestia` format;
  each tenant signs with its own key.
- The hub lists hearth tenants through federation on its next hourly crawl.
- Rollback: delete the seven tenants on the hearth (operator API, DELETE /v1/tenants/SLUG with the deploy token).
- A shell slip while writing this record (an unquoted heredoc let zsh run the backquoted text above as commands) ran
  only `cli deploy` with a bare `--only`, which argparse refused before any request, with no token in that shell;
  the roster afterwards: the same 33 tenants, all seven running.

## Published (2026-11-22, owner «Yes, publish it»)

- The catalogue is LIVE at https://hestia.modelmarket.dev/agents/ (07:29Z), and the hearth's roster gives every
  sandbox agent's `handler_sha256`; all 29 catalogued agents run exactly the published handler. Record:
  `artifacts/hestia-catalogue-rollout-2026-11-22`. The Alien Monitor card and the modelmarket.dev strip link it
  (`alien-hestia-catalogue-2026-11-22`, `hub-hestia-catalogue-link-2026-11-22`).
