"""Publish WARDEN's scan of other ERC-8004 agents' MCP endpoints as ReputationRegistry feedback.

    aimarket-hub/.venv/bin/python deploy/erc-8004/feedback.py --scan SCAN.json --tools TOOLS.jsonl \\
        --key-file ~/.aicom-base-deployer-v4.json                 # writes reports + dry run
    … --send                                                       # sends

What it says, and only that: at `scannedAt`, the MCP endpoint an agent declares served these tool
definitions, and the published @aimarket/warden release found no blocking finding in them (score,
counts, ruleset digest, a hash of the exact definitions). One feedback per agent, from WARDEN's
wallet (the operator, owner of agent 96684); the contract refuses feedback on our own agents.

Agents with a blocking finding are NOT published: WARDEN has false positives, and a public
negative mark on someone else's agent is the owner's call, made per agent.

Reports land in deploy/erc-8004/feedback/warden-<agentId>.json and are served from
https://modelmarket.dev/.well-known/erc-8004/feedback/ (copy them to /var/www/erc-8004/feedback/
on the apex host BEFORE sending: the on-chain hash commits to those bytes).
"""
import argparse
import hashlib
import json
import os
import sys
import time

from eth_abi import encode
from eth_account import Account
from eth_utils import keccak

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import register  # noqa: E402
from register import CHAIN_ID  # noqa: E402

_raw_rpc = register.rpc


def rpc(method, params, tries=6):
    """register.rpc with patience: the public Base endpoint answers 429 to a burst."""
    import urllib.error
    for i in range(tries):
        try:
            out = _raw_rpc(method, params)
            time.sleep(0.4)
            return out
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


register.rpc = rpc  # l1_fee calls it too
l1_fee = register.l1_fee

REPUTATION = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
IDENTITY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
WARDEN_AGENT_ID = 96684
OPERATOR = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"   # owner of our three agents (the Mac's key)
FEEDBACK_WALLET = "0x564bE09d06117A106ECC006a19b67768cBd91666"  # WARDEN's feedback-only wallet (admin-vps)
CLIENTS = {OPERATOR.lower(), FEEDBACK_WALLET.lower()}
OUR_OWNERS = CLIENTS  # never rate an agent either of these owns: that would be self-review
# Where state and reports live: next to this file on the Mac, /var/lib + /var/www on the server.
STATE = os.environ.get("WARDEN_FB_STATE", HERE)
BASE_URL = os.environ.get("WARDEN_FB_BASE_URL", "https://modelmarket.dev/.well-known/erc-8004/feedback")
OUT = os.environ.get("WARDEN_FB_REPORTS", os.path.join(STATE, "feedback"))
LOG = os.path.join(STATE, "feedback.log")
PENDING = os.path.join(STATE, "feedback-pending.json")
CLIENT = OPERATOR  # set from the key file in main()
WARDEN_INTEGRITY = "sha512-jSdepve/mwTLCwrSmbQ3vJLGPSXBWvgIQcJFi3CVrcUqiiXBbSPjlClqMUGIaT0tEE/exRcPgfAPOUe1SyuXow=="
SELECTOR = keccak(text="giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)")[:4]


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def report_for(row: dict, tools: list, scan: dict, scanned_at: str) -> dict:
    return {
        "type": "aimarket.warden-scan/v1",
        "issuer": {"name": "WARDEN", "agentRegistry": f"eip155:{CHAIN_ID}:{IDENTITY}",
                   "agentId": WARDEN_AGENT_ID, "wallet": CLIENT},
        "subject": {"agentRegistry": f"eip155:{CHAIN_ID}:{IDENTITY}", "agentId": int(row["agent_id"]),
                    "name": row["title"], "mcpEndpoint": row["url"]},
        "scannedAt": scanned_at,
        "scanner": {"package": f"@aimarket/warden@{scan['warden']}", "integrity": WARDEN_INTEGRITY,
                    "ruleset": scan["ruleset"]},
        "method": ("initialize + tools/list over streamable HTTP, nothing else called; every advertised "
                   "field of every tool scanned by StaticScanGate and ThreatGate (built-in list)."),
        "result": {"tools": row["tools"], "toolsSha256": hashlib.sha256(canonical(tools)).hexdigest(),
                   "score": row["score"], "blockingFindings": 0, "advisoryFindings": row["advisory"]},
        "meaning": ("A static check of the tool definitions this endpoint served at scannedAt. Not an "
                    "audit of the service, its code or its operator, and not an endorsement."),
        "reproduce": "https://github.com/alexar76/warden",
    }


def calldata(agent_id: int, value: int, endpoint: str, uri: str, digest: bytes) -> str:
    body = encode(["uint256", "int128", "uint8", "string", "string", "string", "string", "bytes32"],
                  [agent_id, value, 0, "warden-scan", "ruleset-v8", endpoint, uri, digest])
    return "0x" + (SELECTOR + body).hex()


REVOKE_SELECTOR = keccak(text="revokeFeedback(uint256,uint64)")[:4]
LAST_INDEX_SELECTOR = keccak(text="getLastIndex(uint256,address)")[:4]
EXCLUDE = os.path.join(STATE, "feedback-exclude.json")
MAX_TX_PER_RUN = 20
#: Absolute ceilings for one feedback transaction. The endpoint string comes from a third
#: party's agent card, so the calldata size — and the gas the estimate returns — is theirs to
#: choose; the wallet pays whatever the node estimates unless capped here.
MAX_GAS = 400_000
MAX_FEE_PER_GAS_WEI = 2_000_000_000          # 2 gwei; Base runs at a few hundredths of that
MAX_ENDPOINT_BYTES = 256
#: Base's GasPriceOracle: the L1 data fee is charged on top of the L2 gas and is not in it.
GAS_PRICE_ORACLE = "0x420000000000000000000000000000000000000F"
GET_L1_FEE_SELECTOR = keccak(text="getL1Fee(bytes)")[:4]


def endpoint_ok(url: str) -> bool:
    """A third party's endpoint as it may go into OUR signed calldata: https, short, plain."""
    raw = str(url or "")
    if not raw.startswith("https://") or len(raw.encode("utf-8")) > MAX_ENDPOINT_BYTES:
        return False
    return not any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw)


def l1_fee_wei(data: str) -> int:
    """What Base charges for posting this calldata to L1 (0 if the oracle cannot be read)."""
    try:
        payload = bytes.fromhex(data[2:] if data.startswith("0x") else data)
        call = "0x" + (GET_L1_FEE_SELECTOR + encode(["bytes"], [payload])).hex()
        return int(rpc("eth_call", [{"to": GAS_PRICE_ORACLE, "data": call}, "latest"]), 16)
    except Exception:  # noqa: BLE001 - the caps below still bound the L2 side
        return 0


def last_index(agent_id: int) -> int:
    data = "0x" + (LAST_INDEX_SELECTOR + encode(["uint256", "address"], [agent_id, CLIENT])).hex()
    return int(rpc("eth_call", [{"to": REPUTATION, "data": data}, "latest"]), 16)


def published() -> dict:
    """agentId -> the newest log entry (published or revoked) for it."""
    out = {}
    if os.path.exists(LOG):
        for line in open(LOG):
            if line.strip():
                e = json.loads(line)
                out[str(e["agentId"])] = e
    return out


def served_matches(uri: str, raw: bytes) -> bool:
    import urllib.request
    req = urllib.request.Request(uri, headers={"user-agent": "aicom-erc8004/1.0"})
    try:
        return urllib.request.urlopen(req, timeout=20).read() == raw
    except Exception:
        return False


def decide(scan: dict, tools_by_id: dict, scanned_at: str, excluded: set) -> tuple[list, list, list]:
    """(actions, held, unreachable). An action is ('give', row, path) or ('revoke', row, reason)."""
    actions, held, unreachable = [], [], []
    seen = published()
    stamp = scanned_at[:10].replace("-", "")
    for r in scan["rows"]:
        aid = str(r["agent_id"])
        if aid in excluded:
            continue
        prev = seen.get(aid)
        # Only a feedback THIS wallet gave can be revoked by it (entries before the field existed
        # were the operator's).
        live = (prev is not None and prev.get("status") == "ok" and prev.get("kind", "give") == "give"
                and prev.get("client", OPERATOR).lower() == CLIENT.lower())
        if r.get("status") != "ok":
            unreachable.append(r)          # a dark endpoint proves nothing either way: leave it
            continue
        if r.get("wouldBlock"):
            held.append(r)
            if live:
                actions.append(("revoke", r, "a blocking finding appeared"))
            continue
        rep = report_for(r, tools_by_id[aid], scan, scanned_at)
        if live:
            old = json.load(open(os.path.join(OUT, os.path.basename(prev["uri"]))))
            if old["result"]["toolsSha256"] == rep["result"]["toolsSha256"]:
                continue                   # same definitions, statement still true
            actions.append(("revoke", r, "tool definitions changed"))
            name = f"warden-{aid}-{stamp}.json"
        else:
            name = f"warden-{aid}.json" if not os.path.exists(os.path.join(OUT, f"warden-{aid}.json")) \
                else f"warden-{aid}-{stamp}.json"
        path = os.path.join(OUT, name)
        if not os.path.exists(path):
            open(path, "wb").write(json.dumps(rep, indent=1, ensure_ascii=False).encode() + b"\n")
        actions.append(("give", r, path))
    return actions, held, unreachable


def send_one(acct, data: str) -> tuple[str, dict]:
    nonce = int(rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    base_fee = int(rpc("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
    prio = int(rpc("eth_maxPriorityFeePerGas", []), 16)
    gas = int(int(rpc("eth_estimateGas", [{"from": acct.address, "to": REPUTATION, "data": data}]), 16) * 1.25)
    max_fee = base_fee * 2 + prio
    if gas > MAX_GAS or max_fee > MAX_FEE_PER_GAS_WEI:
        sys.exit(f"refusing: gas {gas} / maxFee {max_fee} wei exceeds the caps ({MAX_GAS} / {MAX_FEE_PER_GAS_WEI})")
    cost = gas * max_fee + l1_fee_wei(data)
    balance = int(rpc("eth_getBalance", [acct.address, "latest"]), 16)
    if balance < cost:
        sys.exit(f"refusing: {balance / 1e18:.9f} ETH does not cover this transaction ({cost / 1e18:.9f} ETH incl. L1 fee)")
    tx = {"chainId": CHAIN_ID, "nonce": nonce, "to": REPUTATION, "value": 0, "data": data, "gas": gas,
          "maxFeePerGas": max_fee, "maxPriorityFeePerGas": prio, "type": 2}
    signed = acct.sign_transaction(tx)
    tx_hash = "0x" + bytes(signed.hash).hex()
    json.dump({"tx": tx_hash}, open(PENDING, "w"))
    rpc("eth_sendRawTransaction", ["0x" + bytes(signed.raw_transaction).hex()])
    for _ in range(60):
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt:
            os.remove(PENDING)
            return tx_hash, receipt
        time.sleep(2)
    sys.exit(f"not mined after 2 minutes ({tx_hash}); kept in {PENDING}")


def revoke_all(args) -> None:
    global CLIENT
    accounts = json.load(open(os.path.expanduser(args.key_file)))["accounts"]
    acct = Account.from_key(accounts[0]["private_key"])
    del accounts
    if acct.address.lower() not in CLIENTS:
        sys.exit("refusing: the key file is neither WARDEN's feedback wallet nor the operator")
    CLIENT = acct.address
    live = [e for e in published().values() if e.get("status") == "ok" and e.get("kind", "give") == "give"
            and e.get("client", OPERATOR).lower() == CLIENT.lower()]
    print(f"live feedback from {CLIENT}: {[e['agentId'] for e in live]}")
    for e in live:
        idx = last_index(int(e["agentId"]))
        if idx == 0:
            continue
        data = "0x" + (REVOKE_SELECTOR + encode(["uint256", "uint64"], [int(e["agentId"]), idx])).hex()
        if not args.send:
            print(f"  would revoke {e['agentId']} index {idx}")
            continue
        tx_hash, receipt = send_one(acct, data)
        status = "ok" if receipt["status"] == "0x1" else "reverted"
        with open(LOG, "a") as f:
            f.write(json.dumps({"agentId": int(e["agentId"]), "name": e.get("name"), "kind": "revoke",
                                "client": CLIENT, "tx": tx_hash, "status": status,
                                "block": int(receipt["blockNumber"], 16),
                                "uri": f"revoke index {idx}: moved to {FEEDBACK_WALLET}"}) + "\n")
        print(f"  revoke {e['agentId']}: {status} {tx_hash}", flush=True)
        if status != "ok":
            sys.exit("stopping at the first revert")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan")
    ap.add_argument("--tools")
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--revoke-all", action="store_true",
                    help="revoke every live feedback this key's wallet gave (moving to another wallet)")
    args = ap.parse_args()
    if args.revoke_all:
        return revoke_all(args)
    if not (args.scan and args.tools):
        sys.exit("--scan and --tools are required")

    scan = json.load(open(args.scan))
    if scan["warden"] != "0.8.2" or scan["ruleset"]["version"] != "8":
        sys.exit("refusing: the scan must come from the published @aimarket/warden 0.8.2 (ruleset v8)")
    tools_by_id = {}
    for line in open(args.tools):
        if line.strip():
            rec = json.loads(line)
            tools_by_id[str(rec["agent_id"])] = rec.get("tools") or []
    scanned_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(args.tools)))
    excluded = set(map(str, json.load(open(EXCLUDE)))) if os.path.exists(EXCLUDE) else set()
    os.makedirs(OUT, exist_ok=True)
    global CLIENT
    accounts = json.load(open(os.path.expanduser(args.key_file)))["accounts"]
    acct = Account.from_key(accounts[0]["private_key"])
    del accounts
    if acct.address.lower() not in CLIENTS:
        sys.exit("refusing: the key file is neither WARDEN's feedback wallet nor the operator")
    CLIENT = acct.address
    scan = {**scan, "rows": [r for r in scan["rows"] if str(r.get("owner") or "").lower() not in OUR_OWNERS]}
    actions, held, unreachable = decide(scan, tools_by_id, scanned_at, excluded)
    print(f"actions: {[(a, r['agent_id']) for a, r, _ in actions] or 'none'}")
    print(f"held for the owner (blocking findings): {[(r['agent_id'], r['title']) for r in held]}")
    print(f"unreachable this run (left as they are): {[r['agent_id'] for r in unreachable]}")
    if len(actions) > MAX_TX_PER_RUN:
        sys.exit(f"refusing: {len(actions)} transactions in one run (cap {MAX_TX_PER_RUN}); look first")
    if not actions:
        return
    if os.path.exists(PENDING):
        sys.exit(f"refusing: an unsettled send in {PENDING}; check its receipt first")
    balance = int(rpc("eth_getBalance", [acct.address, "latest"]), 16)
    if balance < len(actions) * 5_000_000_000_000:  # 0.000005 ETH a transaction, generous for Base
        sys.exit(f"refusing: {balance / 1e18:.9f} ETH is too little for {len(actions)} transactions")
    for kind, r, extra in actions:
        aid = int(r["agent_id"])
        if kind == "give":
            raw = open(extra, "rb").read()
            uri = f"{BASE_URL}/{os.path.basename(extra)}"
            if not served_matches(uri, raw):
                sys.exit(f"refusing: {uri} is not served byte-for-byte yet (upload feedback/ first)")
            if not endpoint_ok(r["url"]):
                print(f"  skipped {aid}: endpoint is not a short plain https URL")
                continue
            data = calldata(aid, int(r["score"]), r["url"], uri, keccak(raw))
        else:
            idx = last_index(aid)
            if idx == 0:
                continue
            data = "0x" + (REVOKE_SELECTOR + encode(["uint256", "uint64"], [aid, idx])).hex()
            uri = f"revoke index {idx}: {extra}"
        if not args.send:
            print(f"  would {kind} {aid} {r['title'][:30]}  {uri}")
            continue
        tx_hash, receipt = send_one(acct, data)
        status = "ok" if receipt["status"] == "0x1" else "reverted"
        with open(LOG, "a") as f:
            f.write(json.dumps({"agentId": aid, "name": r["title"], "kind": kind, "client": CLIENT,
                                "tx": tx_hash, "status": status,
                                "block": int(receipt["blockNumber"], 16), "uri": uri}) + "\n")
        print(f"  {kind} {aid}: {status} {tx_hash}", flush=True)
        if status != "ok":
            sys.exit("stopping at the first revert")
    if not args.send:
        print("dry run — nothing sent")


if __name__ == "__main__":
    main()
