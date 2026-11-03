"""Read a cooperative provider's durable, signed result; never redispatch work."""
from __future__ import annotations
import hashlib
import json
import os
from urllib.parse import urlparse
import httpx
from aimarket_hub.signing import Signer

PROTOCOL = 'PROVIDER-OP/1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def descriptor(cap):
    # Explicit operator opt-in; a random legacy endpoint is never probed for recovery.
    products = {x.strip() for x in os.getenv('AIMARKET_PROVIDER_OPERATION_PRODUCTS', '').split(',') if x.strip()}
    if cap and cap.product_id in products and cap.source_hub == 'local' and cap.invoke_url and cap.provider_pubkey:
        return {'protocol': PROTOCOL, 'invoke_url': cap.invoke_url, 'public_key': cap.provider_pubkey}
    return None


async def request_status(spec, operation_id):
    from aimarket_hub.outbound_http import (resolve_invoke_url, prepare_safe_request_async,
        invoke_gateway_hosts)
    url = resolve_invoke_url(spec['invoke_url'].rstrip('/') + '/operations/' + operation_id)
    target, headers, extensions = await prepare_safe_request_async(url, invoke=True)
    token = os.getenv('AIMARKET_CAPABILITY_TOKEN', '').strip()
    if token and (urlparse(url).hostname or '').lower() in set(invoke_gateway_hosts()):
        headers['X-AIMarket-Internal-Token'] = token
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        async with client.stream('GET', target, headers=headers, extensions=extensions or None) as response:
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError('provider operation exceeds response limit')
                chunks.append(chunk)
    return json.loads(b''.join(chunks))


def verify(document, spec, operation_id, node, payload):
    if not isinstance(document, dict):
        raise ValueError('invalid provider operation')
    unsigned = {k: v for k, v in document.items() if k != 'signature'}
    if not Signer.verify(spec['public_key'], document.get('signature', ''), canonical(unsigned)):
        raise ValueError('invalid provider operation signature')
    expected = {'protocol': PROTOCOL, 'operation_id': operation_id,
                'product_id': node['product_id'], 'capability_id': node['capability_id'],
                'input_sha256': hashlib.sha256(canonical(payload).encode()).hexdigest()}
    if any(document.get(k) != v for k, v in expected.items()):
        raise ValueError('provider operation differs from the immutable order')
    if document.get('status') not in ('running', 'completed', 'reconciliation_required'):
        raise ValueError('unknown provider operation status')
    if document['status'] == 'completed':
        from aimarket_hub.supply_security import _bound_response_canonical
        bound = _bound_response_canonical(node['capability_id'], node['product_id'], payload, document['result'])
        if not Signer.verify(spec['public_key'], document.get('result_signature', ''), bound):
            raise ValueError('invalid recovered provider result signature')
    return document
