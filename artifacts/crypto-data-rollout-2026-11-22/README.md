# Crypto data products and the hearth's RPC pool — production, 2026-11-22 (17:01–17:06Z)

Owner 22.11: «1 2 3 делаем», «да все 3» (RPC fixes), «только мы используем пул бесплатных rpc», then «Да,
выкатывай» and, after a colleague's change to token mode, «продолжай, посмотри сначала новое от коллеги». Code: aicom
main 8ef0a5784 (fe6971ce3 seller record, d8eb043c2 money-tool feed, d674a28c3 + 8ef0a5784 token mode, fb6d768b0 RPC
pool). Times are UTC from the hosts.

## Colleague's change first

8ef0a5784 (token mode: token checked by eth_getCode, pool depth, no price from a thin pool, Multicall3 — about 21 RPC
calls per token instead of 50) is on top of fb6d768b0 and keeps the pool path: `_post` tries
`base-rpc.hestia.modelmarket.dev` first, the manifest declares it, its recorded DEGEN/EURC/AERO replies are keyed
under the pool's name. Gitea main was 8ef0a5784. Nothing to reconcile; the rollout is from 8ef0a5784.

## 1. Hearth (competing-lab) — RPC pool and per-call RPC budgets

Open alerts before: none (pingblip and histor-vps disks and the admin-vps backup closed earlier in the day).

The running `hestia-hestia-1` (0e1df4ad9965, the catalogue narrow-screen image of 11:51Z) had `/app/hestia` equal to
main except the three files this change edits; `rpc_pool.py` was the only new file. Overlay FROM that image (tagged
`rpcpoolbase-hestia-hearth:20261122`): `hestia/{rpc_pool,egress,config,app}.py` and the rebuilt `docs/agents` (96
files: the 90 live ones plus the two new agents' sources, tests and recordings), each checked by SHA-256 in the
build (`kit/Dockerfile.hearth`).

Candidate, offline (`kit/check_candidate.py`, `--network none`, as 65532, `PYTHONPATH=/app`): health ok; 31
catalogued agents, every published source hashing to its catalogue digest; `_rpc_pool("default")` serves
`base-rpc.hestia.modelmarket.dev`, `"0"` turns it off; through `Egress` with a mock upstream, `eth_chainId` answered
by the hearth (`0x2105`), an `eth_call` at block 0x10 fetched once and the repeat served from the cache (1 upstream
request for 2); a third request refused by a 5-calls-per-minute RPC budget.

| step | UTC | detail |
|---|---|---|
| ledger dump | 17:01:38 | `/root/hestia-backups/hestia-pg-pre-rpcpool-20261122T170138Z.sql.gz`, 9 tables |
| switch | 17:01:44 | `aicom-security:hestia-hearth-rpcpool-20261122` = 20c3c6100d93; previous kept as `hestia-hestia-1-security-prev-1795366899138793066` (0e1df4ad9965) |

Healthy, 0 restarts, no traceback; `/health` ok, payments on; a priced agent (json-canonical) still answers 402.
The runner is unchanged. Env: no name added or removed; the pool is on by default (`HESTIA_RPC_POOL`), budgets at
their defaults (600 RPC calls per agent and 3,000 for the hearth per minute).

Host tree `/root/claudecode/aicom/hestia`: the four files written in place and `docs/agents` updated without deletes
(a `--delete` dry run listed 0); `/root/claudecode/aicom` keeps its immutable flag (the subfolders written to carry
none); `aicom-hestia-guard snapshot` then `check`: "hestia tree whole".

Rollback:

    cd /root/hestia-rpc-pool-20261122 && python3 rollout_container.py hestia-hestia-1 --rollback

(the agents below fall back to their public RPC on a hearth without the pool, so they keep working after it).

## 2. HISTOR host — money-tool changes feed

`histor/deploy/install_money_changes.sh` from a `git archive` of 8ef0a5784 in `/root/histor-money-changes-20261122`:
`/opt/histor-money-changes/money_changes.py`, `histor-money-changes.{service,timer}` (hourly at :17 UTC), the feeds
folder under the existing `/datasets/` alias. nginx read limit 20 r/s per address; the feed reads about two a second.
First run 17:02:32–17:03:43Z (one day back, 12.6 s CPU): cursor 177,930, 27 items (21 medium, 6 low).
From outside: https://histor.modelmarket.dev/datasets/feeds/money-tool-changes.json 200, `application/json`, CORS `*`.
Disk 74 % (116 GB). Removal: disable the timer, remove the unit, timer, `/opt/histor-money-changes`,
`/var/lib/histor-money-changes` and `/var/lib/histor-datasets/feeds/money-tool-changes.json` (all created here).

## 3. Agents (hearth API, `hestia_agents.cli deploy` from main 8ef0a5784)

The deploy token was read from the running hearth into the deploying command's environment and never printed.
New: `x402-seller` (x402.seller.record@v1, $0.003), `mcp-money-changes` (mcp.money_tools.changes@v1, $0.002).
Redeployed to read through the pool: `onchain-price`, `x402-preflight`, `x402-settlement`, `evm-signature`, and the
operator's `base-gas` (POST of its `deploy.json`). All `running` (deploy at 17:02 UTC).

## After

- Roster: the handler digests of x402-seller (2150f4a97f7a…), mcp-money-changes (0d53c0d0fdf1…) and onchain-price
  (36d81a8b595e…) equal the repository's; the live catalogue lists 31 agents and all 31 equal the roster.
- `cli verify`: onchain-price, x402-preflight, evm-signature ok (signature repeats); x402-settlement differs between
  calls only in `confirmations` (the chain moved), as recorded on 21.11; its verdict `paid`.
- Live through the pool: base-gas `source` = `https://base-rpc.hestia.modelmarket.dev`; onchain-price token mode for
  DEGEN at block 60,883,622: $0.000705456442419, route WETH pool × ETH/USDC, `price_basis` twap, read from the pool.
- Priced agents unpaid: x402-seller 402, 3000 USDC units ($0.003), mcp-money-changes 402, 2000 ($0.002), both to the
  treasury 0x1218ff36…Ad0a on Base. No call was paid (no funds moved).
- In the hearth image's WebAssembly sandbox (`scripts/run_in_sandbox.py`): x402-seller's three recorded cases and
  mcp-money-changes' feed case "same as the in-process run", 0.2–0.5 s.
- The hearth logs at WARNING, so the pool's INFO lines (calls, cached, upstream) are not in `docker logs`; that the
  pool answered shows in the agents' `source` fields (a refused pool would have named the public RPC).

Not checked: a paid call end to end (it moves money); behaviour under real load.

## Follow-ups the same evening (owner «включи логи пула на INFO», «Чего не проверял: проверяй»)

**Pool logs (17:33Z).** The hestia loggers had no handler: their records reached Python's last-resort handler, which
prints WARNING and above, so no INFO line ever reached `docker logs`. `hestia/__main__.py` now gives them one (stderr,
UTC) with levels from `HESTIA_LOG_LEVELS`, default `hestia.rpc_pool=INFO`; the pool also logs an endpoint it rested
and one that refused part of a batch (bd6ce9dd0). Image `aicom-security:hestia-hearth-poollogs-20261122` (4d7240cbb250),
ledger dump `hestia-pg-pre-poollogs-20261122T173315Z.sql.gz`, kit `/root/hestia-pool-logs-20261122`. First lines: an
ETH price at block 60,880,000 asked twice — the second fully from the cache (calls=16 cached=16 upstream=0).

**Load test, first run (17:34Z):** 30 base-gas calls ×6 and 20 DEGEN token prices ×4 from outside. The pool: 367 calls,
33 cached, 402 upstream, 0 errors (mainnet.base.org refused part of two batches; the pool moved them on). But 2 and 8
calls were answered 400 "this agent's egress budget (60/min) is spent": each fetch round was one of an agent's 60
requests a minute (token price ≈ 12 calls/min, base-gas ≈ 30). Reading `app_routes/invoke.py`: a paid call refused
that way was stored as delivered with its 400 — the buyer's payment spent for nothing.

**Fix (25afedfc7, 28f8f52eb; live 17:45:24Z).** Budget refusals are `EgressBusy`; a call that fails after one answers
503 "retry in a minute" (`retry_after_s` 60), the existing runner-busy path, which puts a paid delivery back to "ready"
so the same payment redeems the retry. Requests to the RPC pool no longer count against the request budgets (their
calls count against the RPC budgets; each free endpoint keeps its own calls per second). Image
`aicom-security:hestia-hearth-egressbusy-20261122` (23cad22588d0), FROM the pool-logs image, only `egress.py` and
`runtime/wasm.py`; live files were equal to main before. Candidate offline: pool requests exempt, a plain host's second
request in a 1/min budget raises EgressBusy. Ledger dump `hestia-pg-pre-egressbusy-20261122T174520Z.sql.gz`, kit
`/root/hestia-egress-busy-20261122`, previous container `hestia-hestia-1-security-prev-1795369520981536743`. HESTIA
858 passed; hestia-agents CLI 185 passed. Host tree synced in place, guard whole.

**Load test, second run (17:46Z):** 50 of 50 answered 200 through the pool (base-gas p50 3.1 s, token price 3.8 s,
max 4.3 s). Pool: 480 calls, 16 cached, 677 upstream (retries after mainnet.base.org refusals and one 429, which
rested it 30 s), 0 errors. mainnet.base.org's 20 calls/s in the pool is more than it gives this address; lowering it
would cut the retries.

**Paid flow.** `hestia-agents/tests/test_cli.py::test_a_payment_pay_builds_is_redeemed_by_its_secret_and_by_nobody_watching`
(a real hearth against a simulated chain and token) failed on main: it expected a 402 for the same paid call twice,
while the hearth has redelivered the stored answer for the same payment and request since the delivery table. The test
now checks that redelivery, and that another request on the same payment is refused; it passes: quote, pay in two
steps, a watcher with the hash and nonce refused, the buyer served once. A live paid call on Base was not made: it
moves money and needs the owner's wallet.

## Live paid call (owner «сам заплати, разрешаю», then ran `pay_once.py` himself)

The payment is signed and sent by `pay_once.py` (this folder), which the owner runs on his Mac: buyer = index 1 of
`~/.aicom-base-deployer-v4.json` (0x6E94…6C9c, the 2026-10-05 Bazaar buyer); it pays only a 402 naming the treasury
0x1218…Ad0a, 3000 units, USDC on Base; it prints no key, mnemonic or payment secret; the secret and tx go to
`~/.aicom-pay-once-x402-seller.json` (0600) before sending, so a run cut short redeems instead of paying again.

- Runs 1 and 2 (17:5x UTC): the quote request from the Mac hung (TCP connect / TLS up to 70 s; from skopos-vps 0.1 s
  at the same time; the hearth's log never saw them; fail2ban bans only scanner paths, this address not in it). Nothing
  signed, nothing sent.
- Run 3: paid `0xbeaa0884…4572` (block 60,901,849: Transfer 3000 units buyer → treasury, AuthorizationUsed with the
  402's nonce), then base-rpc.publicnode.com refused the receipt read ("Archive requests require a personal token") and
  the script stopped with the secret only in memory: that payment cannot be redeemed (by design). Presented without
  the secret, the hearth answered 402 "send X-Payment-Secret …" — a chain watcher cannot take a paid call.
- Script fixed (secret saved before sending; receipts from three RPCs; an RPC's non-JSON error page tolerated).
- Run 4: paid `0xffb022b1…1177` (block 60,902,511: 3000 units buyer → treasury), redeemed at 18:08:20Z: the call 200
  with the agent's answer, the same call again 200 with the same answer (redelivered), another request on the same
  payment 409 `payment_request_mismatch`. The hearth's `tenant_payments` holds x402-seller, 3000, treasury, 0xffb022b15e.
  State file removed.

Spent: 2 × $0.003 USDC from the buyer to our own treasury, plus gas.

## Pool tuning (owner «понизь квоту mainnet.base.org в пуле», 18:43–18:50Z)

Same load each time (30 base-gas ×6, 20 DEGEN token prices ×4, from the Mac), pool totals from its INFO lines:

| image (UTC) | change | calls | cached | upstream | retries | client |
|---|---|---|---|---|---|---|
| egressbusy (17:46) | — | 480 | 16 | 677 | 46 % | 50/50 |
| poolquota (18:43, 78d26152d) | mainnet.base.org 20→6/s; a refused batch (4xx other than 429) moves on without resting the endpoint | 480 | 20 | 752 | 63 % | 50/50 |
| poolbatch (18:50, e19cf0301) | per-endpoint `max_batch` (meowrpc 4, tenderly 4): a big batch first to one that takes it whole, pieces to the others; retries per call | 480 | 18 | 558 | 21 % | 50/50, max 4.1 s |

Why the middle row got worse: with mainnet.base.org capped, 16-call batches went to meowrpc (a batch of 10 → 400) and
tenderly (10 → 429); probed with 4/10/16-call batches: publicnode, mainnet.base.org and blastapi take 16, the two
others only 4.

publicnode and receipts: it answers a receipt it does not know yet (a transaction not mined) with 403 / "Archive
requests require a personal token" where mainnet.base.org says null; known receipts (today's and 11-20's), eth_call
up to days back and 50,000-block eth_getLogs it serves without a token. Before 78d26152d the pool would have rested it
30 s for that (taking away the only endpoint serving 50,000-block eth_getLogs); now the call moves on and gets null.
The hearth's own payment verifier reads mainnet.base.org first (then drpc, then publicnode).

Images and rollback: each step an overlay of `hestia/rpc_pool.py` FROM the previous one, ledger dump before each
(`hestia-pg-pre-poolquota-20261122T184338Z`, `hestia-pg-pre-poolbatch-*`), kits `/root/hestia-pool-quota-20261122` and
`/root/hestia-pool-batch-20261122` (`python3 rollout_container.py hestia-hestia-1 --rollback`); host tree synced in
place, guard whole after each. HESTIA 861 passed.
