# Lottery: wallet-signing guard (c49e5a76d) on the relayer and agent (my-vps, 2026-11-08)

Owner: «Yes, roll it out» (the lottery half of c49e5a76d, after it went live on the UNI monitor).

## Before

`ailottery-relayer-1` and `ailottery-agent-1` on my-vps (`/root/lottery/docker-compose.migrated.json`, images
`aicom-lottery-migrated:{relayer,agent}-20261107`, moved from admin-vps on 2026-11-07) had no `dev_key_safety`
module. Their files are older than main: `chain.py`, `rpc.py` and the agent's `__main__.py` equal 177648a03 /
62eee7172 (2026-09-11); `config.py` is that era plus a hand-placed mesh-token guard. `economy.py` equals HEAD.

## What was deployed (08:15 UTC)

c49e5a76d's hunks merged onto the running files (`git merge-file`; `config.py` had one conflict, resolved by keeping
the running mesh-token guard and adding `_guard_public_dev_keys`), plus `dev_key_safety.py` from c49e5a76d. Thin
images `FROM` the running ones, context `/root/lottery-sec-20261108/{relayer,agent}` on my-vps:
`aicom-lottery-migrated:relayer-sec-20261108`, `aicom-lottery-migrated:agent-sec-20261108`. Compose backed up as
`/root/lottery/docker-compose.migrated.json.pre-sec-20261108`; `docker compose … up -d --no-deps relayer agent`
(chain and showcase untouched).

Checks before the switch, in the new images with the containers' own environment (values never printed):
- config loads (mode demo, chain 31337, RPC `http://chain:8545` local); all 12 keys — operator, oracle signer,
  treasury, sponsor, benefactor, faucet, five agents, and the agent container's key — are public Anvil keys and pass
  on this chain;
- with the same keys and `RPC_URL=https://mainnet.base.org`, `CHAIN_ID=8453`: the new image refuses ("Public test or
  compromised wallet keys are restricted to a verified local development chain"); the old image loads it.
- relayer tests on the running package with the patch: same 105 passed / 14 environment errors as unpatched.

After: both containers up, relayer healthy, agent verified the contract; no tracebacks.

## What the restart broke, and the fix (deployed 08:24 UTC)

The relayer was recreated between `closeEntries` and `fulfillDraw` of round 9993 (closed 08:15 UTC by chain clock).
The draw word lived only in the old process. The new process logs "round 9993 still drawing — not opening another"
every 5 s and never queues the round: `sweep_stalled_rounds` only revisits rounds this process abandoned. The relayer
does not cancel a round while its seed hash is readable (`economy_draw.safe_cancel`; seedBlock 170466, readable until
about block 170722; head 170550 at 08:22:50 UTC). Correction, found later the same day: that is the relayer's own
rule; the June 2026 contract on this chain would accept the cancel at once (see `artifacts/lottery-agent-door-2026-11-08`).
After that point the round can be cancelled and refunded, but nothing running will do it. The lottery opens no new
round until then.

Fix in `lottery/relayer/ailottery_relayer/economy.py`: a round still Drawing at the top of `run_one_round` is always
inherited (the loop draws close-to-fulfil in one call), so it goes to `defer_stalled`, and the sweep cancels it the
moment the contract allows. Test `test_a_round_left_drawing_by_an_earlier_process_is_taken_over` (fails on the old
code with `[] == [9993]`). The first build-and-switch command was refused by the session's permission check as a new
production change (nothing of it ran); the owner then said «Yes, deploy the fix».

- 08:24:56 UTC: relayer on `aicom-lottery-migrated:relayer-sec2-20261108` (the same Dockerfile plus `economy.py`; the
  host's file equalled HEAD before this change).
- 08:25:10: "round 9993 left unresolved — queued for the stalled-round sweep"; then one ERROR line per cycle
  ("cancelRound is REFUSED while the round is still settleable") until the seed hash aged out.
- About 08:37: 9993 cancelled (on chain `status` 4); 08:37:47 round 9994 opened, 08:38:35 drawn (winner Echo, $8.00);
  9995 and 9996 followed about a minute apart, as before.
- 9993's tickets ($9 of demo ETH value from five agents) and $1 of funding stay claimable through the contract's
  `refund`; nothing in the relayer or the agent calls it.

## Seen, not changed

The external agent (`ailottery-agent-1`) buys nothing: on an open round it calls `paidTicketsEnabled()` and
`workSeated()`, which the contract restored on 2026-11-07 does not have (`execution reverted`, 33 times by 08:41 UTC;
`currentRoundId`, `getRound`, `ticketPrice` answer). Those calls are in its 2026-09-11 code, untouched by this rollout;
the relayer's long-standing "draw-window preflight skipped (contract unreadable)" is the same mismatch. Cause and fix:
`artifacts/lottery-agent-door-2026-11-08/ROLLOUT.md` (the chain runs the June 2026 contract; the agent never entered a
round, nonce 0).

## Rollback

```bash
ssh my-vps 'cd /root/lottery && cp -a docker-compose.migrated.json.pre-sec-20261108 docker-compose.migrated.json && docker compose -f docker-compose.migrated.json up -d --no-deps relayer agent'
```

Relayer alone back to the guard without the takeover: compose image `aicom-lottery-migrated:relayer-sec-20261108`.
Compose before this whole rollout: `/root/lottery/docker-compose.migrated.json.pre-sec-20261108`.
