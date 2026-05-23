# aimarket-nft — User Guide

## Why it matters (plain words)

Pre-paid AI credits as transferable tokens — gift them, resell unused balance, or run loyalty programs without building billing from scratch.

**Простыми словами:** Предоплаченные кредиты AI как передаваемые токены — подарить, перепродать остаток или сделать программу лояльности без биллинга с нуля.


## What it does

Tokenized pre-paid credits (ERC-721). Category: **monetization**.

## Installation

```bash
pip install aimarket-nft
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-nft")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: none

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-nft/mint` | Mint credit NFT |
| `POST` | `/ai-market/v2/p/aimarket-nft/redeem` | Redeem NFT balance to channel |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.nft'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
