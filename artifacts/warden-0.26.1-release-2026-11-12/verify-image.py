"""Verify that a MOMUS overlay changes only the two WARDEN directories."""
import hashlib
import json
import subprocess
import sys
import tarfile

WARDEN_DIRS = (
    'app/scanner/node_modules/@aimarket/warden',
    'opt/warden-source/src',
)


def outside(name):
    return all(name != p and not name.startswith(p + '/') for p in WARDEN_DIRS)


def snapshot(image):
    cid = subprocess.check_output(['docker', 'create', '--network', 'none', image], text=True).strip()
    result = {}
    try:
        with subprocess.Popen(['docker', 'export', cid], stdout=subprocess.PIPE) as proc:
            with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
                for member in archive:
                    if not outside(member.name):
                        continue
                    body = hashlib.file_digest(archive.extractfile(member), 'sha256').hexdigest() if member.isfile() else None
                    result[member.name] = (member.type, member.mode, member.uid, member.gid, member.linkname, body)
            if proc.wait():
                raise RuntimeError('docker export failed')
    finally:
        subprocess.run(['docker', 'rm', '-v', cid], stdout=subprocess.DEVNULL, check=True)
    return result


def config(image):
    obj = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
    return {k: v for k, v in obj['Config'].items() if k not in {'Image', 'Labels'}}


base, candidate = sys.argv[1:]
assert config(base) == config(candidate), 'Docker runtime config differs'
old, new = snapshot(base), snapshot(candidate)
diff = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
assert not diff, f'{len(diff)} paths differ outside WARDEN: {diff[:15]}'
print(f'Docker runtime config matches; {len(new)} filesystem entries outside WARDEN match.')
