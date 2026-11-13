#!/usr/bin/env bash
# Retire only the two inactive QA trees after checking their verified Borg read-back.
set -euo pipefail
umask 077
case ${1-} in ''|--apply) ;; *) exit 2 ;; esac
(( $# <= 1 ))

store=/var/lib/aicom/maintenance-archives
qa=$store/qa-20261113
borg_receipt=$store/qa-20261113-borg-readback.log
trees=(warden-tests aicom-verify)
exec 9>"$qa/.archive.lock"
flock -n 9
test "$(stat -c '%u:%a' "$qa")" = "0:700"
grep -qFx 'archive=hold-attested-qa-20261113' "$borg_receipt"
grep -q '^finished=' "$borg_receipt"

guard_references() {
  python3 - <<'PY'
import json
import os
from pathlib import Path
import re

roots = ("/opt/warden-tests", "/opt/aicom-verify")

def check(path, source):
    if isinstance(path, str) and any(path == r or path.startswith(r+"/") for r in roots):
        raise SystemExit(f"{source} references {path}")

for line in Path("/proc/self/mountinfo").read_text().splitlines():
    mountpoint = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), line.split()[4])
    check(mountpoint, "mount")

for conf in Path("/var/lib/docker/containers").glob("*/config.v2.json"):
    try:
        mounts = json.loads(conf.read_text()).get("MountPoints") or {}
    except FileNotFoundError:
        continue
    for mount in mounts.values():
        check(mount.get("Source"), "Docker bind")

for process in Path("/proc").glob("[0-9]*"):
    for ref in (process/"cwd", process/"exe", process/"root", *(process/"fd").glob("*")):
        try:
            check(os.readlink(ref).removesuffix(" (deleted)"), str(ref))
        except FileNotFoundError:
            continue
PY
}

verify_tree() {
  local tree=$1 parent=$2 path="$qa/$1.tar.zst" expected
  expected=$(sha256sum "$path")
  grep -qFx "off_host_sha256=${expected%% *} $tree.tar.zst" "$borg_receipt"
  test -d "$parent/$tree" && test ! -L "$parent/$tree"
  zstd -q -dc "$path" | tar --compare --acls --xattrs --xattrs-include='*' \
    --selinux --numeric-owner -C "$parent" -f -
  # Compare names independently so a file added after archive creation cannot be lost.
  local live_members archive_members
  live_members=$(mktemp "$qa/.live-members.XXXXXX")
  archive_members=$(mktemp "$qa/.archive-members.XXXXXX")
  (cd "$parent"; find "$tree" -xdev -print0 | LC_ALL=C sort -z) > "$live_members"
  zstd -q -dc "$path" | python3 -c '
import os, sys, tarfile
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as archive:
    for member in archive:
        sys.stdout.buffer.write(os.fsencode(member.name.rstrip("/")) + b"\0")
' | LC_ALL=C sort -z > "$archive_members"
  cmp "$live_members" "$archive_members"
  rm -- "$live_members" "$archive_members"
  printf '%s: archive bytes and all source members verified\n' "$tree"
}

guard_references
for tree in "${trees[@]}"; do
  verify_tree "$tree" /opt
done
[[ ${1-} == --apply ]] || exit 0
guard_references
cat > "$qa/OFFHOST.md" <<'DOC'
# QA archive locations

Both archives and their manifests are in attested's encrypted Borg archive
`hold-attested-qa-20261113`. The attested host keeps the compressed
`aicom-verify.tar.zst` locally. `warden-tests.tar.zst` is stored off-host.

To recover the WARDEN archive on attested as root, run:

```bash
set -euo pipefail
umask 077
base=var/lib/aicom/maintenance-archives/qa-20261113
cd "/$base"
test ! -e warden-tests.tar.zst
part=$(mktemp ./warden-tests.tar.zst.XXXXXX)
trap 'rm -f -- "$part"' EXIT
aicom-borg extract --stdout ::hold-attested-qa-20261113 "$base/warden-tests.tar.zst" > "$part"
test "$(sha256sum "$part" | cut -d' ' -f1)" = "$(awk '$2 == "warden-tests.tar.zst" {print $1}' SHA256SUMS)"
mv -T -n -- "$part" warden-tests.tar.zst
sha256sum -c SHA256SUMS
```

Follow RESTORE.md to extract a selected tree into a staging directory.
DOC

holding=$(mktemp -d /opt/.aicom-qa-retirement.XXXXXX)
restore_on_error() {
  for tree in "${trees[@]}"; do
    if [[ -d "$holding/$tree" && ! -e "/opt/$tree" ]]; then
      mv -T -- "$holding/$tree" "/opt/$tree"
    fi
  done
  rmdir "$holding"
}
trap restore_on_error EXIT
for tree in "${trees[@]}"; do
  mv -T -- "/opt/$tree" "$holding/$tree"
  verify_tree "$tree" "$holding"
done
trap - EXIT

rm -r --one-file-system -- "$holding/warden-tests" "$holding/aicom-verify"
rmdir "$holding"
# Keep aicom-verify compressed locally and leave both encrypted archives in the Borg hold.
rm -- "$qa/warden-tests.tar.zst"
printf 'QA originals retired with verified encrypted copy, UTC %s\n' "$(date -u +%FT%TZ)"
df -h /
