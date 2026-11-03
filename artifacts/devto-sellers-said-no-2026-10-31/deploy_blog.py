"""Deploy the already-verified static blog build, retaining the previous release."""
from pathlib import Path
import datetime
import json
import shlex
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
assert json.loads((EVIDENCE / "blog-preflight.json").read_text())["checksPassed"]
host = "factory-vps"
ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host]


def remote(command):
    return subprocess.run(ssh + [command], check=True, capture_output=True, text=True).stdout.strip()


previous = remote("readlink -f /var/www/modelmarket-blog")
assert previous.startswith("/var/www/modelmarket-blog-releases/")
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
release = f"/var/www/modelmarket-blog-releases/{stamp}-sellers-{uuid.uuid4().hex[:6]}"
remote("mkdir -p " + shlex.quote(release + "/blog"))
subprocess.run(["rsync", "-az", "--delete", str(ROOT / "modelmarket-blog/dist") + "/", host + ":" + release + "/blog/"], check=True)
script = f"""import os
from pathlib import Path
link = Path('/var/www/modelmarket-blog')
assert str(link.resolve()) == {previous!r}, 'Another deployment changed the active blog'
new = Path({release!r})
assert (new / 'blog/index.html').is_file()
assert (new / 'blog/we-built-a-marketplace-for-ai-agents-sellers-told-us-the-integration-wasnt-worth-it/index.html').is_file()
temporary = Path('/var/www/modelmarket-blog.sellers-new')
assert not temporary.exists() and not temporary.is_symlink()
temporary.symlink_to(new)
os.replace(temporary, link)
print(link.resolve())
"""
active = remote("python3 -c " + shlex.quote(script))
assert active == release
receipt = {
    "host": host,
    "previousRelease": previous,
    "activeRelease": active,
    "deployedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "previousReleaseRetained": True,
    "noServiceRestart": True,
    "githubWrites": False,
    "postUrl": "https://modelmarket.dev/blog/we-built-a-marketplace-for-ai-agents-sellers-told-us-the-integration-wasnt-worth-it/",
}
(EVIDENCE / "blog-deployment.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
