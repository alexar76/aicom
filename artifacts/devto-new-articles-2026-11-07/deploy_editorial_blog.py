"""Publish the four reviewed blog additions while retaining every existing page."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
assert json.loads((HERE / "blog-preflight.json").read_text())["checksPassed"]
plan = json.loads((HERE / "editorial-blog-plan.json").read_text())
slugs = [post["slug"] for post in plan]
ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "factory-vps"]


def remote_python(source):
    return subprocess.run(ssh + ["python3 -"], input=source, text=True,
                          capture_output=True, check=True).stdout.strip()


previous = remote_python("from pathlib import Path\nprint(Path('/var/www/modelmarket-blog').resolve(strict=True))\n")
assert previous.startswith("/var/www/modelmarket-blog-releases/")
release = "/var/www/modelmarket-blog-releases/" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-editorial-" + uuid.uuid4().hex[:6]
snapshot = json.loads(remote_python(f"""
from pathlib import Path
import hashlib,json,shutil
old=Path({previous!r}); new=Path({release!r})
assert Path('/var/www/modelmarket-blog').resolve(strict=True)==old
assert not new.exists()
for slug in {slugs!r}: assert not (old/'blog'/slug).exists(), 'Would overwrite existing post'
shutil.copytree(old,new,symlinks=True)
hashes={{str(p.relative_to(old)):hashlib.sha256(p.read_bytes()).hexdigest() for p in old.rglob('*') if p.is_file()}}
(new/'.editorial-before.json').write_text(json.dumps(hashes))
print(json.dumps({{'oldFiles':len(hashes),'oldIndex':hashes['blog/index.html']}}))
"""))
subprocess.run(["rsync", "-az", str(HERE / "blog-overlay") + "/", "factory-vps:" + release + "/blog/"], check=True)
changed = {"blog/index.html", "blog/feed.xml", "blog/sitemap.xml"}
result = json.loads(remote_python(f"""
from pathlib import Path
import hashlib,json,os,xml.etree.ElementTree as ET
link=Path('/var/www/modelmarket-blog');old=Path({previous!r});new=Path({release!r})
assert link.resolve(strict=True)==old, 'Concurrent deployment changed the live blog'
hashes=json.loads((new/'.editorial-before.json').read_text())
for name,digest in hashes.items():
 assert hashlib.sha256((old/name).read_bytes()).hexdigest()==digest, 'Concurrent change to existing file: '+name
 if name not in {changed!r}:
  assert hashlib.sha256((new/name).read_bytes()).hexdigest()==digest, 'Existing page or asset changed: '+name
assert hashlib.sha256((old/'blog/index.html').read_bytes()).hexdigest()=={snapshot['oldIndex']!r}
ns={{'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}}
old_urls={{x.text for x in ET.parse(old/'blog/sitemap.xml').findall('.//s:loc',ns)}}
new_urls={{x.text for x in ET.parse(new/'blog/sitemap.xml').findall('.//s:loc',ns)}}
assert old_urls <= new_urls, 'Existing URLs missing from new sitemap'
for slug in {slugs!r}:
 assert (new/'blog'/slug/'index.html').is_file()
 assert (new/'blog'/slug/'cover.webp').is_file()
 assert 'https://modelmarket.dev/blog/'+slug+'/' in new_urls
temporary=Path('/var/www/modelmarket-blog.editorial-new')
assert not temporary.exists() and not temporary.is_symlink()
temporary.symlink_to(new);os.replace(temporary,link)
print(json.dumps({{'activeRelease':str(link.resolve()),'preservedFiles':len(hashes)-3,'oldUrls':len(old_urls),'newUrls':len(new_urls)}}))
"""))
assert result["activeRelease"] == release
receipt = {"previousRelease": previous, **result, "deployedAt": datetime.now(timezone.utc).isoformat(),
           "previousReleaseRetained": True, "githubWrites": False, "addedUrls": [post["blogUrl"] for post in plan]}
(HERE / "editorial-blog-deployment.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
