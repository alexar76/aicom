# API integration guide

Use this together with **Swagger UI** at **`/api/docs`** on your deployment (proxied through Next.js as **`http(s)://<host>/api/docs`**). OpenAPI JSON is served by FastAPI as **`/openapi.json`** on the backend port.

---

## Base URLs

| Deployment | Typical browser API base |
|------------|-------------------------|
| Docker Compose (README defaults) | `http://localhost:9080/api` (frontend proxies to backend) |
| Direct backend debugging | `http://localhost:8081/api` |

Paths below are **suffixes** after `/api` unless noted.

---

## Authentication

### Admin (JWT)

1. `POST /api/admin/auth/login` with JSON body `{ "username": "admin", "password": "…", "totp_code": "optional" }`.
2. The backend sets an **HTTP-only cookie** `access_token` (see `web/backend/core/security.py`).
3. Subsequent admin calls from the browser reuse the cookie automatically.
4. **API clients / curl:** send `Authorization: Bearer <jwt>` **or** forward the cookie.

Most `/api/admin/*` routers use `Depends(get_current_admin)` except **`/api/admin/auth/*`** (public login).

### Customer accounts

`POST /api/customer/register`, `POST /api/customer/login` — storefront account flows (see router for JWT handling).

### Support chat sessions

When `AIFACTORY_SUPPORT_REQUIRE_TOKEN` is enabled (default **on**), mutating support endpoints expect header **`X-AIF-Support-Token`** returned from session creation. See `web/backend/api/support_chat.py`.

---

## Public and storefront APIs (no admin JWT)

| Prefix | Purpose |
|--------|---------|
| `GET /api/health` | Liveness / version |
| `/api/products`, `/api/products/{id}` | Storefront catalog & detail (listing applies quality + hide rules on shipped products) |
| `/api/products/categories` | Category counts aligned with listing filters |
| `/api/sandbox/*` | Sandbox preview lifecycle |
| `/api/payment/*` | Crypto / checkout helpers |
| `/api/feedback/*` | Product feedback |
| `/api/marketing/*` | Public marketing endpoints |
| `/api/support/*` | Lumen — support chat sessions & messages (storefront buyer help, not MS Copilot) |
| `/api/telemetry/*` | Client telemetry ingestion |
| `/api/customer/*` | Registration, login, entitlements (see routes) |

**Note:** `/ai-market/*` is a **separate pilot router** (prefix **without** `/api`) for AI-to-AI protocol experiments — do not confuse it with the main storefront catalog.

---

## Admin APIs (JWT required)

| Area | Illustrative endpoints |
|------|-------------------------|
| Dashboard & metrics | `GET /api/admin/dashboard`, `GET /api/admin/metrics/stream` (SSE), WebSocket metrics |
| Pipeline | `GET /api/admin/pipeline/products`, product specs, files browser |
| Product lifecycle | `POST /api/admin/products/create`, batch create, discovery hooks |
| Storefront operator | `PATCH /api/admin/pipeline/products/{id}/followup`, `PATCH .../storefront-admin`, `PATCH .../marketplace-copy` |
| LLM | `GET/PATCH /api/admin/providers`, routing rules |
| Security | Audit logs, password rotation |
| Director | Reports, discovery runs |
| Collaboration | `GET/POST /api/admin/chat/*`, `GET/POST /api/admin/discussions/*` |
| Support queue | `GET /api/admin/support-queue/*` |
| Release | `GET /api/admin/release/*` |

Exact paths evolve — **prefer Swagger** as source of truth after upgrades.

---

## curl examples

### Health

```bash
curl -sS http://localhost:9080/api/health | jq .
```

### Admin login + cookie jar

```bash
curl -sS -c cookies.txt -X POST http://localhost:9080/api/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'
curl -sS -b cookies.txt http://localhost:9080/api/admin/dashboard | jq .
```

### Create product (admin)

```bash
curl -sS -b cookies.txt -X POST http://localhost:9080/api/admin/products/create \
  -H 'Content-Type: application/json' \
  -d '{"idea":"A landing page for pet sitters in Berlin","instructions":"Keep scope MVP"}' | jq .
```

### Discovery enqueue (admin)

```bash
curl -sS -b cookies.txt -X POST http://localhost:9080/api/admin/discovery/run \
  -H 'Content-Type: application/json' \
  -d '{"create_product":true,"top_k":5}' | jq .
```

### Storefront listing (public)

```bash
curl -sS 'http://localhost:9080/api/products?category=saas' | jq '.count'
```

---

## Integration nuances

- **CORS:** Backend enables CORS middleware; browser sessions normally go through the Next.js origin so cookies stay same-site.
- **Rate limits:** Support chat enforces per-IP limits (`support_chat.py`).
- **Large payloads:** Task modals and file previews truncate — use SSH / mounted volume for full logs.
- **Idempotency:** Payment and customer endpoints may require idempotency keys — check Swagger models per route.

---

## Related documentation

- [owner-guide.md](./owner-guide.md) — operator scenarios tying UI ↔ API  
- [admin-guide.md](./admin-guide.md) — tab-by-tab mapping  
- [marketing.md](./marketing.md) — storefront behavior & env vars  
- [ai-market-protocol-v0.md](./ai-market-protocol-v0.md) — separate `/ai-market` pilot  
