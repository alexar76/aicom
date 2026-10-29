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

# Fixture paths cannot exempt complete credentials. Markers are assembled here
# so this script does not itself carry a complete credential shape.
plant_flow_fixture() {
  local dest="$1"
  printf -- '-----BEGIN OPENSSH %s-----\nplaceholder\n-----END OPENSSH %s-----\n' 'PRIVATE KEY' 'PRIVATE KEY' > "$dest"
  python3 -c 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_text(p.read_text()+("AKIA"+"ABCDEFGHIJKLMNOP")+"\n")' "$dest"
}
d=$(mk_tree flowfix); mkdir -p "$d/test"
plant_flow_fixture "$d/test/flow-guard.test.ts"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses credential shapes even in the flow-guard fixture path"
d=$(mk_tree flowother); mkdir -p "$d/test" "$d/warden/test"
plant_flow_fixture "$d/test/other.test.ts"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses the same shapes outside the flow-guard fixture"
plant_flow_fixture "$d/warden/test/flow-guard.test.ts"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses the shapes when another file in the tree carries them"

# Frozen acex ZK sigma-proof fixtures. The mirror clone is rooted at acex/, so
# these paths have no acex/ prefix. Exact files and sizes only. The same bytes
# elsewhere, another file in legacy-zk/, or a key-sized blob at the fixture
# path must still fail. Markers are not embedded here; the fixtures are copied.
zk_src="$ROOT/acex/contracts/solana/programs/acex-capital/tests/fixtures/legacy-zk"
zk_rel="contracts/solana/programs/acex-capital/tests/fixtures/legacy-zk"
d=$(mk_tree zkproof)
mkdir -p "$d/$zk_rel"
cp "$zk_src/pubkey_validity.proof" "$zk_src/zero_ciphertext.proof" "$d/$zk_rel/"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows the two frozen acex ZK proof fixtures"
d=$(mk_tree zkother)
mkdir -p "$d/fixtures/legacy-zk"
cp "$zk_src/pubkey_validity.proof" "$zk_src/zero_ciphertext.proof" "$d/fixtures/legacy-zk/"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses the same proof bytes outside the two fixture paths"
d=$(mk_tree zkdir)
mkdir -p "$d/$zk_rel"
cp "$zk_src/pubkey_validity.proof" "$zk_src/zero_ciphertext.proof" "$d/$zk_rel/"
python3 - > "$d/$zk_rel/seed.bin" <<'SEED'
import sys
sys.stdout.buffer.write(bytes((i * 37 + 3) % 256 or 1 for i in range(64)))
SEED
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a real key inside legacy-zk next to the proof fixtures"
d=$(mk_tree zksize)
mkdir -p "$d/$zk_rel"
python3 - > "$d/$zk_rel/pubkey_validity.proof" <<'SEED'
import sys
sys.stdout.buffer.write(bytes((i * 37 + 3) % 256 or 1 for i in range(64)))
SEED
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a key-sized blob at the proof fixture path"
d=$(mk_tree zkandkey)
mkdir -p "$d/$zk_rel" "$d/data"
cp "$zk_src/pubkey_validity.proof" "$zk_src/zero_ciphertext.proof" "$d/$zk_rel/"
python3 - > "$d/data/innocuous_blob" <<'SEED'
import sys
sys.stdout.buffer.write(bytes((i * 37 + 3) % 256 or 1 for i in range(64)))
SEED
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a real key elsewhere when the ZK proof fixtures are present"

# The treasury vendor tree ships momus/targets/quality-public-key.pem, a tracked
# verify pin. The name is *.pem, so the guard must read the header: a public key
# at that path is allowed, a private key under the same name is not.
d=$(mk_tree pubkey); mkdir -p "$d/vendor/momus/momus/targets"
printf -- '-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----\n' > "$d/vendor/momus/momus/targets/quality-public-key.pem"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows a tracked quality-public-key.pem whose header is a public key"

d=$(mk_tree privname); mkdir -p "$d/vendor/momus/momus/targets"
printf -- '-----BEGIN %s-----\nMC4CAQ\n-----END %s-----\n' 'PRIVATE KEY' 'PRIVATE KEY' > "$d/vendor/momus/momus/targets/quality-public-key.pem"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses quality-public-key.pem when the header is a private key"

d=$(mk_tree pubelsewhere); mkdir -p "$d/secrets"
printf -- '-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----\n' > "$d/secrets/quality-public-key.pem"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a public PEM outside the known quality-pin paths"

# Oracle signing-key storage module. The mirror clone is rooted at the
# satellite. Confirmed scanner paths:
#   vendor/oracle-core/oracle_core/_signing_key_storage.py
#   core/oracle_core/_signing_key_storage.py
#   oracles/platon/backend/oracle_platon/_signing_key_storage.py
#   backend/platon/_signing_key_storage.py
# The real module is code. Raw key bytes, a PEM, a tiny file, a lookalike,
# and the same filename on any other path must still fail. Not a
# *signing_key* whitelist.
storage_src="$ROOT/oracles/core/oracle_core/_signing_key_storage.py"
storage_rel="vendor/oracle-core/oracle_core/_signing_key_storage.py"
plant_raw_seed() {
  python3 - "$1" <<'SEED'
import sys
open(sys.argv[1], "wb").write(bytes((i * 37 + 3) % 256 or 1 for i in range(64)))
SEED
}
d=$(mk_tree storageok)
mkdir -p "$d/vendor/oracle-core/oracle_core"
cp "$storage_src" "$d/$storage_rel"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows the vendored oracle-core signing-key storage module"
d=$(mk_tree storagebytes)
mkdir -p "$d/vendor/oracle-core/oracle_core"
plant_raw_seed "$d/$storage_rel"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses raw key bytes named _signing_key_storage.py"
d=$(mk_tree storagepem)
mkdir -p "$d/vendor/oracle-core/oracle_core"
printf -- '-----BEGIN %s-----\nMC4CAQ\n-----END %s-----\n' 'PRIVATE KEY' 'PRIVATE KEY' > "$d/$storage_rel"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a PEM private key at the storage-module path"
d=$(mk_tree storagelookalike)
mkdir -p "$d/vendor/oracle-core/oracle_core"
python3 -c 'import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.write_text("# not the storage module\n" * 80)' "$d/$storage_rel"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a text file that only borrows the storage-module name"
d=$(mk_tree storageandkey)
mkdir -p "$d/vendor/oracle-core/oracle_core" "$d/data"
cp "$storage_src" "$d/$storage_rel"
plant_raw_seed "$d/vendor/oracle-core/oracle_core/_signing_key"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a real key with a similar name next to the storage module"
d=$(mk_tree storagehub)
mkdir -p "$d/aimarket_hub"
cp "$storage_src" "$d/aimarket_hub/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows the exact trusted storage implementation in another package"
d=$(mk_tree storageoracle)
mkdir -p "$d/core/oracle_core"
cp "$storage_src" "$d/core/oracle_core/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows the storage module at the oracles core mirror path"
d=$(mk_tree storageoracleplaton)
mkdir -p "$d/oracles/platon/backend/oracle_platon"
cp "$storage_src" "$d/oracles/platon/backend/oracle_platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows the storage module at the oracles platon mirror path"
d=$(mk_tree storageplaton)
mkdir -p "$d/backend/platon"
cp "$storage_src" "$d/backend/platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows the storage module at the platon mirror path"
d=$(mk_tree storageoracleprefix)
mkdir -p "$d/oracles/core/oracle_core"
cp "$storage_src" "$d/oracles/core/oracle_core/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows exact trusted storage code below a catalog prefix"
d=$(mk_tree storagewrongplaton)
mkdir -p "$d/backend/oracle_platon"
cp "$storage_src" "$d/backend/oracle_platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows exact trusted storage code at another package root"
d=$(mk_tree storageplatonprefix)
mkdir -p "$d/platon/backend/platon"
cp "$storage_src" "$d/platon/backend/platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; ok $? "allows exact trusted storage code with a satellite prefix"
d=$(mk_tree storagetiny)
mkdir -p "$d/core/oracle_core"
printf '%s\n' '# tiny stand-in' > "$d/core/oracle_core/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a tiny file at the oracles core mirror path"
d=$(mk_tree storageoraclepem)
mkdir -p "$d/oracles/platon/backend/oracle_platon"
printf -- '-----BEGIN %s-----\nMC4CAQ\n-----END %s-----\n' 'PRIVATE KEY' 'PRIVATE KEY' > "$d/oracles/platon/backend/oracle_platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a PEM private key at the oracles platon mirror path"
d=$(mk_tree storageplatonpem)
mkdir -p "$d/backend/platon"
printf -- '-----BEGIN %s-----\nMC4CAQ\n-----END %s-----\n' 'PRIVATE KEY' 'PRIVATE KEY' > "$d/backend/platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a PEM private key at the platon mirror path"
d=$(mk_tree storageplatontiny)
mkdir -p "$d/backend/platon"
printf '%s\n' 'def load_or_create_ed25519_keypair():' > "$d/backend/platon/_signing_key_storage.py"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "still refuses a tiny file at the platon mirror path"

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

# ── dotfiles, the ecosystem's own key formats, and a missing scanner ──────────────────────────────
# Hidden files ship (.env.example, .github/, .npmrc*) and rg skipped them: a private host sat in
# metis/deploy/skopos-test/.env.example unseen. The fixture host is a fake one supplied by env.
d=$(mk_tree dotfile); mkdir -p "$d/deploy/x"
echo "PROM_URL=http://host-under-test.invalid:9090" > "$d/deploy/x/.env.example"
MIRROR_FORBIDDEN_HOSTS="host-under-test.invalid" bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses a forbidden host inside a dotfile"

# Shapes assembled at run time so this file itself carries none of them.
for shape in "sk-or-v1-$(printf 'a%.0s' {1..48})" "sk-ant-api03-$(printf 'B%.0s' {1..40})" \
             "$(printf '1234567890'):AA$(printf 'x%.0s' {1..33})" "aimk_$(printf 'Q%.0s' {1..32})"; do
  d=$(mk_tree token)
  echo "KEY=$shape" > "$d/.env.example"
  bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses a ${shape:0:8}… credential in a dotfile"
done

d=$(mk_tree mldsa); mkdir -p "$d/data"
python3 -c "print('ab'*1312); print('cd'*4032)" > "$d/data/hub_signing_key_mldsa"
bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses an ML-DSA key file (<key>_mldsa, 12 KB of hex)"

# Without ripgrep every rule used to read as "no match" and the tree was certified.
d=$(mk_tree norg)
nobin="$TMP/nobin"; mkdir -p "$nobin"
for tool in bash basename dirname find grep head mktemp printf python3 rm tr wc cat; do
  p=$(command -v "$tool") && ln -sf "$p" "$nobin/$tool"
done
PATH="$nobin" bash "$GUARD" "$d" >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "refuses to certify anything when rg is missing"

echo
echo "  $pass passed, $fail failed"
[ "$fail" = 0 ]
