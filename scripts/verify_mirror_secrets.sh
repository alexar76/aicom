#!/usr/bin/env bash
# Fail before push if a satellite mirror tree contains secrets or runtime config.
set -euo pipefail

clone="${1:-}"
[[ -n "$clone" && -d "$clone" ]] || {
  echo "usage: verify_mirror_secrets.sh <clone-dir>" >&2
  exit 2
}

fail=0

for forbidden in .env .env.local .env.production dioscuri.config.json argus.config.json helios.config.yaml client_secret.json youtube_token.json; do
  if [[ -f "$clone/$forbidden" ]]; then
    echo "error: forbidden file in mirror: $forbidden" >&2
    fail=1
  fi
done

# Runtime secret files inside data/ (directory itself may exist e.g. alien-monitor fixtures).
if [[ -f "$clone/data/.env" ]] || find "$clone/data" -name '.env' -print -quit 2>/dev/null | grep -q .; then
  echo "error: .env under data/ must not be mirrored" >&2
  fail=1
fi

# Obvious token shapes — empty assignments in .env.example are fine (not present here).
if rg -q -i \
  '(npm_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[a-zA-Z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})' \
  "$clone" 2>/dev/null; then
  echo "error: suspected API token literal in mirror tree" >&2
  fail=1
fi

# Known private server IPs / SSH hostnames must never ship inside a mirror tree.
# The list is kept OUT of this tracked (and itself-mirrored) file so the addresses
# are not re-leaked here and the scanner can't match itself. Supply it via the
# MIRROR_FORBIDDEN_HOSTS env var (whitespace-separated) or an untracked, gitignored
# scripts/.mirror-forbidden-hosts file (one host/IP per line, # comments allowed).
forbidden_hosts_file="$(dirname "$0")/.mirror-forbidden-hosts"
forbidden_hosts="${MIRROR_FORBIDDEN_HOSTS:-}"
if [[ -z "$forbidden_hosts" && -f "$forbidden_hosts_file" ]]; then
  forbidden_hosts="$(grep -vE '^[[:space:]]*(#|$)' "$forbidden_hosts_file" | tr '\n' ' ')"
fi
if [[ -n "$forbidden_hosts" ]]; then
  rg_host_args=()
  for h in $forbidden_hosts; do rg_host_args+=(-e "$h"); done
  if rg -q -F "${rg_host_args[@]}" \
    -g '!.mirror-forbidden-hosts' \
    -g '!scripts/scrub_private_hosts.sh' \
    "$clone" 2>/dev/null; then
    echo "error: private server IP/hostname literal in mirror tree" >&2
    fail=1
  fi
elif [[ "${MIRROR_ALLOW_NO_HOST_LIST:-0}" == "1" ]]; then
  echo "warn: no MIRROR_FORBIDDEN_HOSTS / $forbidden_hosts_file — private-host check skipped by request" >&2
else
  # Fail closed. The list lives outside the repo, so CI has it only when a secret is
  # wired in; warning instead of failing meant the publish gate passed without ever
  # running the check it exists for. Set MIRROR_ALLOW_NO_HOST_LIST=1 to opt out.
  echo "error: no MIRROR_FORBIDDEN_HOSTS / $forbidden_hosts_file — refusing to certify the mirror" >&2
  fail=1
fi

# Bare hex credentials assigned to an *_TOKEN key. A real MESH_ADMIN_TOKEN shipped to
# the public alexar76/lottery mirror this way; it matched no other rule here.
if rg -q -e '(ADMIN|API|MESH|OPERATOR)_TOKEN["'"'"']?\s*[:=]\s*["'"'"']?[0-9a-f]{32,}' "$clone" 2>/dev/null; then
  echo "error: bare hex token literal in mirror tree" >&2
  fail=1
fi

# Extra credential shapes — AWS access keys, Google API keys, PEM private-key blocks.
# Real Google browser keys are AIzaSy…; bare AIza+35 matches random base64 in HTML assets.
if rg -q \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'AIzaSy[0-9A-Za-z_-]{33}' \
  -e '-----BEGIN (RSA |EC )?PRIVATE KEY-----' \
  "$clone" 2>/dev/null; then
  echo "error: suspected AWS/Google/PEM credential in mirror tree" >&2
  fail=1
fi

# Raw 0x hex private keys assigned via PRIVATE_KEY=, excluding the well-known
# Anvil/Hardhat default test keys already committed under lottery/.
# Public Anvil/Hardhat acct[0..9] — allowlisted for gitleaks (not real secrets).
anvil_test_keys=$(
  cat <<'ANVIL_KEYS'
0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a
0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6
0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a
0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba
0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e
0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356
0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97
0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6
ANVIL_KEYS
)
if rg --no-heading -o -i 'PRIVATE_KEY=0x[0-9a-fA-F]{64}' "$clone" 2>/dev/null \
  | grep -viF "$anvil_test_keys" | grep -q .; then
  echo "error: raw private key literal in mirror tree" >&2
  fail=1
fi

# ── Raw Ed25519 key material — the blind spot this guard had ──────────────────────────────────────
# The checks above look for PEM blocks and `PRIVATE_KEY=0x…` literals. Every signing key in THIS
# ecosystem is neither: oracle_core.signing writes a raw 64-byte binary seed+pubkey, so a planted
# `data/remediation/conductor_key` passed this guard cleanly while being a live key that signs the
# DeployOrders a node agent acts on. The other signing keys were saved only by .gitignore, because the
# mirror commits from the git index — one path that .gitignore did not cover was enough to lose one.
#
# So detect key material by SHAPE, not by name alone:
#   * a file whose name looks like a key, at any depth;
#   * any small file (<= 512 B) that is not text and not a known binary asset — the exact profile of a
#     raw seed. A 32/64-byte blob with no printable structure has no legitimate reason to ship.
# Both are name-independent enough that the next key format we invent is caught too.
key_hits=""
while IFS= read -r f; do
  case "$(basename "$f")" in
    *_signing_key|*_signing_key.*|conductor_key|*_ed25519|*_ed25519.key|id_rsa|id_ecdsa|*.pem|*.p12|*.pfx|*.jks)
      key_hits+="  $f (name looks like key material)"$'\n'; continue;;
  esac
  # Shape test: tiny + contains CONTROL bytes, which text never does.
  #
  # This deliberately does NOT use `grep -I`. GNU/BSD grep calls a file binary only when it finds a NUL
  # byte, and a raw 64-byte Ed25519 seed contains one just 22% of the time — so the first version of
  # this check caught roughly one key in five, and its test passed only because that run's random bytes
  # happened to include a NUL. A flaky test hiding a leaky guard is worse than no guard.
  #
  # Control bytes other than tab/newline/CR appear in no text file and in no UTF-8 sequence, but appear
  # in ~11% of positions in random key material — so a 64-byte key almost certainly has several
  # (P(none) ≈ 0.03%), while a Cyrillic Markdown file has exactly zero. That asymmetry is the test.
  size=$(wc -c < "$f" 2>/dev/null || echo 0)
  if [[ "$size" -gt 0 && "$size" -le 512 ]]; then
    case "$f" in
      *.png|*.jpg|*.jpeg|*.gif|*.ico|*.webp|*.avif|*.bmp|*.woff|*.woff2|*.ttf|*.otf|*.eot|*.wasm|*.pyc|*.so|*.dylib|*.node|*.pack|*.idx|*.mo|*.zip|*.gz|*.br) continue;;
    esac
    ctl=$(LC_ALL=C tr -dc '\000-\010\013\014\016-\037\177' < "$f" 2>/dev/null | wc -c | tr -d ' ')
    # "Any control byte at all" was too blunt above the key-sized range. It flagged
    # docs/assets/icons/bar-chart-3.svg (410 B, ONE control byte) and an AWR
    # canonicalization vector (299 B, one) — both plainly text, both blocking a
    # publish that had no secret in it. A guard that cries wolf gets switched off,
    # and this one stands between us and publishing a signing key.
    #
    # Density is what separates them. Control bytes are 33 of 256 values, so random
    # key material carries ~13% of them: a 64-byte seed has ~8, and P(fewer than 2)
    # is about 0.2%. A text file with a stray control character sits near 0.3%.
    #
    # So: below 129 bytes — the range where a raw 32/64-byte seed actually lives —
    # keep the strictest rule and treat a single control byte as a hit. Above it,
    # require key-like density. Both real secrets this caught (a 64-byte scanner
    # key with 9, a 32-byte salt with 3) are in the strict range and stay caught.
    if [[ "$size" -le 128 ]]; then
      threshold=1
    else
      threshold=$(( size * 3 / 100 ))
      [[ "$threshold" -lt 2 ]] && threshold=2
    fi
    if [[ "${ctl:-0}" -ge "$threshold" ]]; then
      key_hits+="  $f ($size bytes, $ctl control bytes — raw key seed shape)"$'\n'
    fi
  fi
done < <(find "$clone" -type f \
           -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
           -not -path '*/dist/*' -not -path '*/build/*' -not -path '*/target/*' \
           -not -path '*/.ruff_cache/*' -not -path '*/.hypothesis/*' \
           -not -path '*/data/prometheus/*' 2>/dev/null)

if [[ -n "$key_hits" ]]; then
  echo "error: raw key material in mirror tree — a signing key must never be published:" >&2
  printf '%s' "$key_hits" >&2
  fail=1
fi

# Stray satellite pollution — another repo's tree must never ship inside a mirror.
if [[ "$(basename "$clone")" == "dioscuri" ]]; then
  for stray_file in main.py config.yaml pipeline_worker.py; do
    if [[ -f "$clone/$stray_file" ]]; then
      echo "error: stray factory file in dioscuri mirror: $stray_file" >&2
      fail=1
    fi
  done
  for stray in acex web agents ai-service-mesh aimarket-hub alien-monitor argus lottery oracles platon plugins ecosystem-landing dioscuri contracts; do
    if [[ -d "$clone/$stray" ]]; then
      echo "error: stray $stray/ inside dioscuri mirror" >&2
      fail=1
    fi
  done
  if [[ -f "$clone/scripts/mirror_satellites.sh" || -f "$clone/scripts/publish_all_repos.sh" ]]; then
    echo "error: factory publish scripts must not be mirrored into dioscuri" >&2
    fail=1
  fi
fi

if find "$clone" -path '*/broadcast/*.json' -print -quit 2>/dev/null | grep -q .; then
  echo "error: Foundry broadcast artifacts must not be mirrored" >&2
  fail=1
fi

# SQLite runtime artifacts (including accidental :memory: files from connect(":memory:") bugs).
for junk in ":memory:" ":memory:-wal" ":memory:-shm"; do
  if [[ -e "$clone/$junk" ]]; then
    echo "error: SQLite runtime artifact in mirror: $junk" >&2
    fail=1
  fi
done
if find "$clone" -maxdepth 3 \( -name '*.sqlite3' -o -name '*.sqlite3-wal' -o -name '*.sqlite3-shm' \) -print -quit 2>/dev/null | grep -q .; then
  echo "error: SQLite database files must not be mirrored" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "OK mirror secrets check: $(basename "$clone")"
