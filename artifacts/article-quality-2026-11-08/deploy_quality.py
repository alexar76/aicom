"""Replace only the four authorized article directories and shared listings."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

HERE=Path(__file__).resolve().parent
plan=json.loads((HERE/'quality-plan.json').read_text())
assert json.loads((HERE/'preflight.json').read_text())['passed']
slugs=[p['slug'] for p in plan]
baseline={p['id']:p for p in json.loads((HERE/'baseline.json').read_text())['posts']}
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','factory-vps']


def run(source):
    return subprocess.run(ssh+['python3 -'],input=source,text=True,capture_output=True,check=True).stdout.strip()


previous=run("from pathlib import Path\nprint(Path('/var/www/modelmarket-blog').resolve(strict=True))")
assert previous.startswith('/var/www/modelmarket-blog-releases/')
release='/var/www/modelmarket-blog-releases/'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-quality-'+uuid.uuid4().hex[:6]
expected={p['slug']:baseline[p['id']]['blogHtmlSha256'] for p in plan}
snapshot=json.loads(run(f"""
from pathlib import Path
import hashlib,json,shutil
old=Path({previous!r});new=Path({release!r})
assert Path('/var/www/modelmarket-blog').resolve(strict=True)==old
assert not new.exists()
for slug,digest in {expected!r}.items():
 assert hashlib.sha256((old/'blog'/slug/'index.html').read_bytes()).hexdigest()==digest, 'Target article changed concurrently'
hashes={{str(p.relative_to(old)):hashlib.sha256(p.read_bytes()).hexdigest() for p in old.rglob('*') if p.is_file()}}
shutil.copytree(old,new,symlinks=True)
(new/'.quality-before.json').write_text(json.dumps(hashes))
print(json.dumps({{'oldFiles':len(hashes)}}))
"""))
subprocess.run(['rsync','-az',str(HERE/'blog-overlay')+'/','factory-vps:'+release+'/blog/'],check=True)
targets={"blog/index.html","blog/feed.xml","blog/sitemap.xml"}
prefixes=['blog/'+slug+'/' for slug in slugs]
assets={p['slug']:['cover-'+p['imageRevision']+'.webp']+[u.rsplit('/',1)[-1] for u in p['figures']+p['figureSvgs']] for p in plan}
result=json.loads(run(f"""
from pathlib import Path
import hashlib,json,os,xml.etree.ElementTree as ET
link=Path('/var/www/modelmarket-blog');old=Path({previous!r});new=Path({release!r})
assert link.resolve(strict=True)==old, 'Another deployment changed the live blog'
hashes=json.loads((new/'.quality-before.json').read_text());preserved=0
for name,digest in hashes.items():
 assert hashlib.sha256((old/name).read_bytes()).hexdigest()==digest, 'Concurrent file edit: '+name
 allowed=name in {targets!r} or any(name.startswith(prefix) for prefix in {prefixes!r})
 if not allowed:
  assert hashlib.sha256((new/name).read_bytes()).hexdigest()==digest, 'Unrelated file changed: '+name
  preserved+=1
ns={{'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}}
urls=lambda root:{{e.text for e in ET.parse(root/'blog/sitemap.xml').findall('.//s:loc',ns)}}
assert urls(old)<=urls(new), 'A previous post disappeared from the sitemap'
for slug,names in {assets!r}.items():
 for name in names: assert (new/'blog'/slug/name).is_file(), 'Missing public asset: '+name
temporary=Path('/var/www/modelmarket-blog.quality-new')
assert not temporary.exists() and not temporary.is_symlink()
temporary.symlink_to(new);os.replace(temporary,link)
print(json.dumps({{'activeRelease':str(link.resolve()),'preservedUnrelatedFiles':preserved,'sitemapUrls':len(urls(new))}}))
"""))
receipt={'previousRelease':previous,**result,'deployedAt':datetime.now(timezone.utc).isoformat(),'previousReleaseRetained':True,'githubWrites':False,'changedPosts':slugs}
(HERE/'blog-deployment.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
