#!/usr/bin/env python3
"""Download public npm archives, verify registry integrity, read Auten source without executing it."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent


def main():
    folder = HERE / 'artifacts'
    folder.mkdir(exist_ok=True)
    result = []
    for key in ('auten', 'warden'):
        metadata = json.loads((HERE / 'public' / f'{key}-package.json').read_text())
        with urlopen(metadata['dist']['tarball'], timeout=30) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        assert len(data) <= 16 * 1024 * 1024
        actual = 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
        assert actual == metadata['dist']['integrity']
        assert hashlib.sha1(data).hexdigest() == metadata['dist']['shasum']
        name = f'{key}-{metadata["version"]}.tgz'
        (folder / name).write_bytes(data)
        record = {'name': metadata['name'], 'version': metadata['version'], 'archive': name,
                  'url': metadata['dist']['tarball'], 'bytes': len(data), 'integrity': actual,
                  'sha256': hashlib.sha256(data).hexdigest(), 'executed': False}
        if key == 'auten':
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                record['members'] = [member.name for member in archive.getmembers()]
                for name in ('package/package.json', 'package/bin/auten-mcp.js', 'package/README.md'):
                    member = archive.getmember(name)
                    assert member.isfile() and member.size < 1024 * 1024
                    target = HERE / 'static-auten' / name.removeprefix('package/')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
        result.append(record)
    (HERE / 'artifacts.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
