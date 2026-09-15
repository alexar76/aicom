# Ecosystem auto-discovery — how nodes find each other (and appear in the Monitor)

> Goal: the ecosystem behaves like a **living organism** — a new node (e.g. the
> external **Platon Shadow Oracle** at `http://oracles.modelmarket.dev/`) appears in the
> Alien Monitor **automatically**, with no hand-edited node lists, no
> `PLATON_URL`, and no per-node webhook wiring. This document describes the
> mechanism, the security model, and the remaining manual-wiring "crutches"
> with their remediation status.

---

## 1. The corrected mental model

An earlier analysis claimed discovery "already worked" and that the Monitor only
needed a one-line patch. Fact-checking it against the code showed most of its
*concrete* claims were wrong for **this** repo (there was no `aimarket.py`, no
`PLATON_URL`, no `kappa`/`order_parameter` fields, and no Platon anywhere). What
was true is the **architectural principle**. Two distinct channels were being
conflated:

| Channel | Purpose | Before | After |
|---|---|---|---|
| **Hub federation** | Agents discover & invoke `platon.*@v1` via the AIMarket Hub | crawler existed but **never ran on a schedule**, seed list empty, first-contact indexing gated behind manual key approval | **auto-crawl scheduler** + committed seed + **operator-pinned key** ⇒ Platon indexed automatically |
| **Monitor pull** | Monitor renders nodes + live metrics | only polled `{HUB}/ai-market/v2/stats/live`; node list hardcoded in `build_topology()`; a new node never appeared | Monitor now reads **`/ai-market/v2/federation/peers`** and renders matching peers with live `/api/health` |
| Monitor push (webhook) | live events into the activity feed | `POST /api/universe/materialize` (factory→monitor) | unchanged — **not** required for a node to appear |

The webhook is *not* the path by which a node appears; federation discovery is.

---

## 2. End-to-end flow

```
                    ┌──────────────────────── AIMarket Hub (aimarket-hub) ───────────────────────┐
 federation_seeds.json   seed_list ──▶ Crawler (BFS, SSRF-hardened, key-pinning)                 │
 (Platon well-known +                     │  GET {peer}/.well-known/ai-market.json  (validate)    │
  pinned pubkey)                           │  GET {peer}/ai-market/v2/manifest        (verify sig) │
        │                                  ▼                                                       │
        └────────── auto-crawl loop ──▶ peers table (url, categories, pubkey, trust)              │
           (lifespan task, every                 │                                                 │
            crawl_interval_s)                     ├─▶ GET /ai-market/v2/federation/peers  ◀─────────┼──┐
                                                  └─▶ GET /ai-market/v2/search (platon.*@v1)        │  │
                    └───────────────────────────────────────────────────────────────────────────┘  │
                                                                                                     │
                    ┌──────────────────────── Alien Monitor (alien-monitor) ────────────────────────┘
 hub_discovery.py:  GET {HUB}/ai-market/v2/federation/peers  ──▶ for each peer with a matching
                    category {oracle, simulation, math-viz, randomness-beacon}:
                       GET {peer}/.well-known/ai-market.json   (categories / name / ecosystem)
                       GET {peer}/api/health                   (κ, order_parameter, tick, viewers)
                    ──▶ emit graph node (group "oracle") + link from the "federation" node
                    ──▶ merged in REAL mode (fetch_real_metrics) and UNIVERSE mode (tick_universe)
                    ──▶ React/Three.js renders it; NodeDetail shows κ / order_parameter live
```

**Platon's real surface** (verified live 2026-06-13):
`/.well-known/ai-market.json` → `categories:["simulation","math-viz","oracle","agent-tooling"]`,
`signer_public_key:"+UWIwNJV6W5S8yMfWRsPz9MYhun90pcaeFiI6eRA5Jc="`;
`/api/health` → `{kappa, order_parameter, tick, viewers, …}`;
`/ai-market/v2/manifest` → 6 ed25519-signed `platon.*@v1` capabilities.

---

## 3. Hub changes (`aimarket-hub/aimarket_hub/`)

- **Auto-crawl scheduler** — `api.py` now installs a FastAPI `lifespan` task that
  runs the federation crawler every `crawl_interval_s` (default 3600s, advertised
  but previously never consumed). Non-overlapping, jittered, fault-isolated, and
  cancelled cleanly on shutdown. Opt out with `AIMARKET_AUTO_CRAWL=0`.
- **Committed seed list** — `federation_seeds.json` ships the Platon well-known
  URL, so `config.seed_list` is non-empty out of the box (env `AIMARKET_SEED_LIST`
  still overrides; an explicitly empty env value falls back to the file).
- **Operator-vouched trusted-seed pinning** — `crawler._crawl_one` trusts and
  **indexes a seed on first contact** when the peer advertises exactly the
  operator-pinned key   (`federation_seeds.json` `public_key` / `AIMARKET_SEED_PUBKEYS`).
  Seed pins apply on **first contact only**. After that the DB pin is sticky; a
  legitimate key rotation needs admin `POST /federation/peers/repin`, and a
  mismatch shows up on `/federation/peers` as `peer rejected: key changed`
  (see [`aimarket-hub/docs/federation-peer-keys.md`](https://github.com/alexar76/aimarket-hub/blob/main/docs/federation-peer-keys.md)).
  A key mismatch falls back to the safe untrusted-first-contact path (record peer,
  skip indexing until manual approval). This keeps the TOFU security model while
  letting a known node light up automatically.
- **Categories propagation** — peers now carry their self-declared
  `categories` (migration `006_peer_categories`, `Peer.categories`, DB read/write).
  Exposed in `/.well-known/ai-market.json` peers and in `/ai-market/v2/federation/peers`
  (plus `well_known_url`) so the Monitor can filter without a second fetch.

### Hub config / env reference

| Env var | Default | Meaning |
|---|---|---|
| `AIMARKET_AUTO_CRAWL` | `1` | Periodic federation crawl on/off |
| `AIMARKET_CRAWL_INTERVAL_S` | `3600` | Crawl period (min clamped to 60s) |
| `AIMARKET_CRAWL_INITIAL_DELAY_S` | `5` | Delay before first crawl after startup |
| `AIMARKET_SEED_LIST` | *(file)* | Comma-sep well-known URLs; empty ⇒ `federation_seeds.json` |
| `AIMARKET_SEEDS_FILE` | pkg `federation_seeds.json` | Alternate seeds file |
| `AIMARKET_SEED_PUBKEYS` | *(file)* | `{url:key}` JSON or `url=key,…` — trusted-on-first-contact pins |

---

## 4. Monitor changes (`alien-monitor/backend/`)

- **`hub_discovery.py`** (new) — the discovery layer. Fetches `/federation/peers`,
  filters by category, hydrates each match from `/.well-known` + `/api/health`,
  and returns graph nodes (`group:"oracle"`) + links from the `federation` node.
  TTL-cached so the 1.5s monitor tick never stampedes the network.
- **REAL mode** — `main.py:fetch_real_metrics()` merges discovered nodes/links via
  `_merge_discovered()` (dedupe by id; updates the `federation` node's peer count).
- **UNIVERSE mode** — `universe.py:_apply_discovery()` upserts discovered peers as
  `EcosystemEntity` objects each tick, prunes peers that disappear, and adds
  `federation → peer` links + a one-off "federation_join" activity event.
- **Frontend** — `EcosystemGraph.tsx` / `EcosystemGraph2D.tsx` gain an `oracle`
  group colour (violet `#a64dff`); `i18n` gains `group.oracle` and metric labels
  for `kappa` / `order_parameter` / `tick` / `viewers` / `trust_score` (en/ru/es).
  `NodeDetail` already renders `node.metrics` generically, so κ/order_parameter
  surface automatically.

### Monitor discovery env reference

| Env var | Default | Meaning |
|---|---|---|
| `ALIEN_DISCOVERY_ENABLED` | `1` | Federation discovery on/off |
| `ALIEN_DISCOVERY_ALLOW_PRIVATE` | `0` | Allow private/loopback **peer** URLs (UNI mode forces this on) |
| `ALIEN_DISCOVERY_CATEGORIES` | `oracle,simulation,math-viz,randomness-beacon,beacon` | Category allowlist |
| `ALIEN_DISCOVERY_MAX_PEERS` | `25` | Cap peers processed per cycle |
| `ALIEN_DISCOVERY_CONCURRENCY` | `8` | Bounded fan-out |
| `ALIEN_DISCOVERY_TIMEOUT_S` | `4` | Per-request timeout |
| `ALIEN_DISCOVERY_REFRESH_S` | `20` | Discovery cache TTL |

---

## 5. Security model (the Monitor fetches URLs the hub hands it — untrusted)

- **SSRF guard** — peer / well-known / health URLs are scheme-checked (http/https
  only), CRLF-rejected, DNS-resolved, and every resolved IP is matched against
  RFC1918 / loopback / link-local / cloud-metadata / multicast blocklists,
  **including IPv6-embedded IPv4 forms** (mapped, 6to4, NAT64, v4-compatible).
  Private targets are rejected by default (opt in only for local UNI sims). For
  **plain-HTTP peers the connection is pinned to the vetted IP** (Host header
  preserved) so a DNS rebind between the check and httpx's own resolution cannot
  reach an internal address. The hub's own URL is operator-configured (trusted).
- **Hard deadlines** — every fetch has a wall-clock `asyncio.wait_for` budget on
  top of httpx's per-read timeout, and each peer has a total budget, so a
  slowloris peer that dribbles bytes can never hang the monitor tick or hold the
  shared state lock. JSON content-type is **required** (default-closed).
- **Pinned-key trust chain** — capabilities only index when the manifest signature
  verifies against a key that is either previously pinned or operator-vouched, and
  the manifest's signed `generated_at` must be fresh (`AIMARKET_MANIFEST_MAX_AGE_S`,
  default 7 days) to bound replay of a captured manifest over plaintext HTTP. A
  peer changing its key mid-stream is rejected (takeover protection). NOTE: a
  pinned **http** seed (e.g. Platon on a raw IP) still carries IP-hijack replay
  risk bounded by the freshness window — prefer https for pinned seeds where the
  node supports it.
- **Bounds everywhere** — response-size caps (0.5 MB), bounded concurrency,
  max-peer caps, redirects disabled, a `(url, allow_private)`-keyed TTL cache (a
  private-allowed UNI result is never served to the SSRF-guarded REAL path), and
  strict numeric coercion (only finite, magnitude-clamped scalars reach
  `node.metrics`; huge JSON integers can't raise/erase a node).
- **No event-loop stalls** — the Hub auto-crawl runs in a worker thread with its
  own DB connection, so its synchronous SQLite work never freezes request
  handlers.
- **Fault isolation** — one bad/slow/malicious peer can never break the graph or
  the tick loop; discovery failures degrade to "no extra nodes", never an error
  page. A node-id that collides with a real core/product/agent node is skipped,
  never overwritten.

### Adversarial review

This change was put through a 5-dimension adversarial code review with per-finding
verification (each finding re-checked against the code to refute false positives).
It surfaced **16 real issues** (4 high, 7 medium, 5 low) — all fixed and
re-verified above — and correctly rejected 5 non-issues (e.g. the test suite does
**not** issue outbound HTTP to the external IP). Highlights fixed: event-loop
stall during auto-crawl; slowloris DoS via missing wall-clock deadline; DNS-rebind
TOCTOU (now IP-pinned for http); non-idempotent migration rollback; integer
overflow dropping a node; UNI slug-collision overwrite; cached-event replay;
allow_private cache-key leak; and a fail-closed regression in the federation
hub-URL resolver.

---

## 6. Crutch register (manual-wiring sweep)

The audit found ~16 manual-wiring sites. Status:

| # | Site | Crutch | Status |
|---|---|---|---|
| 1 | `alien-monitor` node list / `PLATON_URL` reliance | new nodes never appeared | ✅ **fixed** — federation discovery |
| 2 | Hub `crawl_interval_s` advertised but never run | discovery not automatic | ✅ **fixed** — auto-crawl lifespan task |
| 3 | First-contact indexing blocked for known nodes | Platon caps never indexed | ✅ **fixed** — operator-pinned trusted seeds |
| 4 | web-backend ×3 duplicated hub-URL resolvers (`config.py`, `ai_market_protocol_v2.py`, `landing_embeds.py`) with drifting defaults | config drift | ✅ **fixed** — single `core/aimarket_hub_url.py` |
| 5 | `alien-monitor` localhost default URLs duplicated across `main.py`, `universe.py`, `universe_layers.py` | duplicated defaults | 📋 **remediation**: a shared `service_urls` module; env overrides already work, so no functional bug — scheduled as follow-up |
| 6 | `ai-service-mesh` `MESH_HUB_URL` required / `scripts/deploy_mesh.sh` writes a literal (and disagrees with `config.py`'s `:9080` default) | manual peering + drift | 📋 **remediation**: bootstrap mesh from a discovery seed; reconcile the `:9080`/`:9083` mismatch |
| 7 | `notify_factory.py` monitor URL via env + path-surgery | manual webhook target | 📋 **remediation**: monitor self-announces a typed `materialize` endpoint as a federation peer; factory resolves it from `/federation/peers` |
| 8 | web-backend federates to a single env upstream (`peers:[]`) | no multi-peer crawl on factory side | 📋 **by design today**; converge on the hub's crawled peer set later |
| 9 | `chain_metrics.py` overlapping RPC/contract env vars | env sprawl | 📋 **remediation**: single chain-config resolver |

Items 5–9 keep working today via their env overrides; they are tracked so the
"living organism" goal is reached without destabilising the running system.

---

## 7. Operating it

**Make a new node appear** — stand it up so it serves a valid
`/.well-known/ai-market.json` (with a relevant `categories` entry) and
`/api/health`, then either add its well-known URL to `AIMARKET_SEED_LIST` /
`federation_seeds.json`, or have an already-crawled peer link to it, or
`POST /ai-market/v2/federation/announce` (admin-gated). The next crawl records it;
the Monitor renders it within one discovery refresh (~20s). To also index its
capabilities for search on first contact, pin its key in `AIMARKET_SEED_PUBKEYS`.

**Verify**
```bash
# Hub knows Platon (after a crawl):
curl -s {HUB}/ai-market/v2/federation/peers | jq '.peers[] | {name, categories, capabilities_count}'
curl -s "{HUB}/ai-market/v2/search?intent=oracle" | jq '.matches[].capability_id'
# Platon's live physics:
curl -s http://oracles.modelmarket.dev/api/health | jq '{kappa, order_parameter}'
```
In the Monitor UI a violet **oracle** node ("Platon Shadow Oracle") orbits the
**Federation** node; its detail panel shows live κ and order parameter.

---

## 8. Verification performed

- **Hub**: live crawl of Platon → `1 discovered, 6 indexed, 0 errors`; trusted-seed
  pinning verified on first contact **and** on subsequent (pinned-key) crawls;
  migration `006` applies; `categories` round-trips through the DB.
- **Monitor**: discovery against a stub hub → live Platon node with real
  `kappa`/`order_parameter`, correct id/group/link/event, working TTL cache;
  SSRF guard rejects metadata IP / loopback / `file://` and allows public Platon;
  UNI-mode entity create + prune verified; `_merge_discovered` idempotent.
- **Crutch fix**: `core/aimarket_hub_url.py` precedence/defaults match the three
  former resolvers; all edited files compile.
