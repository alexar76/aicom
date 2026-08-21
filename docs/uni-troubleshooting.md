# UNI Mode — Troubleshooting & Typical Problems

UNI (Universe) mode runs a **local Anvil chain** inside Alien Monitor, deploys **FakeUSDT + AIMarketEscrow + AIMarketCapabilityNFT**, and polls **live** Hub / Mesh / Factory / Prometheus. This document lists what breaks most often and how to fix it.

See also: [uni-economy.md](./uni-economy.md) (architecture), [alien-monitor/README.md](https://github.com/alexar76/alien-monitor/blob/main/README.md) (deploy).

---

## What runs on production Docker today?

| Setting | Default in `docker-compose.prod.yml` |
|---------|--------------------------------------|
| `ALIEN_MODE` | `universe` (not TEST, not LIVE) |
| `ALIEN_UNIVERSE_AUTO_START` | `1` — Anvil + deploy on container start |
| Anvil state | `../data/alien-monitor/universe/anvil-state` (volume) |
| Config | `../data/alien-monitor/universe/universe_config.json` |
| Hub wiring hint | `../data/alien-monitor/universe/hub.env.snippet` |

**Before this fix:** the image had no `anvil`/`forge`, wrong `AICOM_ROOT` (pointed at `/` instead of contracts), and startup never called deploy — so prod showed UNI UI with **no chain**.

**After:** image bundles Foundry + `contracts/evm`, auto-bootstraps on startup, healthcheck waits for `blockchain_ready`.

---

## Quick diagnostics

```bash
# 1. Monitor health (no auth)
curl -s http://127.0.0.1:9100/api/health | jq .

# Expect in UNI:
#   "mode": "universe"
#   "blockchain_ready": true
#   "contracts": { "evm_usdt": "0x...", "evm_escrow": "0x...", "evm_nft": "0x..." }
#   "bootstrap": { "ok": true, ... }

# 2. Anvil RPC
cast chain-id --rpc-url http://127.0.0.1:8545   # 31337

# 3. On-chain code at escrow
cast code $(jq -r .contracts.evm_escrow <(curl -s http://127.0.0.1:9100/api/health)) \
  --rpc-url http://127.0.0.1:8545

# 4. Container logs
docker logs alien-monitor 2>&1 | tail -80

# 5. Saved addresses
cat data/alien-monitor/universe/universe_config.json | jq .
cat data/alien-monitor/universe/hub.env.snippet
```

---

## Typical problems

### 1. `blockchain_ready: false`, `anvil not found`

**Cause:** Foundry not on PATH (old image or custom Dockerfile without `anvil`).

**Fix:**

```bash
cd alien-monitor
docker compose -f docker-compose.prod.yml build --no-cache alien-monitor
docker compose -f docker-compose.prod.yml up -d alien-monitor
```

Verify inside container:

```bash
docker exec alien-monitor which anvil forge
```

---

### 2. USDT deploy OK, Escrow/NFT missing (`evm_escrow: null`)

**Cause:** `forge` failed; contracts dir missing; `INITIAL_TOKENS` empty (USDT step failed);
or `INITIAL_TOKENS` names a token whose `decimals()` is not exactly `6`.

**Fix:**

- Read logs: `[Universe] forge script/Deploy.s.sol failed:` — compile error, timeout, or wrong path.
- `UnsupportedTokenDecimals` in the revert means the escrow **refused** a token it
  cannot prove compatible: `MIN_DEPOSIT`/`MAX_DEPOSIT` are hard-coded in 6-decimal
  units, so the constructor rejects any token that does not answer `decimals()` with
  exactly `6` (an 18-decimal token would make the deposit range bound nothing). This
  is intentional fail-closed behaviour.
  > ⚠️ **Known break in UNI mode.** `contracts/evm/src/FakeUSDT.sol` does not override
  > `decimals()`, so it reports **18**, and `alien-monitor/backend/universe.py` feeds
  > exactly that address to the escrow deploy as `INITIAL_TOKENS`. The escrow
  > constructor therefore reverts and the bootstrap reports `evm_escrow: null`.
  > FakeUSDT needs `function decimals() public pure override returns (uint8) { return 6; }`
  > (and its `_mint` amount re-scaled from `1_000_000 ether`); until then, deploy a
  > 6-decimal test token yourself and pass its address in `INITIAL_TOKENS`.
- Ensure build context is **monorepo root** (`context: ..` in compose).
- On host, test manually:

```bash
cd contracts/evm
export PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
export INITIAL_HUBS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
export INITIAL_TOKENS=<usdt_from_universe_config.json>
forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast
```

---

### 3. Prod shows `mode: test` or `mode: real` instead of `universe`

**Cause:** `ALIEN_MODE` overridden in `.env` or old container.

**Fix:**

```bash
# In aicom/.env or compose override:
ALIEN_MODE=universe
ALIEN_UNIVERSE_AUTO_START=1

docker compose -f alien-monitor/docker-compose.prod.yml up -d --force-recreate alien-monitor
```

---

### 4. Hub has no liquidity / buyer cannot open channels

**Cause:** `AIFACTORY_UNI_GRANT_SECRET` unset — bootstrap grants to `universe:hub-treasury` and `universe:external-buyer` are skipped. Periodic funding still logs on-chain/synthetic txs but Factory UNI float stays zero.

**Fix:**

```bash
# In aicom/.env (Factory + Monitor read the same file on host network):
AIFACTORY_UNI_ENABLED=1
AIFACTORY_UNI_GRANT_SECRET=<long-random-secret>
ALIEN_UNIVERSE_HUB_LIQUIDITY_GRANT_USD=500
ALIEN_UNIVERSE_BUYER_LIQUIDITY_GRANT_USD=300
```

Restart Factory API and Alien Monitor. On EXPANSION, check logs: `[Funding] Hub liquidity bootstrap`.

---

### 5. UNI UI alive but Hub purchases / funding do nothing on-chain

**Cause:** Hub still points at mainnet/Base addresses; channel flow uses **SQLite ledger** with stub `tx_hash` unless Hub is wired to Anvil.

**Fix:** Merge generated snippet into `.env` and restart Hub:

```bash
cat data/alien-monitor/universe/hub.env.snippet
# → AIMARKET_ESCROW_EVM_ADDRESS, AIMARKET_NFT_CONTRACT, AIMARKET_PAYMENT_RECIPIENT, ALIEN_EVM_RPC
docker compose restart aimarket-hub   # or your hub service name
```

For strict on-chain verify, set `AIFACTORY_PAYMENT_VERIFY_STUB=0` only after RPC + addresses are correct.

---

### 5. `POST /api/universe/start` → 401 / 503

**Cause:** Production requires `ALIEN_API_TOKEN` when `ALIEN_ENV=production` or `AIFACTORY_PROD=1`.

**Fix:** Set token in `.env`, call with header:

```bash
curl -X POST -H "Authorization: Bearer $ALIEN_API_TOKEN" \
  http://127.0.0.1:9100/api/universe/start
```

Auto-start on boot does **not** need this call if `ALIEN_UNIVERSE_AUTO_START=1`.

---

### 6. Port 8545 already in use

**Cause:** Another Anvil/Ganache on host; `--with-infra` Ganache also uses 8545 (chain **1337**, not UNI).

**Fix:**

```bash
fuser -k 8545/tcp   # or stop conflicting process
# UNI uses Anvil 31337 only — do not mix with Ganache 1337
```

---

### 7. Healthcheck failing / container restart loop

**Cause:** Bootstrap slower than old 20s start_period; forge compile on first run.

**Fix:** Image runs `forge build` at build time; healthcheck `start-period: 90s`. If still failing:

```bash
docker logs alien-monitor
# Look for [Universe] lines
export ALIEN_ANVIL_VERBOSE=1   # anvil stderr visible
```

---

### 8. Solana node “online” but escrow program empty

**Cause:** `solana-test-validator` may start, but **Solana program is not auto-deployed** in UNI (EVM only).

**Fix:** Manual deploy:

```bash
cd contracts/solana && ./deploy.sh
# Set AIMARKET_ESCROW_SOLANA_PROGRAM_ID in .env
```

---

### 9. Factory products = 0 planets

**Cause:** Factory API down or no shipped products.

**Fix:**

```bash
curl -s http://127.0.0.1:9081/api/health
# Pipeline products appear after COMPLETED / listing
```

---

### 10. Buyer rounds = 0, phase stuck in BOOTSTRAP

**Cause:** Hub search returns no capabilities; Hub unreachable from monitor.

**Fix:**

```bash
curl -s "http://127.0.0.1:9083/ai-market/v2/search?intent=translate&budget=50&limit=5" | jq .
curl -s http://127.0.0.1:9100/api/universe/scenario -H "Authorization: Bearer $ALIEN_API_TOKEN" | jq .
```

---

## Ganache vs Anvil (do not confuse)

| Path | Chain | Port | Used for |
|------|-------|------|----------|
| `./start.sh --with-infra` | Ganache | 8545 | chainId **1337**, TEST seed scripts |
| `./start.sh universe` / Docker UNI | Anvil | 8545 | chainId **31337**, auto deploy |

---

### 11. `mode: test` in `/api/health` but container has `ALIEN_MODE=universe`

**Cause:** A WebSocket client sent `set_mode: test` (browser tab on `/monitor/`). Health reflects **runtime** mode, not only env.

**Fix:** Switch to UNI in the UI, or `curl -X POST …/api/universe/start`. Set `ALIEN_MODE=universe` and avoid auto-switching clients.

---

### 12. Port 9100 serves old dev server (not Docker)

**Cause:** `network_mode: host` — host `python main.py` blocks the port.

**Fix:**

```bash
fuser -k 9100/tcp
pkill -f alien-monitor/backend/main.py
docker compose -f alien-monitor/docker-compose.prod.yml up -d --force-recreate alien-monitor
```

---

### 13. `Insufficient funds for gas` on forge deploy

**Cause:** Stale `anvil-state` volume with wallets that do not match the default Anvil dev key.

**Fix:**

```bash
rm -rf data/alien-monitor/universe/anvil-state/*
docker compose -f alien-monitor/docker-compose.prod.yml restart alien-monitor
```

Bootstrap auto-resets state once when it detects this error.

---

### 14. `Failed to decode private key` / `Insufficient funds` on forge

**Cause:** Corrupt `ANVIL_DEPLOYER_KEY` in an old `universe.py` build, or stale `anvil-state`.

**Fix:** Pull latest (correct key matches `0xf39Fd…` / Foundry default). Wipe state:

```bash
rm -rf data/alien-monitor/universe/anvil-state/*
docker compose -f alien-monitor/docker-compose.prod.yml up -d --build --force-recreate alien-monitor
```

---

### 15. `USDT deploy failed: StackUnderflow`

**Cause:** Old inline ERC20 bytecode was invalid (fixed: `FakeUSDT.sol` + `forge script DeployFakeUSDT.s.sol`).

**Fix:** Rebuild image after pulling latest; verify `contracts/evm/src/FakeUSDT.sol` exists in the image.

---

### 16. Factory product clusters missing on the 3D map (UNI / LIVE)

**Symptoms:** Orange **star clusters** near the Factory node disappear; `factory.metrics.products` is `0`; logs show `factory catalog fetch failed` or `Factory catalog sync skipped — API unreachable`.

**Cause (most common):** Alien Monitor polls **`GET {AICOM_API_URL}/api/products`**. That endpoint can take **12–30s** under pipeline load. If the HTTP client times out (default was 8s), the sync treated the result as an empty catalog and **removed all product entities**.

**Fix (code, v0.6237e2+):**

- Fetch failure returns `None` → **existing clusters are kept** (no purge).
- Default timeout **25s**; set **`ALIEN_FACTORY_API_TIMEOUT=30`** (or higher) in `.env`.
- Ensure **`AICOM_API_URL=http://127.0.0.1:9081`** with prod compose **host network** (see `alien-monitor/docker-compose.prod.yml`).
- Keep **one** `ALIEN_MODE=universe` line in `.env` (duplicate `ALIEN_MODE=real` lines cause confusion).

**Verify:**

```bash
curl -s --max-time 45 http://127.0.0.1:9081/api/products | jq '.products | length'
curl -s http://127.0.0.1:9100/api/state | jq '[.nodes[] | select(.group=="cluster")] | length'
docker logs alien-monitor 2>&1 | grep -i 'factory catalog' | tail -5
```

**UNI vs TEST:** In **`ALIEN_MODE=universe`**, real Factory catalog **should** appear as clusters (storefront-listed products from `/api/products`). **TEST** mode does not sync the catalog — only a simulated counter on the Factory node.

**Empty catalog (not a timeout):** If `/api/products` returns `200` with `[]`, clusters are removed legitimately — e.g. strict QA gates hide all products from the public storefront. See pipeline QA docs; this is separate from API unreachable.

**Localized guides:** [alien-monitor-factory-catalog.md](./alien-monitor-factory-catalog.md) (EN · [RU](./alien-monitor-factory-catalog.ru.md) · [ES](./alien-monitor-factory-catalog.es.md)).

---

```bash
cd /path/to/aicom
rm -rf data/alien-monitor/universe/anvil-state
mkdir -p data/alien-monitor/universe

./scripts/deploy_alien_monitor.sh
# or:
cd alien-monitor && docker compose -f docker-compose.prod.yml up -d --build

sleep 30
curl -s http://127.0.0.1:9100/api/health | jq .
```

---

## Related env vars

| Variable | Purpose |
|----------|---------|
| `ALIEN_MODE` | `universe` \| `real` \| `test` |
| `ALIEN_UNIVERSE_AUTO_START` | `1` = bootstrap on startup (default in prod compose) |
| `ALIEN_UNIVERSE_ANVIL_STATE_DIR` | Persist Anvil chain between restarts |
| `AICOM_ROOT` / `AICOM_CONTRACTS_EVM_DIR` | Contract paths (Docker: `/app`, `/app/contracts/evm`) |
| `ALIEN_UNIVERSE_HUB_URL` | Hub for buyer/scenario (default `http://127.0.0.1:9083`) |
| `ALIEN_ANVIL_VERBOSE` | `1` = show Anvil stderr |
