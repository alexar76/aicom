"""HISTOR's MTL/1 tool-set digest against CrawlCheck's jcs_v1.tools_sha256 (2026-11-07).

    PYTHONPATH=histor:awr/reference/python histor/.venv/bin/python artifacts/crawlcheck-xcheck-2026-11-07/xcheck.py

1. CrawlCheck's two published test vectors (spec text sha256 3cac4a345a85a5e0…, https://crawlcheck.io/spec/mcp-lockfile).
2. Tool sets HISTOR recorded, fetched by digest from https://histor.modelmarket.dev/api/v1/toolsets/<sri> and posted to
   CrawlCheck's POST /api/v1/mcp/lock {tools}, which hashes a list it is given and contacts no server.
"""
import json
import sys
import urllib.parse
import urllib.request

from histor.subject import tool_set_digest

UA = {"User-Agent": "aicom-histor-xcheck (+https://histor.modelmarket.dev/)"}
VECTORS = [
    ("empty list", [], "sha256-T1PNoYwrqgwDVLtfmj7L5e0Sq02OEbqHPC8RFhICuUU="),
    ("read_file", [{"name": "read_file", "title": "Read file", "description": "Read a file from disk.",
                    "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                    "annotations": {"readOnlyHint": True}}],
     "sha256-pUO5TdOtj4yR/mh2VDcu4y6axwVix4xgwST6cFkdd3g="),
]
SETS = [  # HISTOR tool-set digests chosen 2026-11-07 from /api/v1/servers?state=changed (3 to 28 tools)
    "sha256-0QjeQokTt8cWjkULrBONvt/1oWELrTOmdfknXnu+iIY=",
    "sha256-4Dgtm5VWGvwX+xh/CEtM3O3Cz/9e9xkeoFJy+GgCh5Y=",
    "sha256-icryqhRKfWbsxC/wDTNFFQ5QOyGEpC4nQevtGx4rcgE=",
    "sha256-mulEzZ11rVHokorM45fN08jSz2v2zDK+2Dhaq73fTHU=",
    "sha256-S1eStCM4zQLHtIs2qMSTpTPdvDY98S47TRyqkVhetIs=",
    "sha256-NERw6T0Gaex16sTb3BLxaA8Xn8mVboJY+n3G3A1DqPg=",
]


def get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read())


def crawlcheck(tools):
    req = urllib.request.Request("https://crawlcheck.io/api/v1/mcp/lock", data=json.dumps({"tools": tools}).encode(),
                                 method="POST", headers={**UA, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())["jcs_v1"]["tools_sha256"]


ok = True
for name, tools, want in VECTORS:
    got, _ = tool_set_digest(tools)
    ok &= got == want
    print(f"vector {name}: HISTOR {got} CrawlCheck {want} equal={got == want}")
for sri in SETS:
    tools = get("https://histor.modelmarket.dev/api/v1/toolsets/" + urllib.parse.quote(sri, safe=""))
    mine, _ = tool_set_digest(tools)
    theirs = crawlcheck(tools)
    ok &= mine == theirs == sri
    print(f"set {sri} ({len(tools)} tools): HISTOR {mine} CrawlCheck {theirs} equal={mine == theirs == sri}")
sys.exit(0 if ok else 1)
