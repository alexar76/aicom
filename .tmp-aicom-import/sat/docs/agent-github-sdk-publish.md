# Agent brief — publish SDKs & plugins to npm / PyPI

**Audience:** CI agent with registry tokens (`NPM_TOKEN`, `PYPI_TOKEN`).  
**Source of truth:** monorepo paths below — implement and test here first, then mirror + publish.

---

## Package status (audit 2026-06)

| Package | Registry | Monorepo path | Action |
|---------|----------|---------------|--------|
| `aimarket-agent` | PyPI 2.1.0 | `aimarket-agent/` | ✅ published — bump via `aimarket-agent/.github/workflows/publish-pypi.yml` |
| `aimarket-hub` | PyPI 3.0.0 | `aimarket-hub/` | ✅ published |
| Hub plugins (tee, channels, …) | PyPI 2.0.0 | `plugins/aimarket-*` | ✅ most published |
| `aimarket-safety`, `aimarket-mcp-packager` | PyPI | `plugins/` | ⏳ rate limit — publish when unblocked |
| **`aimarket-zk`** | PyPI **404** | `plugins/aimarket-zk/` | **P0 — publish** (`pyproject.toml` v2.0.0 ready) |
| **`@aimarket/agent`** | npm 0.1.0 → **0.1.1** | `aimarket-sdks/typescript/` | **P0 — publish fix** (CommonJS `require()` + exports map) |
| `aimarket-federation` | PyPI 404 | **does not exist** | **Remove from any external docs** — federation is built into `aimarket-hub`, not a separate package |

---

## 1. Mirror satellites before publish

```bash
./scripts/mirror_satellites.sh aimarket-sdks
./scripts/mirror_satellites.sh aimarket-plugins   # includes aimarket-zk
./scripts/mirror_satellites.sh aimarket-agent
```

---

## 2. `@aimarket/agent` npm (P0)

**Bug:** `require('@aimarket/agent')` on Node 22 → `ERR_MODULE_NOT_FOUND` (ESM output without proper exports).

**Fix in monorepo (v0.1.1):**
- `aimarket-sdks/typescript/tsconfig.json` → `"module": "CommonJS"`
- `package.json` → `"exports"` map + version `0.1.1`

**Publish:**

```bash
cd aimarket-sdks/typescript
npm ci && npm test && npm run build
node -e "const {AimarketAgent}=require('.'); console.log(typeof AimarketAgent)"
npm publish --access public
```

Or trigger `aimarket-sdks/.github/workflows/publish-npm.yml` after push to `alexar76/aimarket-sdks`.

**Post-publish verify on VPS:**

```bash
docker run --rm -it node:22-bookworm-slim bash -c \
  'npm i @aimarket/agent@0.1.1 && node -e "console.log(require(\"@aimarket/agent\").AimarketAgent)"'
```

---

## 3. `aimarket-zk` PyPI (P0)

**Bug:** docs say `pip install aimarket-zk` — package not on PyPI.

**Monorepo docs fixed** to `pip install -e plugins/aimarket-zk` until publish.

**Publish:**

```bash
cd plugins/aimarket-zk
python3 -m pip install build twine
python3 -m build
twine upload dist/aimarket_zk-2.0.0*
```

Requires `PYPI_TOKEN`. Plugin entry point: `aimarket.plugins.zk`.

After publish, revert docs to show `pip install aimarket-zk` as primary (optional).

---

## 4. `aimarket-federation` — do not publish

No `aimarket-federation` package exists. Federation crawler lives in `aimarket-hub/aimarket_hub/crawler.py`.

If any landing/README still mentions `pip install aimarket-federation`:
- Replace with `pip install aimarket-hub` (server) or remove the line.

---

## 5. E2E verification scripts (monorepo)

After VPS deploy:

```bash
./scripts/verify_ecosystem_full.sh          # fleet smoke (27 checks)
./scripts/sdk_e2e_hello.sh                # publish hello + Python SDK receipt
./scripts/verify_ecosystem_landing_links.sh # GitHub URLs on landing
```

SDK tests on minimal VPS **without** host pip/nodejs: `sdk_e2e_hello.sh` uses Hub container Python.

---

## 6. ARGUS economy on VPS (operator, not publish)

Documented in `docs/deploy-vps-trimmed.md` and `argus/docs/developer-guide/en.md`:

- `ARGUS_WALLET_KEY` (64 hex) or keystore required for `argus economy discover`
- HTTP `POST /ask` does not auto-approve paid `hub_invoke` — use `argus economy invoke` or approval policy

---

## Related

- Factory mirror agent: [`agent-github-factory-publish.md`](./agent-github-factory-publish.md)
- VPS operator: [`deploy-vps-trimmed.md`](./deploy-vps-trimmed.md)
- Plugin index: [`plugins/README.md`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/README.md)
