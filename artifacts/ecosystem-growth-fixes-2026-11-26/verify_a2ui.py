"""Compare two public observations of the A2UI Catalog without invoking it."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-tool-set-digest/implementations/python"))
from tool_set_digest import digests


OBSERVATORY = "https://raw.githubusercontent.com/mikerawsonnz/mcp-drift-observatory"
SNAPSHOT = "servers/a2uicatalog.ai/57663a025cf9685e6622.json"
HISTOR = "https://histor.modelmarket.dev/api/v1"
CHANGE = f"{HISTOR}/changes/206290"


def load(url):
    request = Request(url, headers={"User-Agent": "aicom-observation-crosscheck/1.0"})
    with urlopen(request, timeout=15) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError(f"Response exceeds 1 MB at {url}")
    return json.loads(data)


def verify():
    record = load(CHANGE)
    sources = {
        "observatory_before": f"{OBSERVATORY}/d59bbcf94ba4fe25fca1be5814d7d82f02bd4298/{SNAPSHOT}",
        "observatory_after": f"{OBSERVATORY}/0c222bd4a2413f20f0ec32f93ff9affb18c61b00/{SNAPSHOT}",
        "histor_before": f"{HISTOR}/toolsets/{quote(record['from_toolset'], safe='')}",
        "histor_after": f"{HISTOR}/toolsets/{quote(record['to_toolset'], safe='')}",
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        before, after, histor_before, histor_after = pool.map(load, sources.values())

    if before["url"] != record["endpoint"] or after["url"] != record["endpoint"]:
        raise ValueError("Snapshots refer to different MCP endpoints")
    for snapshot, stored, expected in (
        (before, histor_before, record["from_toolset"]),
        (after, histor_after, record["to_toolset"]),
    ):
        observed_contract, _ = digests(json.dumps(snapshot["tools"], ensure_ascii=False))
        stored_contract, _ = digests(json.dumps(stored, ensure_ascii=False))
        if observed_contract != expected or stored_contract != expected:
            raise ValueError(f"Contract digest mismatch for the snapshot from {snapshot['observed_at']}")

    names_before = {tool["name"] for tool in before["tools"]}
    names_after = {tool["name"] for tool in after["tools"]}
    added = sorted(names_after - names_before)
    removed = sorted(names_before - names_after)
    if added != sorted(record["summary"]["added"]) or removed != sorted(record["summary"]["removed"]):
        raise ValueError("Change summaries disagree")
    print(json.dumps({
        "endpoint": record["endpoint"],
        "contract_profile": "mcp-tool-set-digest/1",
        "histor_change": CHANGE,
        "histor_observed_at": record["observed_at"],
        "observatory_before_at": before["observed_at"],
        "observatory_after_at": after["observed_at"],
        "tool_counts": [len(before["tools"]), len(after["tools"])],
        "added": added,
        "removed": removed,
        "matched_contract_digests": [record["from_toolset"], record["to_toolset"]],
        "snapshots": sources,
    }, indent=2))


if __name__ == "__main__":
    verify()
