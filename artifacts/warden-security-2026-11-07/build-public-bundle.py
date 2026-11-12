"""Build the publication-safe offline bundle, executed only in remote gVisor."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path('/assets')
OUTPUT = Path('/output')
sha = lambda data: hashlib.sha256(data).hexdigest()

# The compatibility receipt is deliberately reduced to counts and integrity
# witnesses. Raw native result objects are not part of the public bundle.
raw = json.loads((ROOT / 'evidence/binary-resource-fix/summary.json').read_text())
public = {key: raw[key] for key in (
    'format', 'candidateVersion', 'baselineVersion', 'ruleset',
    'classifierFiles', 'classifierIdentitySha256', 'coreEqualAcrossHosts',
    'declaredChangesEqualAcrossHosts', 'toolHashesAcrossHosts',
    'binaryAgreement', 'pairedPaths', 'pairedRows', 'pairedMatches',
    'differences', 'passed',
)}
public['sites'] = {}
for site, item in raw['sites'].items():
    public['sites'][site] = {
        'full': {key: item['full'][key] for key in
                 ('total', 'passed', 'failed', 'files', 'success', 'failedSuites')},
        'focused': item['focused'],
        'sourceUnchanged': item['full']['stability']['unchanged'],
        'allCommandsPassed': item['full']['complete']['allCommandsPassed'],
    }
public['lowResourceDiagnostic'] = {
    key: raw['lowResourceDiagnostic'][key]
    for key in ('cpus', 'tests', 'passed', 'failed', 'retained', 'normalProfileRetest')
}
public['scope'] = 'Frozen .2 compatibility only; bulk definition metrics belong to frozen .1. Current Nov8 hooks are outside these measurements.'
(ROOT / 'evidence/binary-resource-fix/public-summary.json').write_text(
    json.dumps(public, ensure_ascii=False, indent=2) + '\n')

packet = json.loads((ROOT / 'sha256-manifest.json').read_text())
assert sha((ROOT / 'sha256-manifest.json').read_bytes()) == '17d6e7ebd85dede970d77f319bf3734478a037bf9fd971a53f5bbd07b4fce3f8'
names = {'sha256-manifest.json'}
for item in packet['files']:
    data = (ROOT / item['name']).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256'], item['name']
    names.add(item['name'])
inventory = json.loads((ROOT / 'public-inventory-manifest.json').read_text())
assert inventory['metadataOnly'] and not inventory['rawMCPToxRedistributed']
assert inventory['caseCount'] == 18110
for name, item in inventory['files'].items():
    data = (ROOT / name).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256'], name
    names.add(name)
names.update({
    'public-inventory-manifest.json', 'INVENTORY-README.md',
    'figure-metrics.json', 'registry-at-publication.json',
    'cover.png', 'method.png', 'results.png', 'coverage.png',
    'evidence/candidate19/summary.json', 'evidence/candidate19/REPORT.md',
    'evidence/binary-resource-fix/public-summary.json',
    'evidence/binary-resource-fix/REPORT.md', 'evidence/live/README.md',
})
for language in ('', '.ru', '.es', '.fr', '.zh'):
    for suffix in ('.md', '.html'):
        names.add('reports/security-benchmark-2026-11-07' + language + suffix)
names.add('reports/render-receipt.json')

readme = '''# WARDEN: five-product definition comparison\n\nOpen reports/security-benchmark-2026-11-07.html for English, or use its language navigation for RU/ES/FR/ZH. The Markdown originals are alongside the HTML. No server or JavaScript is required.\n\nPrimary products: published @aimarket/warden0.23.0, mcp-audit-scanner[mcp]0.28.0, mcp-shield1.0.4, @askalf/truecopy0.10.5, @roshan6335/mcpsentry0.1.5. Each received18,110 target rows on each of two remote gVisor hosts. Overlapping views are not independent attacks.\n\npublic-inventory.csv and .json list all18,110 rows as metadata. paired-case-outcomes.csv lists90,550 paired primary-product outcomes. The candidate19 CSV separately lists18,110 frozen .1 pairs. Gzip copies are supplied. Raw definitions, payloads, schemas, source code and complete native finding objects are excluded.\n\nHigh/critical and any-signal columns measure definition signals; they are not common enforcement decisions. Public/HISTOR positive frequency is not a false-positive rate. Errors remain outside completed-result denominators. See enforcement-mapping.json, comparison-methods.md, and audit-profile.md.\n\nFrozen candidate .1 and compatibility .2 are unpublished builds with separate receipts. Nov8 working-tree hook changes are outside the bulk measurements in this bundle. No npm release was made.\n\nHISTOR archive attribution: Aleksandr Artamokhov / HISTOR, CC-BY-4.0, https://histor.modelmarket.dev/datasets/2026-10-20/toolsets.jsonl.gz and manifest.json. Three immutable API-sourced package rows have no separately stated response license; only metadata is included. MCPTox official commit f85189f9ad12504c197c7f920ab818a40657b1fa, https://github.com/zhiqiangwang4/MCPTox-Benchmark and https://arxiv.org/abs/2508.14925; no license was specified, so raw benchmark content is not redistributed. See INVENTORY-README.md for provenance and scope.\n\nThe author maintains WARDEN and HISTOR. This is a maintainer-run comparison, not an independent ranking. AI assistance was used for implementation, orchestration, analysis, writing and figures; responsibility remains with the maintainer.\n\nBUNDLE-MANIFEST.json records every included file. Hash manifests establish integrity, not independent authorship or correctness.\n'''
(ROOT / 'README.md').write_text(readme)
names.add('README.md')
assert all(not name.startswith('/') and '..' not in Path(name).parts for name in names)
assert all(not re.search(r'\.(?:py|mjs|ts|env|key|pem)$', name) for name in names)
files = {name: (ROOT / name).read_bytes() for name in sorted(names)}
manifest = {
    'format': 'warden.public-offline-bundle/v1',
    'execution': 'remote gVisor',
    'metadataOnlyInputs': True,
    'rawBenchmarkContentIncluded': False,
    'sourceCodeIncluded': False,
    'files': {name: {'bytes': len(data), 'sha256': sha(data)}
              for name, data in files.items()},
}
files['BUNDLE-MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
OUTPUT.mkdir(exist_ok=True)
archive = OUTPUT / 'reports-and-data.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
    for name, data in sorted(files.items()):
        info = zipfile.ZipInfo(name, (2026, 11, 7, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        handle.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
with zipfile.ZipFile(archive) as handle:
    assert handle.testzip() is None
    assert set(handle.namelist()) == set(files)
    for name, data in files.items():
        assert handle.read(name) == data, name
receipt = {'format': 'warden.public-bundle-receipt/v1', 'files': len(files),
           'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes()),
           'packetManifestSha256': sha((ROOT / 'sha256-manifest.json').read_bytes()),
           'execution': 'remote gVisor', 'sourceCodeIncluded': False,
           'rawBenchmarkContentIncluded': False}
(OUTPUT / 'bundle-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
