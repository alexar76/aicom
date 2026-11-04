#!/usr/bin/env bash
# Run on factory-vps as root, e.g. ssh factory-vps 'sudo -n bash -s' < link-blog.sh.
# --check compares the live article and the exact planned addition without writing.
set -euo pipefail
if [[ $# -gt 1 || (${1:-} != "" && ${1:-} != "--check") ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi
exec python3 - "${1:-}" <<'PY'
import fcntl
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

slug = "two-public-records-of-mcp-tool-definitions-one-day-23190-servers-where-they-agree"
public_url = f"https://modelmarket.dev/blog/{slug}/"
root = Path("/var/www/modelmarket-blog")
releases = Path("/var/www/modelmarket-blog-releases")
paragraph = b"""<p>rugsnare's published pins tell the same story on a smaller scale. 18 package versions are in both
records, and 16 are identical. <code>mongodb-mcp-server@3.1.0</code> was started with a connection string
and read-only mode on one side and with neither on the other. <code>server-everything@2.0.1</code> lists four
more tools to a client that declares more capabilities.</p>"""
link = b"https://histor.modelmarket.dev/mongodb-mcp-read-only-tools.html?from=capture-conditions-article"
addition = (
    b'<p>Compare the tool names your MongoDB MCP client receives with and without <code>--readOnly</code>. '
    b'<a href="' + link + b'">Open the browser checker</a>.</p>'
)
check_only = sys.argv[1] == "--check"


def public_article():
    request = Request(
        f"{public_url}?blog_link_check={time.time_ns()}",
        headers={"Cache-Control": "no-cache", "User-Agent": "modelmarket-blog-release-check"},
    )
    with urlopen(request, timeout=15) as response:
        if response.status != 200 or not response.geturl().startswith(public_url):
            raise RuntimeError("Public article did not answer HTTP 200 at its expected URL")
        return response.read()


def atomic_write(path, data, original_stat):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".blog-link-", delete=False) as staging:
        temporary = Path(staging.name)
        try:
            if os.geteuid() == 0:
                os.fchown(staging.fileno(), original_stat.st_uid, original_stat.st_gid)
            os.fchmod(staging.fileno(), original_stat.st_mode & 0o777)
            staging.write(data)
            staging.flush()
            os.fsync(staging.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def run():
    if not root.is_symlink():
        raise RuntimeError("Expected the modelmarket blog release symlink")
    release = root.resolve(strict=True)
    if release.parent != releases:
        raise RuntimeError("Blog symlink does not identify an existing release directory")
    article = release / "blog" / slug / "index.html"
    if article.resolve(strict=True) != article or not article.is_file():
        raise RuntimeError("Unexpected article path")
    original = article.read_bytes()
    live = public_article()
    if paragraph not in live or original.count(paragraph) != 1:
        raise RuntimeError("Original MongoDB paragraph does not match the deployed article")
    if link in original:
        if original.count(addition) != 1 or paragraph + b"\n" + addition not in original or addition not in live:
            raise RuntimeError("Checker link exists in an unexpected form")
        print("Checker link already present locally and in the public article")
        return
    if link in live:
        raise RuntimeError("Public checker link differs from the active release file")
    candidate = original.replace(paragraph, paragraph + b"\n" + addition, 1)
    if check_only:
        print(f"Public and on-disk article match the original paragraph. Would update {article}")
        return
    if root.resolve(strict=True) != release or article.read_bytes() != original:
        raise RuntimeError("Blog release or article changed during the check")

    backups = Path("/var/backups/modelmarket-blog")
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="mongodb-link-", dir=backups))
    backup = directory / "index.html"
    shutil.copy2(article, backup)
    original_stat = article.stat()
    atomic_write(article, candidate, original_stat)
    try:
        if root.resolve(strict=True) != release or paragraph + b"\n" + addition not in public_article():
            raise RuntimeError("Public article did not return the expected checker link")
    except BaseException:
        if article.read_bytes() != candidate:
            raise RuntimeError(f"Concurrent change after release. Restore manually from {backup}")
        atomic_write(article, backup.read_bytes(), original_stat)
        raise
    print(f"Public article returned HTTP 200 with the checker link. Backup {backup}")


if check_only:
    run()
else:
    with Path("/run/lock/modelmarket-blog-link.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run()
PY
