"""Offline compatibility check; no foreign code, keys, calls or state changes."""
import ast,base64,copy,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
source=REPO/"aimarket-hub/aimarket_hub/signing.py"
tree=ast.parse(source.read_text())
cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="Signer")
fn=copy.deepcopy(next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=="manifest_canonical"))
fn.decorator_list=[]
module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
ns={"Any":Any};exec(compile(module,str(source),"exec"),ns)
def verify(key,sig,text):
 try:Ed25519PublicKey.from_public_bytes(base64.b64decode(key,validate=True)).verify(base64.b64decode(sig,validate=True),text.encode());return True
 except Exception:return False
rows=[]
for name in ["machina","agentexec"]:
 d=json.loads((ROOT/(name+"-discovery.json")).read_text());m=json.loads((ROOT/(name+"-manifest.json")).read_text())
 sig=m.get("signature");key=d.get("signer_public_key","")
 value=sig.get("value","") if isinstance(sig,dict) else sig if isinstance(sig,str) else ""
 canonical=ns["manifest_canonical"](None,m)
 tampered=copy.deepcopy(m)
 tampered["tools"][0]["description"]=tampered["tools"][0].get("description","")+" CONTROL"
 altered=ns["manifest_canonical"](None,tampered)
 compact=json.dumps({k:v for k,v in m.items() if k!="signature"},sort_keys=True,separators=(",",":"))
 rows.append({"name":name,"protocol_version":m.get("protocol_version"),"tools":len(m.get("tools",[])),"all_tools_have_input_schema":all(isinstance(t.get("input_schema"),dict) for t in m.get("tools",[])),"signature_is_object":isinstance(sig,dict),"signature_key_matches_discovery":isinstance(sig,dict) and sig.get("public_key")==key,"ed25519_valid_for_hub_manifest_canonical":verify(key,value,canonical),"negative_control_modified_description_valid":verify(key,value,altered),"ed25519_valid_for_compact_sorted_document":verify(key,value,compact),"generated_at":m.get("generated_at"),"canonical_sha256":hashlib.sha256(canonical.encode()).hexdigest()})
out={"verified_at_utc":datetime.now(timezone.utc).isoformat(),"source":str(source.relative_to(REPO)),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"method":"Only the local manifest_canonical pure method extracted via AST; Ed25519 checked with cryptography. No full protocol certification, invokes, transactions, beneficial-owner verification or live assay.","records":rows}
(ROOT/"peer-manifest-compatibility.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(out,ensure_ascii=False,indent=2))

