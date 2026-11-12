"""Verify saved public manifest signatures; execute only our pure canonicalizer."""
import ast
import base64
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
source = REPO / "aimarket-hub/aimarket_hub/signing.py"
tree = ast.parse(source.read_text())
cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Signer")
function = copy.deepcopy(next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "manifest_canonical"))
function.decorator_list = []
namespace = {"Any": Any}
exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(source), "exec"), namespace)


def valid(key, signature, canonical):
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True)).verify(base64.b64decode(signature, validate=True), canonical.encode())
        return True
    except Exception:
        return False


rows = []
for name, discovery_file, manifest_file in [
    ("agent-exec", "agent-exec-discovery.raw", "agentexec-manifest.raw"),
    ("machina", "machina-discovery.raw", "machina-manifest.raw"),
]:
    discovery = json.loads((ROOT / discovery_file).read_text())
    manifest = json.loads((ROOT / manifest_file).read_text())
    signature = manifest.get("signature")
    key = discovery.get("signer_public_key", "")
    signature_value = signature.get("value", "") if isinstance(signature, dict) else signature
    canonical = namespace["manifest_canonical"](None, manifest)
    modified = copy.deepcopy(manifest)
    modified["tools"][0]["description"] = modified["tools"][0].get("description", "") + " CONTROL"
    modified_canonical = namespace["manifest_canonical"](None, modified)
    rows.append({
        "peer": name,
        "protocol_version": manifest.get("protocol_version"),
        "advertised_tools": len(manifest.get("tools", [])),
        "signature_is_object": isinstance(signature, dict),
        "signature_key_matches_discovery": isinstance(signature, dict) and signature.get("public_key") == key,
        "valid_under_hub_manifest_canonical": valid(key, signature_value, canonical),
        "modified_description_valid": valid(key, signature_value, modified_canonical),
        "canonical_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    })
result = {
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "canonicalizer_source": str(source.relative_to(REPO)),
    "canonicalizer_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "scope": "Saved manifest signature compatibility and negative control only. No invoke, payment, runtime safety certification or owner-independence verification.",
    "records": rows,
}
(ROOT / "peer-signatures.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
