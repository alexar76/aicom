#!/usr/bin/env python3
"""Read-only candidate metadata/permissions diagnosis; never starts HISTOR."""

import argparse
import json
import re
import subprocess
import sys
import time

DEFAULT_IMAGE = "sha256:04c6683cbf8d36201359baf9322aee49c580b6f00b63ab5f59598881bc232639"
LIVE = "histor-histor-1"
MAX_BYTES = 128 * 1024


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90, check=False)
    if len(result.stdout.encode()) > MAX_BYTES:
        raise RuntimeError("oversized candidate observation")
    if result.returncode:
        markers = [name for name in ("PermissionError", "Permission denied", "EACCES", "FileNotFoundError", "ModuleNotFoundError", "SyntaxError") if name in result.stderr]
        return {"exitCode": result.returncode, "stderrBytes": len(result.stderr.encode()), "errorMarkers": markers}
    return {"exitCode": 0, "value": json.loads(result.stdout)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        parser.error("immutable image digest required")
    image = args.image
    python = r"""
import errno,hashlib,json,os,stat
from pathlib import Path
import histor
p=Path('/app/scanner/node_modules/@aimarket/warden')
meta=p/'package.json'
out={'uid':os.getuid(),'gid':os.getgid(),'packageJson':{'mode':oct(stat.S_IMODE(meta.stat().st_mode)),'uid':meta.stat().st_uid,'gid':meta.stat().st_gid,'readable':os.access(meta,os.R_OK)}}
try:
    body=meta.read_bytes()
    package=json.loads(body)
    out['packageJson'].update(version=package.get('version'),name=package.get('name'),sha256=hashlib.sha256(body).hexdigest())
except OSError as error:
    out['packageJson'].update(errorClass=type(error).__name__,errno=errno.errorcode.get(error.errno))
h=hashlib.sha256();files=sorted((p/'dist').glob('*.js'));unreadable=[]
for path in files:
    try:
        body=path.read_bytes()
        h.update(path.name.encode()+b'\0'+body+b'\0')
    except OSError:
        unreadable.append(path.name)
out['javascript']={'files':len(files),'unreadableFiles':len(unreadable),'buildDigest':h.hexdigest() if not unreadable else None,'modes':sorted({oct(stat.S_IMODE(path.stat().st_mode)) for path in files})}
root=Path(histor.__file__).resolve().parent;files=sorted(root.rglob('*.py'),key=lambda path:path.relative_to(root).as_posix());h=hashlib.sha256()
for path in files:h.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
out['historApplication']={'version':histor.__version__,'pythonFiles':len(files),'sourceSha256':h.hexdigest()}
print(json.dumps(out))
"""
    result = {
        "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "imageDigest": image,
        "scope": "ephemeral read-only network-none metadata probes; no app start, evaluation or live writes",
    }
    for label, user in (("defaultUser", []), ("rootReadOnly", ["--user", "0"])):
        result[label] = command([
            "docker", "run", "--rm", "--network", "none", "--read-only", *user,
            "--entrypoint", "/opt/venv/bin/python", image, "-B", "-c", python,
        ])
    result["liveDefaultUser"] = command(["docker", "exec", LIVE, "python", "-B", "-c", python])
    info = subprocess.run([
        "docker", "image", "inspect", "--format",
        '{{json .Config.User}} {{json (index .Config.Labels "skopos.source.commit")}}', image,
    ], capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    result["imageConfig"] = {"user": info.split()[0].strip('"'), "sourceCommit": info.split()[1].strip('"')}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Candidate observation failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
