"""Verify captured peer bytes using our pure Hub canonicalizer, offline only."""
import ast, base64, copy, datetime, hashlib, json
from pathlib import Path
from typing import Any
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[2]/'aimarket-hub/aimarket_hub/signing.py'
tree=ast.parse(SOURCE.read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Signer')
fn=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='manifest_canonical'))
fn.decorator_list=[]
ns={'Any':Any}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(SOURCE),'exec'),ns)
discovery=json.loads((ROOT/'bodies/agent-exec-discovery.body').read_text())
manifest=json.loads((ROOT/'bodies/agent-exec-manifest-advertised.body').read_text())
sig=manifest['signature']; key=discovery['signer_public_key']
assert sig['public_key']==key
public=Ed25519PublicKey.from_public_bytes(base64.b64decode(key,validate=True))
canonical=ns['manifest_canonical'](None,manifest)
public.verify(base64.b64decode(sig['value'],validate=True),canonical.encode())
changed=copy.deepcopy(manifest)
changed['tools'][0]['description']=changed['tools'][0].get('description','')+' CONTROL'
rejected=False
try:public.verify(base64.b64decode(sig['value'],validate=True),ns['manifest_canonical'](None,changed).encode())
except InvalidSignature:rejected=True
assert rejected
result={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_url':discovery['manifest_url'],'advertised_tools':len(manifest['tools']),'signature_key_matches_discovery':True,'valid_under_hub_manifest_canonical':True,'modified_description_rejected':rejected,'canonical_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'canonicalizer_source':str(SOURCE.relative_to(ROOT.parents[2])),'canonicalizer_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'limits':'Captured signed manifest compatibility only, under self-declared peer key; no tool invoked, package installed, identity attested, payment made or runtime safety established.'}
(ROOT/'agent-exec-signature.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
