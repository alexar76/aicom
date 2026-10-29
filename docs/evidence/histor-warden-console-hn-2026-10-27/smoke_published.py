"""Smoke-check the verified npm artifact against an isolated synthetic MCP server."""

import json
import os
from pathlib import Path
import shutil
import subprocess


OUT = Path(__file__).resolve().parent
artifact = json.loads((OUT / "published-artifact.json").read_text())
package = Path(artifact["extractedTo"]) / "package"
node = shutil.which("node")
assert node
fixture = OUT / "fixture"
fixture.mkdir(exist_ok=True)
(fixture / "description.txt").write_text("Returns a saved note by its ID.\n")
(fixture / "server.mjs").write_text('''import readline from 'node:readline';
import { readFileSync, appendFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const trace = fileURLToPath(new URL('./requests.jsonl', import.meta.url));
const description = () => readFileSync(new URL('./description.txt', import.meta.url), 'utf8').trim();
for await (const line of readline.createInterface({ input: process.stdin })) {
  const req = JSON.parse(line);
  appendFileSync(trace, JSON.stringify({ method: req.method }) + '\\n');
  if (req.id === undefined) continue;
  let result;
  if (req.method === 'initialize') result = {
    protocolVersion: '2025-06-18', capabilities: { tools: {} },
    serverInfo: { name: 'console-hn-synthetic-notes', version: '1.0.0' }
  };
  else if (req.method === 'tools/list') result = { tools: [{
    name: 'get_note', description: description(),
    inputSchema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] }
  }] };
  else {
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: req.id,
      error: { code: -32601, message: 'Method not found' } }) + '\\n');
    continue;
  }
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: req.id, result }) + '\\n');
}
''')
config = fixture / ".mcp.json"
config.write_text(json.dumps({"mcpServers": {"notes": {
    "command": node, "args": [str(fixture / "server.mjs")]
}}}, indent=2) + "\n")
env = {key: os.environ[key] for key in ("PATH", "TMPDIR", "LANG", "LC_ALL") if key in os.environ}
env["WARDEN_STATE_DIR"] = str(fixture / "state")
env["NO_COLOR"] = "1"
base = [node, str(package / "dist/mcp-server.js"), "scan"]
lock = str(fixture / "warden.lock.json")
results = []


def run(name, args):
    proc = subprocess.run(base + args, cwd=fixture, env=env, capture_output=True, text=True, timeout=30)
    (OUT / (name + ".stdout.txt")).write_text(proc.stdout)
    (OUT / (name + ".stderr.txt")).write_text(proc.stderr)
    rec = {"name": name, "exitCode": proc.returncode, "args": args}
    results.append(rec)
    return proc


help_result = run("cli-help", ["--help"])
assert help_result.returncode == 0
for flag in ("--lock", "--update-lock", "--histor", "--no-launch", "--json", "--sarif", "--markdown"):
    assert flag in help_result.stdout, flag

common = [str(config), "--state-dir", str(fixture / "state"), "--json", "--fail-on-error"]
first = run("lock-create", common + ["--lock", lock, "--update-lock"])
first_report = json.loads(first.stdout)
assert first.returncode == 0, first.stderr
assert first_report["version"] == "0.22.2"
assert first_report["summary"]["scanned"] == 1
assert first_report["summary"]["errors"] == 0
assert first_report["summary"]["blocked"] == 0

same = run("lock-unchanged", common + ["--lock", lock])
assert same.returncode == 0, same.stderr

(fixture / "description.txt").write_text("Returns a saved note by its ID, including its last edit time.\n")
changed = run("lock-changed", common + ["--lock", lock])
assert changed.returncode == 1, changed.stderr
assert "TOOL_DEF_DRIFT" in changed.stdout

trace = [json.loads(line)["method"] for line in (fixture / "requests.jsonl").read_text().splitlines()]
assert "tools/list" in trace
assert "tools/call" not in trace
before_no_launch = len(trace)
no_launch = run("no-launch", common + ["--no-launch"])
assert no_launch.returncode == 0, no_launch.stderr
assert json.loads(no_launch.stdout)["summary"]["launchOnly"] == 1
assert len((fixture / "requests.jsonl").read_text().splitlines()) == before_no_launch

summary = {"status": "passed", "version": "0.22.2", "artifactIntegrityVerified": True,
           "scope": "synthetic stdio fixture only; no user configs, credentials, network calls or tools/call",
           "checks": results, "methodsObserved": sorted(set(trace))}
(OUT / "smoke-results.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
