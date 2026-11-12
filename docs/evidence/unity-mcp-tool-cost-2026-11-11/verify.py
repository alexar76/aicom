"""Recount the archived Unity MCP list and exercise the HISTOR CI gate offline."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from histor.subject import tool_set_digest

from histor import __version__

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "unity-10.3.0-tools.json"


def require(condition: bool, error: str) -> None:
    if not condition:
        raise SystemExit(error)


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "histor", "tool-cost", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def main() -> None:
    evidence = json.loads((HERE / "observation.json").read_bytes())
    versions = {"histor": __version__, "tiktoken": version("tiktoken"), "rfc8785": version("rfc8785")}
    require(versions == evidence["counterVersions"], f"install the pinned versions, got {versions}")
    raw = TOOLS.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == evidence["toolListFileSha256"], "archive byte hash mismatch")
    tools = json.loads(raw)
    require(len(tools) == evidence["toolCount"], "unexpected tool count")
    digest, _ = tool_set_digest(tools)
    require(digest == evidence["toolSetDigest"], "MTL/1 tool-list digest mismatch")
    observations = evidence["observations"]
    require(observations and all(row["toolSetDigest"] == digest for row in observations),
            "observations must all refer to the archived tool list")

    with TemporaryDirectory(prefix="unity-mcp-tool-cost-") as folder:
        baseline = Path(folder) / "baseline.json"
        snapshot = cli("snapshot", "--tools", str(TOOLS), "--output", str(baseline))
        require(snapshot.returncode == 0, f"snapshot failed: {snapshot.stderr}")
        counts = json.loads(baseline.read_bytes())
        require(counts["tokenizer"] == evidence["tokenizer"], "unexpected tokenizer")
        require(counts["totals"] == evidence["expectedTotals"], "archived counts changed")

        command = ("check", "--baseline", str(baseline), "--max-increase", "10%", "--noise", "50", "--json")
        # The observed runs reference the same immutable array, so one saved copy supplies both inputs.
        unchanged = cli(*command, "--tools", str(TOOLS))
        require(unchanged.returncode == 0, f"unchanged observation failed: {unchanged.stderr or unchanged.stdout}")
        require(json.loads(unchanged.stdout)["ok"], "unchanged observation returned a failing verdict")

        # Change one tool schema in memory. The 64 fields below are an artificial regression.
        physics = next(tool for tool in tools if tool["name"] == "manage_physics")
        properties = physics["inputSchema"]["properties"]
        extra_fields = {
            f"fixture_probe_field_{index}": {
                "type": "string",
                "description": "A hypothetical per-action option for the input schema budget regression example.",
            }
            for index in range(64)
        }
        require(not properties.keys() & extra_fields.keys(), "fixture overlaps recorded schema")
        properties.update(extra_fields)
        fixture = Path(folder) / "synthetic-schema-growth.json"
        fixture.write_text(json.dumps(tools, ensure_ascii=False), encoding="utf-8")

        grown = cli(*command, "--tools", str(fixture))
        require(grown.returncode == 1, f"synthetic regression should fail: {grown.stderr or grown.stdout}")
        result = json.loads(grown.stdout)
        require(result["problems"] == evidence["expectedSyntheticProblems"], "unexpected synthetic regression verdict")

    top = sorted(counts["tools"], key=lambda tool: (-tool["sent"], tool["name"]))[:5]
    print(json.dumps({
        "versions": versions,
        "tokenizer": counts["tokenizer"],
        "toolCount": counts["toolCount"],
        "observedRunCount": sum(row["count"] for row in observations),
        "toolSetDigest": digest,
        "totals": counts["totals"],
        "largestTools": [{"name": tool["name"], "tokens": tool["sent"]} for tool in top],
        "unchangedObservationExitCode": unchanged.returncode,
        "syntheticGrowthExitCode": grown.returncode,
        "syntheticGrowthProblems": result["problems"],
    }, indent=2))


if __name__ == "__main__":
    main()
