# Deploy runbook — Argus in the Alien Monitor (+ LIVE crypto switch)

Audience: whoever (re)deploys the Alien Monitor on the server
(`/root/claudecode/aicom`, the monitor container `alien-monitor` on `:9100`,
public at `https://magic-ai-factory.com/monitor/`). Read this before deploying
the commits that add the Argus node + the LIVE crypto-honest-state.

---

## ⚠️ Pre-flight — the one thing not to forget

**To keep the demo on Base (real LIVE), set `AIFACTORY_CRYPTO_ENABLED=1` in the
server `.env`** (the ecosystem master switch, default OFF).

Two clarifications so nobody panics:

- **UNI is always there.** UNI has its own private local Anvil chain and is
  unaffected by this switch — deploying these commits does **not** move the demo
  off UNI.
- What the switch actually does: with crypto **ON**, the monitor's **LIVE** mode
  binds to Base and the on-chain nodes (chain · escrow · NFT · ACEX · lottery)
  **light up**. With crypto **OFF**, LIVE still runs, but those nodes are
  honestly **greyed/disabled** and a badge "Real blockchain disabled in
  settings" appears (links to `docs/crypto-switch.*`). This is intended honest
  state, not a bug.

For the monitor to be in LIVE at all (it currently runs `universe`), deploy with
`ALIEN_MODE=real`:

```bash
cd /root/claudecode/aicom
git pull origin main                       # must include commit ed50fae3 or later
ALIEN_MODE=real AIFACTORY_CRYPTO_ENABLED=1 ./scripts/deploy_alien_monitor.sh --live
```

If you instead want to keep showing the self-contained UNI demo, just deploy
normally (`./scripts/deploy_alien_monitor.sh`, defaults to `universe`) — the
Argus node still appears there.

---

## What changed (the feature)

- **Argus is now a node ("ball") in the ecosystem graph** in all three modes
  (TEST / UNI / LIVE). Clicking it opens an animated **verifiable-run panel**
  (calls a signed oracle → WARDEN refuses a malicious tool → hires+pays another
  agent over USDC → seals a verifiable receipt).
- **The global ARGUS button (right of REP) was removed** — the panel opens on
  node click instead. Multiple Argus nodes are supported by design.
- i18n: `argus.*` and `crypto.*` strings in **en / ru / es**.
- **LIVE crypto-honest-state**: in LIVE with crypto OFF the monitor never
  contacts a chain (`should_build_chain_context("real", false) === false`),
  greys all on-chain nodes, and shows the disabled badge.

## Why the deployed Argus wasn't visible before — and the remaining gap

- Before: there was simply **no Argus node** in the monitor topology. Now there
  is (hardcoded in `build_topology` for TEST/LIVE and `seed_entities` for UNI).
- **Important honest caveat:** the deployed Argus process did **not** yet
  register itself or push its runs. The node showed a representative DEFAULT run
  until a live Argus `POST`s a real run to `POST /api/argus/run`
  (monitor-auth). **As of ARGUS 0.2.4+**, set `ALIEN_MONITOR_URL` (or
  `MONITOR_URL`) and `ALIEN_API_TOKEN` on the Argus host — each completed run
  is pushed fail-soft to the monitor (120s TTL). **Production URL:**
  `https://magic-ai-factory.com/monitor` (nginx → `:9100`). Avoid
  `http://host.docker.internal:9100` when the monitor uses `network_mode: host`
  — UFW typically blocks Docker bridge → host `:9100`. Until a push succeeds,
  the panel shows the demo run (TEST) or waits for a live run (UNI/LIVE).

## Extensibility — how other instances auto-join (and Argus's gap)

- **Oracles (e.g. Platon on another server) auto-join via Hub federation**, in
  **both UNI and LIVE**: the operator adds the service's
  `/.well-known/ai-market.json` + pinned key to
  `aimarket-hub/.../federation_seeds.json`; the hub crawler indexes it; the
  monitor reads `GET /ai-market/v2/federation/peers` every tick and renders each
  peer (categories oracle/simulation/beacon…) as a distinct node. This is
  genuinely multi-instance (≤25 peers).
- **The lottery uses a single-slot PUSH feed** (`POST /api/lottery/update` →
  one in-memory slot, 30s TTL). One lottery only.
- **Argus today is neither**: `"argus"` is a hardcoded singleton node and
  `argus_feed` is a single slot (last `POST /api/argus/run` within 120s TTL
  wins). A second Argus on another server would **not** appear as a separate
  node. For true multi-Argus auto-registration we'd add either (a) hub-federation
  registration with an "agent" discovery category, or (b) a per-instance keyed
  push feed + the Argus app actually pushing its runs/heartbeat.

## Verify after deploy

```bash
# Argus node present
curl -s http://127.0.0.1:9100/api/topology | python3 -c "import sys,json;d=json.load(sys.stdin);print('argus:', any(n['id']=='argus' for n in d['nodes']))"
# Crypto switch reflected
curl -s http://127.0.0.1:9100/api/health   # expect crypto_enabled:true, chain_context:true in LIVE-on-Base
```
Then open the monitor, click the **Argus** ball → the verifiable-run panel
animates. In LIVE-with-crypto-off you should see the on-chain nodes greyed + the
"Real blockchain disabled in settings" badge bottom-left.

## Docs-link note

The badge's "How to enable" link points at `docs/crypto-switch.{md,ru.md,es.md}`
on GitHub. If the public mirror trims `docs/`, either ensure those files are
mirrored or set `VITE_CRYPTO_DOCS_URL` at build time to a reachable docs host.
