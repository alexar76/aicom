"""Only bounded diagnostic classes/statuses for the known already-paid operation."""
import json,pathlib,subprocess
HERE=pathlib.Path(__file__).resolve().parent
REMOTE=r'''
import subprocess,json,re
r=subprocess.run(['docker','logs','--since','2026-11-08T08:34:00Z','--until','2026-11-08T08:44:00Z','--tail','400','modelmarket-hub'],capture_output=True,text=True)
lines=(r.stdout+'\n'+r.stderr).splitlines()
allowed_classes=('TypeError','AttributeError','ValueError','NameError','KeyError','RuntimeError','TimeoutError','HTTPStatusError','ReadTimeout','ConnectError','AssertionError','StopIteration','InvalidSignature','SchemaError','ValidationError','JSONDecodeError')
classes=[];frames=[];codes={};http=[]
for line in lines:
 for cls in allowed_classes:
  if re.match(r'^\s*'+re.escape(cls)+r'\b',line):classes.append(cls)
 m=re.search(r'File "([^"\n]+\.py)", line (\d+), in ([A-Za-z_][A-Za-z_0-9]*)',line)
 if m:frames.append({'file_basename':m[1].rsplit('/',1)[-1],'line':int(m[2]),'function':m[3]})
 for code in ('child_failed','job_required','job_invalid','job_replayed','job_limit','allowance_required','daily_cap_reached','daily_cap_unavailable','price_limit_exceeded','payment_invalid','internal_error','reconciliation_required'):
  if code in line:codes[code]=codes.get(code,0)+1
 m=re.search(r'"(?:POST|GET) ([^ ?"]+)(?:\?[^ ]*)? HTTP/[0-9.]+" (\d{3})',line)
 if m and (m[1].startswith('/ai-market/v2/operations/') or m[1]=='/ai-market/v2/invoke' or m[1].startswith('/providers/weather-witness/')):http.append({'route':'seller_operation' if '/operations/' in m[1] else 'provider_invoke' if '/providers/' in m[1] else 'hub_invoke','status':int(m[2])})
print(json.dumps({'container':'modelmarket-hub','window_utc':['2026-11-08T08:34:00Z','2026-11-08T08:44:00Z'],'bounded_log_lines_examined':len(lines),'exception_classes':classes,'traceback_frames':frames[-35:],'known_error_code_counts':codes,'selected_http_statuses':http[-35:],'raw_messages_or_env_emitted':False,'read_only':True}))
'''
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no','factory-vps','python3 -'],input=REMOTE,capture_output=True,text=True,timeout=35)
if p.returncode:raise RuntimeError('Bounded diagnostic classification failed; raw diagnostics suppressed')
d=json.loads(p.stdout);(HERE/'factory-hub-error-codes.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d))
