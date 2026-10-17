import pathlib,shutil,subprocess,urllib.request,json,os
root=pathlib.Path('/root/visitor-journey-20261011'); backup=root/'backup'
# Check expected role, language, links and backend proxy before switching.
def get(url):
    with urllib.request.urlopen(url,timeout=60) as r: return r.read().decode()
assert 'Что создадим?' in get('http://127.0.0.1:9089/?lang=ru')
assert 'https://magic-ai-factory.com/?lang=ru' in get('http://127.0.0.1:9091/ru/')
assert json.loads(get('http://127.0.0.1:3848/api/config?lang=ru'))['strings']['back']=='Вернуться в фабрику'
assert 'journeyNext' in get('http://127.0.0.1:3848/?lang=ru')
assert get('http://127.0.0.1:9089/api/public/pipeline-status')
configs=[pathlib.Path('/etc/nginx/sites-available')/n for n in ['magic-ai-factory.com','modeldev.modelmarket.dev']]
for p in configs:
    if (backup/p.name).exists(): raise RuntimeError('Backup exists; review before repeating cutover')
    shutil.copy2(p,backup/p.name)
magic=configs[0].read_text(); assert magic.count('proxy_pass http://127.0.0.1:9080;')==1
magic=magic.replace('proxy_pass http://127.0.0.1:9080;','proxy_pass http://127.0.0.1:9089;')
assert magic.count('proxy_pass http://127.0.0.1:3847/;')==1
magic=magic.replace('proxy_pass http://127.0.0.1:3847/;','proxy_pass http://127.0.0.1:3848/;\n        proxy_intercept_errors on;\n        error_page 404 = @previous_landing_result;')
# Existing preview/download IDs stay available from the retained generator.
magic=magic.replace('    include /etc/nginx/snippets/argus-landing.conf;', '''    location @previous_landing_result {
        proxy_pass http://127.0.0.1:3847;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    include /etc/nginx/snippets/argus-landing.conf;''')
marketing=configs[1].read_text(); assert marketing.count('127.0.0.1:9088')==3
marketing=marketing.replace('127.0.0.1:9088','127.0.0.1:9091')
link=pathlib.Path('/var/www/ecosystem.modelmarket.dev'); old=os.readlink(link)
(backup/'ecosystem-target').write_text(old)
new=pathlib.Path('/var/www/ecosystem-visitor-20261011')
shutil.copytree(root/'scripts/github-io',new)
try:
    configs[0].write_text(magic); configs[1].write_text(marketing)
    subprocess.run(['nginx','-t'],check=True)
    staged=link.with_name(link.name+'.visitor-new'); staged.symlink_to(new); staged.replace(link)
    subprocess.run(['systemctl','reload','nginx'],check=True)
except BaseException:
    for p in configs: shutil.copy2(backup/p.name,p)
    if os.readlink(link)!=old:
        staged=link.with_name(link.name+'.visitor-rollback'); staged.symlink_to(old); staged.replace(link)
    subprocess.run(['nginx','-t'],check=True);subprocess.run(['systemctl','reload','nginx'],check=True)
    raise
print('CUTOVER_COMPLETE: factory 9089, marketing 9091, generator 3848, ecosystem static; previous services retained')
