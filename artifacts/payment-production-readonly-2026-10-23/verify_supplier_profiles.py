"""Query existing wholesale profiles; never order, cancel, refund or sign."""
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
source = '''import json,subprocess
script="""
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { supplierFromEnv } from './src/config.js';
import { asSupplier } from './src/supplier.js';
const supplier=asSupplier(supplierFromEnv(process.env));
const records=JSON.parse(await readFile('/data/orders.json','utf8'));
for(const [key,record] of Object.entries(records).filter(([,x])=>x.profileId && x.refund?.status==='refunded')){
 const profiles=await supplier.profiles({profileId:record.profileId});
 console.log(JSON.stringify({record_ref:createHash('sha256').update(key).digest('hex').slice(0,12),profiles:profiles.map(p=>({state:p.state,installed:p.installed,data_used:p.dataUsedBytes})),read_only:true}));
}
"""
for container in ['esim-node','esim-test-rails']:
 result=subprocess.run(['docker','exec','-i',container,'node','--input-type=module','-'],input=script,capture_output=True,text=True,check=True)
 print(result.stdout,end='')
'''
raw = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'factory-vps', shlex.join(['python3', '-c', source])], text=True)
records = [json.loads(line) for line in raw.splitlines()]
assert len(records) == 4
assert all(len(r['profiles']) == 1 and r['profiles'][0] == {'state':'CANCEL','installed':False,'data_used':0} for r in records)
(HERE / 'supplier-verification.json').write_text(json.dumps(records, indent=2) + '\n')
print(json.dumps({'verified_cancelled_unused_profiles':len(records),'read_only':True}))
