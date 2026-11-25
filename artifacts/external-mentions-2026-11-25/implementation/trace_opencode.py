"""Capture the first OpenCode model request with a local mock provider and synthetic MCP.

Pass the local OpenCode 2.4.1 binary as the only argument. Requires Node for mcp-token-cost.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FILE = Path(__file__).resolve()
ROOT = FILE.parents[3]
TOOL_COST = ROOT / 'mcp-token-cost/bin/mcp-token-cost.js'
TOOLS = [
    {'name': f'lookup_{kind}',
     'description': f'Look up a {kind} in a synthetic public catalogue by its unique reference. '
                    'Returns a title, a year and any catalogue tags.',
     'inputSchema': {'type': 'object', 'properties': {
         'reference': {'type': 'string', 'description': 'Catalogue reference, for example K-123.'},
         'locale': {'type': 'string', 'enum': ['en', 'es', 'fr', 'ru', 'zh']},
     }, 'required': ['reference'], 'additionalProperties': False}}
    for kind in ('book', 'map', 'record', 'poster', 'photo', 'catalogue', 'periodical')
]
MOCK_USAGE = {'prompt_tokens': 1234, 'completion_tokens': 7, 'total_tokens': 1241}


def mcp():
    for line in sys.stdin:
        msg = json.loads(line)
        if 'id' not in msg:
            continue
        result = {'jsonrpc': '2.0', 'id': msg['id']}
        if msg['method'] == 'initialize':
            result['result'] = {'protocolVersion': msg['params']['protocolVersion'],
                                'serverInfo': {'name': 'catalog-fixture', 'version': '1.0.0'},
                                'capabilities': {'tools': {}}}
        elif msg['method'] == 'tools/list':
            result['result'] = {'tools': TOOLS}
        else:
            result['error'] = {'code': -32601, 'message': 'The fixture only lists tools.'}
        print(json.dumps(result), flush=True)


class MockProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/v1/chat/completions':
            self.send_error(404)
            return
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(data)
        chunk = {'id': 'measurement', 'object': 'chat.completion.chunk', 'created': 1,
                 'model': data['model']}
        events = [
            {**chunk, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'Measured.'},
                                  'finish_reason': None}]},
            {**chunk, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
            {**chunk, 'choices': [], 'usage': MOCK_USAGE},
        ]
        stream = ''.join(f'data: {json.dumps(e)}\n\n' for e in events) + 'data: [DONE]\n\n'
        body = stream.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def config(port, codemode):
    return {
        'model': 'measurement/trace',
        'providers': {'measurement': {
            'package': '@opencode/ai/providers/openai-compatible',
            'env': ['TRACE_FIXTURE_KEY'], 'settings': {'baseURL': f'http://127.0.0.1:{port}/v1'},
            'models': {'trace': {'name': 'Local mock', 'capabilities': {'tools': True}}},
        }},
        'mcp': {'servers': {'catalog_fixture': {'type': 'local', 'codemode': codemode,
                                               'command': [sys.executable, str(FILE), '--mcp']}}},
    }


def count(node, dest, name, tools):
    dump = dest / f'{name}.json'
    dump.write_text(json.dumps({'tools': tools}))
    raw = subprocess.check_output([node, str(TOOL_COST), 'scan', '--tools', str(dump),
                                   '--offline', '--format', 'json'], text=True)
    report = json.loads(raw)
    return report['totals']['sent']


def capture(binary, server, dest, label, codemode):
    dest.mkdir()
    (dest / 'opencode.json').write_text(json.dumps(config(server.server_port, codemode)))
    temp = dest / 'tmp'
    temp.mkdir()
    env = {'PATH': os.environ['PATH'], 'TMPDIR': str(temp), 'TRACE_FIXTURE_KEY': 'local-fixture',
           'OPENCODE_DISABLE_MODELS_FETCH': '1', 'OPENCODE_DISABLE_AUTOUPDATE': '1',
           'OPENCODE_DISABLE_TELEMETRY': '1'}
    for key in ('DATA', 'CONFIG', 'CACHE', 'STATE'):
        env[f'XDG_{key}_HOME'] = str(dest / key.lower())
    server.requests.clear()
    cli = subprocess.run([str(binary), '--standalone', 'run', '--format', 'json', '--title', 'Fixture trace',
                          'Reply with Measured.'], cwd=dest, env=env, text=True,
                         capture_output=True, timeout=45)
    primary_requests = [req for req in server.requests if req.get('tools')]
    if cli.returncode or len(primary_requests) != 1:
        raise RuntimeError(f'{label}: {cli.returncode}, requests={len(server.requests)}\n'
                           f'{cli.stdout[-4000:]}\n{cli.stderr[-4000:]}')
    event = next(json.loads(line) for line in cli.stdout.splitlines()
                 if line.startswith('{') and json.loads(line).get('type') == 'step_finish')
    definitions = [tool['function'] for tool in primary_requests[0]['tools']
                   if tool.get('type') == 'function']
    return {
        'catalogue_functions_sent': sorted(t['name'] for t in definitions if t['name'].startswith('catalog_fixture_')),
        'model_facing_function_names': sorted(t['name'] for t in definitions),
        'model_requests_with_tools': len(primary_requests),
        'other_model_requests': len(server.requests) - len(primary_requests),
        'model_facing_definitions': [{'name': t['name'], 'description': t.get('description', ''),
                                      'inputSchema': t.get('parameters', {})} for t in definitions],
        'opencode_step_tokens': event['part']['tokens'],
    }


def main(binary):
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js is required for the local mcp-token-cost CLI.')
    with tempfile.TemporaryDirectory(prefix='aicom-code-mode-') as tmp:
        dest = Path(tmp)
        with ThreadingHTTPServer(('127.0.0.1', 0), MockProvider) as server:
            server.requests = []
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                direct = capture(binary, server, dest / 'direct', 'direct', False)
                mode = capture(binary, server, dest / 'code-mode', 'code-mode', True)
            finally:
                server.shutdown()
        assert len(direct['catalogue_functions_sent']) == len(TOOLS), direct['model_facing_function_names']
        assert not mode['catalogue_functions_sent'], mode['model_facing_function_names']
        for label, run in [('direct', direct), ('code_mode', mode)]:
            defs = run.pop('model_facing_definitions')
            run['all_model_facing_function_tokens'] = count(node, dest, label, defs)
            catalogue = [t for t in defs if t['name'] in run['catalogue_functions_sent']]
            run['catalogue_function_tokens'] = count(node, dest, f'{label}-catalogue', catalogue) if catalogue else 0
        print(json.dumps({
            'client': 'OpenCode 2.4.1', 'tokenizer': 'o200k_base', 'synthetic_catalogue': TOOLS,
            'full_catalogue_tokens': count(node, dest, 'full', TOOLS),
            'provider': 'Local mock. The usage field is a fixed fixture, not a token measurement.',
            'provider_usage_fixture_per_request': MOCK_USAGE,
            'direct': direct, 'code_mode': mode,
        }, indent=2))


if __name__ == '__main__':
    if sys.argv[1:] == ['--mcp']:
        mcp()
    elif len(sys.argv) == 2:
        main(Path(sys.argv[1]).resolve())
    else:
        sys.exit(f'Usage: python3 {FILE.name} /path/to/opencode')
