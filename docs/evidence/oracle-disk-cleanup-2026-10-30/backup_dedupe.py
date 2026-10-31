from pathlib import Path
import re, subprocess, sys
root = Path('/var/backups/histor')
groups = {}
for dump in sorted(root.glob('histor-*.dump')):
    match = re.fullmatch(r'histor-(\d{8}T\d{6}Z)\.dump', dump.name)
    if not match:
        continue
    stamp = match[1]
    keys = root / f'keys-{stamp}.tar'
    if keys.is_file():
        groups.setdefault(stamp[:8], []).append((dump, keys))
remove = []
for day, pairs in sorted(groups.items()):
    dump, keys = pairs[-1]
    with dump.open('rb') as stream:
        subprocess.run(['docker','exec','-i','histor-histor-postgres-1','pg_restore','--list'], stdin=stream, stdout=subprocess.DEVNULL, check=True)
    listing = subprocess.check_output(['tar','-tf',str(keys)], text=True)
    if not any(name.endswith('/issuer.key') or name == 'issuer.key' for name in listing.splitlines()):
        raise RuntimeError(f'No issuer key: {keys.name}')
    print(f'KEEP validated {dump.name} + {keys.name}', flush=True)
    remove.extend(path for pair in pairs[:-1] for path in pair)
size = sum(path.stat().st_size for path in remove)
for path in remove:
    print(f'REMOVE {path.name}', flush=True)
print(f'Reclaimable: {size} bytes ({size / 1024**3:.2f} GiB)', flush=True)
if '--apply' in sys.argv:
    for path in remove:
        path.unlink()
    print('APPLIED', flush=True)
