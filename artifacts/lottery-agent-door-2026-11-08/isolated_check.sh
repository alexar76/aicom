#!/bin/bash
# The agent fix against the SAME contract source the live demo chain runs (chain image src,
# sha256 6866ae73…), deployed on a throw-away anvil on its own network. Live chain untouched.
set -u
W=/root/lottery-agent-door-20261108
NET=agentdoor-net
CHIMG=aicom-lottery-migrated:chain-20261107
NEW=aicom-lottery-migrated:agent-door-20261108
OLD=aicom-lottery-migrated:agent-sec-20261108
AG=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
OP=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
MN="test test test test test test test test test test test junk"
ENVF=$(mktemp); chmod 600 "$ENVF"
cleanup() { docker rm -f agentdoor-chain agentdoor-new agentdoor-old >/dev/null 2>&1; docker network rm $NET >/dev/null 2>&1; rm -f "$ENVF"; }
trap cleanup EXIT
mkdir -p $W/out; rm -f $W/out/addr

docker network create $NET >/dev/null
docker run -d --name agentdoor-chain --network $NET --entrypoint anvil $CHIMG \
  --host 0.0.0.0 --chain-id 31337 --accounts 12 --balance 100000 --mnemonic "$MN" --block-time 1 --silent >/dev/null
CIP=$(docker inspect agentdoor-chain --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
R=http://$CIP:8545
c() { docker exec agentdoor-chain cast "$@"; }
for i in $(seq 1 30); do c chain-id --rpc-url $R >/dev/null 2>&1 && break; sleep 1; done

echo "== deploy the chain image's contract source (forge install + build, takes a while)"
docker run --rm --network $NET -v $W/out:/out -e RPC_URL=$R -e LOTTERY_ADDRESS_FILE=/out/addr \
  -e ENTRY_WINDOW=600 -e MIN_DRAW_DELAY=2 --entrypoint bash $CHIMG -c \
  'export PRIVATE_KEY=$(cast wallet private-key "test test test test test test test test test test test junk" 0); ./docker-deploy.sh > /tmp/d.log 2>&1; rc=$?; grep -E "deploy:|Error|error" /tmp/d.log | tail -5; exit $rc' || { echo DEPLOY FAILED; exit 1; }
C=$(cat $W/out/addr)
echo "throw-away contract $C, code size $(c codesize $C --rpc-url $R)"
echo "paidTicketsEnabled() here: $(c call $C 'paidTicketsEnabled()(bool)' --rpc-url $R 2>&1 | tail -1 | cut -c1-90)"

docker inspect ailottery-agent-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(AGENT_KEY|CHAIN_ID)=' > "$ENVF"
run_agent() { docker run -d --name $1 --network $NET --env-file "$ENVF" -e RPC_URL=$R -e LOTTERY_ADDRESS=$C \
  -e RELAYER_URL= -e TICKETS=2 -e POLL=1 -e USE_VOUCHER=0 $2 >/dev/null; }

echo "== round 1, the agent as it runs today"
c send --unlocked --from $OP $C "openRound()" --rpc-url $R >/dev/null
run_agent agentdoor-old $OLD; sleep 10
docker logs agentdoor-old 2>&1 | tail -3
echo "agent nonce $(c nonce $AG --rpc-url $R), paidBy[1] $(c call $C 'paidBy(uint256,address)(uint256)' 1 $AG --rpc-url $R)"
docker rm -f agentdoor-old >/dev/null
c send --unlocked --from $OP $C "cancelRound(uint256)" 1 --rpc-url $R >/dev/null

echo "== round 2, the fixed agent"
c send --unlocked --from $OP $C "openRound()" --rpc-url $R >/dev/null
run_agent agentdoor-new $NEW; rm -f "$ENVF"; sleep 10
docker logs agentdoor-new 2>&1 | tail -3
echo "agent nonce $(c nonce $AG --rpc-url $R), paidBy[2] $(c call $C 'paidBy(uint256,address)(uint256)' 2 $AG --rpc-url $R)"
B0=$(c balance $AG --rpc-url $R)
echo "== cancel round 2: the agent should take its tickets back"
c send --unlocked --from $OP $C "cancelRound(uint256)" 2 --rpc-url $R >/dev/null; sleep 6
docker logs agentdoor-new 2>&1 | tail -2
B1=$(c balance $AG --rpc-url $R)
echo "paidBy[2] after $(c call $C 'paidBy(uint256,address)(uint256)' 2 $AG --rpc-url $R), balance change $(python3 -c "print(($B1-$B0)/1e18)") ETH (2 tickets = 0.002 minus gas)"
echo "== round 3 opened while the agent runs: it should enter again without a restart"
c send --unlocked --from $OP $C "openRound()" --rpc-url $R >/dev/null; sleep 6
docker logs agentdoor-new 2>&1 | tail -1
echo "live chain: agent nonce still $(docker exec ailottery-chain-1 cast nonce $AG --rpc-url http://127.0.0.1:8545)"
