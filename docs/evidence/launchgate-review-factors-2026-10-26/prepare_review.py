"""Make a complete deduplicated semantic-review index, hiding treatment labels."""
from hashlib import sha256
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/'run-01/out'
def main():
 rows=[json.loads(x) for x in (OUT/'runs.jsonl').read_text().splitlines()]
 cases={x['pair_id']:x for x in json.loads((OUT/'workcases.json').read_text())['cases']}
 reviews={};slots={}
 for row in rows:
  key=sha256((cases[row['pair_id']]['fixture']['id']+'\n'+row['answer']).encode()).hexdigest()
  slots[row['slot_id']]=key
  if key not in reviews:
   parsed=json.loads(row['answer']) if row['status']=='ok' else None
   reviews[key]={'fixture':cases[row['pair_id']]['fixture'],'answer':row['answer'],'answer_sha256':row['answer_sha256'],'parsed':parsed,'status':row['status']}
 ordered=sorted(reviews.items(),key=lambda x:x[0])
 result={'schema':'fresh-recheck-review-index/1','method':'complete exact-answer deduplication within fixture; treatment labels omitted from review index, not independent blinded adjudication','items':[{'review_id':key,**value} for key,value in ordered]}
 (HERE/'review-index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 (HERE/'review-slot-map.json').write_text(json.dumps(slots,indent=2)+'\n')
 (HERE/'review-text.jsonl').write_text(''.join(json.dumps({'n':i,'review_id':key,'fixture_id':value['fixture']['id'],'selected':value['parsed']['selected_hotel_id'] if value['parsed'] else None,'reason':value['parsed']['reason'] if value['parsed'] else None},ensure_ascii=False)+'\n' for i,(key,value) in enumerate(ordered)))
 prior=json.loads((HERE.parent/'launchgate-fresh-rechecks-2026-10-26/review-decisions.json').read_text())
 new=[(i,key,value) for i,(key,value) in enumerate(ordered) if key not in prior]
 (HERE/'unreviewed-text.jsonl').write_text(''.join(json.dumps({'n':i,'review_id':key,'fixture_id':value['fixture']['id'],'selected':value['parsed']['selected_hotel_id'] if value['parsed'] else None,'reason':value['parsed']['reason'] if value['parsed'] else None},ensure_ascii=False)+'\n' for i,key,value in new))
 print('Complete captured answers:',len(rows),'; unique fixture/answer texts:',len(ordered),'; previously reviewed exact matches:',len(ordered)-len(new),'; new full texts:',len(new))

if __name__=='__main__':main()
