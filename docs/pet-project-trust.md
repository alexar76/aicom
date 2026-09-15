# Pet-project trust model

This ecosystem is a **self-hosted, single-operator demo** — not an audited DeFi protocol.
Use it for learning, prototyping, and small personal deployments. Do not present it as
production-grade financial infrastructure without completing the operator checklist below.

## What we claim

| Layer | Status |
|-------|--------|
| AI-Factory pipeline | Self-host MIT stack; your keys, your infra |
| Base mainnet demo | ~$2 USDC + small ETH; [onchain journal](onchain-journal.md) |
| Hub federation | Signed manifests, supply stake (off-chain bookkeeping), LUMEN trust |
| Dispute oracle | **m-of-n when configured** (`AIMARKET_ORACLE_AUTHORITIES`); else single-operator |
| Dispute filing | `POST /ai-market/v2/reputation/disputes` (consumer-signed or admin) |
| External audit | **Not performed** (pet-project budget) — Slither + Foundry tests only |

## What we do not claim

- Trail of Bits / OpenZeppelin-grade contract assurance (KI-2 — waived for pet project)
- Decentralized oracle network or multi-hub production mesh at scale (KI-10)
- Hardened oracle cryptography (KI-6) or production VDF service
- ARGUS WARDEN as guarantee against sophisticated MCP attacks (KI-9)
- Metis distributed cluster as HA production mesh (KI-8)
- Factory pipeline at scale without load test (KI-3, KI-7)
- Hosted multi-tenant SaaS with SLAs
- Insurance or bug bounty (Immunefi planned, not active)

## Component tiers (honest)

| Tier | Components | Posture |
|------|------------|---------|
| **Core demo** | AI-Factory, Hub, Metis, ARGUS, Oracles, Lottery | Research/prototype — protocol wiring real, scale/audit open |
| **Observability** | Alien Monitor | Polished; not economic trust layer |
| **Secondary** | Widget, desktop integrations, HELIOS, aimarket-mcp | Supporting tools; not primary value prop |
| **Devrel / reference** | DIOSCURI (Castor/Pollux) | Community Q&A + injection-hardening **demo** on public chat |

Full scorecard: [`ecosystem-maturity-review.en.md`](ecosystem-maturity-review.en.md) · [RU](ecosystem-maturity-review.ru.md)

## Operator checklist (no paid audit)

Run before pointing real money at the stack:

```bash
chmod +x scripts/pre_mainnet_checklist.sh scripts/multisig_transfer_runbook.sh
./scripts/pre_mainnet_checklist.sh
```

1. **Multisig (KI-4)** — `./scripts/multisig_transfer_runbook.sh dry-run` then `broadcast`
2. **Oracle quorum (O-1)** — set in hub `.env`:
   ```
   AIMARKET_ORACLE_AUTHORITIES=<pubkey1>,<pubkey2>,<pubkey3>
   AIMARKET_ORACLE_THRESHOLD=2
   ```
3. **Prod factory** — `./scripts/run_prod_compose.sh up -d --build`
4. **Load test (KI-3)** — `./scripts/load_test_factory.sh --duration 600 --concurrency 10`
5. **Slither** — `bash scripts/run_contract_audit.sh` (fix High before >$1k TVL)
6. **Frontend e2e** — `cd web/frontend && npm test` (React 19 + recharts + framer-motion smoke)

## Honest mainnet banner

Live contracts on Base mainnet are a **demonstration deployment** from one wallet
(see [onchain-journal.md](onchain-journal.md)). They prove end-to-end protocol wiring;
they are not a substitute for external audit + multisig + load testing at scale.

For public messaging, use: *"Pre-mainnet demo — self-host pet project, not audited DeFi."*
