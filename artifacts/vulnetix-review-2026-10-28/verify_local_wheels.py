"""Verify local release contents against source and exercise their keyless gates."""
import email
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROJECTS = {
 'aimarket-mcp': 'aimarket-mcp', 'aimarket-metis': 'metis',
 'aimarket-treasury': 'treasury', 'aimarket-platon': 'platon/backend',
 'aimarket-oracle-core': 'oracles/core', 'aimarket-logos': 'logos',
 'aimarket-atlas': 'atlas', 'skopos-fleet': 'skopos',
}
spec = importlib.util.spec_from_file_location('wheel_keyless_tests', ROOT/'tests/test_keyless_tcp_authorization.py')
helpers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helpers
spec.loader.exec_module(helpers)
results = []
with TemporaryDirectory(prefix='vulnetix-wheel-source-') as directory:
 stage = Path(directory)
 for wheel in sorted((HERE/'release-wheels').glob('*.whl')):
  raw = wheel.read_bytes()
  with zipfile.ZipFile(wheel) as archive:
   names = archive.namelist()
   metadata = email.message_from_bytes(archive.read(next(n for n in names if n.endswith('.dist-info/METADATA'))))
   package = metadata['Name']; project = PROJECTS[package]
   checked = []
   for member in names:
    assert not member.startswith('/') and '..' not in Path(member).parts, member
    assert not member.endswith(('.db', '.sqlite', '.sqlite3', '.pem', '.key', '.pyc')), member
    assert Path(member).name not in ('.env', 'treasury_signing_key', 'ledger.jsonl'), member
    if not member.endswith('.py') or '.dist-info/' in member:
     continue
    source = ROOT/project/member
    content = archive.read(member)
    assert source.is_file(), str(source)
    assert source.read_bytes() == content, 'stale packaged source: '+member
    target = stage/project/member; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    checked.append(member)
   results.append({'package':package, 'version':metadata['Version'], 'wheel':wheel.name,
                   'sha256':hashlib.sha256(raw).hexdigest(), 'python_sources_verified':len(checked)})
 assert len(results) == len(PROJECTS)
 helpers.ROOT = stage
 gates=[]
 for source in helpers.SOURCES:
  if source.path.startswith('oracles/oracles/'):
   continue  # local mirror is tested separately; not a separate distribution
  admission=helpers.Admission(source)
  assert admission.gate(helpers.request()) is False
  admission.opt_in()
  assert admission.gate(helpers.request()) is True
  admission.files.clear()
  assert admission.gate(helpers.request()) is False
  admission.opt_in(unverified=True)
  assert admission.gate(helpers.request()) is True
  gates.append({'source':source.path,'default_denied':True,'verified_opt_in_accepted':True,
                'missing_proc_needs_both_flags':True})
report={'wheels':results,'packaged_keyless_gates':gates,'published':False,
        'verification':'All packaged Python source bytes match workspace; metadata and archive paths checked; no install or network.'}
(HERE/'local-wheel-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'wheels':len(results),'python_sources_verified':sum(r['python_sources_verified'] for r in results),'packaged_keyless_gates_verified':len(gates),'all_match_workspace':True}))
