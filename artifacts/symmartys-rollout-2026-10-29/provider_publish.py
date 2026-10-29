"""Publish the canonical route and persist the already verified runtime configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

os.umask(0o077)
work = Path('/root/symmartys-rollout-20261029')
baseline = json.loads((work / 'private-baseline.json').read_text())
with urllib.request.urlopen('http://127.0.0.1:9351/health', timeout=10) as response:
    assert json.load(response)['service'] == 'symmartys'
site = Path('/etc/nginx/sites-available/modelmarket.dev')
legacy_site = Path('/etc/nginx/sites-available/emporion.modelmarket.dev')
snippet = Path('/etc/nginx/snippets/symmartys.conf')
backups = work / 'nginx-before'
backups.mkdir(mode=0o700, exist_ok=True)
originals = {path: path.read_bytes() if path.exists() else None for path in (site, legacy_site, snippet)}
for path, body in originals.items():
    saved = backups / path.name
    if body is not None and not saved.exists():
        saved.write_bytes(body)
        saved.chmod(0o600)
text = site.read_text()
if 'include snippets/symmartys.conf;' not in text:
    assert text.count('include snippets/emporion.conf;') == 1
    text = text.replace('include snippets/emporion.conf;',
                        'include snippets/emporion.conf;\n    include snippets/symmartys.conf;')
snippet.write_text('''# SYMMARTYS canonical provider; legacy route remains an alias.
location = /providers/symmartys { return 301 /providers/symmartys/; }
location ^~ /providers/symmartys/ops/ { return 404; }
location /providers/symmartys/ {
    proxy_pass http://127.0.0.1:9351/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 90s;
    client_max_body_size 256k;
}
''')
snippet.chmod(0o644)
site.write_text(text)
legacy_site.write_text(legacy_site.read_text().replace('/opt/emporion/src/emporion/docs/landing',
                                                    '/opt/emporion/src/symmartys/docs/landing'))
try:
    subprocess.run(['nginx', '-t'], check=True)
except Exception:
    for path, body in originals.items():
        if body is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(body)
    raise
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)

runtime = json.loads(subprocess.check_output(['docker', 'inspect', 'symmartys']))[0]
env = dict(item.split('=', 1) for item in runtime['Config']['Env'] if '=' in item)
settings = {k: v for k, v in env.items()
            if k.startswith(('SYMMARTYS_', 'EMPORION_', 'ORACLE_')) or k == 'COMPANIES_HOUSE_API_KEY'}
settings.update(SYMMARTYS_VOLUME_NAME=baseline['volume_name'],
                SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY=baseline['manifest']['signature']['public_key'])
env_file = Path('/opt/emporion/.env')
saved_env = work / 'installation.env.before'
if not saved_env.exists():
    shutil.copyfile(env_file, saved_env)
    saved_env.chmod(0o600)
# JSON double quotes preserve escapes; $$ prevents Compose interpolation of literal dollars.
env_file.write_text(''.join(k + '=' + json.dumps(v.replace('$', '$$'), ensure_ascii=False) + '\n'
                           for k, v in sorted(settings.items())))
env_file.chmod(0o600)
compose = Path('/opt/emporion/src/symmartys/docker-compose.yml')
command = ['docker', 'compose', '-p', 'symmartys', '--env-file', str(env_file), '-f', str(compose),
           'config', '--format', 'json']
rendered = json.loads(subprocess.check_output(command, stderr=subprocess.PIPE))
service = rendered['services']['symmartys']
for key, value in settings.items():
    if key.startswith('SYMMARTYS_') and key not in ('SYMMARTYS_VOLUME_NAME', 'SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY'):
        assert service['environment'].get(key) == value, 'Persisted provider setting differs'
    elif key.startswith('ORACLE_') or key == 'COMPANIES_HOUSE_API_KEY':
        assert service['environment'].get(key) == value, 'Persisted operator setting differs'
assert rendered['volumes']['symmartys_data']['name'] == baseline['volume_name']
legacy_compose = Path('/opt/emporion/src/emporion/docker-compose.yml')
saved_compose = work / 'legacy-compose.before.yml'
if not saved_compose.exists():
    shutil.copyfile(legacy_compose, saved_compose)
legacy_compose.write_text('''# Compatibility entry point: the existing provider is now SYMMARTYS.
name: symmartys
include:
  - path: ../symmartys/docker-compose.yml
    env_file: ../../.env
''')
command[command.index(str(compose))] = str(legacy_compose)
legacy = json.loads(subprocess.check_output(command, stderr=subprocess.PIPE))
assert legacy['services']['symmartys']['environment'] == service['environment']
print(json.dumps({'canonical_route_configured': True, 'legacy_route_retained_as_alias': True,
                  'legacy_landing_uses_symmartys_source': True, 'nginx_validated_and_reloaded': True,
                  'compose_settings_preserved': True, 'legacy_compose_forwards_to_symmartys': True}))
