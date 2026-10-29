"""Verify captured public provider manifest with our local protocol canonical.

Never imports or executes provider code, invokes a capability, or sends a payment.
"""
import ast
import base64
import copy
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
SOURCE = WORKSPACE / 'web/backend/services/ai_market_protocol/signing.py'
source = SOURCE.read_text()
module = ast.parse(source)
function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'manifest_canonical')
selected_source = ast.get_source_segment(source, function)
namespace = {'Any': Any, 'json': json}
exec(compile(selected_source, str(SOURCE), 'exec'), namespace)
canonical = namespace['manifest_canonical']

rows = json.loads((ROOT/'industrial-federation-source-live.json').read_text())
record = next(row for row in rows if row['url'].endswith('/ai-market/v2/manifest'))
manifest = record['result']
discovery = next(row['result'] for row in rows if row['url'].endswith('/.well-known/ai-market.json'))
signature = manifest['signature']
public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(signature['public_key'], validate=True))
signed_bytes = base64.b64decode(signature['value'], validate=True)
public_key.verify(signed_bytes, canonical(manifest).encode('utf-8'))

changed = copy.deepcopy(manifest)
changed['tools'][0]['price_per_call_usd'] = 0.01
tamper_rejected = False
try:
    public_key.verify(signed_bytes, canonical(changed).encode('utf-8'))
except InvalidSignature:
    tamper_rejected = True
assert tamper_rejected

result = {
    'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_url': record['url'],
    'source_retrieved_at_utc': record['retrieved_at_utc'],
    'source_response_sha256': record['sha256'],
    'provider_name': discovery['name'],
    'provider_node_id': discovery['ecosystem']['nodes'][0]['id'],
    'provider_relationship_self_declared': discovery['ecosystem']['relationship'],
    'origin': manifest['base_url'],
    'signature_algorithm': signature['algorithm'],
    'self_declared_public_key_base64': signature['public_key'],
    'canonical_form_fields': ['capabilities_count', 'generated_at', 'protocol_version', 'tools_hash', 'by_hub_hash'],
    'canonical_value': canonical(manifest),
    'local_canonical_source': str(SOURCE.relative_to(WORKSPACE)),
    'local_canonical_function_source_sha256': hashlib.sha256(selected_source.encode()).hexdigest(),
    'canonical_sha256': hashlib.sha256(canonical(manifest).encode()).hexdigest(),
    'manifest_signature_verifies_with_our_canonical': True,
    'changed_first_tool_price_signature_rejected': tamper_rejected,
    'capabilities_count': manifest['capabilities_count'],
    'free_capabilities': sum(tool.get('price_per_call_usd') == 0 for tool in manifest['tools']),
    'limits': 'Compatibility of this captured signed manifest under its self-declared key; no identity attestation, invoke, installation, payment, customer use or complete protocol conformance is established.'
}
(ROOT/'industrial-manifest-compatibility.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(result, ensure_ascii=False))
