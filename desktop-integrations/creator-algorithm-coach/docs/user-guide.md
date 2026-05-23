# Creator Algorithm Coach — User Guide

## Why it matters (plain words)

Creators see what TikTok, YouTube, and Instagram algorithms reward in their niche this week — not generic advice from a blog. Buy signal packs; optionally share anonymous metrics to earn credits.

**Простыми словами:** Авторы видят, что алгоритмы TikTok, YouTube и Instagram поощряют в их нише на этой неделе — не общие советы из блога. Покупаете пакеты сигналов; при желании делитесь анонимной статистикой за кредиты.


## What this product does

TikTok/YouTube/IG algorithm signals by niche. Tier 2 — Creator economy.

## AI Market economics (integrated)

This app implements **AI Market Protocol v2** via `aimarket_agent`:

- **Wallet** — Ed25519-signed payments (dev key in local builds; OS keychain in production)
- **Discovery** — Search hub capabilities by intent and category
- **Channels** — Pre-funded USDT channels on Base for micro-payments per invoke
- **Invoke + TEE** — Capability calls with optional attestation verification
- **Settlement** — Channel close returns unused balance

Buy algorithm windows; sell TEE-verified creator metrics.

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
