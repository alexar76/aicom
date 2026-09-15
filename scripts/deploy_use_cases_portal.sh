#!/usr/bin/env bash
# Deploy the static use-cases portal to its nginx web root.
#
# Data/JS/locales are uploaded before HTML so every visible document points to
# a complete release. The command intentionally does not use rsync --delete.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/use-cases-portal"
NGINX_SOURCE="$ROOT/deploy/nginx/use.modelmarket.dev.conf"
REMOTE=""
IDENTITY=""
INSTALL_NGINX=0
REMOTE_ROOT="/var/www/use.modelmarket.dev"

usage() {
  sed -n '2,8p' "$0"
  echo "Usage: $0 --remote USER@HOST [--identity PATH] [--install-nginx]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --identity) IDENTITY="${2:-}"; shift 2 ;;
    --install-nginx) INSTALL_NGINX=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ "$REMOTE" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] \
  || { echo "--remote must be an explicit USER@HOST" >&2; exit 2; }
if [[ -n "$IDENTITY" ]]; then
  [[ "$IDENTITY" =~ ^[A-Za-z0-9_./-]+$ && -f "$IDENTITY" ]] \
    || { echo "--identity must name an existing path without whitespace" >&2; exit 2; }
fi
[[ -d "$SOURCE" && -f "$SOURCE/index.html" && -f "$SOURCE/data/boards.json" ]] \
  || { echo "portal source is incomplete: $SOURCE" >&2; exit 1; }
[[ -f "$NGINX_SOURCE" ]] || { echo "missing nginx config: $NGINX_SOURCE" >&2; exit 1; }

python3 "$SOURCE/scripts/validate.py"

ssh_args=(-o BatchMode=yes -o ConnectTimeout=10)
if [[ -n "$IDENTITY" ]]; then
  ssh_args+=(-i "$IDENTITY" -o IdentitiesOnly=yes)
fi
rsync_rsh="ssh -o BatchMode=yes -o ConnectTimeout=10"
if [[ -n "$IDENTITY" ]]; then
  rsync_rsh+=" -i $IDENTITY -o IdentitiesOnly=yes"
fi

remote_exec() {
  ssh "${ssh_args[@]}" "$REMOTE" "$@"
}

# Do not write through a symlinked web root or a linked managed subdirectory.
remote_exec 'set -eu
root=/var/www/use.modelmarket.dev
test -d "$root"
test ! -L "$root"
linked=$(find "$root" -type l -print -quit)
test -z "$linked" || { echo "refusing linked portal path: $linked" >&2; exit 1; }
for part in assets css data js locales; do
  test -d "$root/$part"
  test ! -L "$root/$part"
done'

for part in assets css data js locales; do
  rsync -az -e "$rsync_rsh" \
    "$SOURCE/$part/" "$REMOTE:$REMOTE_ROOT/$part/"
done

# Documents are the release pointer and therefore land last.
rsync -az -e "$rsync_rsh" \
  "$SOURCE/index.html" "$SOURCE/ideas.html" "$SOURCE/.nojekyll" \
  "$REMOTE:$REMOTE_ROOT/"

if [[ "$INSTALL_NGINX" -eq 1 ]]; then
  scp "${ssh_args[@]}" "$NGINX_SOURCE" "$REMOTE:/tmp/use.modelmarket.dev.conf.next"
  remote_exec 'set -eu
current=/etc/nginx/sites-available/use.modelmarket.dev
test -f "$current"
test ! -L "$current"
backup="${current}.bak.$(date +%Y%m%d%H%M%S)"
cp -p "$current" "$backup"
install -m 0644 /tmp/use.modelmarket.dev.conf.next "$current"
if nginx -t; then
  systemctl reload nginx
  echo "nginx reloaded"
else
  mv "$backup" "$current"
  nginx -t
  echo "nginx config restored" >&2
  exit 1
fi'
fi

for relative in index.html ideas.html data/boards.json js/idea-page.js js/proof.js css/portal.css locales/en.json locales/ru.json; do
  local_sum="$(shasum -a 256 "$SOURCE/$relative" | awk '{print $1}')"
  remote_sum="$(remote_exec "sha256sum '$REMOTE_ROOT/$relative'" | awk '{print $1}')"
  [[ "$local_sum" == "$remote_sum" ]] \
    || { echo "checksum mismatch: $relative" >&2; exit 1; }
done

release="$(sed -n 's/.*const DATA_VERSION = "\([^"]*\)".*/\1/p' "$SOURCE/js/boards.js" | head -1)"
[[ -n "$release" ]] || { echo "could not resolve portal release" >&2; exit 1; }
curl -fsS "https://use.modelmarket.dev/index.html?release=$release" >/dev/null
curl -fsS "https://use.modelmarket.dev/data/boards.json?release=$release" >/dev/null
echo "Portal deployed: https://use.modelmarket.dev/?release=$release"
