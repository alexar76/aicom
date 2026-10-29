import { readFileSync, writeFileSync } from 'node:fs';
import { makeGate, seed, baseMessages, body } from './study.mjs';
const cases = new Map(JSON.parse(readFileSync('/study/cases.json', 'utf8')).cases.map(c => [c.pair_id, c]));
const slots = JSON.parse(readFileSync('/study/slots.json', 'utf8'));
const requests=[];
for(const slot of slots){
  const c=cases.get(slot.pair_id),gate=makeGate(c,slot),base=baseMessages(c,gate);
  requests.push(body(base));
  for(const kind of ['C','D']){const p=seed(c,gate,kind);requests.push(body(base,p,gate.evaluate(p).feedback));}
}
writeFileSync('/out/preflight-requests.jsonl',requests.map(r=>JSON.stringify(r)).join('\n')+'\n');
console.log(JSON.stringify({requestsChecked:requests.length}));
