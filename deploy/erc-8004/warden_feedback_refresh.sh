#!/bin/bash
# Weekly refresh of WARDEN's ERC-8004 feedback, on admin-vps (deploy/erc-8004/feedback.py decides).
#
#   /opt/warden-feedback/warden_feedback_refresh.sh           # full run (systemd: warden-feedback.timer)
#   DRY=1 /opt/warden-feedback/warden_feedback_refresh.sh     # everything but the transactions
#
# Signs with WARDEN's feedback-only wallet (/etc/warden-feedback/wallet.json, created on this host,
# never copied off it). Steps: 8004scan's active, endpoint-verified Base agents with MCP →
# initialize + tools/list on each → the published @aimarket/warden 0.8.2 → reports written where
# nginx serves them → feedback.py. A short public summary goes to last-run.json, which the alerter
# on not-my-vps turns into a Telegram message (the bot token stays there).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export WARDEN_FB_STATE=${WARDEN_FB_STATE:-/var/lib/warden-feedback}
export WARDEN_FB_REPORTS=${WARDEN_FB_REPORTS:-/var/www/warden-feedback}
export WARDEN_FB_BASE_URL=${WARDEN_FB_BASE_URL:-https://histor.modelmarket.dev/.well-known/erc-8004/feedback}
KEY_FILE=${KEY_FILE:-/etc/warden-feedback/wallet.json}
RUN="$WARDEN_FB_STATE/runs/$(date -u +%Y%m%dT%H%M%SZ)"
WARDEN_PKG="$HERE/node/node_modules/@aimarket/warden/dist/index.js"
PY_VENV="$HERE/.venv/bin/python"
mkdir -p "$RUN" "$WARDEN_FB_REPORTS"
[ -f "$WARDEN_PKG" ] || { echo "install first (deploy/erc-8004/install_refresh.sh)" >&2; exit 1; }

curl -fsS -m 30 "https://api.8004scan.io/api/v1/agents?chain_id=8453&has_mcp=true&is_active=true&is_endpoint_verified=true&limit=100" -o "$RUN/verified.json"
python3 - "$RUN" <<'PY'
import json, subprocess, sys, time
run = sys.argv[1]
items = json.load(open(f"{run}/verified.json"))["items"]
OURS = ("0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a", "0x564be09d06117a106ecc006a19b67768cbd91666")
out = []
for a in items:
    if a.get("owner_address", "").lower() in OURS:
        continue  # our own agents: the contract forbids it, and it would be self-review
    det = {}
    for wait in (0, 3, 8, 20):  # 8004scan rate-limits a burst; an agent it never answers for is left alone
        time.sleep(wait)
        raw = subprocess.run(["curl", "-fsS", "-m", "20", f"https://api.8004scan.io/api/v1/agents/8453/{a['token_id']}"],
                             capture_output=True, text=True).stdout
        if raw:
            det = json.loads(raw)
            break
    time.sleep(1)
    mcp = det.get("mcp_server")
    if isinstance(mcp, dict):
        mcp = mcp.get("endpoint") or mcp.get("url")
    out.append({"agent_id": a["token_id"], "name": a["name"], "mcp": mcp or ""})
json.dump(out, open(f"{run}/targets.json", "w"), indent=1)
PY
(cd "$HERE" && python3 - "$RUN" <<'PY'
import json, sys
sys.path.insert(0, ".")
from mcpclient import list_tools
run = sys.argv[1]
with open(f"{run}/tools_raw.jsonl", "w") as f:
    for t in json.load(open(f"{run}/targets.json")):
        status, tools, info = list_tools(t["mcp"], timeout=20) if t["mcp"] else ("no-endpoint", None, None)
        f.write(json.dumps({"name": f"erc8004:base:{t['agent_id']}", "agent_id": t["agent_id"], "title": t["name"],
                            "url": t["mcp"], "status": status, "tools": tools or [], "server_info": info or {}}) + "\n")
PY
)
node "$HERE/warden_scan.mjs" "$RUN/tools_raw.jsonl" "$RUN/scan_results.json" "$WARDEN_PKG" > "$RUN/scan.txt"
ARGS=(--scan "$RUN/scan_results.json" --tools "$RUN/tools_raw.jsonl" --key-file "$KEY_FILE")
"$PY_VENV" "$HERE/feedback.py" "${ARGS[@]}" > "$RUN/plan.txt" 2>&1 || { cat "$RUN/plan.txt"; exit 1; }
chmod 644 "$WARDEN_FB_REPORTS"/*.json 2>/dev/null || true
if [ "${DRY:-0}" = "1" ]; then cat "$RUN/plan.txt"; exit 0; fi
status=ok
"$PY_VENV" "$HERE/feedback.py" "${ARGS[@]}" --send > "$RUN/send.txt" 2>&1 || status=failed
cat "$RUN/plan.txt" "$RUN/send.txt"
python3 - "$RUN" "$status" "$WARDEN_FB_REPORTS/last-run.json" <<'PY'
import json, re, sys, time, urllib.request
run, status, out = sys.argv[1:4]
WALLET = "0x564bE09d06117A106ECC006a19b67768cBd91666"
try:
    req = urllib.request.Request("https://mainnet.base.org", headers={"content-type": "application/json", "user-agent": "warden-feedback"},
                                 data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [WALLET, "latest"]}).encode())
    balance = int(json.load(urllib.request.urlopen(req, timeout=20))["result"], 16) / 1e18
except Exception:
    balance = None


def live_total():
    """How many agents carry a live feedback from this wallet: the newest log entry per agent."""
    import os
    newest = {}
    path = os.path.join(os.environ.get("WARDEN_FB_STATE", "/var/lib/warden-feedback"), "feedback.log")
    try:
        for line in open(path):
            if line.strip():
                e = json.loads(line)
                if str(e.get("client", "")).lower() == WALLET.lower() and e.get("status") == "ok":
                    newest[e["agentId"]] = e.get("kind", "give")
    except OSError:
        return None
    return sum(1 for kind in newest.values() if kind == "give")
plan = open(f"{run}/plan.txt").read(); send = open(f"{run}/send.txt").read()
held = re.findall(r"\('(\d+)', '([^']*)'\)", plan.split("held for the owner")[1].split("\n")[0]) if "held for the owner" in plan else []
json.dump({"ranAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "status": status,
           "given": len(re.findall(r"^  give \d+: ok", send, re.M)), "revoked": len(re.findall(r"^  revoke \d+: ok", send, re.M)),
           "held": [{"agentId": int(a), "name": n} for a, n in held],
           "error": None if status == "ok" else send.strip().splitlines()[-1][:300],
           "wallet": WALLET, "balanceEth": balance, "liveFeedback": live_total()}, open(out, "w"), indent=1)
PY
chmod 644 "$WARDEN_FB_REPORTS/last-run.json"
[ "$status" = ok ]
