# Interview Prep Coach — User Guide

## Why it matters (plain words)

You get interview questions that are actually fresh — from this week, for your target company — instead of stale forum posts. Pay a few cents per question bank instead of a $500 course. Your practice answers stay on your computer; you only share anonymized patterns if you choose to sell them.

**Простыми словами:** Вы получаете актуальные вопросы с собеседований — за эту неделю, под вашу компанию — а не устаревшие посты с форумов. Платите копейки за банк вопросов вместо курса за $500. Ответы при практике остаются на вашем компьютере; в маркетплейс уходят только обезличенные паттерны, если вы сами решите их продать.


## What this product does

Company-specific interview banks with marketplace freshness. Tier 1 — Flagship consumer.

## AI Market economics (integrated)

This app implements **AI Market Protocol v2** via `aimarket_agent`:

- **Wallet** — Ed25519-signed payments (dev key in local builds; OS keychain in production)
- **Discovery** — Search hub capabilities by intent and category
- **Channels** — Pre-funded USDT channels on Base for micro-payments per invoke
- **Invoke + TEE** — Capability calls with optional attestation verification
- **Settlement** — Channel close returns unused balance

Discover question banks, open USDT channels, invoke with TEE verify, sell anonymized trajectories.

## First launch

1. Complete onboarding / connect wallet (Settings or wallet panel)
2. Open marketplace or discovery tab
3. Search by intent relevant to your workflow
4. Open a channel (\$5 covers ~50 calls at \$0.10 each)
5. Invoke capabilities; review Bill of Materials / receipts

## Privacy

See product README and `docs/architecture.md`. Local-first apps keep sensitive content on-device; only structural or anonymized metrics may be published.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Hub unreachable | Check `HUB_URL` or use local factory at `http://127.0.0.1:8080` |
| `privateKeyHex` error | Wallet key must be 64-char hex |
| Empty marketplace | Run factory pipeline to seed demo capabilities |

## More

- [User cases](user-cases.md)
- [SDK integration](sdk-integration.md)
- [Architecture](architecture.md)
