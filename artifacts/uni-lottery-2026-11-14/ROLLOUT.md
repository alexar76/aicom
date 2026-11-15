# UNI charity lottery deployed again: factory-vps, 2026-11-14

Times are server UTC. Owner's words: «Да, чини копию UNI» (2026-11-14). The production lottery
(lottery.modelmarket.dev, on my-vps since 2026-11-07) was healthy throughout and was not touched.

## What was broken

The UNI realm runs its own copy of the lottery on factory-vps: `ailottery-relayer-uni` drives an
`AIAgentLottery` on the UNI monitor's embedded anvil (127.0.0.1:8545, chain 31337). From
2026-11-01 or earlier no lottery existed on that chain:

- `universe_config.json` saved `evm_lottery` = `0x9fe46736…`, which is the NFT. That is the
  deployer's nonce-2 address: under an older deploy order the lottery came third, and after a
  chain reset USDT, Escrow and NFT are redeployed from nonce 0, so the NFT took the address.
- `_lottery_contract_verified()` only asked whether the address held code. The NFT does, so
  every bootstrap skipped the lottery deploy.
- The relayer's env named `0x5910fBf5…` (no code); its self-heal re-bound to the address in
  `hub.env.snippet` because that one held code. It then drove rounds against the NFT: each
  round reverted at `currentRoundId()` (577k `round failed` lines).
- The alerter's `uni_demo_chain_up` only checked that a lottery address was set.

Each container also carried its own stale "lottery" address in env, none of them a lottery:
hub-uni `0xdc64a140…` (now the ACEX vault), alien-monitor `0xa513e6e4…` (ACEX lending pool).
Neither container reads that variable in code (checked in the live images); left as they are.

## What changed (code in aicom, ported onto the live files)

- `alien-monitor/backend/universe.py`: `_lottery_contract_verified()` requires code, an address
  no other UNI contract has, and a 32-byte answer to `currentRoundId()` (selector `0x9cbe5efd`).
  Bootstrap notes «saved lottery … is not an AIAgentLottery; deploying one», clears it, and
  deploys the lottery after the ACEX deploy (not before), so on a fresh chain the ACEX contracts
  keep the addresses ARGUS UNI's env names. Rehearsal confirmed the reason: deployed right
  after the core three, the lottery lands on `0xdc64a140…`, today's ACEX vault.
- `alien-monitor/backend/universe_deploy.py` (live: `universe.py`): `_parse_broadcast_address`
  no longer falls back to "first hex string in the file" when a contract name was asked for.
- `alien-monitor/backend/main.py` + `live_lottery_feed.py`: `/api/health` (universe mode)
  publishes `lottery_feed` = `{fresh, age_s, round}`. The relayer pushes only from inside a
  round, so a stale feed means rounds stopped.
- `lottery/relayer/ailottery_relayer/economy.py`: `_ensure_contract_live()` uses
  `_is_lottery()` (code AND `currentRoundId()` answers); a revert is "not a lottery", a failed
  RPC still raises and is still treated as a blip.
- `scripts/ecosystem_alert.py`: new check `uni_lottery_rounds` (EN/RU). It fails when the
  lottery address equals another published contract, or when the relayer has reported no round
  for 15 minutes. Monitors without `lottery_feed` get no extra check.

Tests: `alien-monitor/tests/test_universe_lottery.py` (+4, one updated), `test_live_lottery_feed.py`
(+1), `lottery/relayer/tests/test_address_selfheal.py` (+2, stub gained `eth.call`),
`tests/test_ecosystem_alert.py` (+6 cases). Python 3.12: monitor 1168 passed, 3 skipped, 1 failed
(`test_warden_ruleset_mirror`: v12 vs v19, an older drift); relayer 124 passed, 6 errors
(`test_abi_contract_agreement.py` needs `forge build`, which this checkout cannot run without
the `forge-std` submodule); alerter 202 passed.

## Rollout (kit on factory-vps: `/root/alien-uni-lottery-20261114`)

1. Backup before any change (14:37:10Z): `backup/` = `universe_config.json`,
   `hub.env.snippet`, `anvil-state/state.json`, `SHA256SUMS`. Previous image name in
   `alien-monitor.previous-image` (`alien-monitor:uni-sec-20261108`).
2. Rehearsal in a throwaway container of the candidate, network none, its own anvil
   (`rehearse.py`, `rehearsal.log`): core deployed; NFT saved as the lottery → has code, not
   accepted; `_deploy_lottery_forge()` → `AIAgentLottery` at a new address, `currentRoundId()`
   = 0, snippet names it. `REHEARSAL-OK`.
3. Monitor, step 1 (14:37Z): `docker stop -t 90` (main.py's shutdown hook stops anvil, which
   saves its state), then `scripts/redeploy_alien_monitor_live.sh alien-monitor --image
   alien-monitor:uni-lottery-20261114` (env kept, 79 vars, values not shown). Bootstrap:
   «saved lottery 0x9fe4… is not an AIAgentLottery; deploying one» → `AIAgentLottery deployed:
   0x84ea74d481ee0a5332c457a4d796187f6ba67feb`. Config and snippet name it.
4. Relayer restart (14:39Z): re-bound `0x5910… → 0x84eA74d4…`, round 1 opened, Hub tithe,
   round 1 drawn (winner Boreas, $0.80), round 2 opened.
5. Relayer image (14:44Z): `aicom-security:ailottery-relayer-uni-lottery-20261114` =
   `hc-live-20261031` + patched `economy.py` (`relayer-ctx/`, SHA256SUMS there). Read-only probe
   on the live chain: NFT has code, not a lottery; `0x5910…` no code; `0x84ea…` lottery. Host
   compose `/root/claudecode/aicom/lottery/docker-compose.uni.yml`: image line changed (copy of
   the old file: `docker-compose.uni.yml.pre`). Recreated with `docker compose -p ailottery-uni
   --env-file relayer.env up -d --no-deps --no-build relayer`; `relayer.env` (0600) is the old
   container's own env. Before: the compose-rendered environment equals the running one (31 of
   31 keys). After: env and mounts identical to the old container (`relayer.inspect.{pre,post}.json`,
   0600). healthz `contract_live: true`.
6. Monitor, step 2 (14:51Z): same procedure with `alien-monitor:uni-lottery-feed-20261114`.
   The saved lottery was accepted (no redeploy, same address); health shows
   `lottery_feed {"fresh": true, "round": 30}` at 14:53:45Z.
7. Alerter on not-my-vps (alias `skopos-vps`): `/usr/local/lib/aicom-alert/ecosystem_alert.py`
   = aicom `scripts/ecosystem_alert.py` (sha256 `513631ec…`); previous file
   `/root/ecosystem_alert.py.pre-uni-lottery-20261114`. Dry run with the unit's env: 161 of 163
   checks OK (the two open: disks of competing-lab and PingBlip). Probe on the host:
   `uni_demo_chain_up True`, `uni_lottery_rounds True — round 33 reported 4 s ago`.

Images: `alien-monitor:uni-lottery-20261114` `sha256:a4bb5128…`,
`alien-monitor:uni-lottery-feed-20261114` `sha256:e8fb4ce6…` (running),
`aicom-security:ailottery-relayer-uni-lottery-20261114` `sha256:8da893bd…` (running).

Check at 14:56Z: `currentRoundId()` = 33; last 10 minutes: 20 rounds drawn, 0 `round failed`.

## Rollback

```
# monitor (either earlier image works; the saved lottery stays valid)
ssh factory-vps 'docker stop -t 90 alien-monitor; cd /root/claudecode/aicom && ./scripts/redeploy_alien_monitor_live.sh alien-monitor --image alien-monitor:uni-sec-20261108'
# relayer
ssh factory-vps 'K=/root/alien-uni-lottery-20261114; cp -p $K/docker-compose.uni.yml.pre /root/claudecode/aicom/lottery/docker-compose.uni.yml && cd /root/claudecode/aicom/lottery && docker compose -p ailottery-uni -f docker-compose.uni.yml --env-file $K/relayer.env up -d --no-deps --no-build relayer'
# alerter
ssh skopos-vps 'install -m 0644 /root/ecosystem_alert.py.pre-uni-lottery-20261114 /usr/local/lib/aicom-alert/ecosystem_alert.py'
```

Rolling back the monitor to `uni-sec-20261108` brings back the "code is enough" check; with the
current config that is harmless (the saved address is a real lottery) until the next chain reset.

## Not done

- The production relayer on my-vps runs an older image without `_is_lottery()`; it gets it with
  its next normal rollout. It was healthy and was not touched.
- The stale lottery variables in hub-uni and alien-monitor env, and `LOTTERY_ADDRESS=0x5910…` in
  the relayer env, stay: no code reads the first two, and the relayer treats its env as a first
  guess and follows `hub.env.snippet`.
- aicom's `lottery/docker-compose.uni.yml` still says `image: ailottery-relayer:uni` (built from
  source); only the host's copy pins the security image.
