# API integration

> Full guide: [`docs/api-integration-guide.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/api-integration-guide.md)

## Base URLs

| Context | Base |
|---------|------|
| Via Next proxy | `https://your-host/api/...` |
| Direct uvicorn | `http://host:9081/api/...` |
| **AI Market v1** | `https://your-host/ai-market/...` and `/.well-known/ai-market.json` *(no `/api` prefix)* |

Interactive schema: **`/api/docs`** (Swagger).

## Auth patterns

| Pattern | Header / cookie |
|---------|-----------------|
| Admin session | `access_token` cookie + `X-CSRF-Token` on mutations |
| Admin API token | `Authorization: Bearer <jwt>` |
| Public | No auth — products, sandbox file, pipeline-status, support |
| AI Market invoke | `X-Payment` / `X-Payment-Channel` or `x-ai-market-license` (v0) |

Login: `POST /api/admin/login` → sets cookies.

## High-value public endpoints

```http
GET /api/health
GET /api/public/pipeline-status
GET /api/products
GET /api/sandbox/file/{product_id}/index.html
GET /api/public/pipeline-demo-replay
GET /.well-known/ai-market.json
GET /ai-market/manifest
```

## Admin examples

```bash
# Login (save cookies)
curl -c cookies.txt -X POST https://factory.example.com/api/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"***"}'

# Pipeline list
curl -b cookies.txt https://factory.example.com/api/admin/pipeline/products

# Trigger discovery
curl -b cookies.txt -X POST https://factory.example.com/api/admin/discovery/run
```

## AI Market protocol

| Doc | Topic |
|-----|-------|
| **v1 (recommended)** | [`docs/ai-market-protocol-v1.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/ai-market-protocol-v1.md) — MCP manifest, HTTP 402, channels, pipelines |
| Wiki summary | [[AI-Market-Protocol]] |
| v0 pilot | [`docs/ai-market-protocol-v0.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/ai-market-protocol-v0.md) |

```bash
# Discover + channel + invoke (demo payment mode)
curl -sS https://factory.example.com/.well-known/ai-market.json | jq .
python cli/ai_market_agent.py --base-url https://factory.example.com \
  "translate spec to 5 langs + legal review" --budget 3.0
```

## Versioning

REST under `/api/` — breaking changes should be noted in repo CHANGELOG / release tags. AI Market v1 paths are stable under `/ai-market` and `/.well-known/ai-market.json`.
