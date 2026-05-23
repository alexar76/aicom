# aimarket-tee — User Guide

## Why it matters (plain words)

Runs sensitive AI inside secure hardware so even the server owner cannot read your input. You get a hardware attestation — proof the right code ran in a protected enclave.

**Простыми словами:** Чувствительный AI работает в защищённом железе — даже владелец сервера не видит ваш ввод. Получаете аппаратное подтверждение: нужный код выполнен в изолированной среде.


## What it does

TEE-attested execution (AWS Nitro / Intel TDX). Category: **security**.

## Installation

```bash
pip install aimarket-tee
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-tee")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: `on_invoke_post_check`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| — | — | Hooks only (no public routes) |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.tee'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
