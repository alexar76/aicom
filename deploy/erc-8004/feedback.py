"""Publish WARDEN's scan of other ERC-8004 agents' MCP endpoints as ReputationRegistry feedback.

    aimarket-hub/.venv/bin/python deploy/erc-8004/feedback.py --scan SCAN.json --tools TOOLS.jsonl \\
        --key-file ~/.aicom-base-deployer-v4.json                 # writes reports + dry run
    … --send                                                       # sends

What it says, and only that: at `scannedAt`, the MCP endpoint an agent declares served these tool
definitions, and the published @aimarket/warden release named in WARDEN_VERSION found no blocking
finding in them (score, counts, ruleset digest, a hash of the exact definitions). The report carries
the fields EIP-8004 requires of a feedback file (agentRegistry, agentId, clientAddress, createdAt,
value, valueDecimals) at its top level. One feedback per agent, from WARDEN's
wallet (the operator, owner of agent 96684); the contract refuses feedback on our own agents.

Agents with a blocking finding are NOT published: WARDEN has false positives, and a public
negative mark on someone else's agent is the owner's call, made per agent.

On chain the feedback is tagged `compliance` / `warden-scan` (TAG1 / TAG2 below). Until 2026-11-26
it was `warden-scan` / `ruleset-v<N>`. ERC-8004 leaves tag1 free-form, and indexers that compute a
score average only the tag1 values they know hold a 0-100 rating (QuickNode's explorer, reputation
formula v1.4, lists `compliance` among them and showed `warden-scan` as "not in score"). The value
did not change: WARDEN's 0-100 score of the served tool definitions against its ruleset, which is
what "compliance" says. The ruleset stays in the report file the on-chain hash commits to. A live
feedback under the old tags is re-issued (revoke + give) by decide(), within the run's budget.

A feedback stays on chain as given for as long as its statement holds. Every run re-scans every
agent with the release named in WARDEN_VERSION; where the endpoint serves the same definitions and
the score is the same, nothing is sent and the agent is listed in confirmed.json next to the reports
(what was re-checked, when, with which release). A feedback is revoked and given again only when the
definitions changed, the score changed, or the report format or tags did. Until 2026-11-26 a new
release re-issued every live feedback. Each revoke leaves a revoked row on the rated agent, and
indexers count those against it (QuickNode's explorer: reliability = 1 - revoked / total), so our
housekeeping was lowering other agents' scores.

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
#: The published release every scan must come from. Moving to a new release re-scans every agent
#: and re-issues only the feedback whose score it changes: see decide().
WARDEN_VERSION = "0.39.2"
RULESET_VERSION = "24"
WARDEN_INTEGRITY = "sha512-lnCGPlssvJVYCxVRx+FRiCyQL4E4I/u4wdLhHJt/g6sIQexgho19a5327GMpsEvV+AUucXyin0S+bzk1tURCpA=="
REPORT_TYPE = "aimarket.warden-scan/v2"
#: tag1 is the dimension the 0-100 value is a rating on; tag2 says whose rating it is.
TAG1 = "compliance"
TAG2 = "warden-scan"
SELECTOR = keccak(text="giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)")[:4]


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def report_for(row: dict, tools: list, scan: dict, scanned_at: str) -> dict:
    return {
        # What EIP-8004 requires of a feedback file, with the optional fields that match the
        # on-chain call; the scan itself follows.
        "agentRegistry": f"eip155:{CHAIN_ID}:{IDENTITY}",
        "agentId": int(row["agent_id"]),
        "clientAddress": f"eip155:{CHAIN_ID}:{CLIENT}",
        "createdAt": scanned_at,
        "value": int(row["score"]),
        "valueDecimals": 0,
        "tag1": TAG1,
        "tag2": TAG2,
        "endpoint": row["url"],
        "type": REPORT_TYPE,
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
                  [agent_id, value, 0, TAG1, TAG2, endpoint, uri, digest])
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


def take_tx_budget(actions: list, limit: int) -> tuple[list, int]:
    """Keep at most `limit` transactions, never splitting a revoke+give for the same agent.

    A hard refuse on oversized plans left the weekly timer failed and last-run.json stale
    (admin-vps 2026-11-23: 52 actions vs cap 20). Defer the rest to the next run instead.
    """
    if len(actions) <= limit:
        return actions, 0
    kept: list = []
    i = 0
    while i < len(actions) and len(kept) < limit:
        kind, row, _extra = actions[i]
        paired = (
            kind == "revoke"
            and i + 1 < len(actions)
            and actions[i + 1][0] == "give"
            and str(actions[i + 1][1].get("agent_id")) == str(row.get("agent_id"))
        )
        need = 2 if paired else 1
        if len(kept) + need > limit:
            break
        kept.extend(actions[i:i + need])
        i += need
    return kept, len(actions) - len(kept)


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
    CONFIRMED.clear()
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
            same_tools = old["result"]["toolsSha256"] == rep["result"]["toolsSha256"]
            same_type = old.get("type") == rep["type"]
            # A v2 report states its on-chain tags and value; one given under other tags, or whose
            # score this release changes, is re-issued so the live record says what the file says.
            same_tags = (old.get("tag1"), old.get("tag2")) == (TAG1, TAG2)
            same_value = old.get("value") == rep["value"]
            if same_tools and same_type and same_tags and same_value:
                # Same definitions, same score: the statement on chain still holds, whichever
                # release made it. Nothing is sent; the re-check is recorded off chain.
                CONFIRMED.append({"agentId": int(aid), "report": prev["uri"], "value": rep["value"],
                                  "toolsSha256": rep["result"]["toolsSha256"]})
                continue
            if not same_tools:
                reason = "tool definitions changed"
            elif not same_type:
                reason = f"rescanned with @aimarket/warden {WARDEN_VERSION} (ruleset v{RULESET_VERSION})"
            elif not same_tags:
                reason = f"moved to the tags {TAG1} / {TAG2}"
            else:
                reason = (f"score changed from {old.get('value')} to {rep['value']} under "
                          f"@aimarket/warden {WARDEN_VERSION}")
            actions.append(("revoke", r, reason))
            name = f"warden-{aid}-{stamp}.json"
        else:
            name = f"warden-{aid}.json" if not os.path.exists(os.path.join(OUT, f"warden-{aid}.json")) \
                else f"warden-{aid}-{stamp}.json"
        path = free_report_path(name, rep)
        if not os.path.exists(path):
            open(path, "wb").write(json.dumps(rep, indent=1, ensure_ascii=False).encode() + b"\n")
        actions.append(("give", r, path))
    return actions, held, unreachable


#: Live feedback the last decide() left in place: re-checked, statement unchanged, nothing sent.
CONFIRMED: list = []
CONFIRMED_TYPE = "aimarket.warden-scan-confirmations/v1"


def write_confirmed(scan: dict, scanned_at: str) -> str:
    """Publish what this run re-checked without a transaction, next to the reports it refers to."""
    path = os.path.join(OUT, "confirmed.json")
    doc = {
        "type": CONFIRMED_TYPE,
        "checkedAt": scanned_at,
        "scanner": {"package": f"@aimarket/warden@{scan['warden']}", "ruleset": scan["ruleset"]},
        "meaning": ("Each entry is a feedback WARDEN gave earlier and left unchanged on chain: at checkedAt "
                    "the agent's MCP endpoint served the same tool definitions (toolsSha256) and this release "
                    "gave the same score with no blocking finding. The report holds the original statement."),
        "confirmed": sorted(CONFIRMED, key=lambda e: e["agentId"]),
    }
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(json.dumps(doc, indent=1, ensure_ascii=False).encode() + b"\n")
    os.replace(tmp, path)
    return path


def _says_the_same(a: dict, b: dict) -> bool:
    """Two reports make the same on-chain statement (a retry may reuse the file already served)."""
    key = lambda d: (d.get("tag1"), d.get("tag2"), d.get("value"), d.get("type"),  # noqa: E731
                     d.get("scanner", {}).get("package"), d.get("result", {}).get("toolsSha256"))
    return key(a) == key(b)


def free_report_path(name: str, rep: dict) -> str:
    """Where this report goes. A served report is never rewritten: the hash on chain commits to its
    bytes. A second, different report for the same agent on the same day takes the next free name."""
    stem, n = name[:-len(".json")], 1
    while True:
        path = os.path.join(OUT, name if n == 1 else f"{stem}-{n}.json")
        if not os.path.exists(path):
            return path
        try:
            if _says_the_same(json.load(open(path)), rep):
                return path
        except ValueError:
            pass
        n += 1


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
    ap.add_argument("--max-tx", type=int, default=MAX_TX_PER_RUN,
                    help=f"transaction budget for this run (default {MAX_TX_PER_RUN}); extras defer to the "
                         "next run. Raise only after reading the dry run, e.g. once when a change of "
                         "tags or report format re-issues every feedback")
    ap.add_argument("--revoke-all", action="store_true",
                    help="revoke every live feedback this key's wallet gave (moving to another wallet)")
    args = ap.parse_args()
    if args.revoke_all:
        return revoke_all(args)
    if not (args.scan and args.tools):
        sys.exit("--scan and --tools are required")

    scan = json.load(open(args.scan))
    if scan["warden"] != WARDEN_VERSION or scan["ruleset"]["version"] != RULESET_VERSION:
        sys.exit(f"refusing: the scan must come from the published @aimarket/warden {WARDEN_VERSION} "
                 f"(ruleset v{RULESET_VERSION})")
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
    write_confirmed(scan, scanned_at)
    print(f"confirmed without a transaction: {len(CONFIRMED)}")
    deferred = 0
    actions, deferred = take_tx_budget(actions, args.max_tx)
    print(f"actions: {[(a, r['agent_id']) for a, r, _ in actions] or 'none'}")
    if deferred:
        print(f"deferred to next run (cap {args.max_tx}): {deferred} transactions")
    print(f"held for the owner (blocking findings): {[(r['agent_id'], r['title']) for r in held]}")
    print(f"unreachable this run (left as they are): {[r['agent_id'] for r in unreachable]}")
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
