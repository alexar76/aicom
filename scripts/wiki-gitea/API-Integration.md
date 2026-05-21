# API integration

> Full guide: [`docs/api-integration-guide.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/api-integration-guide.md)

## Base URLs

| Context | Base |
|---------|------|
| Via Next proxy | `https://your-host/api/...` |
| Direct uvicorn | `http://host:9081/api/...` |

Interactive schema: **`/api/docs`** (Swagger).

## Auth patterns

| Pattern | Header / cookie |
|---------|-----------------|
| Admin session | `access_token` cookie + `X-CSRF-Token` on mutations |
| Admin API token | `Authorization: Bearer <jwt>` |
| Public | No auth — products, sandbox file, pipeline-status, support |

Login: `POST /api/admin/login` → sets cookies.

## High-value public endpoints

```http
GET /api/health
GET /api/public/pipeline-status
GET /api/products
GET /api/sandbox/file/{product_id}/index.html
GET /api/public/pipeline-demo-replay
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

Reference for agent-to-agent commerce: [`docs/ai-market-protocol-v0.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/ai-market-protocol-v0.md)

## Versioning

REST under `/api/` — breaking changes should be noted in repo CHANGELOG / release tags.
