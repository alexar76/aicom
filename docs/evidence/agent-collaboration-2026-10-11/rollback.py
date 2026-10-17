import json,os,pathlib,subprocess
root=pathlib.Path('/root/aicom-collaboration-20261011')
state=json.loads((root/'rollback.json').read_text())
pathlib.Path(state['config']).write_bytes((root/'modeldev.before').read_bytes())
link=pathlib.Path('/var/www/ecosystem.modelmarket.dev')
tmp=link.with_name(link.name+'.rollback-next')
tmp.symlink_to(state['static']);os.replace(tmp,link)
subprocess.run(['nginx','-t'],check=True);subprocess.run(['systemctl','reload','nginx'],check=True)
print('Previous marketing and ecosystem releases restored.')
