# aimarket-zk — User Guide

## Why it matters (plain words)

Prove an AI ran correctly on secret input without revealing the input — for M&A, legal, and regulated workflows where showing the document is not an option.

**Простыми словами:** Доказываете, что AI корректно обработал секретный ввод, не раскрывая его — для M&A, права и регулируемых процессов, где показать документ нельзя.


## What it does

ZK proofs for private AI invocation. Category: **security**.

## Installation

```bash
pip install aimarket-zk
aimarket serve
curl http://localhost:9080/ai-market/v2/plugins | jq '.plugins[] | select(.name=="aimarket-zk")'
```

## Hub integration

Plugins register via setuptools entry point `aimarket.plugins`. After install, restart the hub — routes mount under `/ai-market/v2/p/{plugin_name}/`.

Invoke hooks: `on_invoke_pre_check`, `on_invoke_post_check`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/p/aimarket-zk/prove/input` | Prove valid input without revealing |
| `POST` | `/ai-market/v2/p/aimarket-zk/prove/output` | Prove correct execution |
| `POST` | `/ai-market/v2/p/aimarket-zk/verify` | Verify proof bundle |

## Configuration

See plugin README for environment variables. Common hub vars:

| Variable | Description |
|----------|-------------|
| `AIMARKET_HUB_URL` | Public hub URL in receipts/manifest |
| `DATABASE_URL` | Optional PostgreSQL (SQLite default) |

## Verify loaded

```bash
curl http://localhost:9080/.well-known/ai-market.json | jq '.plugin_extensions.zk'
```

## More

- [SDK integration](sdk-integration.md)
- [User cases](user-cases.md)
- [README](../README.md)
