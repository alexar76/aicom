import json, os, pathlib, subprocess
root=pathlib.Path('/root/visitor-journey-20261011')
def run(*args):
    return subprocess.check_output(args, text=True).strip()
def start(source,name,image,port,overrides):
    info=json.loads(run('docker','inspect',source))[0]
    env=dict(item.split('=',1) for item in info['Config']['Env'])
    env.update(overrides)
    envfile=root/(name+'.env')
    fd=os.open(envfile,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:
        for k,v in env.items():
            if '\n' in v or '\r' in v: raise RuntimeError('Multiline environment needs explicit handling')
            f.write(k+'='+v+'\n')
    internal=3847 if 'generator' in name else 8080
    run('docker','run','-d','--name',name,'--restart','unless-stopped','--network','aicom_aicom_net','--cap-drop','ALL','--security-opt','no-new-privileges:true','--env-file',str(envfile),'-p',f'127.0.0.1:{port}:{internal}',image)
    print(name, 'started',port)
start('aicom-app-1','aicom-frontend-visitor-20261011','ai-factory-frontend:visitor-20261011',9089,{'NEXT_PUBLIC_SITE_URL':'https://magic-ai-factory.com','AICOM_SITE_ROLE':'workspace','AICOM_BACKEND_INTERNAL_URL':'http://aicom-app-1:8081','INTERNAL_API_URL':'http://aicom-app-1:8081','NEXT_TELEMETRY_DISABLED':'1'})
start('aicom-frontend-modeldev-20261011','aicom-frontend-visitor-marketing-20261011','ai-factory-frontend:visitor-marketing-20261011',9091,{'NEXT_PUBLIC_SITE_URL':'https://modeldev.modelmarket.dev','AICOM_SITE_ROLE':'factory-landing','AICOM_BACKEND_INTERNAL_URL':'http://aicom-app-1:8081','INTERNAL_API_URL':'http://aicom-app-1:8081','NEXT_TELEMETRY_DISABLED':'1'})
start('aicom-landing-aicom-landing-1','aicom-generator-visitor-20261011','aicom-landing:visitor-20261011',3848,{'AICOM_LANDING_HOST':'0.0.0.0','AICOM_LANDING_PORT':'3847','AICOM_LANDING_BASE_PATH':'/landing-page-generation','AICOM_LANDING_PUBLIC_UI':'1'})
