#!/usr/bin/env python3
"""Local fixtures only. Generate a temporary public CA/server key, test real HTTPS and stdio MCP, then remove them."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent

def run(command, **kwargs):
    result=subprocess.run(command,text=True,capture_output=True,**kwargs)
    if result.returncode:
        print(result.stdout,end=''); print(result.stderr,end='')
        raise SystemExit(result.returncode)
    return result

python=run([shutil.which('python3'),'-m','unittest','discover','-s',str(HERE/'tests'),'-p','test_*.py','-v'])
print(python.stderr,end='')
with tempfile.TemporaryDirectory(prefix='qa-adapter-ca-') as directory:
    root=Path(directory)
    run(['openssl','req','-x509','-newkey','rsa:2048','-sha256','-nodes','-days','1','-subj','/CN=QA Adapter Fixture CA','-keyout',str(root/'ca.key'),'-out',str(root/'ca.crt')])
    run(['openssl','req','-new','-newkey','rsa:2048','-sha256','-nodes','-subj','/CN=127.0.0.1','-keyout',str(root/'server.key'),'-out',str(root/'server.csr')])
    (root/'extensions.cnf').write_text('subjectAltName=IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
    run(['openssl','x509','-req','-in',str(root/'server.csr'),'-CA',str(root/'ca.crt'),'-CAkey',str(root/'ca.key'),'-CAcreateserial','-days','1','-sha256','-extfile',str(root/'extensions.cnf'),'-out',str(root/'server.crt')])
    for key in ['ca.key','server.key']:(root/key).chmod(0o600)
    package=HERE.parents[2]/'artifacts'/'multica-qa-runner-2026-11-10'/'build'/'aimarket-warden-0.23.1-dev.20261108.tgz'
    preflight=run([shutil.which('python3'),str(HERE/'install.py'),'--package',str(package),'--ca',str(root/'ca.crt')])
    print(preflight.stdout,end='')
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'NODE_EXTRA_CA_CERTS':str(root/'ca.crt'),'QA_TEST_TLS_KEY':str(root/'server.key'),'QA_TEST_TLS_CERT':str(root/'server.crt')}
    result=run([shutil.which('node'),'--test',str(HERE/'tests'/'adapter.test.mjs')],env=env)
    print(result.stdout,end='')
    print(result.stderr,end='')
