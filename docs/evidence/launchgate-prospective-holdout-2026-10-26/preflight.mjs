import { readFileSync,writeFileSync } from 'node:fs';
import { makeGate,seed,baseMessages,body } from './study.mjs';
const cases=JSON.parse(readFileSync('/study/cases.json','utf8')).cases,requests=[];
for(const c of cases){
 for(const condition of ['clean','injected']){
  const s={slot_id:'preflight-'+c.case_id+'-'+condition,population:'natural',condition,seed_kind:null},g=makeGate(c,s),base=baseMessages(c,s,g);
  requests.push(body(base));
  const kinds=['violating-list','omitted-eligible'];if(c.oracle.optimal.length===1)kinds.push('suboptimal-selection');
  for(const kind of kinds){const p=seed(c,g,kind);requests.push(body(base,p,g.evaluate(p).feedback));}
 }
}
writeFileSync('/out/preflight-requests.jsonl',requests.map(r=>JSON.stringify(r)).join('\n')+'\n');
console.log(JSON.stringify({requestsChecked:requests.length}));
