"""One-off published-package probe on the existing sandbox host, never a service update.

Run as histor-sandbox. Use the installed observer's resolution, bounded installer,
slot locks and disposable gVisor containers. This process has no DNS logger/sink,
so the run stage is --network none and Session never invokes a tool.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

assert os.getuid() != 0, "Run as the sandbox user"
observer_path = Path('/usr/local/bin/histor-observe')
loader = importlib.machinery.SourceFileLoader('histor_launch_recheck', str(observer_path))
spec = importlib.util.spec_from_loader(loader.name, loader)
obs = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = obs
loader.exec_module(obs)
assert obs.DNS is None and obs.SINK is None
assert obs.traced_available() is False
obs.SLOT_WAIT_S = 120

current = {}
original_send = obs.Session.send
original_call = obs.Session.call
original_install = obs.install
original_resolve = obs.resolve


def resolve(registry, name, version):
    if current.get('artifact'):
        path = Path(current['artifact'])
        return {'version': version, 'has_wheel': True,
                'integrity': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()}
    return original_resolve(registry, name, version)


def send(self, message):
    method = message.get('method')
    assert method in {'initialize', 'notifications/initialized', 'tools/list'}, method
    current['wire'].append({'direction': 'client', 'message': message})
    return original_send(self, message)


def call(self, rid, method, params, wait_s):
    response = original_call(self, rid, method, params, wait_s)
    current['wire'].append({'direction': 'server', 'message': response})
    return response


def install(registry, name, version, work, run_id, pins=None, image=None):
    requirement_name = name + '[mcp]' if current.get('mcpExtra') else name
    if current.get('artifact'):
        artifact = Path(current['artifact'])
        shutil.copy2(artifact, work / artifact.name)
        flags = [*obs.base_flags(run_id + '-i'), '--network', obs.FETCH_NETWORK,
                 '--memory', '1g', '--memory-swap', '1g', '--cpus', '1',
                 '-v', f"{obs.STATE / 'resolv.conf'}:/etc/resolv.conf:ro",
                 '-v', f'{work}:/work', '-e', 'HOME=/work/.home', '-w', '/work']
        requirement = '/work/' + artifact.name
        command = (['pip', 'install', '--disable-pip-version-check', '--no-cache-dir',
                    '--only-binary=:all:', '--no-compile', '--target', '/work/pkg', requirement]
                   if registry == 'pypi' else
                   ['npm', 'install', '--ignore-scripts', '--omit=dev', '--no-audit',
                    '--no-fund', '--prefix', '/work/pkg', requirement])
        try:
            result = obs.docker('run', *flags, image or obs.IMAGES[registry], *command,
                                timeout=obs.INSTALL_TIMEOUT_S)
            ok, log = result.returncode == 0, obs.tail(result.stderr or result.stdout)
        except subprocess.TimeoutExpired:
            obs.docker('rm', '-f', f'histor-{run_id}-i')
            ok, log = False, 'install timed out'
    else:
        ok, log = original_install(registry, requirement_name, version, work, run_id, pins, image)
    current['installation'] = {'ok': ok, 'log': log}
    dependencies = {}
    if ok and registry == 'pypi':
        for path in (work / 'pkg').glob('*.dist-info/METADATA'):
            fields = {}
            for line in path.read_text().splitlines():
                if line.startswith(('Name: ', 'Version: ')):
                    key, value = line.split(': ', 1)
                    fields[key] = value
            if fields.get('Name') and fields.get('Version'):
                dependencies[fields['Name']] = fields['Version']
    elif ok:
        for package in [name, '@modelcontextprotocol/sdk', '@aimarket/warden', 'zod']:
            path = work / 'pkg/node_modules' / package / 'package.json'
            if path.is_file():
                metadata = json.loads(path.read_text())
                dependencies[package] = metadata.get('version')
    current['installedVersions'] = dependencies
    return ok, log


obs.Session.send = send
obs.Session.call = call
obs.install = install
obs.resolve = resolve
cases = [
    ('argus-default', 'npm', '@alexar76/argus3', '0.3.3', []),
    ('packager-default', 'pypi', 'aimarket-mcp-packager', '2.1.1', []),
    ('oracle-default', 'pypi', 'aimarket-oracle-gateway', '0.3.1', []),
]
configured = [
    ('argus-mcp', 'npm', '@alexar76/argus3', '0.3.3', ['mcp']),
    ('packager-extra-mcp', 'pypi', 'aimarket-mcp-packager', '2.1.1', []),
    ('oracle-full-error', 'pypi', 'aimarket-oracle-gateway', '0.3.1', []),
]
case_specs = {}
if len(sys.argv) == 3 and sys.argv[1] == '--cases':
    specifications = json.loads(Path(sys.argv[2]).read_text())
    case_specs = {spec['case']: spec for spec in specifications}
    cases = [(s['case'], s['registry'], s['name'], s['version'], s.get('args', []))
             for s in specifications]
elif sys.argv[1:] == ['configured']:
    cases = configured
    # Preserve the chained exception for the failed registration, rather than only its tail.
    obs.tail = lambda text: str(text)[-24000:]
    obs.head_tail = lambda text, head=600, end=1400: str(text)[-24000:]
else:
    assert not sys.argv[1:]
for label, registry, name, version, args in cases:
    current = {'case': label, 'registry': registry, 'name': name,
               'requestedVersion': version, 'args': args, 'wire': [],
               'observerSha256': hashlib.sha256(observer_path.read_bytes()).hexdigest(),
               'probeStartedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'runNetwork': 'none', 'toolCallsAllowed': False}
    current.update({k: v for k, v in case_specs.get(label, {}).items()
                    if k in {'artifact', 'sourceKind'}})
    current['mcpExtra'] = label == 'packager-extra-mcp'
    started = time.monotonic()
    try:
        current['observation'] = obs.observe(registry, name, version, args=args)
    except Exception as exc:
        current['probeError'] = {'type': type(exc).__name__, 'message': str(exc)[:1000]}
    current['elapsedSeconds'] = round(time.monotonic() - started, 3)
    print(json.dumps(current, ensure_ascii=False), flush=True)
