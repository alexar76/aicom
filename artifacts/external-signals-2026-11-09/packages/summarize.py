"""Derive bounded weekly counts and validate saved capture hashes."""
import collections,hashlib,json,pathlib
R=pathlib.Path(__file__).parent
windows=[('2026-10-19','2026-10-25'),('2026-10-26','2026-11-01'),('2026-11-02','2026-11-08')]
out={'scope':'Public GET only; registry downloads are not users; deps.dev is version scoped.','windows_utc':windows,'npm':[],'pypi':[],'dependents':[]}
for p in sorted(R.glob('downloads-*.raw')):
 d=json.loads(p.read_text()); rows=d['downloads']; vals=[]
 for a,b in windows:
  selected=[x for x in rows if a<=x['day']<=b]
  vals.append({'start':a,'end':b,'downloads':sum(x['downloads'] for x in selected),'returned_days':len(selected)})
 out['npm'].append({'package':d['package'],'start':d['start'],'end':d['end'],'weekly':vals,'latest_days':rows[-7:]})
for p in sorted(R.glob('overall-*.raw')):
 d=json.loads(p.read_text()); rows=[x for x in d['data'] if x['category']=='without_mirrors']; vals=[]
 for a,b in windows:
  selected=[x for x in rows if a<=x['date']<=b]
  vals.append({'start':a,'end':b,'downloads':sum(x['downloads'] for x in selected),'returned_days':len(selected)})
 out['pypi'].append({'package':d['package'],'first_returned_date':rows[0]['date'],'last_returned_date':rows[-1]['date'],'category':'without_mirrors','weekly':vals,'latest_rows':rows[-7:]})
for p in sorted(R.glob('deps-*.raw')):
 d=json.loads(p.read_text());out['dependents'].append(d)
d=json.loads((R/'shortformkit-full.raw').read_text());out['shortformkit']={'tested':d['tested'],'rows':[x for x in d['servers'] if any(s in json.dumps(x).lower() for s in ['alexar76','modelmarket.dev','attestedmemory'])]}
statuses=collections.Counter(); captures=[]
for idx in ['http-index.json','followup-index.json','final-index.json','research-index.json']:
 for x in json.loads((R/idx).read_text()):
  statuses[str(x.get('status','error'))]+=1
  p=R/(x['name']+'.raw')
  if 'sha256' in x: assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],p
  captures.append(x)
out['capture_count']=len(captures);out['capture_statuses']=dict(statuses)
hf=json.loads((R/'hf-histor.raw').read_text());oa=json.loads((R/'openalex-histor.raw').read_text())
out['research']={'huggingface':{k:hf.get(k) for k in ['id','downloads','likes','lastModified','createdAt']},'openalex':{k:oa.get(k) for k in ['id','doi','title','cited_by_count','updated_date','publication_date']}}
out['evidence_notes']=['shortformkit.raw is an 8,000,000-byte truncated first capture; use valid shortformkit-full.raw (8,539,637 bytes) for all derivations.','pypistats recent last_month is smaller than last_week for several packages; report derives explicit date windows only from overall.','Unreturned daily rows are not independently verified as zero; totals sum returned rows in the specified windows.','HISTOR first returned date is 2026-10-22, so the first displayed week is partial and should not be used for a complete-week growth claim.']
(R/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({'capture_count':out['capture_count'],'statuses':out['capture_statuses'],'version_graphs':len(out['dependents']),'nonzero_version_graphs':sum(x['totalCount']>0 for x in out['dependents']),'shortformkit_rows':len(out['shortformkit']['rows'])},indent=2))
