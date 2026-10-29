import copy,json,unittest
from collections import Counter
from pathlib import Path
from study import schedule,body,decode,digest,ARMS
from constraint_claims import host_check

class FrozenStudy(unittest.TestCase):
 def setUp(self):self.cases=json.loads((Path(__file__).parent/'cases.json').read_text())['cases']
 def test_complete_balanced_schedule(self):
  s=schedule(self.cases);self.assertEqual(len(s),288)
  self.assertEqual(Counter(x['arm'] for x in s),dict.fromkeys(ARMS,96))
  self.assertEqual(len({(x['pair_id'],x['repeat'],x['arm']) for x in s}),288)
  for i in range(0,288,3):
   self.assertEqual(len({(x['pair_id'],x['repeat']) for x in s[i:i+3]}),1)
   self.assertEqual({x['arm'] for x in s[i:i+3]},set(ARMS))
 def test_schedule_is_reproducible(self):self.assertEqual(schedule(self.cases),schedule(self.cases))
 def test_no_reconstructed_initial_transcript(self):
  for c in self.cases:
   b=body(c,'review')
   self.assertEqual(b['messages'][:4],c['base_body']['messages']);self.assertEqual(len(b['messages']),6)
   self.assertEqual(b['messages'][4]['content'],c['initial_answer'])
   self.assertEqual(b['messages'][5],{'role':'user','content':'review'})
 def test_changed_initial_answer_fails_before_dispatch(self):
  c=copy.deepcopy(self.cases[0]);c['initial_answer']+='x'
  with self.assertRaises(AssertionError):body(c,'review')
 def test_invalid_and_incomplete_answers_remain_non_success(self):
  for text,finish in [('not JSON','stop'),('{}','stop'),('{"selected_hotel_id":"A","reason":""}','stop'),('{}','length')]:
   r={'status':'ok','provider_response':{'model':'deepseek-flash','choices':[{'finish_reason':finish,'message':{'content':text}}]}}
   self.assertNotEqual(decode(r)['status'],'ok')
 def test_unexpected_model_is_not_silently_accepted(self):
  r={'status':'ok','provider_response':{'model':'different','choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}}
  self.assertEqual(decode(r)['status'],'model_mismatch')
 def test_record_snapshots_bind_to_actual_rotated_transcripts(self):
  for c in self.cases:self.assertEqual(c['fixture']['records'],c['tool_result']['hotels'])
 def test_host_checks_use_frozen_user_constraints(self):
  for c in self.cases:
   x,_=host_check(c['initial_answer'],c['fixture'],'test',1)
   self.assertEqual(x['answerSha256'],digest(c['initial_answer']))
   self.assertEqual(x['rules'],c['fixture']['criterion']['constraints'])

if __name__=='__main__':unittest.main()
