# MOMUS — Genesis Conductor critic, marketplace, and meter

Epoch **2026-09-13-E2** (Critique-to-Cash).

MOMUS is Igor Holt's fleet agent for critique, coalition-seat licensing (R05), A2A skill-marketplace fees (R09), and metered API licensing. It is not the alexar76 red-team satellite and not the momusai.io prediction agent.

## Planes

| Plane | Duty | Must not |
|---|---|---|
| Critic | Review artifacts, DORA gate, signed findings | Hold Stripe or x402 payer keys |
| Marketplace | List skills, grant coalition seats | Auto-pay itself |
| Meter | D1 usage + 30-min Stripe flush + x402 | Enforce hard quotas from Stripe lag |

## Layout

```
docs/EPOCH-E2.md          epoch brief and provenance
skill/momus/SKILL.md      Grok / OpenClaw skill contract
worker/                   Cloudflare Worker (Hono) E2 spec
```

## Operator sequence

1. Create D1 `momus-usage` and KV `API_KEYS`, `METER_CURSOR`.
2. Apply `worker/migrations/0001_init.sql` and `0002_e2.sql`.
3. Put secrets: `STRIPE_API_KEY`, `STRIPE_METER_EVENT_NAME`, `X402_RECEIVER`, provider keys.
4. Bind through Ambient Access Layer. Do not deploy a bare worker to production.
5. Smoke `/v1/health`, then a signed `/v1/critique`, then `/v1/infer` with a starter key.

Owner: Kovach Enterprises. ORCID 0009-0008-8389-1297.
