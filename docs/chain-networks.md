# Chain networks & RPC failover

The AIMarket ecosystem is **multi-chain**. The same escrow + lottery exist as EVM contracts
(Base / Ethereum / Arbitrum) **and** as Solana programs. At runtime exactly **one network is
active**, selected by environment variable, defaulting to **Base** — pre-loaded with our live
demo contracts. Every runtime chain reader reaches its RPC through one shared layer that does
**health-checked failover across multiple endpoints**, so a single provider outage never takes
the ecosystem offline, and your preferred endpoint is always used when it is up.

> Our live demo deployment is on **Base mainnet** (chainId 8453). Canonical address record:
> [`docs/onchain-journal.md`](onchain-journal.md). The programmatic source of truth for
> network presets + demo addresses is [`aimarket_hub/chain_net.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/chain_net.py).

---

## 1. One module, two responsibilities

[`aimarket_hub/chain_net.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/chain_net.py) is dependency-free
(stdlib `urllib`, transport injectable for tests). It is:

- **imported directly** by `aimarket-hub` and by `web/backend` (which already depends on
  `aimarket_hub`);
- **vendored verbatim** into the standalone `alien-monitor` service at
  [`alien-monitor/backend/chain_net.py`](https://github.com/alexar76/alien-monitor/blob/main/backend/chain_net.py). A parity test
  (`alien-monitor/tests/test_chain_net_parity.py`) fails the moment the copy drifts. To
  re-vendor: `cp aimarket-hub/aimarket_hub/chain_net.py alien-monitor/backend/chain_net.py`.

### a. Network registry + selection
A preset per network carries its kind (EVM / Solana), chainId or cluster, a **priority-ordered
RPC list**, native token, explorer, and our deployed contract/program addresses. The active
network is chosen by env, defaulting to Base + demo contracts.

### b. Health-checked RPC failover
Both EVM and Solana speak **JSON-RPC 2.0 over HTTP**, so one `RpcPool` serves both — only the
health probe differs (`eth_chainId` vs `getHealth`). The pool:

- always prefers the **highest-priority endpoint that is healthy** → a working default wins;
- **fails over** to the next endpoint on a transport error;
- **returns to the preferred default** once it recovers (a demoted endpoint is re-probed after
  a cooldown);
- is bounded by a short per-call **timeout**, so an offline environment **fails fast instead of
  hanging**;
- distinguishes a *node-level rejection* (a JSON-RPC `error` — surfaced, not retried) from a
  *transport failure* (retried on the next endpoint).

---

## 2. Selecting a network & RPCs (env)

| Variable | Meaning | Default |
| --- | --- | --- |
| `AIMARKET_CHAIN` (alias `AIMARKET_NETWORK`) | Active network id | `base` |
| `AIMARKET_TESTNET` | Use the network's testnet variant (Base Sepolia, Sepolia, …) | off |
| `AIMARKET_RPC_<ID>` | Comma-separated RPC URLs, **priority order** (your default first) | — |
| `AIMARKET_RPC_TIMEOUT` | Per-call timeout, seconds | `6` |
| `AIMARKET_RPC_COOLDOWN` | Seconds a failed endpoint is skipped before re-probe | `30` |
| `AIMARKET_RPC_USER_AGENT` | UA sent to RPC providers (public RPCs 403 the default urllib UA) | `aimarket-chain-net/1.0` |
| `AIMARKET_CHAIN_KIND` / `AIMARKET_CHAIN_ID` | Define an ad-hoc EVM network not in the presets | — |
| `AIMARKET_ADDR_<ID>_<NAME>` | Override / add a contract address for a network | — |

**RPC priority** (deduped, order-preserving): `AIMARKET_RPC_<ID>` → legacy single-URL vars
(`BASE_RPC_URL`, `AIFACTORY_PAYMENT_RPC_BASE`, …) → built-in public presets. So your configured
endpoints — new or legacy — always outrank the public backups.

```bash
# Use your own Base node as the preferred default, with a public backup, then the presets:
export AIMARKET_RPC_BASE="https://my-base-node.example,https://base-rpc.publicnode.com"

# Switch the whole stack to Arbitrum:
export AIMARKET_CHAIN=arbitrum
```

### Built-in network presets

| id | kind | chainId / cluster | native | demo contracts |
| --- | --- | --- | --- | --- |
| `base` *(default)* | EVM | 8453 | ETH | ✅ our live deployment |
| `ethereum` | EVM | 1 | ETH | — (set via env) |
| `arbitrum` | EVM | 42161 | ETH | — (set via env) |
| `solana` | Solana | mainnet-beta | SOL | — (programs exist in `contracts/solana`; set when deployed) |

Each preset ships several public RPC endpoints (failover backups). Any other EVM network is
addable **without code changes** via the ad-hoc env vars.

### Add an EVM network with no code change
```bash
export AIMARKET_CHAIN=optimism
export AIMARKET_CHAIN_KIND=evm
export AIMARKET_CHAIN_ID=10
export AIMARKET_RPC_OPTIMISM="https://mainnet.optimism.io,https://optimism-rpc.publicnode.com"
```

---

## 3. Who uses it

| Consumer | What it reads | Wiring |
| --- | --- | --- |
| `web/backend/api/payment.py` | EVM + Solana payment-tx verification | EVM via `pool.run` (web3 per healthy URL), Solana via `pool.call("getTransaction", …)`. `RPC_ENDPOINTS` now derives from `chain_net`. |
| `alien-monitor/backend/chain_metrics.py` | LIVE on-chain metrics (block/gas/chainId, contract code, Solana slot) | Async failover over the priority URL list; surfaces the active network (`network` / `network_name`) so the UI shows the real chain. |
| `aimarket-hub/aimarket_hub/capability_nft.py` | On-chain NFT registry (mint / ownerOf / consumeCall) | Builds Web3 from a health-checked pool; `AIMARKET_NFT_CHAIN_RPC` is now **optional** (defaults to the chain's pool). |

> `alien-monitor`'s **UNI / universe** mode (`universe.py`) runs against a **local anvil** node
> by design and is intentionally *not* part of the multi-endpoint failover.

**Per-consumer timeout overrides.** `payment.py` uses its own `AIFACTORY_PAYMENT_RPC_TIMEOUT`
(default 15s) for the pool's per-call timeout — checkout verification tolerates a slower call
than a metrics tick — which takes precedence over `AIMARKET_RPC_TIMEOUT` for that consumer.
`alien-monitor` bounds the *whole* snapshot with a hard total timeout (default 8s), so an
all-endpoints-down situation degrades promptly rather than scaling with endpoint count.

**Production NFT writes.** With `AIFACTORY_PROD=1`, `make_nft_registry` requires an explicit
`AIMARKET_NFT_CHAIN_RPC` — it refuses to send owner-key writes (mint/consumeCall) over a shared
public RPC. Reads/failover still use the pool; only the write endpoint must be operator-chosen.

---

## 4. Contracts vs. RPC

Contract **source** lives in separate Foundry projects — `contracts/evm`, `lottery/contracts`,
`acex/contracts/evm` — plus the ZK verifier (`contracts/zk`) and the Solana programs
(`contracts/solana`). Those **deploy** via Foundry's `--rpc-url` / `foundry.toml`
`[rpc_endpoints]` (or `anchor`/`solana` for Solana); they do not need the runtime pool. The
runtime failover layer applies to the **services that read the chain live** (§3). The network
registry in `chain_net.py` is the single programmatic source for chainIds + our demo addresses,
which those repos' deployment docs reference.

---

## 5. Tests

- `aimarket-hub/tests/test_chain_net.py` — registry/selection + failover (priority, return-to-
  default, fail-fast, node-error-vs-transport, EVM vs Solana probe). Fully offline (injected
  transport + fake clock).
- `alien-monitor/tests/test_chain_net_parity.py` — vendored copy stays byte-identical.
- `alien-monitor/tests/test_chain_metrics.py` — monitor RPC-list priority, demo-address
  defaults, active-network surfacing, async failover.
