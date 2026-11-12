"""Additional public GETs selected after reviewing the first snapshot."""
import concurrent.futures
import json
from collect_public import ROOT, fetch

TARGETS = {
    "agentexec-manifest": "https://agent-exec.448c.org/ai-market/manifest",
    "machina-discovery": "https://mach402.dev/.well-known/ai-market.json",
    "apis-attested": "https://apis.io/providers/attestedmemory-net/",
    "apis-attested-source": "https://artifacts.apis.io/attestedmemory-net/apis.yml",
    "vibeleaderboard-histor": "https://www.vibeleaderboard.ai/app/d8a7cafb-d59e-470a-9207-e89df4720091",
    "aer-data": "https://agenteconomy.report/s/data/",
    "aer-actions": "https://agenteconomy.report/s/actions",
    "industrial-discovery": "https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json",
}

if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "http-followup-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
