import { readFileSync,writeFileSync } from 'node:fs';
import { requestFor } from './study.mjs';
const contexts=new Map(JSON.parse(readFileSync('/study/cohort.json','utf8')).contexts.map(c=>[c.context_id,c]));
const slots=JSON.parse(readFileSync('/study/slots.json','utf8'));
const requests=slots.map(s=>requestFor(contexts.get(s.context_id),s).body);
writeFileSync('/out/preflight-requests.jsonl',requests.map(r=>JSON.stringify(r)).join('\n')+'\n');
console.log(JSON.stringify({requestsChecked:requests.length}));
