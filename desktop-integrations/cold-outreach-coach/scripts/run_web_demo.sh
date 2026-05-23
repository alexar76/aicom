#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${FLUTTER_ROOT:-/root/flutter}/bin:$PATH"
cd "$ROOT"
flutter pub get
flutter build web --release --no-tree-shake-icons
fuser -k 9925/tcp 2>/dev/null || true
cd build/web
echo "Cold Outreach Coach: http://127.0.0.1:9925"
exec python3 -m http.server 9925 --bind 127.0.0.1
