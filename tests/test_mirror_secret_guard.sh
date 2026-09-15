#!/usr/bin/env bash
# Regression test for the pre-publish secret guard.
#
# It exists because the guard was ASSUMED to work and did not: a tree containing
# data/remediation/conductor_key — a live Ed25519 key that signs the DeployOrders a node agent acts
# on — passed cleanly. The guard looked for PEM blocks and `PRIVATE_KEY=0x…` literals, and every
# signing key in this ecosystem is neither (oracle_core.signing writes a raw 64-byte binary seed).
# The keys were saved only by .gitignore, because the mirror commits from the git index; the one path
# .gitignore did not cover would have been enough to lose one.
#
# Run: bash tests/test_mirror_secret_guard.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUARD="$ROOT/scripts/verify_mirror_secrets.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ if [ "$1" = 0 ]; then echo "  ✓ $2"; pass=$((pass+1)); else echo "  ✗ $2"; fail=$((fail+1)); fi; }

# ── it must REFUSE a tree carrying key material ──────────────────────────────
mk_tree(){ local d="$TMP/$1"; rm -rf "$d"; mkdir -p "$d"; echo "# readme" > "$d/README.md"; echo "$d"; }

d=$(mk_tree named); mkdir -p "$d/data/remediation"
head -c 64 /dev/urandom > "$d/data/remediation/conductor_key"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses data/remediation/conductor_key"

d=$(mk_tree signing); mkdir -p "$d/data"
head -c 64 /dev/urandom > "$d/data/momus_signing_key"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses data/momus_signing_key"

# DETERMINISTIC key material. The first version of this case planted /dev/urandom bytes and passed by
# luck: the guard then relied on `grep -I`, which only calls a file binary when it finds a NUL byte, and
# 64 random bytes contain one just 22% of the time. The test was flaky AND the guard was leaky, and the
# flakiness is what hid the leak. So plant a fixed seed with the control bytes a real key has.
d=$(mk_tree renamed)
python3 - > "$d/innocuous_blob" <<'SEED'
import sys
# A plausible Ed25519 seed: high-entropy, no NUL at all, several control bytes — exactly the case the
# old NUL-based check waved through.
sys.stdout.buffer.write(bytes((i * 37 + 3) % 256 or 1 for i in range(64)))
SEED
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses a 64-byte key blob with an innocent name and NO NUL byte"

d=$(mk_tree nonul)
python3 - > "$d/seed.bin" <<'SEED'
import sys
# Belt: not a single NUL byte, so a NUL-based binary test would call this text. It is still a key.
sys.stdout.buffer.write(bytes(range(1, 65)))
SEED
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses key material grep -I would classify as text"

d=$(mk_tree sshkey); mkdir -p "$d/deploy"
head -c 64 /dev/urandom > "$d/deploy/conductor_ed25519"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses an *_ed25519 key file"

d=$(mk_tree pem)
# Split markers so this fixture source itself does not trip verify_mirror_secrets on the factory tree.
printf -- '-----BEGIN %s-----\nMC4CAQ\n-----END %s-----\n' 'PRIVATE KEY' 'PRIVATE KEY' > "$d/server.pem"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a PEM private key (pre-existing check)"

# ── and it must ACCEPT a clean tree, or it blocks every publish ──────────────
d=$(mk_tree clean); mkdir -p "$d/docs/badges" "$d/src"
printf '<svg xmlns="http://www.w3.org/2000/svg"></svg>' > "$d/docs/badges/ci.svg"
printf '\x89PNG\r\n\x1a\n' > "$d/logo.png"                      # tiny binary ASSET
head -c 200 /dev/urandom > "$d/docs/badges/favicon.ico"          # tiny binary ASSET
echo '{"a":1}' > "$d/src/config.json"
printf 'x' > "$d/src/marker"                                     # 1-byte TEXT
# A Cyrillic doc: every multibyte UTF-8 byte is non-printable under LC_ALL=C, so a naive
# "non-printable ratio" check would flag every translated document in this repo. Control bytes do not
# have that problem, and this row proves it.
printf '# Заголовок\n\nТекст с табом:\tи переводом строки.\n' > "$d/docs/ru.md"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "accepts a clean tree with small binary assets"

# ── text files that happen to carry ONE control byte ───────────────────────────────────────────────
# Both of these blocked a real publish. The guard used to hit on any control byte at all, which is
# right for a 32/64-byte seed and wrong for a 300-byte text file with one stray character in it.
# Key material runs ~13% control bytes; these are ~0.3%. If someone re-tightens the rule to "any",
# this row fails and says why.
mkdir -p "$d/docs/assets/icons" "$d/awr/vectors"
# Sizes match the real files that blocked the publish — 410 B and 299 B. That matters: below
# 129 bytes the guard is deliberately strict (a raw seed is 32 or 64), so an undersized fixture
# would fail here for the wrong reason and teach nothing.
python3 - "$d" <<'FIXTURES'
import sys, pathlib
d = pathlib.Path(sys.argv[1])
svg = ('<?xml version="1.0" encoding="UTF-8"?><!-- Lucide BarChart3 -->'
       '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
       'stroke="currentColor" stroke-width="2" stroke-linecap="round">'
       '<path d="M3 3v18h18"/><path d="M8 17V9"/><path d="M13 17V5"/><path d="M18 17v-6"/></svg>')
svg = svg + ' ' * (409 - len(svg)) + '\x01'
(d / 'docs/assets/icons/bar-chart-3.svg').write_text(svg, encoding='utf-8')
vec = ('{"c0-controls":"' + ''.join(f'\\u{i:04x}' for i in range(0, 32)) +
       '","raw":"\x02","note":"canonicalization vector: escaped vs raw"}')
(d / 'awr/vectors/escapes-all-forms.canonical').write_text(vec, encoding='utf-8')
print(f"  fixtures: svg={len(svg)}B  vector={len(vec)}B", file=sys.stderr)
FIXTURES
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "accepts text files carrying a single control byte (SVG icon, canonicalization vector)"

# ── and the density rule must not open a hole ──────────────────────────────────────────────────────
# A 300-byte blob of real key material has ~39 control bytes and must still be refused, so the
# threshold above cannot be widened into "large files are fine".
head -c 300 /dev/urandom > "$d/big_blob.bin" 2>/dev/null || python3 -c "
import os,sys; open(sys.argv[1],'wb').write(os.urandom(300))" "$d/big_blob.bin"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a 300-byte random blob (density stays key-like)"
rm -f "$d/big_blob.bin"

echo
echo "  $pass passed, $fail failed"
[ "$fail" = 0 ]
