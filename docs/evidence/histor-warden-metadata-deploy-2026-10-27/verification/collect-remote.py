#!/usr/bin/env python3
"""Read only whitelisted HISTOR/container metadata on the enrolled deployment host.

Intended invocation: ssh admin-vps python3 - < collect-remote.py
No container is started/recreated, no tool is called, and no key/config/env is read.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

CONTAINER = "histor-histor-1"
BASE = "sha256:befe7e54d444d0d9b2658151725b264fc6bb61dbbdb0927caff60f281ba249d6"
PACKAGE = "/app/scanner/node_modules/@aimarket/warden"
MAX_BYTES = 1024 * 1024


def command(args, *, stdin=None, timeout=30):
    result = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode or len(result.stdout.encode()) > MAX_BYTES:
        raise RuntimeError("bounded observation command failed")
    return result.stdout.strip()


def inspect(template, target=CONTAINER, *, image=False):
    prefix = ["docker", "image", "inspect"] if image else ["docker", "inspect"]
    return command([*prefix, "--format", template, target])


def read_json(path):
    body = Path(path).read_bytes()
    if len(body) > MAX_BYTES:
        raise ValueError("oversized binding")
    return json.loads(body)


def loopback(path):
    with urlopen("http://127.0.0.1:9490" + path, timeout=15) as response:
        body = response.read(MAX_BYTES + 1)
        status = response.status
    if len(body) > MAX_BYTES:
        raise ValueError("oversized loopback response")
    return status, json.loads(body)


def main():
    image = inspect("{{.Image}}")
    started = inspect("{{.State.StartedAt}}")
    source = inspect('{{ index .Config.Labels "skopos.source.commit" }}', image, image=True)
    layers = json.loads(inspect("{{json .RootFS.Layers}}", image, image=True))
    base_layers = json.loads(inspect("{{json .RootFS.Layers}}", BASE, image=True))
    node = r"""
const {readFileSync,readdirSync,statSync}=require('node:fs');
const {createHash}=require('node:crypto');
const p='/app/scanner/node_modules/@aimarket/warden';
const bytes=readFileSync(p+'/package.json'); const metadata=JSON.parse(bytes);
const files=readdirSync(p+'/dist').filter(n=>n.endsWith('.js')).sort();
if(!files.length || files.some(n=>n.startsWith('._'))) throw Error('Invalid JavaScript file list');
const h=createHash('sha256');
for(const name of files) h.update(name+'\0').update(readFileSync(p+'/dist/'+name)).update('\0');
console.log(JSON.stringify({name:metadata.name,version:metadata.version,
  packageJsonMode:(statSync(p+'/package.json').mode&0o7777).toString(8).padStart(4,'0'),runtimeUid:process.getuid(),
  packageJsonSha256:createHash('sha256').update(bytes).digest('hex'),
  buildDigest:h.digest('hex'),javascriptFiles:files.length}));
"""
    package = json.loads(command(["docker", "exec", CONTAINER, "node", "-e", node]))
    python = r"""
import hashlib,json
from pathlib import Path
import histor
root=Path(histor.__file__).resolve().parent
files=sorted(root.rglob('*.py'),key=lambda p:p.relative_to(root).as_posix())
h=hashlib.sha256()
for path in files:
    h.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
print(json.dumps({'version':histor.__version__,'pythonFiles':len(files),'sourceSha256':h.hexdigest()}))
"""
    application = json.loads(command(["docker", "exec", CONTAINER, "python", "-B", "-c", python]))
    describe = json.loads(command(["docker", "exec", CONTAINER, "node", "/app/scanner/scan.mjs", "describe"]))
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "histor-deployment-acceptance", "version": "1"},
        }},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    wire = command(
        ["docker", "exec", "-i", CONTAINER, "node", PACKAGE + "/dist/mcp-server.js"],
        stdin="".join(json.dumps(row) + "\n" for row in requests),
    )
    responses = {row["id"]: row for row in map(json.loads, wire.splitlines())}
    if any(row.get("error") for row in responses.values()) or set(responses) != {1, 2}:
        raise ValueError("MCP discovery failed")
    health_status, health = loopback("/health")
    issuer_status, issuer = loopback("/api/v1/issuer")
    binding = read_json("/var/lib/momus-quality/live-image.json")
    pointer = read_json("/var/lib/skopos-deploy-hand/warden/source/source.json")
    result = {
        "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "read-only metadata, immutable image identities, public HTTP and MCP discovery; no tool calls",
        "container": {
            "name": CONTAINER, "imageDigest": image, "sourceCommit": source,
            "running": inspect("{{.State.Running}}") == "true",
            "health": inspect("{{.State.Health.Status}}"),
            "startedAt": started,
        },
        "pinnedApplicationBase": {
            "imageDigest": BASE, "baseLayerCount": len(base_layers), "imageLayerCount": len(layers),
            "baseLayersPreserved": layers[:len(base_layers)] == base_layers,
        },
        "installedPackage": package,
        "historApplication": application,
        "scannerDescribe": {
            "warden": describe["warden"],
            "patternSet": {key: describe["patternSet"].get(key) for key in ("package", "version", "digest", "ruleCount")},
            "recordSet": {"package": describe["recordSet"]["package"], "records": len(describe["recordSet"]["records"])},
        },
        "mcpDiscovery": {
            "serverInfo": responses[1]["result"]["serverInfo"],
            "protocolVersion": responses[1]["result"]["protocolVersion"],
            "toolNames": sorted(row["name"] for row in responses[2]["result"]["tools"]),
            "toolCalls": 0,
        },
        "loopback": {
            "health": {"httpStatus": health_status,
                       "historicalInterruptedRunMarker": str(health.get("last_crawl_error") or "").startswith("interrupted"),
                       **{key: health.get(key) for key in (
                "ok", "service", "version", "profile", "store", "tree_size", "crawl_running")}},
            "issuer": {"httpStatus": issuer_status, **{key: issuer.get(key) for key in ("warden", "patternSet", "recordSet")}},
        },
        "qualityBinding": {key: binding.get(key) for key in ("imageDigest", "buildDigest")},
        "acceptedSource": {key: pointer.get(key) for key in ("imageDigest", "commit")},
    }
    if inspect("{{.Image}}") != image or inspect("{{.State.StartedAt}}") != started:
        raise RuntimeError("container changed during observation")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Read-only observation failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
