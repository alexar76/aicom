"""Prepare immutable synthetic contexts and a fixed schedule; no runtime/model execution."""
from hashlib import sha256
import json,random
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'launchgate-review-factors-2026-10-26'
def put(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 original=json.loads((OLD/'cases.json').read_text());labels=json.loads((OLD/'initial-labels.json').read_text())
 cases=[]
 for row in original['cases']:
  assert sha256(row['initial_answer'].encode()).hexdigest()==row['initial_answer_sha256']
  cases.append({**row,'initial_grounding':labels[row['pair_id']]['initial']['grounding']})
 assert len(cases)==12 and sum(c['initial_grounding']=='contradicted' for c in cases)==4
 put(HERE/'cases.json',{'sourceCasesSha256':sha256((OLD/'cases.json').read_bytes()).hexdigest(),'cases':cases})
 slots=[]
 for c in cases:
  for repeat in range(8):
   populations=[('natural',None)]
   if c['initial_grounding']=='contradicted':populations.extend([('controlled','C'),('controlled','D')])
   for population,seed in populations:
    slot={'pair_id':c['pair_id'],'repeat':repeat,'population':population,'seed':seed}
    slot['slot_id']=sha256(json.dumps(slot,sort_keys=True).encode()).hexdigest()[:32];slots.append(slot)
 random.Random(2026102603).shuffle(slots)
 assert len(slots)==160 and len({s['slot_id'] for s in slots})==160
 put(HERE/'slots.json',slots)
 put(HERE/'pricing.json',{'checkedDate':'2026-10-26','source':'https://api-docs.deepseek.com/quick_start/pricing/',
  'modelAlias':'deepseek-flash','documentedVersion':'DeepSeek-V4.1-Flash-1017','peakUSDPerMillionTokens':{'inputMiss':.30,'inputHit':.006,'output':1.20},
  'offPeakMultiplier':.5,'expectedUSD':[.05,.10],'conservativeLedgerLimitUSD':.15,'reservationUSD':.01,
  'scope':'Usage-based peak upper accounting, not a provider invoice/balance statement; existing server, no rental purchase.'})
 print(json.dumps({'cases':len(cases),'natural':96,'controlled':64,'maxFreshCalls':416,'budgetUSD':.15}))
if __name__=='__main__':main()
