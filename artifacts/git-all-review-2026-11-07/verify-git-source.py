"""Verify the immutable native-Git source transport inside remote gVisor."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

root = Path('/source')
metadata = Path('/metadata')
version = sys.argv[1] if len(sys.argv) > 1 else 'v3'
assert re.fullmatch('[a-z0-9-]+', version)
expected = {}
blob_manifest = metadata / f'source-blobs-{version}.txt'
for line in blob_manifest.read_text().splitlines():
    fields, relative = line.split('\t', 1)
    mode, kind, oid = fields.split()
    assert kind == 'blob' and mode in ('100644', '100755', '120000')
    assert not relative.startswith('/') and '..' not in Path(relative).parts
    expected[relative] = (mode, oid)
actual = {}
for relative, (mode, oid) in expected.items():
    path = root / relative
    if mode == '120000':
        assert path.is_symlink(), relative
        data = os.readlink(path).encode()
    else:
        assert path.is_file() and not path.is_symlink(), relative
        data = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    assert blob == oid, relative
    actual[relative] = {'gitBlob': blob, 'sha256': hashlib.sha256(data).hexdigest()}
paths = {str(path.relative_to(root)) for path in root.rglob('*')
         if path.is_file() or path.is_symlink()}
assert paths == set(expected), sorted(paths.symmetric_difference(expected))
manifest_bytes = (json.dumps(actual, sort_keys=True, separators=(',', ':')) + '\n').encode()
output = Path('/results')
(output / 'source-file-hashes.json').write_bytes(manifest_bytes)
receipt = {
    'format': 'aicom.immutable-source-verification/v1',
    'sourceTree': (metadata / f'source-tree-{version}.txt').read_text().strip(),
    'files': len(expected),
    'sourceFileHashesSha256': hashlib.sha256(manifest_bytes).hexdigest(),
    'expectedBlobManifestSha256': hashlib.sha256(blob_manifest.read_bytes()).hexdigest(),
    'execution': 'remote gVisor',
    'allMatched': True,
}
(output / 'source-verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
