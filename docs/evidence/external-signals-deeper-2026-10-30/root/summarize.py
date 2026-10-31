from pathlib import Path
import json
from datetime import datetime,timezone
p=Path("docs/evidence/external-signals-deeper-2026-10-30/root")
a=json.loads((p/"agent402-modelmarket.json").read_text())
r=json.loads((p/"agent402-route-warden.json").read_text())
peers=json.loads((p/"hub-peers.json").read_text())
compat=json.loads((p/"peer-manifest-compatibility.json").read_text())
paid=[t for t in a.get("tools",[]) if t.get("paid")]
out={
"date":"2026-10-30","timezone":"Europe/Moscow","web_queries":28,"captured_gets":17,
"agent402":{"source":"https://agent402.tools/api/index?seller=modelmarket.dev","source_fetched_at_utc":datetime.fromtimestamp(a["fetchedAt"]/1000,timezone.utc).isoformat(),"previous_reason":"settlement_self_funded","current_reason":a.get("routerDispatchReason"),"paid_routes":len(paid),"routes_with_unproven_tier":sum(bool(t.get("routerDispatchByChain",{}).get("base",{}).get("unprovenTier")) for t in paid),"routes":[{"route":t.get("route"),"price":t.get("price"),"reason":t.get("routerDispatchReason"),"base":t.get("routerDispatchByChain",{}).get("base")} for t in paid],"warden_recommendations":[{"route":x.get("route"),"seller":x.get("seller"),"executeViaCallableNow":x.get("executeViaCallableNow"),"executeViaLane":x.get("executeViaLane"),"executeVia":x.get("executeVia")} for x in r.get("results",[]) if x.get("seller")=="https://modelmarket.dev"],"limits":"Public router eligibility declaration and free recommendation, not an executed call, new customer, payment or independently reproduced netting algorithm."},
"external_protocol":{"validation":"peer-manifest-compatibility.json","results":compat["records"],"agentexec_peer":[{k:x.get(k) for k in ["url","trusted","status","capabilities_count","public_key","last_crawl"]} for x in peers.get("peers",[]) if x.get("url")=="https://agent-exec.448c.org"],"limits":"agent-exec active/trusted was already recorded in29Oct evidence. New check is snapshot signature compatibility, not a newly deployed implementation or successful tool execution. Hub still reports0capabilities. Machina remains pending with incompatible signature."},
"usetested":{"source":"https://usetested.com/v1/review?service=modelmarket.dev","calls_tested":1,"receipt_date":"2026-10-27","delta":"unchanged","limits":"Historical paid test previously captured29Oct; not new demand."},
"hub_stats":{"source":"https://modelmarket.dev/ai-market/v2/stats/live","limits":"Operator telemetry, not independent evidence. External label with traffic_basis=null is a fallback; do not count pseudonymous sandbox rows as verified new people."},
"limitations":["Exact domains for Emberline use emberlinedesk.com; no new attributed match in queried pages","No invoke, payment, admission, messages or foreign-code execution","No new independent runtime user confirmed"]
}
(p/"summary.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"agent402":out["agent402"]["current_reason"],"unproven":out["agent402"]["routes_with_unproven_tier"],"warden":out["agent402"]["warden_recommendations"],"agentexec_valid":compat["records"][1]["ed25519_valid_for_hub_manifest_canonical"]},ensure_ascii=False,indent=2))

