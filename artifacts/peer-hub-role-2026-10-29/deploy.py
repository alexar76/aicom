import hashlib,json,shutil,subprocess
from pathlib import Path

def run(*args,capture=False):
    return subprocess.run(args,check=True,text=True,capture_output=capture).stdout

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

release=Path(__file__).resolve().parent
repo=Path('/root/claudecode/aicom')
backend=repo/'alien-monitor/backend'
script=repo/'scripts/redeploy_alien_monitor_live.sh'
baseline=json.loads((release/'baseline.json').read_text())
spec=json.loads(run('docker','inspect','alien-monitor-live',capture=True))[0]
assert spec['Image']==baseline['image_id'],'LIVE image changed; recheck baseline'
assert sha(script)==baseline['script_sha256'],'Redeploy script changed; inspect first'
for name,source in baseline['sources'].items():
    assert sha(backend/name)==source['host_sha256'],'Host source changed: '+name
    actual=run('docker','exec','alien-monitor-live','sha256sum','/app/backend/'+name,capture=True).split()[0]
    assert actual==source['running_sha256'],'Running source changed: '+name
    compile((release/name).read_text(),name,'exec')
    for mount in spec.get('Mounts',[]):
        dest=mount['Destination'].rstrip('/')
        assert not ('/app/backend/'+name).startswith(dest+'/') and dest!='/app/backend/'+name,'Source is mounted'
    shutil.copy2(backend/name,release/('host-before-'+name))
old_image=spec['Config']['Image']
(release/'previous-image.txt').write_text(old_image+'\n')
image='alien-monitor:peer-hub-role-20261029'
copies=''.join('COPY --chown=10001:10001 '+name+' /app/backend/'+name+'\n' for name in baseline['sources'])
(release/'Dockerfile').write_text('FROM '+old_image+'\n'+copies)
run('docker','build','--network=none','-t',image,str(release))
smoke=run('docker','run','--rm','--network','none','--entrypoint','python','-v',str(release/'smoke.py')+':/tmp/smoke.py:ro',image,'/tmp/smoke.py',capture=True)
(release/'smoke-result.json').write_text(smoke)
print(smoke,flush=True)
current=json.loads(run('docker','inspect','alien-monitor-live',capture=True))[0]
assert current['Image']==baseline['image_id'],'LIVE image changed during build'
for name,source in baseline['sources'].items():
    assert sha(backend/name)==source['host_sha256'],'Host source changed during build'
for name in baseline['sources']:
    shutil.copy2(release/name,backend/name)
try:
    run(str(script),'alien-monitor-live','--image',image)
except BaseException:
    for name in baseline['sources']:
        shutil.copy2(release/('host-before-'+name),backend/name)
    run(str(script),'alien-monitor-live','--image',old_image)
    raise
result={'status':'deployed','container':'alien-monitor-live','previous_image':old_image,'image':image,'sources':{name:sha(release/name) for name in baseline['sources']},'release_directory':str(release)}
(release/'deploy-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
