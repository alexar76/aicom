"""Read-only regression probe: run source helper functions against a synthetic Linux proc view.
No external sockets, network calls, application imports, or implementation writes.
"""
import ast
import io
import ipaddress
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path('/Users/alex/Desktop/ai_tests/aicompany/aicom')
PATHS = [
    'aimarket-mcp/aimarket_mcp/server.py',
    'metis/metis/api/auth.py',
    'treasury/treasury/service.py',
    'platon/backend/platon/main.py',
    'oracles/oracles/platon/backend/oracle_platon/main.py',
]
FUNCS = {'_proc_endpoint', '_flag', '_pid_holding', '_listens_beyond_loopback',
         '_process_name', '_socket_relays', '_caller_is_this_user', '_peer_is_loopback',
         '_is_loopback_name', '_host_is_loopback', '_origin_is_local', '_auth_ok',
         '_local_caller', 'local_caller'}
# Parent 100 owns the public listener. A Python relay worker 101 owns accepted
# ingress and outbound backend sockets, and closes the listening FD after fork.
# Backend 102 runs as the same user. This is a normal per-connection worker model.
FDS = {'/proc': ['100', '101', '102'], '/proc/100/fd': ['3'],
       '/proc/101/fd': ['4', '5'], '/proc/102/fd': ['6']}
LINKS = {'/proc/100/fd/3': 'socket:[300]', '/proc/101/fd/4': 'socket:[301]',
         '/proc/101/fd/5': 'socket:[302]', '/proc/102/fd/6': 'socket:[303]'}
HEADER = '  sl local_address rem_address st tx_queue tr tm_when retrnsmt uid timeout inode\n'
def row(n, local, remote, state, inode):
    return f'{n}: {local} {remote} {state} 00000000:00000000 00:00000000 00000000 501 0 {inode} 1\n'
TABLE = HEADER + ''.join([
    row(0, '00000000:1F90', '00000000:0000', '0A', 300),
    row(1, '0A0200C0:1F90', '22D8B85D:9C41', '01', 301),  # 192.0.2.10:8080 <- 93.184.216.34:40001
    row(2, '0100007F:9C40', '0100007F:2382', '01', 302),
    row(3, '0100007F:2382', '0100007F:9C40', '01', 303),
])
FILES = {'/proc/net/tcp': TABLE, '/proc/100/comm': 'python3\n',
         '/proc/101/comm': 'python3\n', '/proc/102/comm': 'python3\n'}
def fake_open(path, *args, **kwargs):
    try:
        return io.StringIO(FILES[path])
    except KeyError:
        raise FileNotFoundError(path)

def fake_listdir(path):
    try:
        return FDS[path]
    except KeyError:
        raise FileNotFoundError(path)

def fake_readlink(path):
    try:
        return LINKS[path]
    except KeyError:
        raise FileNotFoundError(path)

for relpath in PATHS:
    tree = ast.parse((ROOT / relpath).read_text())
    body = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    body += [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCS
             or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('_PROC_NET_TCP', '_RELAY_PROGRAMS', '_LOOPBACK_NAMES', '_FORWARDING_HEADERS') for t in node.targets)]
    ns = {'os': SimpleNamespace(listdir=fake_listdir, readlink=fake_readlink,
                               geteuid=lambda: 501, environ={}, path=SimpleNamespace(exists=lambda p: p in FILES)),
          'sys': SimpleNamespace(byteorder='little'), 'ipaddress': ipaddress, 'open': fake_open,
          '_API_KEY': '', '_PUBLIC': False, '_PRODUCTION': False}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(ROOT / relpath), 'exec'), ns)
    conn = SimpleNamespace(client=SimpleNamespace(host='127.0.0.1', port=40000),
                           scope={'server': ('127.0.0.1', 9090)}, headers={'host': '127.0.0.1:9090'})
    local_gate = next(name for name in ('_auth_ok', '_local_caller', 'local_caller') if name in ns)
    result = {'source': relpath, 'relay_worker_pid': ns['_pid_holding'](302),
              'parent_has_public_listener': ns['_listens_beyond_loopback'](100, ['/proc/net/tcp']),
              'worker_has_public_listener': ns['_listens_beyond_loopback'](101, ['/proc/net/tcp']),
              'relay_detected': ns['_socket_relays'](302, ['/proc/net/tcp']),
              'caller_allowed_without_opt_in': ns['_caller_is_this_user'](conn),
              'local_gate_function': local_gate,
              'full_local_gate_allowed_without_opt_in': ns[local_gate](conn)}
    ns['_PROC_NET_TCP'] = ()
    result['missing_proc_denied_by_default'] = not ns['_caller_is_this_user'](conn)
    print(json.dumps(result))
