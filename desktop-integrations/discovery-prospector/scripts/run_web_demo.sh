#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${FLUTTER_ROOT:-/root/flutter}/bin:$PATH"
cd "$ROOT"
flutter pub get
flutter build web --release --no-tree-shake-icons
fuser -k 9927/tcp 2>/dev/null || true
cd build/web
echo "Discovery Prospector: http://127.0.0.1:9927"
exec python3 -m http.server 9927 --bind 127.0.0.1
