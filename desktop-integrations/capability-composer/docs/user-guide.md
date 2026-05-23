# Capability Composer — User Guide

## Why it matters (plain words)

You visually connect AI building blocks into a pipeline — like Lego for AI services — without writing integration code. Test it, run it with one wallet, and sell your pipeline as a template to others.

**Простыми словами:** Вы собираете AI-блоки в цепочку на холсте — как конструктор — без написания интеграционного кода. Проверяете, запускаете с одним кошельком и можете продать свой пайплайн как шаблон.


## What this product does

Visual pipeline builder for AI Market capabilities. Tier 3 — Builder tool.

## AI Market economics (integrated)

This app implements **AI Market Protocol v2** via `aimarket_agent`:

- **Wallet** — Ed25519-signed payments (dev key in local builds; OS keychain in production)
- **Discovery** — Search hub capabilities by intent and category
- **Channels** — Pre-funded USDT channels on Base for micro-payments per invoke
- **Invoke + TEE** — Capability calls with optional attestation verification
- **Settlement** — Channel close returns unused balance

Discover capabilities, chain DAG, execute via channels, publish templates for sale.

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
