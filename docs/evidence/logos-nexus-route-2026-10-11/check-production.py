"""Real public, zero-price NEXUS call plus deployed asset/source verification."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = 'https://logos.modelmarket.dev'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def get(path, payload=None):
    request = Request(BASE + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type': 'application/json', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=60) as response:
        return response.status, response.read()


health_status, health_body = get('/health')
catalog_status, catalog_body = get('/api/v1/federation/capabilities')
catalog = json.loads(catalog_body)['capabilities']
routes = [cap for cap in catalog if cap['capability_id'] == 'logos.federation.summary@v1'
          and cap['product_id'] == 'prod-logos' and cap['source_hub'] == BASE]
assert len(routes) == 1, routes
route = routes[0]
assert route['price_per_call_usd'] == 0, 'Only the confirmed free route may be tested'
payload = {key: route[key] for key in ('product_id', 'capability_id', 'source_hub')}
payload.update(input={}, max_price_usd=0)
invoke_status, invoke_body = get('/api/v1/federation/invoke', payload)
result = json.loads(invoke_body)
assert invoke_status == 200 and result['status'] == 'ok', result
assert result['result']['ok'] is True and result['price_usd'] == 0, result
index_status, index_body = get('/')
asset_paths = re.findall(r'(?:src|href)="(/assets/[^\"]+\.(?:js|css))"', index_body.decode())
assert asset_paths
assets = []
for path in asset_paths:
    status, body = get(path)
    local = ROOT / 'logos/frontend/dist' / path.lstrip('/')
    assert body == local.read_bytes(), path
    assets.append({'path': path, 'status': status, 'sha256': hashlib.sha256(body).hexdigest(),
                   'matches_local_build': True})
evidence = {
    'observed_at': datetime.now(timezone.utc).isoformat(),
    'base_url': BASE, 'health_status': health_status, 'health': json.loads(health_body),
    'catalog_status': catalog_status, 'catalog_count': len(catalog), 'selected_route': route,
    'request': payload, 'invoke_http_status': invoke_status, 'response': result,
    'index_status': index_status, 'assets': assets,
}
(HERE / 'production-checks.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps(evidence, indent=2))
