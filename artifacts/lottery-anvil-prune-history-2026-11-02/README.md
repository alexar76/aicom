# Lottery chain: `--prune-history` instead of `--preserve-historical-states` (live since 2026-11-03 04:21Z)

## Why

`ailottery-chain-1` on admin-vps runs anvil 1.3.1 with `--state /state/anvil-state.json --state-interval 60
--preserve-historical-states` (host-local `/root/lottery/docker-compose.override.yml`). Anvil keeps every historical
state. Measured on 2026-11-02:

- **Memory:** 3.4 GB RSS.
- **Temporary dumps:** ~2.2 GB of `anvil-state-*` dumps in the container's `/root/.foundry/anvil/tmp` every 15 minutes.
  The cron `prune-anvil-state.sh` (`*/15`) frees them each run (`/var/log/prune-anvil-state.log`: 2,132–2,215 MB a run).
- **State file:** 0.3–2.5 GB, rewritten every minute (1,001,398,267 bytes at 17:34Z; 790 MB of it is
  `historical_states`).

The disk of admin-vps therefore swings between 85 and 90 % every 15 minutes, and the alert "The disk of oracle is
filling up" stays open.

## Test on a copy (17:34–17:47Z), container `lotchain-test-20261102`

The test ran with `--network none`, the same image (`aicom-security:ailottery-chain-1-os-20261031`) and the same
flags, with bare `--prune-history` in place of `--preserve-historical-states`.

- **Loading the full copy** (1.0 GB with `historical_states`): killed by OOM at a 2.5 GB memory limit.
- **Loading the copy without `historical_states`** (`head -c` up to the comma before the key, plus `}`; 210 MB):
  up in 6 s.
- **Compared with the live chain:**

  | Check | Result |
  |---|---|
  | Block | 45501, continuing from the copy |
  | Lottery contract `0x5fbd…0aa3` code hash | same |
  | `owner()` | same |
  | Hashes of blocks 1 and 45000 | same |
  | Logs of blocks 45000–45500 | 320 = 320 |
  | Receipt of a block-1000 transaction | success |

- **Five minutes running:**
  - RSS flat at 606–629 MiB;
  - tmp flat at 153 MB;
  - state file 210 MB, growing ~19 KB a minute.
- **Restart from its own dump:** stop took 1 s; the chain came back at the same block with the same hashes.
- **What changes:** state at an older block is no longer served (`BlockOutOfRangeError` for block N-2). The lottery
  code does not ask for it:
  - the relayer reads block headers for `blockhash` (`seed_status`), and they stay;
  - `"pending"` is used for nonces only;
  - no `block_identifier` or `blockTag` anywhere in `lottery/` outside vendored files;
  - only relayer, agent and showcase are on the chain's network; showcase has no RPC.

## Roll-out

The roll-out is `roll.sh`, run on admin-vps from `/root/lotchain-test-20261102/`. It:

1. switches the override flag;
2. stops the chain with a 300 s grace period, so anvil dumps on exit;
3. keeps the full final dump as `live-final-full.json`, the rollback copy;
4. strips `historical_states`;
5. recreates only `chain` (`up -d --no-deps`);
6. checks the block and the code hash.

Any failure restores the old override and the full dump and starts the chain again. The lottery chain is down for
about a minute.

The auto-mode classifier refused to run it on 2026-11-02, because the owner's yes was for "the prune every 5 minutes",
not for restarting the chain.

The cron prune (`aicom-prune-anvil`) stays as a belt.

## Result (owner ran `roll.sh`, 2026-11-03)

`roll.log`:
- 04:20:49 live block 55142, RSS 960 MiB;
- stopped in 10 s, final dump 539,660,295 bytes (kept as `live-final-full.json`);
- historical states stripped: 254,231,379 bytes;
- 04:21:07 up at block 55143, same code hash, `--prune-history` in the command; DONE.

After the restart, the following match: `owner()`, the hashes of blocks 1 and 45000, and the logs of blocks
45000–45500 (320). RSS was 693 MiB and tmp 153 MB.

**Trap: the chain's clock.** In demo mode the relayer warps anvil time with `evm_increaseTime`, and over 3,225 rounds the
chain clock ran about 2.9 days (250,700 s) ahead of real time. Anvil does not keep that offset across a restart:
- blocks 55144–55153 (50 s) were stamped with real time, 250,667 s earlier than block 55143; block 55154 jumped forward again;
- the relayer's `closeEntries(3226)` landed in that window and reverted (`TooEarly`, two reverted transactions,
  "round failed" at 04:21:11);
- on its next pass the relayer warped the clock forward again, and round 3226 was drawn at 04:22:01.

The only trace left is the dip in the timestamps of blocks 55144–55153.

Next time, right after the start, set the next block to just after the last one, before the relayer acts:
`cast rpc evm_setNextBlockTimestamp <last + 5>`.
