import asyncio
import json
import math
import sys

sys.path.insert(0, '/app/backend')

import hub_discovery
from ecosystem_layout import local_ecosystem_radius, node_position

fetched = []


async def fake_get_json(client, url, **kwargs):
    fetched.append(url)
    if url.endswith('/federation/peers'):
        return {'peers': [{'url': 'https://agent-exec.448c.org', 'name': 'agent-exec',
                           'capabilities_count': 0, 'trust_score': 0.265}], 'pending': []}
    if '127.0.0.1' in url and 'well-known' in url:
        return {'hub_url': 'https://ours.example', 'hub_version': '3.16.1'}
    if 'agent-exec.448c.org' in url and 'well-known' in url:
        return {'name': 'agent-exec', 'protocol_versions': ['v1', 'mcp'],
                'manifest_url': 'https://agent-exec.448c.org/ai-market/manifest'}
    if url == 'https://agent-exec.448c.org/health':
        return {'ok': True, 'service': 'agent-exec'}
    return None


hub_discovery._get_json = fake_get_json
hub_discovery.url_is_safe = lambda *a, **kw: True
result = asyncio.run(hub_discovery.discover_async('http://127.0.0.1:9083'))
nodes = [n for n in result['nodes'] if n['label'] == 'agent-exec']
assert len(nodes) == 1, result
node = nodes[0]
assert (node['group'], node['role'], node['icon'], node['hop']) == ('peer_hub', 'hub', 'hub', 1), node
assert node['status'] == 'active', node
assert node['metrics']['capabilities'] == 0, node
assert node['metrics']['trust_score'] == 0.265, node
centre = node_position('hub')
distance = math.dist([node['position'][k] for k in ('x', 'y', 'z')],
                     [centre[k] for k in ('x', 'y', 'z')])
assert distance > local_ecosystem_radius(), node
assert 'https://agent-exec.448c.org/health' in fetched
assert 'https://agent-exec.448c.org/ai-market/v2/health' not in fetched
assert not hub_discovery._is_peer_hub({'protocol_versions': ['v1']})
assert hub_discovery._is_peer_hub({'hub_version': '3.16.1'})
print(json.dumps({'smoke': 'passed', 'agent_exec': node, 'distance_from_modelmarket': distance,
                  'local_ecosystem_radius': local_ecosystem_radius()}))
