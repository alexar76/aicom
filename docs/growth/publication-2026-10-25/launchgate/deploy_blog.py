"""Deploy the reviewed public static blog, verify hashes before atomic activation.

Transfers only modelmarket-blog/dist. Keeps all prior releases for rollback.
No source credentials, GitHub or npm operations.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DIST = ROOT / 'modelmarket-blog/dist'
HOST = 'factory-vps'


def main():
    files = {str(path.relative_to(DIST)): sha256(path.read_bytes()).hexdigest() for path in sorted(DIST.rglob('*')) if path.is_file()}
    assert files and all(not any(part.startswith('.') for part in Path(name).parts) for name in files)
    assert not any(name.endswith(('.env', '.py', '.sh', '.ts')) for name in files)
    release = '/var/www/modelmarket-blog-releases/' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    def ssh(command):
        return subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, command], check=True, capture_output=True, text=True).stdout.strip()
    old = ssh('readlink /var/www/modelmarket-blog')
    receipt = {'host': HOST, 'previousRelease': old, 'newRelease': release, 'publicFiles': len(files), 'bytes': sum(path.stat().st_size for path in DIST.rglob('*') if path.is_file()), 'source': 'modelmarket-blog/dist', 'githubWrites': False}
    (HERE / 'deployment-input-manifest.json').write_text(json.dumps(files, indent=2) + '\n')
    ssh('mkdir ' + shlex.quote(release) + ' && mkdir ' + shlex.quote(release + '/blog'))
    subprocess.run(['rsync', '-az', str(DIST) + '/', HOST + ':' + release + '/blog/'], check=True)
    verify = 'from pathlib import Path; import hashlib,json; root=Path(' + repr(release + '/blog') + '); manifest=json.loads(' + repr(json.dumps(files)) + '); actual={str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}; assert actual==set(manifest); assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in manifest.items()); print(len(manifest))'
    receipt['remoteFilesHashVerified'] = int(ssh('python3 -c ' + shlex.quote(verify)))
    assert receipt['remoteFilesHashVerified'] == len(files)
    ssh('ln -sfn ' + shlex.quote(release) + ' /var/www/modelmarket-blog.new && mv -T /var/www/modelmarket-blog.new /var/www/modelmarket-blog')
    receipt['activeRelease'] = ssh('readlink /var/www/modelmarket-blog')
    assert receipt['activeRelease'] == release
    receipt['activatedAt'] = datetime.now(timezone.utc).isoformat()
    receipt['priorReleasesPruned'] = False
    (HERE / 'blog-deployment.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
