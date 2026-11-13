#!/usr/bin/env python3
"""Reap only abandoned work directories that the HISTOR observer normally removes."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

root = Path('/var/lib/histor-sandbox/runs')
cutoff = time.time() - 7 * 24 * 60 * 60
assert root.resolve(strict=True) == root
assert os.stat(root).st_uid == os.stat(root.parent).st_uid
assert shutil.rmtree.avoids_symlink_attacks
if sys.argv[1:] not in ([], ['--apply']):
    raise SystemExit('usage: competing-lab-sandbox-scratch.py [--apply]')

names = subprocess.check_output(['docker', 'ps', '-a', '--format', '{{.Names}}'], text=True, timeout=20)
references = set()
for name in names.splitlines():
    match = re.fullmatch(r'histor-([0-9a-f]{12})(?:-[isr])?', name)
    if match:
        references.add(match[1])


def preserve(path):
    if not isinstance(path, str):
        return
    if path.startswith(str(root) + '/'):
        references.add(path[len(str(root)) + 1:].split('/', 1)[0])
    if path.rstrip('/') in {str(root), str(root.parent)}:
        raise SystemExit('observer work root is mounted or held open')


# Read bind sources from Docker's persisted container metadata. This also finds any
# container outside the observer naming convention, without a potentially stuck inspect.
for config in Path('/var/lib/docker/containers').glob('*/config.v2.json'):
    try:
        mounts = json.loads(config.read_text()).get('MountPoints') or {}
    except FileNotFoundError:
        continue
    for mount in mounts.values():
        preserve(mount.get('Source'))
for proc in Path('/proc').glob('[0-9]*'):
    for link in (proc / 'cwd', proc / 'root', *(proc / 'fd').glob('*')):
        try:
            target = os.readlink(link)
        except (FileNotFoundError, ProcessLookupError):
            continue
        preserve(target)

candidates = []
for item in root.iterdir():
    if not re.fullmatch(r'[0-9a-f]{12}', item.name) or item.name in references:
        continue
    before = item.lstat()
    if stat.S_ISDIR(before.st_mode) and before.st_mtime < cutoff and before.st_uid == root.stat().st_uid:
        candidates.append((item, before))

# A mount below a candidate is retained even if it did not come from Docker.
def unescape(text):
    return re.sub(r'\\([0-7]{3})', lambda value: chr(int(value[1], 8)), text)

for line in Path('/proc/self/mountinfo').read_text().splitlines():
    preserve(unescape(line.split()[4]))
before = shutil.disk_usage(root).free
removed = 0
for item, original in candidates:
    if item.name in references:
        continue
    current = item.lstat()
    if (current.st_dev, current.st_ino, current.st_mtime_ns) != (original.st_dev, original.st_ino, original.st_mtime_ns):
        continue
    if sys.argv[1:]:
        shutil.rmtree(item)
        removed += 1
    else:
        print('abandoned scratch', item.name)
print(f'{len(candidates)} candidates, {removed} removed; physical free space delta {(shutil.disk_usage(root).free - before) / 2**20:.0f} MiB')
