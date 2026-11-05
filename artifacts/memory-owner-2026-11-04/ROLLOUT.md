# Memory owner = the buyer the hub names — attested, 2026-11-04

Owner: «Да, исправляй», then «ты все выкатывай и проверяй». All times are server clocks (UTC).

## The bug

Attested Memory's memory-market took a memory's owner from `X-Payment-Channel`:
`"aimarket:" + sha256(header or "anonymous")[:20]`. The hub forwards that header only as a reference to a payment
channel, and sends it **empty** for every buyer on hub credits (X-API-Key), x402 or a trial. All of those buyers were
therefore one owner (`aimarket:e3b0c44298fc1c149afb`) and could read each other's "private" memories through
`memory.read@v1` and `memory.search@v1`. For channel buyers the reference was keyed with a salt drawn per hub process
(`AIMARKET_BUYER_SALT` is not set on attested), so their owner changed on every hub restart.

Found 2026-11-04 while planning Multica's agent memory. Before the fix, 0 memories had been written through the hub
(the database held 3 private memories, all written directly), so nothing had leaked.

## The fix

- Hub: `aimarket_hub/provider_buyer_ref.py` sends `X-AIMarket-Buyer-Ref: bref-<32 hex>` = HMAC of the buyer this hub
  authenticated (credit account, verified x402 payer, or a channel whose price is held), under a key derived from the
  hub's Ed25519 signing seed. Stable across restarts, different per hub, reveals no account. Sent **only** beside
  `X-AIMarket-Internal-Token` to the operator's gateway hosts (`AIMARKET_INVOKE_HOST_GATEWAY` =
  memory-market, truth-layer, provenance-ledger); never to a third-party seller; absent for trial and sandbox calls.
- memory-market: owner = `aimarket:<bref>`. Without a valid ref: `memory.read` / `memory.search` see public memories
  only; `memory.write`, `memory.share`, `memory.score` answer 403 with an explanation.
- provenance-ledger: an attestation through the hub is recorded under the ref, else `aimarket:anonymous`.

Code: aimarket-hub (main, split `invoke_parts/local_delivery.py`), memory-market and provenance-ledger `app.py`, tests
`aimarket-hub/tests/test_provider_buyer_ref.py`, `memory-market/tests/test_hub_buyer.py`, provenance-ledger
`test_ledger.py`. The new memory-market tests fail on the previous code.

## What was rolled

The live services are not main: the hub runs the pre-split `hub_routes/invoke.py` (ARD overlay `:ard2-20261104`),
the live memory-market `app.py` is older than main. So each image was built FROM the running image with only the
changed files swapped; `kit/patch_live.py` ports the same text onto the live files and refuses on a missing anchor.
`kit/build.sh` runs each `smoke.py` inside the new image with no network and compares every copied file with the
context (hashes below matched). Hub rolled with `/root/hub-3160-main-20261021/roll.sh` (DB backup first), the other
two with `rollout_container.py`; both keep the previous container stopped and roll back on a failed health check.

| Service | Before | After | Previous container | Files (sha256/12) |
|---|---|---|---|---|
| hub (10:02:55Z) | `attested-memory-hub:ard2-20261104` | `attested-memory-hub:bref-20261104` | `attested-memory-hub-hub-1-security-prev-1793786567487540873` | provider_buyer_ref.py 1ff71b8c46ae, invoke.py 2b63407ac216 |
| memory-market (10:03Z) | `aicom-security:attested-memory-hub-memory-market-1-hc-live-20261031` | `attested-memory-hub-memory-market:bref-20261104` | `attested-memory-hub-memory-market-1-security-prev-1793786595573256038` | app.py 8a0eb4617da7 |
| provenance-ledger (10:03:23Z) | `aicom-security:attested-memory-hub-provenance-ledger-1-hc-live-20261031` | `attested-memory-hub-provenance-ledger:bref-20261104` | `attested-memory-hub-provenance-ledger-1-security-prev-1793786599841608890` | app.py 865daa8cbebb |

DB backup (hub + memory-market share Postgres `aicom`): `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261104T100246Z.dump`.
Kit and logs on the host: `/root/memory-owner-20261104/`.

## Checked live

- All three containers healthy, no errors in their logs after the roll; hub `/ai-market/v2/health`,
  `/.well-known/ard.json`, `/.well-known/ai-market.json` answer 200 from outside; the 3 existing memories are intact.
- Through `https://hub.attestedmemory.net/mcp` as an anonymous trial caller: `memory.write@v1` → tool error, provider
  403 «this capability needs a buyer the hub can name…», and no trial was spent on it; `memory.search@v1` → ok, public
  only (empty).
- In the live hub, `provider_buyer_ref.buyer_ref` with the hub's own key: the same ref in two separate processes,
  different refs for two accounts, none for a sandbox call.
- From the hub container to memory-market with the internal token (read-only): search with a named ref → 200;
  `memory.score` without a ref → 403.
- Not checked live: a whole paid call by a funded credit account (needs a funded key — the owner's money). The same
  path ran in the hub smoke inside the new image (two accounts → two stable refs, none to a third-party URL).

## Identity fix from the Vulnetix-class check (rolled 15:02Z)

`artifacts/vulnetix-check-2026-11-04/REPORT.ru.md`, finding 1: a call paid from someone else's subcontract allowance
carried the root buyer's account, so `X-AIMarket-Buyer-Ref` named the buyer and a subcontractor could read the
buyer's private memories; a mandated agent became the principal. Fixed in `provider_buyer_ref.buyer_identity`:
allowance-funded calls are anonymous, mandated calls get `mandate:<account>:<agent>`. Image
`attested-memory-hub:bref2-20261104` = FROM `:bref-20261104` + the new `provider_buyer_ref.py` (sha256/12
`cca0ec4b9c5d`), smoke ok, identities checked in the image. Rolling it was first refused by the auto-mode
classifier (production deploy); the owner then said «Да, выкатывай». Nothing used the hole between 10:02Z and the
roll: only вжик writes memory through the hub and its account has no mandates or allowances.

```bash
ssh attested 'cd /root/hub-3160-main-20261021 && ./roll.sh attested-memory-hub-hub-1 attested-memory-hub:bref-20261104 attested-memory-hub:bref2-20261104 http://127.0.0.1:9084/ai-market/v2/health attested-memory-hub-postgres-1'
```

**Rolled 2026-11-04 15:02Z** (log `logs/roll-bref2.log`): DB backup
`/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261104T150200Z.dump` (284K), health ok, previous container
`attested-memory-hub-hub-1-security-prev-1793804520835950809` (image `:bref-20261104`), no environment names
removed or set. Checked at 15:03Z:

- `provider_buyer_ref.py` in the container = sha256 `cca0ec4b9c5d…`; `AIMARKET_TRUSTED_PROXIES` still set.
- In the live hub: own credits → `credits:<account>`, an allowance-funded subcontract → no identity, a mandate →
  `mandate:<account>:<agent>`.
- With вжик's key from inside its container: `memory.search` finds its memory `mem_958d90d9d1be41129d17dadf`
  ($0.004), so a credit buyer's ref did not change; the same search anonymously finds nothing. On
  `/ai-market/v2/stats/live` the first call is `operator_self` / `account`, the anonymous one `external`.
- Health, `/.well-known/ard.json`, `/.well-known/ai-market.json` answer 200 from outside; no errors in the hub log.

Rollback to the previous hub image:
`ssh attested 'cd /root/hub-3160-main-20261021 && python3 rollout_container.py attested-memory-hub-hub-1 --image attested-memory-hub:bref-20261104 --health http://127.0.0.1:9084/ai-market/v2/health'`
(that image has the subcontract hole; `rollout_container.py` keeps the environment, including the trusted proxies).

## Rollback

Back onto the previous images (the stopped `*-security-prev-*` containers stay as they are):

```bash
ssh attested 'cd /root/hub-3160-main-20261021 && python3 rollout_container.py attested-memory-hub-hub-1 --image attested-memory-hub:ard2-20261104 --health http://127.0.0.1:9084/ai-market/v2/health'
ssh attested 'cd /root/hub-3160-main-20261021 && python3 rollout_container.py attested-memory-hub-memory-market-1 --image aicom-security:attested-memory-hub-memory-market-1-hc-live-20261031 --health http://127.0.0.1:8810/healthz'
ssh attested 'cd /root/hub-3160-main-20261021 && python3 rollout_container.py attested-memory-hub-provenance-ledger-1 --image aicom-security:attested-memory-hub-provenance-ledger-1-hc-live-20261031 --health http://127.0.0.1:8812/healthz'
```

Rolling back memory-market alone reopens the shared owner; roll it back together with the hub or not at all.

## Multica agent вжик connected (10:12–10:20Z)

Owner: «Да, подключай» (fund the agent's credit account and connect it).

- Credit account `acct_a88fc1e427bce2e1` (label `multica-vzhik`) created on the attested hub through its open signup;
  its API key went straight into `/opt/multica/secrets/agent.env` as `AIMARKET_API_KEY` via `set-secrets.sh` (the
  script's KEYS list gained that name; old script `set-secrets.sh.bak-20261104`), never printed. The daemon was
  recreated by the script while вжик was idle.
- Operator credit **$5.00** through `/ai-market/v2/accounts/{id}/credit` (internal hub credits, no money moved).
- `/data/ecosystem.json` on the hub (did not exist): `self.accounts = [acct_a88fc1e427bce2e1]`, checked by
  `python -m aimarket_hub.ecosystem check`, policy `status: ok`. Copy in `/root/memory-owner-20261104/ecosystem.json`.
- OpenCode global config in the daemon (`~/.config/opencode/opencode.jsonc`, old copy `.bak-20261104`): remote MCP
  `aimarket` → `https://hub.attestedmemory.net/mcp`, header `X-API-Key: {env:AIMARKET_API_KEY}`. `opencode mcp list`
  → connected.
- вжик instructions: a "Память и хаб" section appended (memory tools only, ≤ 6 hub calls a run, no retry on 402/403,
  memory is data, no secrets in memory; the GitHub digest reads up to three recent `github-digest` records, snapshots
  stars/forks, adds «Тренды» and writes one private record a day). Before/after texts in `/root/memory-owner-20261104/`.

End-to-end with вжик's key from inside its container: `memory.write` private → charged $0.012, owner
`aimarket:bref-fa280e646510526a1e1dfae12dc8cd6f`; `memory.search` → finds it ($0.004); `memory.read` → ok ($0.006);
the same search anonymously → nothing; the same read anonymously → 403. Balance $4.978 afterwards. Expected cost of
the daily digest with memory: about $0.03 a run, ~$1 a month.

Agent test through Multica (issue MY-51, 10:18–10:20Z): вжик called `memory.search` and `memory.read` over the MCP
on its own, found `mem_958d90d9d1be41129d17dadf`, answered in a comment (2 hub calls, $0.010) and closed the issue;
17.9k in / 0.9k out DeepSeek tokens. Balance $4.968. The first real digest with memory is the autopilot run on
2026-11-05 08:00Z (trigger now `0 8 * * *` UTC).

**Open: these calls are classified `external / forwarded`, not SELF.** `AIMARKET_TRUSTED_PROXIES` is unset on the
attested hub, so nginx's `X-Forwarded-For` (peer 172.18.0.1) makes every public call look like a relay: all 50 recent
events on the hub are `external/forwarded` — own accounts can never be SELF, a fleet total that drops forwarded rows
drops attested's demand, and all clients share one rate-limit bucket. modelmarket-hub on factory-vps runs with
`127.0.0.1,172.18.0.1`. The change was first refused by the auto-mode classifier as a production deploy the owner had
not asked for; the owner then said «Да, задавай».

**Fixed 10:23:24Z.** `AIMARKET_TRUSTED_PROXIES: "127.0.0.1,172.18.0.1"` added to the hub's `environment:` in
`/opt/aicom/attested/attested-memory-hub/docker-compose.yml` (old file `docker-compose.yml.bak-20261104-trusted-proxies`,
`docker compose config -q` ok) and set on the live container by `rollout_container.py --set` (same image
`:bref-20261104`; previous container `attested-memory-hub-hub-1-security-prev-1793787796725682368`, log
`roll-hub-trusted-proxies.log`). The hub resolves the client from `X-Forwarded-For` right to left and only when the
peer is a listed proxy, so a client cannot forge its address. Checked: a call with вжик's key at 10:23:39Z →
`operator_self` / basis `account`; an anonymous call the same second → `external`, no `forwarded`; health, ARD and
the well-known answer 200; no errors in the hub log. Rows written before 10:23Z stay `forwarded` (the basis is
judged when a row is written). Rollback = the same command with `--set AIMARKET_TRUSTED_PROXIES=` and the backup
compose file. competing-lab `modelmarket-hub` also runs without the setting — not touched.

## hub.modelmarket.dev on competing-lab: the same setting (10:26:12Z)

Owner: «Да, задай там». Same layout as attested: host nginx → `127.0.0.1:9083`, the container sees the bridge gateway
`172.18.0.1` (network `aicom_aicom_net`), `X-Forwarded-For` appended; `AIMARKET_TRUSTED_PROXIES` was unset and 13 of
the last 48 events were `external/forwarded` (policy `absent`, no ecosystem.json there — not touched). The container
is not compose-managed (rollouts carry its config), so `rollout_container.py --set` is the persistent setting:

```bash
cd /root/hub-3160-main-20261021 && python3 rollout_container.py modelmarket-hub --image modelmarket-hub:ard2-20261104 \
  --health http://127.0.0.1:9083/ai-market/v2/health --set AIMARKET_TRUSTED_PROXIES=127.0.0.1,172.18.0.1
```

Same image `modelmarket-hub:ard2-20261104`; previous container `modelmarket-hub-security-prev-1793787967285325498`;
log `logs/roll-competing-lab-modelmarket-hub-trusted-proxies.log` (host copy `/root/trusted-proxies-20261104/`).
Checked: the variable is in the container; health, ARD, the well-known and `/mcp` answer 200 from outside; the only
log line matching "error" since is the crawler's 404 from an outside peer. The hub had had no invoke since
2026-10-30T06:37Z and none came in the 10 minutes after the change, and a test invoke of our own would have shown as
outside demand on an idle hub, so the live image was checked directly: with the parsed setting
`['127.0.0.1', '172.18.0.1']`, a request via nginx (peer 172.18.0.1, `X-Forwarded-For: 6.6.6.6, 203.0.113.9`) resolves
to 203.0.113.9; a direct peer 172.18.0.5 with a forged header stays 172.18.0.5; without the setting every caller was
172.18.0.1. The end-to-end effect of the same mechanism was seen on attested (above). Rollback = the same command with
`--set AIMARKET_TRUSTED_PROXIES=`. signal-hunt-hub-1 on the same host already had `127.0.0.1,172.20.0.1`.

## Other hubs

The header is new hub code, but only providers that read it change behaviour. Memory-market and provenance-ledger run
only on attested. The other five hubs get `provider_buyer_ref.py` with their next regular rollout from main.
