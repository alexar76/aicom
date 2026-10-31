"""Materialize tracked first-party source only for read-only, offline malware scanners."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
DEST=Path('/private/tmp/aicom-security-review-20261030/source');DEST.mkdir(exist_ok=True)
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
excluded={'artifacts','research','docs','output','vendor','vendor-rust','test-vectors','tests','fixtures','node_modules','.git','.venv','dist','build','gallery','assets'}
extensions={'.py','.js','.mjs','.cjs','.ts','.tsx','.jsx','.rs','.go','.sol','.sh','.toml','.json','.yaml','.yml','.txt','.lock','.dart','.c','.h'}
rows=[]
for rel in paths:
 p=ROOT/rel
 if not rel or any(c in excluded for c in p.relative_to(ROOT).parts) or p.is_symlink() or not p.is_file() or p.suffix not in extensions:continue
 if p.name.startswith('test_') or p.name.endswith(('.test.ts','.test.js','_test.go')):continue
 target=DEST/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 rows.append({'path':rel,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(OUT/'source-inventory.json').write_text(json.dumps({'method':'git tracked production-source snapshot; excludes docs/research/artifacts/vendor/tests/assets and symlinks','files':rows,'total_bytes':sum(r['bytes'] for r in rows)},indent=2)+'\n')
# The CLI discovers installed dependencies, so make our source snapshot an explicit local install target.
site=Path('/private/tmp/aicom-security-review-20261030/malscan-target/.venv/lib/python3.12/site-packages');site.mkdir(parents=True,exist_ok=True)
shutil.copytree(DEST,site/'aicom_owned_source',dirs_exist_ok=True)
print(len(rows),'source files',sum(r['bytes'] for r in rows),'bytes')
