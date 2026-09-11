# aimarket-oracle-gateway v0.1.1

Release from the AICOM monorepo mirror (`main`), capturing changes since 2026-05-29.

## Changes
- sync: pull helios from Gitea#2 + staged changes (argus MCP, helios broadcast LLM/renderer, plugins, scripts, docs)
- feat(oracles): 17-oracle family (6 new) + ARGUS conscience, live 3D previews
- feat(oracles): expand MCP gateway v0.2.0 and fix broken verify paths
- fix(security #2): per-channel debit secret — close unauthorized off-chain channel drain
- fix(security): audit sweep — manifest signature scope, demo-credit fail-closed, debit auth, credential redaction
- fix(oracle-program): audit sweep — verifiability, payment-safety, signing, test hardening
- feat(mcp): payment design+threat-model (spec 03) + gateway spending-cap security core (item 3)
- feat(oracles): LUMEN verifiability — convergence proof, graph commitment, lumen.score@v1 + lumen.verify@v1 (spec-01 item 1 cont.)
- feat(oracles): platon.verify@v1 + Chronos modulus_hex + gateway verify_random (spec-01 item 1)
- polish(mcp): AAA-grade tool definitions for the Oracle Gateway (calibrated to the packager)
- feat(mcp): passthrough Oracle Gateway MCP server (Glama-ready) — the discovery storefront

Source: monorepo path `plugins/aimarket-oracle-gateway` · https://github.com/alexar76/aimarket-oracle-gateway
