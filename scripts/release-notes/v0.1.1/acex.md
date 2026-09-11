# acex v0.1.1

Release from the AICOM monorepo mirror (`main`), capturing changes since 2026-05-29.

## Changes
- fix(docs): point satellite markdown links at GitHub repos
- fix(acex-security): fix all 6 audit findings in source (for redeploy)
- feat(chain): unified EVM+Solana network registry + health-checked RPC failover
- docs: document the Base demo deployment in every contract subproject
- feat(deploy): full ecosystem on Base from single wallet 0x1218 + verified + tested + documented
- security/quality: fix audit findings across the ecosystem
- feat: standardize badges, CI coverage scripts, and docs across all satellites
- fix(security): harden prod sandbox guard, blog assets, and ACEX default burn
- Fix ACEX Solana build: Rust 1.85, lockfile, and Anchor init-if-needed.
- Document Proof-of-Audit Phase 2 hub, Pulse, and Solana flows.
- Ship Proof-of-Audit Phase 2 across hub, Pulse, and Solana.
- Extend Proof-of-Audit baseline capture window to 30 days.
- Fix Proof-of-Audit baseline bypass and default compensation bugs.
- Add negative regressions for Merkle leaf hardening in PulseDistributor.
- Add ACEX Proof-of-Audit with staked auditor market and slash on default.
- Security audit fixes: channel race, merkle leaf hardening, vesting, sweep.
- ACEX: real money-market lending with funded liquidations + fix compile blocker.
- feat: complete Agent IPO leg — factory → hub → ACEX with on-chain settlement
- Link all product READMEs to the public ecosystem landing page.

Source: monorepo path `acex` · https://github.com/alexar76/acex
