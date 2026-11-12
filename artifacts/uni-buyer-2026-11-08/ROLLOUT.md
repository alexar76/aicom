# UNI realm buyer lets go of a channel the hub refused (factory-vps, 2026-11-08)

Owner, looking at monitor-uni.modelmarket.dev: «а на юни у нас всего 4 инвокации за сутки?», then «Yes, fix it».

## What was wrong

- The header's INVOCATIONS is the UNI hub's own `invocations_24h` (uni.modelmarket.dev, `modelmarket-hub-uni` on
  factory-vps :9183), and it was true: 4 calls in 24 h, one `geo.bearing@v1` probe every 6 hours (00:41, 06:41, 12:41,
  18:41 UTC). The hub's own daily counts: 10-25 8,543, 10-26..28 4 a day, 10-29 10,419, 10-30 4,164, 10-31 5,792,
  11-01 11,134, then 4 a day from 11-02.
- The realm's buyer (`alien-monitor/backend/universe_external_buyer.py`) opened `ch_0c657ee9ed4c4e8c` at
  2026-10-31 21:59 UTC; the hub credited $124.73. The hub bills a channel in whole cents rounded up
  (`channels._dollars_to_cents_bill`, BILLING-001), so a $0.002–0.005 call takes $0.01, while the buyer subtracted the
  bare catalogue price. By 2026-11-01 15:26 UTC the hub had debited all $124.73 (12,309 calls) and answered 402
  "insufficient balance", balance 0.0; the buyer counted $13.57 spent and $86.43 left. At 22:02 UTC the hub expired
  the channel after its 24 hours ("channel not open").
- `_channel_for` reused a channel on the buyer's own tally, and `_invoke` only logged a refusal, so every round from
  then on bought nothing. The header showed rounds (BUYER RND) and nothing said the rounds were empty: the
  "economy stalled" line only covered refused channel opens. 10-26..28 was the same stall, ended by a container
  restart, which drops the in-memory channel.

## What changed

- The hub's word on the channel: credited balance and `expires_at` taken from the `channel/open` reply;
  `remaining_balance` from an invoke reply when the hub gives one (local delivery), otherwise the charge billed the
  hub's way (whole cents, up).
- A 402 "insufficient balance", "channel not open", "channel expired" or "channel closed" marks the channel dead: the
  round stops invoking it, settles it, and the next round opens a new one. A channel within 15 minutes of
  `expires_at` is replaced before the hub expires it.
- 20 rounds in a row that held a channel and bought nothing put `stalled` in the buyer's status, with the hub's last
  refusal; `apply_buyer_health` turns it into the header's "economy stalled" line.
- Tests: `TestTheHubsWordOnTheChannel` + the cent-billing test in `alien-monitor/tests/test_universe_buyer_health.py`
  (7 of the 8 new class tests fail on the old code); one existing expectation corrected ($0.002 is billed $0.010).
  Monitor suite 1160 passed; `test_warden_ruleset_mirror.py` fails with and without this change.

## Deployed

The running container's buyer was older than main (`git show 4b7778fff~1:…` byte for byte; it lacks c49e5a76d, the
2026-10-25 wallet-signing binding, and `evm_dev_key_safety.py`), so the same change was merged onto that version
(`git merge-file`, no conflicts, hunks identical to the repository diff) instead of shipping main's file;
`universe_layers.py` in the container equalled HEAD.

- 07:10 UTC `alien-monitor:uni-buyer-20261108`, 07:19 UTC `alien-monitor:uni-buyer2-20261108` (adds cent billing):
  `FROM aicom-security:alien-monitor-hc-live-20261031` + the two backend files, context in
  `/root/alien-uni-buyer-20261108/ctx` on factory-vps; recreated with `scripts/redeploy_alien_monitor_live.sh
  alien-monitor --image …` (env kept, values not shown). Only the UNI container; the LIVE monitor does not run the buyer.
- Checked: rounds buy again from round 1 (`bought 6 of 6 for $0.060`); at 07:22 UTC the buyer's balance $160.14 equals
  the hub's `ch_898d0f2fa7194a47` (16,014 cents, credited 16,039); the hub's `invocations_1h` went from 1 to 29 within
  minutes of the first deploy.
- Not yet seen live: the hand-over to a new channel. The current one runs out in about 18 h or is replaced 15 minutes
  before 2026-11-09 07:22 UTC; look for `[Buyer] hub says channel … cannot pay` or a round right after
  `Channel open` in `docker logs alien-monitor`.

## Rollback

```bash
ssh factory-vps 'cd /root/claudecode/aicom && ./scripts/redeploy_alien_monitor_live.sh alien-monitor --image aicom-security:alien-monitor-hc-live-20261031'
```

(`/root/alien-uni-buyer-20261108/alien-monitor.previous-image` holds the same name.)

## Security change c49e5a76d on the UNI monitor (07:43 UTC)

Owner: «ну деплой, выкладывай». c49e5a76d (2026-10-25, bind wallet signing to the actual RPC chain) was on main but not
in the UNI image. The container runs the pre-split `universe.py` (2,738 lines, no `universe_deploy.py`), so its
hunks were ported by hand (`universe-c49e5a76d-port.diff` here, 31 changed lines): `_init_web3` refuses a non-local
RPC and a chain other than 31337; `_assert_demo_deployment_rpc` before each of the three `forge script` runs, which now
pass `--chain-id 31337`. The buyer is main's file exactly (it equals the running buyer + this fix + c49e5a76d + one
comment, checked with `git merge-file`), plus `evm_dev_key_safety.py` from main.

- Image `alien-monitor:uni-sec-20261108` = `FROM alien-monitor:uni-buyer2-20261108` + those three files, context
  `/root/alien-uni-sec-20261108/ctx` on factory-vps; previous image in `alien-monitor.previous-image` there.
- In the image, host network: local anvil 127.0.0.1:8545 connects (chain 31337, 20 accounts) and passes the deploy
  guard; `http://8.8.8.8:8545` and `https://mainnet.base.org` are refused by both. Both UNI RPCs answer chain id
  0x7a69 (31337), the buyer's 172.17.0.1:8546 included.
- Live after the recreate: universe connected, the buyer opened `ch_47fe8fbde0a648a1` with a deposit through
  172.17.0.1:8546 and bought from round 1; its balance equals the hub's ($120.92); no errors in the log.
  "[Universe] EVM connected" once a minute is the anvil watchdog calling `_init_web3`, as before.
- Rollback: `./scripts/redeploy_alien_monitor_live.sh alien-monitor --image alien-monitor:uni-buyer2-20261108`
  (keeps the buyer fix) or `--image aicom-security:alien-monitor-hc-live-20261031` (neither).
- `tests/test_evm_public_dev_key_safety.py` 58 passed.

## Seen, not changed

- Channel billing rounds every sub-cent price up to a cent: through a channel a $0.001 capability costs $0.01. That is
  the hub's deliberate BILLING-001 rule, on every hub, for real buyers too; whether to keep it is a pricing decision.
- The lottery half of c49e5a76d is not deployed either: `ailottery-relayer-1` and `ailottery-agent-1` on my-vps
  (images `aicom-lottery-migrated:*-20261107`) have no `dev_key_safety` module. Separate service and host.
- The LIVE monitor (`alien-monitor-live`) image also lacks c49e5a76d; LIVE mode does not run the universe or its buyer.
