# 🔍 AI Service Mesh — Security & Quality Audit

**Audit date:** 2026-05-23  
**Version:** 0.1.0  
**Scope:** All source files under `ai-service-mesh/` (backend Python, frontend TypeScript/React, Docker, tests, docs, scripts)  
**Verdict:** Production-ready skeleton with solid security foundations; several medium-severity issues to address before external exposure.

---

## 📊 Summary

| Category | Critical | High | Medium | Low | Info |
|----------|----------|------|--------|-----|------|
| Backend | 0 | 0 | 5 | 3 | 4 |
| Frontend | 0 | 0 | 2 | 1 | 2 |
| Docker/Infra | 0 | 1 | 2 | 1 | 2 |
| Tests | 0 | 0 | 1 | 0 | 2 |
| **Total** | **0** | **1** | **10** | **5** | **10** |

---

## 🔴 High Severity

### H1 — Docker Compose ships well-known default tokens

**File:** [`docker-compose.yml`](docker-compose.yml:27-28)

```yaml
MESH_API_TOKEN: ${MESH_API_TOKEN:-mesh-local-api}
MESH_ADMIN_TOKEN: ${MESH_ADMIN_TOKEN:-mesh-local-admin}
```

Anyone who deploys `docker compose up` without setting `MESH_API_TOKEN`/`MESH_ADMIN_TOKEN` gets predictable, publicly documented default tokens. An attacker reading this file (or the README) can authenticate to any production instance where defaults were not overridden.

**Impact:** Full API access (create tasks, spend budget) and admin access (register agents).

**Fix:** Remove the shell-fallback defaults. Require tokens to be explicitly set, or generate them at container startup with a warning.

```yaml
MESH_API_TOKEN: ${MESH_API_TOKEN:?err "MESH_API_TOKEN must be set"}
MESH_ADMIN_TOKEN: ${MESH_ADMIN_TOKEN:?err "MESH_ADMIN_TOKEN must be set"}
```

---

## 🟡 Medium Severity

### M1 — Synchronous DNS resolution blocks the async event loop

**File:** [`security.py`](ai-service-mesh/backend/ai_service_mesh/security.py:58-64)

```python
try:
    for family, _, _, _, sockaddr in socket.getaddrinfo(host, parsed.port or 443):
        if family in (socket.AF_INET, socket.AF_INET6):
            if _ip_blocked(sockaddr[0]):
                return False
except socket.gaierror:
    return False
```

`socket.getaddrinfo()` is a synchronous blocking call. In a FastAPI async handler, this blocks the entire event loop for the duration of the DNS resolution (typically 50–300ms, but up to 5s on timeout). Under concurrent load, this degrades all other requests.

**Fix:** Wrap in `await asyncio.to_thread(...)` or `loop.run_in_executor()`:

```python
import asyncio

async def _resolve_host(host: str, port: int) -> list[tuple[int, str]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: socket.getaddrinfo(host, port)
    )
```

### M2 — Rate limiter has unbounded memory growth (memory leak)

**File:** [`security.py`](ai-service-mesh/backend/ai_service_mesh/security.py:78-91)

```python
class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.time()
        window = self._hits[key]
        self._hits[key] = [t for t in window if now - t < 60.0]
        ...
```

The dictionary `_hits` grows forever. When a new IP address appears, a new list is created. But when an IP stops sending requests, its key (and the empty list `[]`) remains forever. With IPv6 prefixes, CDN/proxy IPs, or a long-running deployment, this accumulates thousands of dead entries.

**Fix:** Periodically purge stale keys. Simplest approach: every N calls, scan and remove keys with empty lists.

```python
def check(self, key: str) -> None:
    now = time.time()
    # Purge stale keys every 1000 checks
    self._check_count += 1
    if self._check_count % 1000 == 0:
        stale = [k for k, v in self._hits.items() if not v]
        for k in stale:
            del self._hits[k]
    ...
```

Alternatively, use a TTL-based cache like `cachetools.TTLCache`.

### M3 — Task pipeline fails on first match without retry fallback

**File:** [`orchestrator.py`](ai-service-mesh/backend/ai_service_mesh/orchestrator.py:36-158)

The `run_task` method sorts matches by score (`matches.sort(key=lambda m: m.score, reverse=True)`) and then only attempts the top result:

```python
best = matches[0]
...
invoke_ok, latency, detail, _raw = await self._invoke_match(best, task.intent)
```

If the top agent's invocation fails (timeout, 500, etc.), the entire task fails. The remaining 11 candidates in `matches` are never tried. Discovery returns up to 12 results but only 1 is ever used.

**Impact:** Artificially low task success rate. A single slow agent fails the task even when 11 other capable agents are available.

**Fix:** Iterate through matches until one succeeds or all fail.

```python
for match in matches[:3]:  # try top 3
    invoke_ok, latency, detail, _raw = await self._invoke_match(match, task.intent)
    if invoke_ok:
        best = match
        break
else:
    # all failed
    task.status = TaskStatus.FAILED
    ...
```

### M4 — Hub agents skip preflight health check

**File:** [`orchestrator.py`](ai-service-mesh/backend/ai_service_mesh/orchestrator.py:160-163)

```python
async def _preflight(self, match: DiscoveryMatch) -> tuple[bool, int, str]:
    if match.source == "hub" and match.agent.product_id:
        return True, 0, "hub_capability_indexed"
    return await preflight_agent(match.agent.endpoint_url)
```

Hub-discovered agents are always assumed healthy. The `preflight_agent` HTTP health check is entirely bypassed. If the hub indexes a capability that is currently down, the mesh will still attempt to route paid tasks to it, burning escrow cycles on a guaranteed failure.

**Impact:** Wasted escrow holds and failed invocations for hub-indexed agents that are offline.

**Fix:** At minimum, do a lightweight HEAD/GET health check on the hub's invoke endpoint before routing. Or have the hub expose agent health status in search results.

### M5 — `_invoke_match` can route to empty hub URL

**File:** [`orchestrator.py`](ai-service-mesh/backend/ai_service_mesh/orchestrator.py:165-186)

```python
async def _invoke_match(self, match: DiscoveryMatch, intent: str):
    agent = match.agent
    if match.source == "hub" or (agent.product_id and agent.capability_id and self._hub_url):
        hub = self._hub_url or agent.endpoint_url
        return await invoke_via_hub(...)
    if agent.product_id and agent.capability_id:
        return await invoke_via_hub(   # <— self._hub_url could be ""
            self._hub_url,
            agent.product_id,
            ...
        )
    return await invoke_direct(agent.endpoint_url, intent)
```

The second `if` block (line 177) triggers when `match.source != "hub"` but `agent.product_id` and `agent.capability_id` are set. It then passes `self._hub_url` (which may be empty string `""`) to `invoke_via_hub`, constructing a URL like `/ai-market/v2/invoke` — guaranteed to fail.

**Fix:** Guard the second block with a hub URL check:

```python
if agent.product_id and agent.capability_id and self._hub_url:
    return await invoke_via_hub(...)
```

### M6 — Frontend polls every 4s instead of using SSE stream

**File:** [`App.tsx`](ai-service-mesh/frontend/src/App.tsx:35-39)

```typescript
useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 4000);
    return () => clearInterval(id);
}, [refresh]);
```

The dashboard polls all 4 endpoints (stats, agents, activity, tasks) every 4 seconds, generating 1 request/second to the API. The backend already exposes `/v1/activity/stream` as a Server-Sent Events endpoint for real-time activity. Polling the full dataset is wasteful at scale.

**Impact:** Unnecessary load on the API. With 50 concurrent dashboard users, that's 50 req/s sustained.

**Fix:** Use `EventSource` to consume `/v1/activity/stream` for activity updates, and only poll stats/agents/tasks at a slower interval (15–30s).

### M7 — SQLite migration pattern silently swallows all schema errors

**File:** [`db.py`](ai-service-mesh/backend/ai_service_mesh/db.py:96-104)

```python
for col_def in (
    "product_id TEXT NOT NULL DEFAULT ''",
    "capability_id TEXT NOT NULL DEFAULT ''",
    "source_hub TEXT NOT NULL DEFAULT 'local'",
):
    try:
        c.execute(f"ALTER TABLE agents ADD COLUMN {col_def}")
    except sqlite3.OperationalError:
        pass
```

Any `OperationalError` during migration (disk full, permission denied, locked database, corrupt schema) is silently discarded. This masks real failures as successful no-ops.

**Fix:** Check for the specific "duplicate column" error:

```python
except sqlite3.OperationalError as e:
    if "duplicate column" not in str(e).lower():
        raise
```

### M8 — No nginx SPA fallback routing in frontend Docker image

**File:** [`frontend/Dockerfile`](ai-service-mesh/frontend/Dockerfile:8-10)

```dockerfile
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

The default nginx configuration does not include `try_files $uri $uri/ /index.html`. If a user navigates directly to a client-side route (e.g., `/tasks/tsk_abc123`) or refreshes the page, nginx returns a 404 because that path doesn't exist on disk.

**Fix:** Add a custom nginx config:

```dockerfile
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

With `try_files $uri $uri/ /index.html;` in the location block.

### M9 — Orchestrator skips `update_task` before verification phase

**File:** [`orchestrator.py`](ai-service-mesh/backend/ai_service_mesh/orchestrator.py:55-56)

```python
task.status = TaskStatus.VERIFYING
self._store.update_task(task)
```

The task status is updated to `VERIFYING` but if the orchestrator crashes after this line and before the preflight check completes, the task is stuck in `VERIFYING` forever. No timeout mechanism or dead-letter recovery exists.

**Fix:** Add a task timeout mechanism or a periodic sweep that moves stale tasks to `FAILED`.

### M10 — Test DNS monkeypatch is too broad

**File:** [`conftest.py`](ai-service-mesh/backend/tests/conftest.py:52-63)

```python
@pytest.fixture(autouse=True)
def public_dns(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        return
    import socket

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host in ("localhost", "127.0.0.1"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port or 80))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
```

This patches `socket.getaddrinfo` globally for all unit tests. Any test (or library) that needs real DNS resolution will silently get fake results. The fixed IP `93.184.216.34` (example.com) is used for all non-localhost hosts, which means URL safety checks for `https://evil.internal` would resolve to a safe public IP — masking SSRF bypasses in tests.

**Fix:** Only patch for security-specific tests. The `public_dns` fixture should not be `autouse=True`.

---

## 🔵 Low Severity

### L1 — Hardcoded budget in frontend task submission

**File:** [`App.tsx`](ai-service-mesh/frontend/src/App.tsx:44)

```typescript
await meshApi.createTask(taskIntent, 3.5);
```

The budget is hardcoded to `$3.50`. Users cannot adjust it from the UI.

### L2 — Static `_ENV_FILE` path resolution

**File:** [`config.py`](ai-service-mesh/backend/ai_service_mesh/config.py:11)

```python
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
```

Assumes the config module is exactly 2 levels deep from the project root. If the package is reorganized or installed as a site-package, this path breaks silently (pydantic-settings just doesn't load the file).

### L3 — `MeshTopology` is purely decorative

**File:** [`MeshTopology.tsx`](ai-service-mesh/frontend/src/components/MeshTopology.tsx:1-55)

The SVG visualization uses fixed positions and the "Mesh Core" node is always at the center regardless of which agents are connected. No interactive hover/click, no actual topology data (it's a star topology hardcoded). Misleading as a "topology" view.

### L4 — No structured logging

All logging uses `logging.info()` / `logging.warning()` with f-strings. In production, structured JSON logging is expected for SIEM ingestion (as mentioned in [deployment.md](docs/deployment.md:38): "Structured logs from uvicorn (JSON formatter recommended)"). The application itself doesn't output JSON logs.

### L5 — `stats()` method could be expensive under load

**File:** [`db.py`](ai-service-mesh/backend/ai_service_mesh/db.py:340-372)

The `stats()` method fetches ALL tasks from the last 24 hours and iterates them in Python to count hops and compute success rate. With 10k+ tasks/day, this becomes an expensive in-memory operation. SQL could compute these aggregates directly.

---

## ℹ️ Informational

### I1 — Escrow is in-memory/SQLite (no real funds)

**File:** [`payments.py`](ai-service-mesh/backend/ai_service_mesh/payments.py:1-33)

The `EscrowLedger` stores holds in SQLite with no cryptographic guarantees. This is documented as "v0.1 dev" and the roadmap plans TEE escrow via `aimarket-plugins`. Not a bug — just a known limitation.

### I2 — No agent authentication on `invoke_direct`

**File:** [`invoke.py`](ai-service-mesh/backend/ai_service_mesh/invoke.py:80-97)

`invoke_direct` sends an unauthenticated POST to the agent's `/invoke` endpoint. There's no API key, JWT, or mTLS between mesh and agent. Phase 2 roadmap mentions mTLS.

### I3 — Activity stream uses polling internally

**File:** [`api.py`](ai-service-mesh/backend/ai_service_mesh/api.py:200-211)

The SSE `/v1/activity/stream` endpoint polls the database every 2 seconds (`await asyncio.sleep(2)`). A proper push-based mechanism (Redis pub/sub, `asyncio.Queue` with notify) would be more efficient.

### I4 — No database connection pooling

SQLite is used with `check_same_thread=False` and a threading lock. For a single-process deployment this works, but if the app were to use multiple workers (gunicorn with multiple processes), SQLite would become a bottleneck. The architecture doc correctly notes this should be PostgreSQL for HA.

### I5 — Missing test coverage areas

No dedicated tests exist for:
- `discovery.py` — capability scoring, hub federation, price estimation
- `verification.py` — attestation validation, key loading edge cases
- `payments.py` — escrow hold/release/refund lifecycle
- `db.py` — direct CRUD operations, migration edge cases

### I6 — API allows unauthenticated reads by design

**File:** [`api.py`](ai-service-mesh/backend/ai_service_mesh/api.py:79-83)

When `MESH_API_TOKEN` is unset, reads (GET endpoints) are fully open. This is fail-open for development convenience. Production deployments MUST set the token.

### I7 — WebSocket upgrade not supported

The dashboard uses polling instead of WebSockets. SSE is available for activity streaming. WebSocket would be more efficient for bidirectional real-time updates but is not implemented.

### I8 — No pagination cursors for activity/tasks

List endpoints use `limit` + `since_id` for activity but tasks only use `limit`. For large datasets, offset-based or cursor-based pagination would be needed.

### I9 — Vite dev proxy only forwards `/v1` and `/health`

**File:** [`vite.config.ts`](ai-service-mesh/frontend/vite.config.ts:8-11)

The proxy doesn't forward `/docs` (OpenAPI) or `/openapi.json`, preventing devs from accessing the Swagger UI through the Vite dev server.

### I10 — `register_e2e_agent.py` script not found in audit

The `run-infra-test.sh` script references `scripts/register_e2e_agent.py` but only `scripts/real_agent_server.py` and `scripts/run-infra-test.sh` exist in the directory listing. This script is missing from the repository.

---

## 🛡️ Security Strengths (What's Done Well)

1. **SSRF protection** — [`url_is_safe()`](ai-service-mesh/backend/ai_service_mesh/security.py:40-65) performs DNS-resolving IP checks against private/loopback/link-local/reserved ranges, blocks `metadata.google.internal`, strips null bytes, and enforces HTTPS. This is a thorough implementation.

2. **Fail-closed CORS** — Empty `MESH_CORS_ORIGINS` means no cross-origin access. Origins must be explicitly configured.

3. **Constant-time token comparison** — Uses [`hmac.compare_digest`](ai-service-mesh/backend/ai_service_mesh/security.py:74) for Bearer token verification, preventing timing attacks.

4. **Security headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` on all responses.

5. **Attestation verification** — SHA-256 canonical metadata attestation with base64url encoding and proper padding handling.

6. **PEM public key validation** — Only RSA and Ed25519 keys are accepted; other key types are rejected.

7. **Demo output rejection** — [`response_is_demo_marked()`](ai-service-mesh/backend/ai_service_mesh/invoke.py:11-22) prevents demo/factory executions from being treated as real paid invocations.

8. **Clean separation of concerns** — `config.py`, `db.py`, `discovery.py`, `orchestrator.py`, `payments.py`, `security.py`, `verification.py` are well-isolated modules.

9. **Comprehensive .gitignore** — Covers Python, Node, database files, environment files.

---

## 📋 Action Items (Priority Order)

| # | Severity | ID | Status | Action |
|---|----------|----|--------|--------|
| 1 | 🔴 High | H1 | ✅ Fixed | Remove default tokens from docker-compose.yml |
| 2 | 🟡 Medium | M1 | ✅ Fixed | Make `url_is_safe()` async with `asyncio.to_thread` |
| 3 | 🟡 Medium | M2 | ✅ Fixed | Add stale-key purging to RateLimiter |
| 4 | 🟡 Medium | M3 | ✅ Fixed | Implement retry-with-fallback in orchestrator |
| 5 | 🟡 Medium | M5 | ✅ Fixed | Fix `_invoke_match` empty hub URL branch |
| 6 | 🟡 Medium | M7 | ✅ Fixed | Narrow exception handling in DB migrations |
| 7 | 🟡 Medium | M8 | ✅ Fixed | Add SPA fallback nginx config |
| 8 | 🟡 Medium | M10 | ✅ Fixed | Remove `autouse=True` from DNS monkeypatch |
| 9 | 🟡 Medium | M4 | ✅ Fixed | Add hub-agent health preflight (`preflight_hub`) |
| 10 | 🟡 Medium | M6 | ✅ Fixed | Use SSE stream for activity in frontend |
| 11 | 🟡 Medium | M9 | ✅ Fixed | Add task timeout/dead-letter recovery |
| 12 | 🔵 Low | L1 | ✅ Fixed | Configurable task budget in dashboard UI |
| 13 | 🔵 Low | L2 | ✅ Fixed | Robust `.env` path resolution in config |
| 14 | 🔵 Low | L3 | ✅ Fixed | Topology shows verified peer count |
| 15 | 🔵 Low | L4 | ✅ Fixed | JSON structured logging in production |
| 16 | 🔵 Low | L5 | ✅ Fixed | SQL aggregates for stats volume/success rate |

---

## 🏁 Overall Assessment

The AI Service Mesh codebase is well-structured, follows solid security principles, and has appropriate documentation. The architecture is clean and the separation of concerns is excellent for a v0.1 product. The main risks for production deployment are:

1. **Default tokens in Docker Compose** — the only high-severity finding.
2. **Blocking DNS in async context** — will cause performance degradation under load.
3. **No retry fallback** — limits task success rate unnecessarily.
4. **Memory leak in rate limiter** — will manifest after days/weeks of uptime.

All issues are fixable with targeted, low-risk changes. The product is on a solid trajectory for the Phase 2 roadmap milestones.
