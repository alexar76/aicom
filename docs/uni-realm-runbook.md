# UNI realm — runbook

> 🌐 **English** · [Русский](uni-realm-runbook.ru.md) · [Español](uni-realm-runbook.es.md) · [Français](uni-realm-runbook.fr.md) · [中文](uni-realm-runbook.zh.md)

A cheat sheet for running, moving and checking the UNI bubble. The why is in
[uni-realm.md](uni-realm.md); this page is the what and the order.

## Two chains, never one

| Chain | Who runs it | Address seen by containers | What lives on it |
|---|---|---|---|
| **Bubble chain** | container `anvil-uni`, volume `anvil_uni_state` | `http://172.17.0.1:8546` | the hub's money: token `0x5fbd…0aa3`, escrow `0xe7f1…0512`, the hub wallet (Anvil #1) and the buyer (Anvil #2) |
| **Demo chain** | the Alien Monitor UNI container (`alien-monitor`), its own Anvil | `http://172.17.0.1:8545` (via `uni-rpc-bridge`) | the map's world: lottery, NFT, ACEX (PulseAMM, registry, lending) |

The UNI hub **settles on the bubble chain** (`AIMARKET_RPC_BASE=…:8546`) and reads the lottery and
NFT on the demo chain (`ALIEN_EVM_RPC=…:8545`). The demo chain is disposable: the monitor wipes it
past 64 MB and redeploys its contracts at new addresses. Money never lives there.

## Moving UNI to another host — checklist

1. Copy the `anvil_uni_state` volume (stop `anvil-uni` first, so the state on disk is complete).
2. Start `anvil-uni` on the new host — the `docker run` in [uni-realm.md](uni-realm.md#standing-it-up),
   published on `172.17.0.1:8546` only.
3. Firewall: containers must reach `172.17.0.1:8546`, the internet must not.
   `ufw allow proto tcp from 172.17.0.0/16 to 172.17.0.1 port 8546`
4. Check the bubble chain holds the economy: code at the token and the escrow, balances at Anvil #1
   and #2. Empty → the state was not copied; run `scripts/deploy_uni_realm.py` against **8546**
   (never 8545) and use the addresses it prints.
5. Start the hub from the monorepo: `bash deploy/uni-hub.sh <image> <token> <escrow>`.
   Never from a copy on the host, never by merging `hub.env.snippet` into the hub.
6. Move what the hub sells, too — it runs on the host, not in a container: the six satellites
   (copy `/var/lib/uni-satellites`, then `bash deploy/uni-satellites.sh`) and the `uni.answer@v1`
   provider (copy `/var/lib/uni_provider_key`, then `bash deploy/uni-provider.sh`). The hub pins both
   keys, so a new key means a refused peer or refused signatures. Then crawl
   (`POST /ai-market/v2/federation/crawl`, admin) and stop the old copies on the previous host.
7. Set the monitor's buyer to the bubble chain: `ALIEN_UNIVERSE_BUYER_RPC=http://172.17.0.1:8546`,
   `ALIEN_UNIVERSE_BUYER_TOKEN=<token>`.
8. Run `python3 deploy/uni-hub-verify.py` **on the host**. Every line must be `ok`.
9. Within ~15 minutes the monitor log shows `hub declares its settlement wallet` and a channel opens;
   the red "REALM ECONOMY STALLED" banner must not come back.

## `deploy/uni-hub-verify.py`

Run after every start or recreate of the hub. Beyond the publication rules it checks the money
side against the chains themselves:

- the hub settles on its own chain, not on the monitor's demo chain;
- one token for deposits and x402, and it exists on the settlement chain;
- one escrow address everywhere, and it exists on the settlement chain;
- paid at one wallet everywhere (recipient = x402 payTo = escrow hub);
- the charity lottery exists on the demo chain.

`--no-chain` skips the chain checks (off-host), `--no-live` skips the public ones.

## When the demo chain changes

After a monitor reset the lottery, NFT and ACEX addresses change. The new ones are in
`data/alien-monitor/universe/hub.env.snippet`. Take **only** these from it:

- hub: `AIMARKET_CHARITY_LOTTERY_ADDRESS`, `LOTTERY_ADDRESS`, `HUB_LOTTERY_ADDRESS`, `AIMARKET_NFT_CONTRACT`;
- ARGUS-UNI: the `ARGUS_UNI_*` lines in `argus/.env`, then `docker compose up -d argus-uni`.

Never take its `AIMARKET_PAYMENT_RECIPIENT`, `AIFACTORY_PAYMENT_VERIFY_STUB` or RPC lines into the
hub: they describe the demo chain and Anvil #0, and they break settlement. `AIMARKET_ADDR_UNI_*` is
ignored by the hub (its network is named `base`).

The monitor's Anvil writes its state every 30 s (`ALIEN_ANVIL_STATE_INTERVAL_S`), so a restart no
longer loses contracts deployed since the last clean exit.

## Symptoms

| On the map / in the log | Cause | Fix |
|---|---|---|
| `settlement chain http://172.17.0.1:8546 is unreachable` | `anvil-uni` not running, or the firewall rule missing | steps 2–3 |
| `channel/open … moved no USDC to the configured recipient` | buyer paid another wallet, or the hub's recipient is not Anvil #1 | verifier; the buyer drops such a deposit by itself |
| `transaction not found or not yet mined`, every round | buyer and hub on different chains | step 7, verifier |
| verifier: "settlement token exists … FAIL" | hub points at a chain without its token | step 4 |
| verifier: "charity lottery exists … FAIL" | demo chain was reset | "When the demo chain changes" |
| `listing_not_sellable` in the buyer log | normal: that listing has no payout address; channels are paid to the wallet the hub declares | — |
| `Invoke error for uni.answer@v1: timed out` | the provider is not running on this host; the connect hangs past the buyer's timeout | step 6 (`deploy/uni-provider.sh`) |
| `no match for …` every round; the catalogue has a handful of tools instead of ~93 | the satellites are not running on this host (nginx answers 502 on `/sat/*`) | step 6 (`deploy/uni-satellites.sh`), then a crawl |
