import json, os, pathlib, shutil, subprocess, urllib.request
root = pathlib.Path('/root/catalog-shelves-20261011')
name = 'aicom-frontend-catalog-shelves-20261011'
def run(*args):
    return subprocess.check_output(args, text=True).strip()
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:9094'+path, timeout=90) as r:
        return r.read().decode()
info = json.loads(run('docker','inspect','aicom-frontend-catalog-audit-20261011'))[0]
env = dict(item.split('=',1) for item in info['Config']['Env'])
fd = os.open(root/'frontend.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
    for k,v in env.items():
        if '\n' in v or '\r' in v: raise ValueError('Unexpected multiline env')
        f.write(k+'='+v+'\n')
run('docker','run','-d','--name',name,'--restart','unless-stopped','--network','aicom_aicom_net','--cap-drop','ALL','--security-opt','no-new-privileges:true','--env-file',str(root/'frontend.env'),'-p','127.0.0.1:9094:8080','ai-factory-frontend:catalog-shelves-20261011')
# Docker health check waits for Next to be ready before the proxy can change.
import time
for _ in range(30):
    status=run('docker','inspect','--format','{{.State.Health.Status}}',name)
    if status=='healthy': break
    time.sleep(2)
else: raise RuntimeError('New frontend did not become healthy; old frontend is still live')
html=get('/?lang=en')
for marker in ['landing-products','full-products','Factory pipeline and style presets','Landing generator with optional web assistant']:
    assert marker in html, marker
products=json.loads(get('/api/products'))['products']
assert products
cfg=pathlib.Path('/etc/nginx/sites-available/magic-ai-factory.com')
before=cfg.read_text()
assert before.count('proxy_pass http://127.0.0.1:9093;')==1
backup=root/'magic-ai-factory.com.before'
assert not backup.exists()
shutil.copy2(cfg,backup)
try:
    cfg.write_text(before.replace('proxy_pass http://127.0.0.1:9093;','proxy_pass http://127.0.0.1:9094;'))
    run('nginx','-t')
    run('systemctl','reload','nginx')
except BaseException:
    shutil.copy2(backup,cfg)
    run('nginx','-t'); run('systemctl','reload','nginx')
    raise
print(json.dumps({'container':name,'port':9094,'public_products':len(products),'landings':sum(p.get('delivery_profile')=='marketing_landing' for p in products),'full_products':sum(p.get('delivery_profile')!='marketing_landing' for p in products),'previous_container_retained':True}))
