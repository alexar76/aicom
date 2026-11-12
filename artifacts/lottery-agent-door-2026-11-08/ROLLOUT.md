# Lottery: why the external agent never entered a round, and the fix (my-vps, 2026-11-08)

Owner: «Yes, look into it» (after the relayer takeover fix in `artifacts/lottery-sec-2026-11-08`).

## What is wrong

`ailottery-agent-1` (wallet `0x7099…79C8`, anvil account 1) has never sent a transaction on the demo chain:
its nonce is 0 and its balance is the untouched 100,000 ETH of genesis. Every poll since its start ends in
`agent: ('execution reverted', '0x')`, 945 times in two hours on 2026-11-08.

The agent asks the contract `paidTicketsEnabled()` before entering. The contract on the demo chain
(`0x5FbD…0aa3`) does not have that function, nor `workSeated`; both calls revert with no data.
`currentRoundId`, `getRound`, `ticketPrice`, `entryWindow` (120) and `paused` (false) answer, and so do
`buyTickets`, `buyTicketsWithVoucher`, `claimPrize` and `refund`.

The contract is older than the agent. It was deployed from the June 2026 source: the chain image
`aicom-lottery-migrated:chain-20261107` holds `src/AIAgentLottery.sol` with sha256 `6866ae731c24…`, the
same file as e60aa7218 (2026-06-16) and 34e078fc9 (2026-07-03). The image's `COPY src` layer was built on
2026-10-11 13:37 UTC on admin-vps from `/root/lottery` (clone of Gitea `alexar76/lottery`), whose
`contracts/src/AIAgentLottery.sol` still has that June hash; the 2026-10-31 layer on top is only the OS
package upgrade. The agent and relayer images carry the September code, so the stack was built from a
tree whose parts came from different months. Since 2026-11-07 the lottery runs on my-vps from those
same images; my-vps has no build tree.

What the June contract lacks against main (`lottery/contracts/src/AIAgentLottery.sol`), from the changes
7f4a283af (07-02 audit), 12f115204 (07-26 fairness rework), 1b1413758, 5eca0a9de, 610b34d3f (09-10 work
seat by default) and ec902d260:
- the unpaid work seat (`enterFromWork`, `workSeated`, `paidTicketsEnabled`); on this chain buying tickets
  is the only way in, while the lottery README says the default door is unpaid work;
- `cancelStalledRound` (anyone refunds a stalled round) and `forfeitUnclaimedPrize`;
- the rule that the operator cannot cancel a Drawing round while its seed block hash is readable.
  The June `cancelRound` accepts any Open or Drawing round at any time. The relayer applies that rule
  itself (`economy_draw.safe_cancel`), which is why round 9993 waited about 12 minutes this morning.

The relayer already reads a missing `paidTicketsEnabled` as "paid tickets are open"
(`ChainClient.paid_tickets_enabled`), so its own five agents buy tickets on this contract. The external
agent had no such rule.

## The fix (deployed 2026-11-08 10:28 UTC)

`lottery/agent/ailottery_agent/__main__.py`:
- `paid_door_open`: a `paidTicketsEnabled()` call that reverts with no data means the contract predates
  the switch, and `buyTickets` is the door; a revert that carries data, or a transport error, is raised
  as before. Same reading as the relayer.
- A transaction that is mined and reverts (receipt status 0) is an error (`TxReverted`). Before, the
  agent printed "bought" or "claimed" for a reverted transaction.
- A voucher purchase the contract refuses falls back to plain tickets in the same round.
- A round the agent cannot enter is tried 3 times, then the agent waits for the next round, instead of
  sending a transaction every poll for the whole entry window.
- A cancelled round the agent paid for is refunded through `refund` (both the June contract and main
  have it). A claim or refund that reverts is reported once.
- Work seat path on a newer contract is unchanged.

Tests: `lottery/agent/tests/test_agent_doors.py`, 15 passed (locally and inside the image).

## Checked

A fork of the live chain does not work: the chain runs with `--prune-history`, so a fork cannot read
state once the chain has moved one block. `isolated_check.sh` instead starts a throw-away anvil on its
own Docker network, deploys the chain image's own contract source with the image's own deploy script
(same address `0x5fbd…0aa3`, same code size 18,663 bytes as the live contract), and runs both agents
with the live agent's key (env file 0600, deleted):

- round 1, image `agent-sec-20261108` (running today): `execution reverted` every poll, nonce 0.
- round 2, image `agent-door-20261108` (the fix): "bought 2 tickets", nonce 1, `paidBy` 0.002 ETH.
- round 2 cancelled by the operator: "tickets refunded", `paidBy` 0, balance back 0.00196 ETH (0.002 less gas).
- round 3 opened while it runs: "bought 2 tickets" without a restart.
- Live chain afterwards: agent nonce still 0. Containers and network removed.

This historical script reads the serving agent's environment and the live chain's nonce. It is not
executed by the current gVisor validation: that harness uses the public legacy Git source and a
synthetic Anvil wallet, with no production keys or state.

## Deployed (10:28 UTC)

Owner: «Yes, deploy it». The compose file's agent image was changed with `sed` (one line; mode 0600 kept; backup
`docker-compose.migrated.json.pre-agent-door-20261108`), then `docker compose -f docker-compose.migrated.json up -d
--no-deps agent` at 10:28:02 UTC. The image's `__main__.py` has the same md5 as the commit (`7a23eb3a…`);
`dev_key_safety.py` is unchanged.

- 10:28:12 the agent started behind the startup guard ("restored contract verified") and bought 2 tickets in round
  10093 with a relayer voucher (+0 bps). It won that round ("winner Agent-7099") and claimed 0.0096 ETH.
- Rounds 10094, 10095 and 10096: 2 tickets each; `paidBy` 0.002 ETH in each of the four rounds; nonce 5 at
  10:32:27 UTC. The prize pool went from $8.00 to $9.60 with the agent's tickets.
- Relayer: no ERROR lines and no tracebacks since the swap; rounds open and draw about once a minute as before.
  lottery.modelmarket.dev answers 200.

## How it was deployed

The image is built on my-vps: `aicom-lottery-migrated:agent-door-20261108` =
`FROM aicom-lottery-migrated:agent-sec-20261108` + the fixed `__main__.py` (the running file equalled
main before the fix). Context: `/root/lottery-agent-door-20261108/ctx`.

```bash
ssh my-vps 'cd /root/lottery && cp -a docker-compose.migrated.json docker-compose.migrated.json.pre-agent-door-20261108 && python3 - <<EOF
import json; p="docker-compose.migrated.json"; d=json.load(open(p))
d["services"]["agent"]["image"]="aicom-lottery-migrated:agent-door-20261108"; json.dump(d,open(p,"w"),indent=2)
EOF
docker compose -f docker-compose.migrated.json up -d --no-deps agent'
```

Entry, claim/refund follow-up and retry tracking are kept only in memory. Restarting during an Open
round can buy tickets again; restarting after entry loses automatic follow-up for that round. Check
any outstanding claims or refunds against chain state separately.

After the swap the agent spends 0.002 demo ETH per round (about 3 ETH a day of its 100,000) and can win.

Rollback: `cp -a docker-compose.migrated.json.pre-agent-door-20261108 docker-compose.migrated.json` and
the same `up -d --no-deps agent`.

## Not changed

- The demo chain keeps the June contract. Moving it to main's contract means a new deployment on the
  chain (new address), the relayer's agents entering through work seats, and the showcase following the
  new address; that is a separate decision.
- `/root/lottery` on admin-vps (June contract) and `/root/aicom` there (2026-09-04 contract) are stale
  trees; the lottery no longer builds there. Any rebuild should come from the monorepo.
