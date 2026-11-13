#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p bundle
archive=https://deb.debian.org/debian-security
paths=(dists/trixie-security/InRelease dists/trixie-security/main/binary-amd64/Packages.xz
    pool/updates/main/a/apt/apt_3.0.4_amd64.deb
    pool/updates/main/a/apt/libapt-pkg7.0_3.0.4_amd64.deb
    pool/updates/main/z/zlib/zlib1g_1.3.dfsg+really1.3.1-1+deb13u1_amd64.deb)
for path in "${paths[@]}"; do
    name=${path##*/}
    curl --proto '=https' --tlsv1.2 -fsS --retry 2 --max-time 30 "$archive/$path" -o "bundle/$name.tmp"
    mv "bundle/$name.tmp" "bundle/$name"
done
cp verify-debian.py bundle/verify-debian.py
