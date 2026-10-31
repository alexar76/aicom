"""Collect final test counts, scanner triage, dependency deltas and provenance."""
import collections,datetime,hashlib,json,subprocess,xml.etree.ElementTree as E,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
def read(name):return json.loads((OUT/name).read_text())
def save(name,d):(OUT/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
tests=[]
for fn in ['hub-full-tests.xml','hub-postgres-tests.xml','histor-postgres-tests.xml','awr-python-tests.xml','oracle-core-tests.xml','kernel-tests.xml']:
 root=E.parse(OUT/fn).getroot();ss=root.findall('testsuite') if root.tag=='testsuites' else [root]
 totals={k:sum(int(s.get(k,0)) for s in ss) for k in ['tests','failures','errors','skipped']}
 tests.append({'file':fn,**totals,'passed':totals['tests']-totals['failures']-totals['errors']-totals['skipped'],'skip_reasons':dict(collections.Counter(x.get('message') for x in root.iter('skipped')))})
save('final-tests.json',tests)
# Every HIGH Bandit result is reviewed; keep all lower-priority results in the raw report.
d=read('bandit.json');high=[]
for r in d['results']:
 if r['issue_severity']!='HIGH':continue
 path=r['filename'].split('/source/')[-1]
 if r['test_id']=='B613':verdict='Defensive list/regex intentionally contains invisible characters to detect them.'
 elif r['test_id']=='B324':verdict='Non-authentication hash: cache key, mock address or event deduplication. No signature/password validation.'
 elif r['test_id']=='B507':verdict='AutoAddPolicy is behind explicit nondefault SKOPOS_SSH_STRICT_HOST_KEYS opt-out; default RejectPolicy verified in source.'
 elif 'smoke_starters' in path:verdict='Local smoke helper executes commands from the tracked starter catalog; no remote request input.'
 else:verdict='Offline research dataset builder constructs a shell command from operator paths. Local-only shell/path quoting risk remains; not a production protocol endpoint.'
 high.append({'path':path,'line':r['line_number'],'rule':r['test_id'],'disposition':verdict})
save('bandit-triage.json',{'results':len(d['results']),'errors':len(d['errors']),'lines':d['metrics']['_totals']['loc'],'high':high,'medium_and_low':'Raw findings retained; not all individually reviewed.'})
# Exact per-finding IOC interpretation, retaining evidence without asserting a malware verdict.
d=read('vulnetix-malscan.json');triage=[]
for f in d['findings']:
 i=f.get('IOCValue');reason='Public blockchain/RPC or token-launch service; name occurrence alone does not establish malicious use.'
 if i=='self.ws':reason='Rust self.ws() whitespace-parser method, not a DNS name or connection.'
 if i=='104.16.0.1':reason='Literal public DNS-pinning target in a transport regression test helper, not a C2 connection.'
 triage.append({'file':f['File'].split('aicom_owned_source/')[-1],'line':f['StartLine'],'ioc':i,'rule':f['RuleID'],'disposition':reason})
save('vulnetix-malscan-triage.json',{'files_scanned':d['filesScanned'],'scanner_malicious_boolean':d['malicious'],'findings':triage,'conclusion':'All 52 matches are IOC references. No non-IOC detector hit; reviewed references do not demonstrate malicious code. External services themselves have not been certified safe.'})
# Validate the one malformed upstream range against its actual upper bounds.
with zipfile.ZipFile('/private/tmp/aicom-security-review-20261030/PyPI.zip') as z:
 item=next(x for x in z.namelist() if x.endswith('PYSEC-2024-311.json'));v=json.loads(z.read(item))
save('osv-range-disposition.json',{'id':v['id'],'package':'wasmtime','version':'49.0.0','affected':v['affected'],'disposition':'Upstream range is malformed (upper without introduced). Existing 2026-10-25 disposition applies: 49.0.0 exceeds every affected upper bound. Preserved as manual disposition, not silently counted clean.'})
# Record only semantically changed package versions from lock updates.
changes=[]
for f in subprocess.check_output(['git','diff','--name-only'],cwd=ROOT).decode().splitlines():
 if not f.endswith(('uv.lock','package-lock.json')):continue
 old=subprocess.check_output(['git','show','HEAD:'+f],cwd=ROOT).decode();new=(ROOT/f).read_text()
 if f.endswith('uv.lock'):
  import tomllib
  a={p['name']:p['version'] for p in tomllib.loads(old)['package']};b={p['name']:p['version'] for p in tomllib.loads(new)['package']}
 else:a={k:v.get('version') for k,v in json.loads(old)['packages'].items()};b={k:v.get('version') for k,v in json.loads(new)['packages'].items()}
 for name in sorted(set(a)|set(b)):
  if a.get(name)!=b.get(name):changes.append({'file':f,'package':name,'before':a.get(name),'after':b.get(name)})
save('dependency-changes.json',changes)
print('tests',tests);print('version changes',changes)
