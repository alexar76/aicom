#!/usr/bin/env python3
"""Read public npm metadata and archive text in memory. No extraction or execution."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import io
import json
import re
from pathlib import Path
import tarfile
import urllib.parse
import urllib.request

HERE=Path(__file__).resolve().parent
CASES={17172:('@mapled/mcp','0.21.5','0.21.6'),
       20433:('@browserbridge/bbx','1.12.2','1.12.5'),
       23671:('@suparse/mcp','1.4.0','1.5.0')}

def fetch(url,limit=50_000_000):
    request=urllib.request.Request(url,headers={'User-Agent':'HISTOR-public-evidence-review/1.0'})
    with urllib.request.urlopen(request,timeout=60) as response:
        body=response.read(limit+1)
        assert len(body)<=limit,'archive limit exceeded'
        return body,{'url':url,'finalURL':response.url,'status':response.status,
                     'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}

def inspect(job):
    event_id,package,side,version=job
    out=HERE/'real-cases'/str(event_id)
    raw,meta=fetch(f'https://registry.npmjs.org/{urllib.parse.quote(package,safe="")}/{version}',2_000_000)
    (out/f'{side}-npm-metadata.json').write_bytes(raw)
    npm=json.loads(raw)
    assert npm['name']==package and npm['version']==version
    archive,archive_meta=fetch(npm['dist']['tarball'])
    sha1=hashlib.sha1(archive).hexdigest()
    assert sha1==npm['dist']['shasum']
    algorithm,expected=npm['dist']['integrity'].split('-',1)
    assert algorithm in ('sha512','sha256')
    actual=base64.b64encode(hashlib.new(algorithm,archive).digest()).decode()
    assert actual==expected
    tools=json.loads((out/f'{side}-toolsets.json').read_text())
    descriptions={t['name']:t.get('description','') for t in tools}
    matches=[]
    contexts=[]
    package_json=None
    scanned=[]
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        for member in tar.getmembers():
            if not member.isfile():continue
            if member.name=='package/package.json':
                package_json=json.load(tar.extractfile(member))
            if member.size>10_000_000 or not member.name.endswith(('.js','.mjs','.cjs','.json','.ts')):continue
            value=tar.extractfile(member).read().decode('utf-8',errors='replace')
            scanned.append({'name':member.name,'bytes':member.size})
            literal = r'"(?:[^"\\]|\\.)*"'
            concatenated=[]
            for match in re.finditer(r'\bdescription\s*:\s*('+literal+r'(?:\s*\+\s*'+literal+r')*)',value):
                try:
                    joined=''.join(json.loads(token) for token in re.findall(literal,match.group(1)))
                except ValueError: continue
                concatenated.append((joined,value.count('\n',0,match.start())+1))
            if event_id==17172 and member.name.endswith('tools.js'):
                for keyword in ['propose_setup_plan','without asking','awaiting_approval']:
                    start=value.find(keyword)
                    if start>=0:contexts.append({'file':member.name,'keyword':keyword,'context':value[max(0,start-250):start+2000]})
            for tool,description in descriptions.items():
                if not description:continue
                variants={'verbatim':description,
                          'JSON-escaped-unicode':json.dumps(description,ensure_ascii=False)[1:-1],
                          'JSON-escaped-ascii':json.dumps(description,ensure_ascii=True)[1:-1],
                          'JS-single-quoted':description.replace('\\','\\\\').replace("'","\\'").replace('\n','\\n').replace('\r','\\r').replace('\t','\\t')}
                for style,needle in variants.items():
                    if needle in value:
                        matches.append({'tool':tool,'file':member.name,'match':style,
                                        'fullDescriptionLength':len(description)})
                        break
                else:
                    for joined,line in concatenated:
                        if joined==description:
                            matches.append({'tool':tool,'file':member.name,'line':line,'match':'concatenated-JSON-string-literals','fullDescriptionLength':len(description)})
                            break
    report={'changeId':event_id,'side':side,'package':package,'version':version,
            'metadataRequest':meta,'archiveRequest':archive_meta,
            'integrityVerified':npm['dist']['integrity'],'sha1Verified':sha1,
            'packageBin':package_json.get('bin') if package_json else None,
            'packageEngines':package_json.get('engines') if package_json else None,
            'packageScripts':package_json.get('scripts') if package_json else None,
            'keywordContexts':contexts,'textFilesScanned':scanned,'fullDescriptionMatches':matches,
            'matchedToolCount':len({m['tool'] for m in matches}),
            'snapshotToolCount':len(tools),
            'scope':'Archive read in memory, no extraction, npm install, lifecycle scripts or package code execution.'}
    (out/f'{side}-npm-static-inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report

def main():
    jobs=[(event_id,package,side,version) for event_id,(package,old,new) in CASES.items()
          for side,version in [('from',old),('to',new)]]
    with ThreadPoolExecutor(max_workers=3) as pool:
        reports=list(pool.map(inspect,jobs))
    summary={'inspectedAt':datetime.now(timezone.utc).isoformat(),
             'cases':[{k:r[k] for k in ('changeId','side','package','version','integrityVerified','packageBin','matchedToolCount','snapshotToolCount')} for r in reports]}
    (HERE/'real-cases'/'npm-static-inspection.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
