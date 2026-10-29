#!/usr/bin/env python3
"""Verify a candidate as its configured non-root user without starting HISTOR."""

import argparse
import json
import re
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image) or not re.fullmatch(r"[0-9a-f]{40}", args.source):
        parser.error("immutable image and 40-hex source required")
    node = r"""
const {readFileSync,readdirSync,statSync}=require('node:fs');
const {createHash}=require('node:crypto');
const {spawnSync}=require('node:child_process');
const root='/app/scanner/node_modules/@aimarket/warden';
const body=readFileSync(root+'/package.json');const metadata=JSON.parse(body);
const files=readdirSync(root+'/dist').filter(n=>n.endsWith('.js')).sort();
if(!files.length || files.some(n=>n.startsWith('._')))throw Error('Invalid file list');
const h=createHash('sha256');for(const name of files)h.update(name+'\0').update(readFileSync(root+'/dist/'+name)).update('\0');
function run(args,input){const r=spawnSync(process.execPath,args,{input,encoding:'utf8',timeout:30000,maxBuffer:1024*1024});if(r.status!==0)throw Error('Metadata subprocess failed');return r.stdout;}
const described=JSON.parse(run(['/app/scanner/scan.mjs','describe']));
const requests=[
 {jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'candidate-acceptance',version:'1'}}},
 {jsonrpc:'2.0',id:2,method:'tools/list',params:{}}
];
const wire=run([root+'/dist/mcp-server.js'],requests.map(r=>JSON.stringify(r)+'\n').join(''));
const replies=new Map(wire.trim().split('\n').map(line=>{const r=JSON.parse(line);if(r.error)throw Error('MCP discovery failed');return[r.id,r.result]}));
if(replies.size!==2 || !replies.has(1) || !replies.has(2))throw Error('Incomplete discovery');
console.log(JSON.stringify({
 runtimeUid:process.getuid(),runtimeGid:process.getgid(),
 package:{name:metadata.name,version:metadata.version,sha256:createHash('sha256').update(body).digest('hex'),mode:(statSync(root+'/package.json').mode&0o7777).toString(8).padStart(4,'0')},
 javascript:{files:files.length,buildDigest:h.digest('hex')},
 scannerDescribe:{warden:described.warden,patternSetPackage:described.patternSet.package,recordSetPackage:described.recordSet.package},
 mcpDiscovery:{serverInfo:replies.get(1).serverInfo,protocolVersion:replies.get(1).protocolVersion,toolNames:replies.get(2).tools.map(t=>t.name).sort(),toolCalls:0}
}));
"""
    docker = ["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint"]
    probe = subprocess.run([*docker, "node", args.image, "-e", node], capture_output=True, text=True, timeout=120, check=False)
    if probe.returncode or len(probe.stdout.encode()) > 128 * 1024:
        raise RuntimeError("unprivileged candidate runtime observation failed")
    runtime = json.loads(probe.stdout)
    python = r"""
import hashlib,json
from pathlib import Path
import histor
root=Path(histor.__file__).resolve().parent;files=sorted(root.rglob('*.py'),key=lambda p:p.relative_to(root).as_posix());h=hashlib.sha256()
for path in files:h.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
print(json.dumps({'version':histor.__version__,'pythonFiles':len(files),'sourceSha256':h.hexdigest()}))
"""
    application = subprocess.run([
        *docker, "/opt/venv/bin/python", args.image, "-B", "-c", python,
    ], capture_output=True, text=True, timeout=90, check=False)
    if application.returncode or len(application.stdout.encode()) > 128 * 1024:
        raise RuntimeError("candidate application fingerprint observation failed")
    application = json.loads(application.stdout)
    source = subprocess.run([
        "docker", "image", "inspect", "--format", '{{index .Config.Labels "skopos.source.commit"}}', args.image,
    ], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    checks = {
        "exactSourceCommit": source == args.source,
        "unprivilegedUser": runtime["runtimeUid"] == 65532,
        "packageVersion": runtime["package"]["version"] == "0.22.2",
        "packageMode": runtime["package"]["mode"] == "0644",
        "packageBytes": runtime["package"]["sha256"] == "0411601d6ec47d8d14f608a6643a94589e094940dcd93dde36bdcda52a57a34b",
        "javascriptBytes": runtime["javascript"] == {
            "files": 63, "buildDigest": "3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de",
        },
        "scannerRuntimeMetadata": runtime["scannerDescribe"]["warden"] == {
            "package": "@aimarket/warden@0.22.2", "version": "0.22.2",
        } and runtime["scannerDescribe"]["patternSetPackage"] == "@aimarket/warden@0.22.2"
          and runtime["scannerDescribe"]["recordSetPackage"] == "@aimarket/warden@0.22.2",
        "mcpRuntimeMetadata": runtime["mcpDiscovery"]["serverInfo"]["version"] == "0.22.2"
          and runtime["mcpDiscovery"]["serverInfo"]["name"] == "warden"
          and len(runtime["mcpDiscovery"]["toolNames"]) == 9 and runtime["mcpDiscovery"]["toolCalls"] == 0,
        "historSourcePreserved": application == {
            "version": "0.4.2", "pythonFiles": 43,
            "sourceSha256": "a24be58d10784e10a1e0bade153d9bd6ac1ccdd5335c063a47b5cb14b0111e41",
        },
    }
    result = {
        "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "network-none/read-only/default-user candidate metadata and discovery; no service start or tool calls",
        "passed": all(checks.values()), "imageDigest": args.image, "sourceCommit": source,
        "checks": checks, "runtime": runtime, "historApplication": application,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("Candidate runtime verification failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
