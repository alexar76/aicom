import json, os, pathlib, shutil, subprocess, time, urllib.request
root=pathlib.Path('/root/aicom-collaboration-20261011')
name='aicom-frontend-collaboration-marketing-20261011'
static=pathlib.Path('/var/www/ecosystem-collaboration-20261011')
link=pathlib.Path('/var/www/ecosystem.modelmarket.dev')
cfg=pathlib.Path('/etc/nginx/sites-available/modeldev.modelmarket.dev')
def run(*args): return subprocess.check_output(args,text=True).strip()
def get(url):
 with urllib.request.urlopen(url,timeout=30) as r: return r.read().decode()
assert link.is_symlink(), 'Expected the existing versioned ecosystem symlink'
assert not static.exists(), 'Release already exists; inspect before retry'
before=cfg.read_text(); assert before.count('proxy_pass http://127.0.0.1:9091;')==3
old_static=os.readlink(link)
info=json.loads(run('docker','inspect','aicom-frontend-visitor-marketing-20261011'))[0]
env=dict(item.split('=',1) for item in info['Config']['Env'])
assert env['AICOM_SITE_ROLE']=='factory-landing'
fd=os.open(root/'frontend.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
 for k,v in env.items():
  if '\n' in v or '\r' in v: raise ValueError('Unexpected multiline environment')
  f.write(k+'='+v+'\n')
run('docker','run','-d','--name',name,'--restart','unless-stopped','--network','aicom_aicom_net','--cap-drop','ALL','--security-opt','no-new-privileges:true','--env-file',str(root/'frontend.env'),'-p','127.0.0.1:9095:8080','ai-factory-frontend:collaboration-marketing-20261011')
for _ in range(30):
 if run('docker','inspect','--format','{{.State.Health.Status}}',name)=='healthy': break
 time.sleep(2)
else: raise RuntimeError('New frontend failed health check; production unchanged')
phrases={'en':'Your AI doesn’t have to do it all.','ru':'Вашему ИИ не нужно уметь всё.','es':'Tu IA no tiene que saber hacerlo todo.','fr':'Votre IA n’a pas besoin de tout savoir faire.','zh':'你的 AI 不必无所不能。'}
for lang,phrase in phrases.items():
 route='/' if lang=='en' else '/'+lang+'/'
 html=get('http://127.0.0.1:9095'+route)
 assert phrase in html and 'f-case-steps' in html, lang
 assert 'https://magic-ai-factory.com/?lang='+lang in html, lang
shutil.copytree(root/'ecosystem',static)
shutil.copy2(cfg,root/'modeldev.before')
(root/'rollback.json').write_text(json.dumps({'static':old_static,'config':str(cfg)}))
def switch_static(target):
 tmp=link.with_name(link.name+'.collaboration-next')
 assert not tmp.exists() and not tmp.is_symlink()
 tmp.symlink_to(target); os.replace(tmp,link)
try:
 switch_static(str(static))
 cfg.write_text(before.replace('proxy_pass http://127.0.0.1:9091;','proxy_pass http://127.0.0.1:9095;'))
 run('nginx','-t');run('systemctl','reload','nginx')
 for domain in ['modeldev.modelmarket.dev','ecosystem.modelmarket.dev']:
  assert phrases['en'] in get('https://'+domain+'/'), domain
except BaseException:
 cfg.write_text(before);switch_static(old_static)
 run('nginx','-t');run('systemctl','reload','nginx');raise
print(json.dumps({'factory_landing_container':name,'port':9095,'ecosystem_static':str(static),'previous_static':old_static,'previous_marketing_retained':True,'working_factory_unchanged':'aicom-frontend-catalog-shelves-20261011:9094'}))
