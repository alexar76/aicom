"""Independent read-only reproduction of ACS #38 snapshot statistics, 2026-10-28."""
import gzip, json, hashlib, collections, bisect, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parents[3]
SNAP = ROOT/'artifacts/histor-zenodo-2026-10-20'
REG = ROOT.parent/'PromoMaterials/outreach/acs38-same-version-2026-10-28/registry-all-2026-10-28.jsonl.gz'
def rows(path):
    with gzip.open(path,'rt') as stream:
        for line in stream:
            yield json.loads(line)
def dt(s):
    if not s: return None
    s = s.replace('Z', '+00:00')
    s = re.sub(r'\.(\d+)(?=[+-]\d\d:)', lambda m: '.'+m[1][:6].ljust(6,'0'), s)
    return datetime.fromisoformat(s)
manifest = json.loads((SNAP/'manifest.json').read_text())
hashes = {}
for name in ['servers.jsonl.gz','changes.jsonl.gz','toolsets.jsonl.gz']:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with (SNAP/name).open('rb') as stream:
        while chunk := stream.read(1<<20):
            sha.update(chunk); md5.update(chunk)
    hashes[name] = {'sha256':sha.hexdigest(),'md5':md5.hexdigest(),'manifestMatches':sha.hexdigest()==manifest['files'][name]['sha256']}
servers={r['id']:r for r in rows(SNAP/'servers.jsonl.gz')}
published=collections.defaultdict(list)
registry_rows=0
for r in rows(REG):
    registry_rows += 1
    if r.get('publishedAt'): published[r['name']].append(dt(r['publishedAt']))
for values in published.values(): values.sort()
changes=collections.defaultdict(list)
all_detail=collections.Counter(); remote_detail=collections.Counter(); all_count=0
for c in rows(SNAP/'changes.jsonl.gz'):
    all_count+=1
    summ=json.loads(c['summaryJson']); detail=summ.get('detail','missing');all_detail[detail]+=1
    s=servers.get(c['serverId'])
    if s and s['endpoint'].startswith('https://'):
        mods=summ.get('modified') or []
        only_desc=bool(mods) and not summ.get('added') and not summ.get('removed') and all(set(m['fields'])=={'description'} for m in mods)
        changes[c['serverId']].append({'id':c['id'],'when':dt(c['observedAt']),'detail':detail,'descriptionOnly':only_desc})
        remote_detail[detail]+=1
out=collections.Counter(); same_servers=set(); same_ids=[]; same_detail=collections.Counter(); desc_ids=[]; namespace_total=collections.Counter();namespace_same=collections.Counter(); zero=[];bad=[]
sens=collections.Counter(); start_min=None
for sid, cs in changes.items():
    s=servers[sid]; start=dt(s['firstPinned']);pub=published.get(s['name']);ns=s['name'].split('/')[0]
    for c in sorted(cs,key=lambda r:(r['when'],r['id'])):
        when=c['when'];out['remoteChanges']+=1
        if start is None:out['noFirstPinned']+=1
        elif not pub:out['nameNotInRegistry']+=1
        else:
            out['judged']+=1;namespace_total[ns]+=1
            if start>when:bad.append(c['id'])
            if start==when:zero.append(c['id'])
            any_release = bisect.bisect_right(pub,when)>bisect.bisect_right(pub,start)
            if any_release:out['publishedInInterval']+=1
            else:
                out['noPublication']+=1;same_servers.add(sid);same_ids.append(c['id']);same_detail[c['detail']]+=1;namespace_same[ns]+=1
                if c['descriptionOnly']:desc_ids.append(c['id'])
            for lag in [0,1,7,30]:
                back=start-timedelta(days=lag)
                if bisect.bisect_right(pub,when)==bisect.bisect_right(pub,back): sens[lag]+=1
        start=when
largest=namespace_same.most_common(2)
excluded={n for n,_ in largest}
result={'snapshotCreatedAt':manifest['createdAt'],'changesFrom':manifest['changesFrom'],'changesUntil':manifest['changesUntil'],'hashes':hashes,'registryRows':registry_rows,'registryNames':len(published),'allChanges':all_count,'allDetail':dict(all_detail),'remoteServersChanged':len(changes),'remoteDetail':dict(remote_detail),'counts':dict(out),'sameServers':len(same_servers),'sameDetail':dict(same_detail),'descriptionOnlyAtSameVersion':len(desc_ids),'lagSensitivity':dict(sens),'largestNamespaces':largest,'excludingLargestTwo':{'same':sum(v for k,v in namespace_same.items() if k not in excluded),'judged':sum(v for k,v in namespace_total.items() if k not in excluded)},'negativeIntervals':bad,'zeroIntervals':zero,'notes':['Intervals are (previous change timestamp or firstPinned, current change timestamp], not (last successful observation, current observation].','Names are matched to all versions in a registry export taken 28 October; versions removed before that export may be missing.','No-publication classification does not prove which registry version or runtime deployment was active.','Description-only means only among retained/digested fields.']}
path=Path(__file__).with_name('snapshot-result.json');path.write_text(json.dumps(result,indent=2)+'\n')
Path(__file__).with_name('same-ids-independent.json').write_text(json.dumps(sorted(same_ids))+'\n')
print(json.dumps(result,indent=2))
