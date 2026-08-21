#!/usr/bin/env bash
# Publish a Python package from the monorepo (or satellite path) to PyPI.
#
# Usage:
#   PYPI_API_TOKEN=pypi-xxx ./scripts/publish_pypi.sh aimarket-agent
#   ./scripts/publish_pypi.sh aimarket-agent --dry-run
#   ./scripts/publish_pypi.sh aimarket-agent --testpypi
#
# Requires: python3 -m pip install build twine
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PKG="${1:-}"
DRY_RUN=0
TEST_PYPI=0

usage() {
  cat <<'EOF'
publish_pypi.sh — build and upload a package to PyPI

  PYPI_API_TOKEN=pypi-... ./scripts/publish_pypi.sh <package-dir>

  <package-dir>  Path under monorepo root (e.g. aimarket-agent, aimarket-hub)

Options:
  --dry-run     Build + twine check only
  --testpypi    Upload to https://test.pypi.org (token from TESTPYPI_API_TOKEN)
  -h, --help    This help

First-time setup:
  1. Create account: https://pypi.org/account/register/
  2. Enable 2FA (required for new projects)
  3. Create API token: https://pypi.org/manage/account/token/
     Scope: "Entire account" (first upload) or project aimarket-agent
  4. export PYPI_API_TOKEN=pypi-...
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --testpypi) TEST_PYPI=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage; exit 1 ;;
    *) PKG="$1"; shift ;;
  esac
done

[[ -n "$PKG" ]] || { usage; exit 1; }
[[ -f "$ROOT/$PKG/pyproject.toml" ]] || {
  echo "error: no pyproject.toml at $ROOT/$PKG/" >&2
  exit 2
}

python3 -m pip install --quiet --upgrade pip build twine

echo "== Build $PKG =="
cd "$ROOT/$PKG"
rm -rf dist build *.egg-info
python3 -m build
python3 -m twine check --strict dist/*

# ── Secret gate ───────────────────────────────────────────────────────────────
# Runs on every build, including --dry-run, and BEFORE any upload. A PyPI version can be
# yanked but never replaced or truly withdrawn, so a secret published here is published
# permanently — the artifact stays downloadable from the yanked release.
#
# This is not hypothetical. hatchling, given no explicit sdist file set, walks UP the tree for
# a .gitignore and uses it as its exclusion list. Inside the monorepo it finds one whose
# `**/data/` rule hides key material; build the same package where that ancestor is not
# reachable — a CI checkout of one subdirectory, a Docker build context, an rsync'd release
# dir — and the rule disappears with it. Reproduced 2026-07-30: an out-of-tree sdist build of
# oracles/oracles/chronos packaged data/chronos_signing_key, an Ed25519 PRIVATE key, in
# plaintext. Whoever holds an oracle's signing key can forge its receipts, which is the entire
# trust story of this ecosystem.
#
# Only oracles/core and aimarket-bridges declare allow-lists today; 17 oracles, both platon
# trees and gaia do not. (An earlier version of this comment claimed they all did — they never
# did, and a comment asserting a protection that is absent is worse than no comment.) So this
# gate is not a backstop for a solved problem, it is the only thing standing in front of most of
# these packages.
#
# It also refuses PATH TRAVERSAL, which is not a secret-leak problem but belongs to the same
# family: something outside the package escaping into the artifact. `aimarket-platon 0.1.0` is
# live on PyPI right now carrying `aimarket_platon-0.1.0/../README.md`, and pip refuses to
# install that sdist outright — "would be extracted to ... which is outside the destination".
# The first version of this gate passed it, because it only looked for secrets by name. A member
# that escapes its own root is malformed by construction and can never be right.
echo "== Secret gate =="
gate_hits=""
for archive in dist/*.tar.gz dist/*.whl; do
  [[ -e "$archive" ]] || continue
  if [[ "$archive" == *.tar.gz ]]; then
    listing="$(tar -tzf "$archive")"
  else
    listing="$(unzip -Z1 "$archive")"
  fi
  # Paths that must never be inside a distribution. `data/` covers the oracle signing keys and
  # the hub's operational databases; .gitignore is not a secret itself but IS a map of where
  # every secret in the private monorepo lives, and it has shipped.
  # `.env.example` is the one dotenv filename that is meant to ship (scaffold templates).
  # Real secrets live in `.env`, `.env.local`, `.env.production`, etc.
  bad="$(printf '%s\n' "$listing" | grep -Ei '(^|/)(data)/|_signing_key|signing_key$|(^|/)\.env$|(^|/)\.env\.(local|prod|production|development|dev|secret|private)($|\.)|\.pem$|\.key$|(^|/)id_rsa|\.sqlite3?$' || true)"
  if [[ -n "$bad" ]]; then
    gate_hits+="  $archive:"$'\n'"$(printf '%s\n' "$bad" | sed 's/^/    /')"$'\n'
  fi

  # Path traversal / absolute members. pip treats these as a security violation and refuses the
  # archive, so such a distribution is not merely untidy — it cannot be installed at all from
  # source. Checked by structure rather than by name, because the offending file is usually
  # something innocuous like a README that the build reached for one directory up.
  escapes="$(printf '%s\n' "$listing" | grep -E '(^|/)\.\.(/|$)|^/' || true)"
  if [[ -n "$escapes" ]]; then
    gate_hits+="  $archive: member(s) escape the archive root — pip will refuse this"$'\n'
    gate_hits+="$(printf '%s\n' "$escapes" | sed 's/^/    /')"$'\n'
  fi

  # .gitignore is judged by CONTENT, not by name. hatchling force-includes whichever exclusion
  # file it discovered — see the note above — and it walks UP the tree to find one, so the file
  # that ships is either the package's own (harmless, and normal in an sdist) or an ancestor's
  # (a map of where every secret in a private monorepo lives, which is how the repo-root
  # 209-line file ended up inside a distribution). Comparing against the package's own file is
  # exact; matching on the filename would either miss the leak or forbid something benign.
  #
  # Only the package-root member (`<sdist-root>/.gitignore`) is the hatchling force-include.
  # Nested template `.gitignore` files (e.g. scaffolds) are package content and are ignored here.
  # Prefer `tar -xOf <exact-member>` — macOS bsdtar ignores GNU `--include=` and yields empty,
  # which falsely tripped this gate even when the package shipped its own file.
  if [[ "$archive" == *.tar.gz ]]; then
    root_gi="$(printf '%s\n' "$listing" | grep -E '^[^/]+/\.gitignore$' | head -1 || true)"
    if [[ -n "$root_gi" ]]; then
      shipped="$(tar -xOf "$archive" "$root_gi" 2>/dev/null || true)"
      own=""
      [[ -f .gitignore ]] && own="$(cat .gitignore)"
      if [[ -z "$own" || "$shipped" != "$own" ]]; then
        gate_hits+="  $archive:"$'\n'"    .gitignore came from OUTSIDE this package"
        if [[ -z "$own" ]]; then
          gate_hits+=" (this package has none of its own — add one to stop hatchling walking up)"
        fi
        gate_hits+=$'\n'
      fi
    fi
  fi
done
if [[ -n "$gate_hits" ]]; then
  cat >&2 <<EOF
error: refusing to publish — the built artifacts contain paths that must never ship.

$gate_hits
Nothing was uploaded.

For key material, a database or a .env: declare an explicit file set in $PKG/pyproject.toml.

  [tool.hatch.build.targets.sdist]
  include = ["/<package_dir>", "/tests", "/README.md", "/LICENSE", "/pyproject.toml"]

For a foreign .gitignore you need BOTH that allow-list AND a .gitignore of the package's own —
the allow-list alone is not enough, and finding that out the hard way is why this says so.
hatchling picks its exclusion list by walking UP for a .gitignore and then force-includes
whichever file it found, which bypasses both \`include\` and \`exclude\`. Give the package its own
three-line .gitignore and the walk stops there, so the file that ships is harmless.

For a member escaping the archive root: something in the build reaches outside the package
directory — usually \`readme\` or a \`package-dir\` pointing at \`../\`. Copy or symlink the file in,
or point the setting at a path inside the package. There is no flag that makes this safe; pip
rejects the archive.

If one of the paths above is genuinely meant to be published, narrow the pattern in this gate
rather than removing it — and say in the commit why it is safe.
EOF
  exit 4
fi
echo "OK no key material, .env, database or .gitignore in $(ls dist/ | tr '\n' ' ')"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "OK dry-run — dist/ ready:"
  ls -la dist/
  exit 0
fi

if [[ "$TEST_PYPI" -eq 1 ]]; then
  TOKEN="${TESTPYPI_API_TOKEN:-${PYPI_API_TOKEN:-}}"
  REPO="testpypi"
  URL="https://test.pypi.org/legacy/"
else
  TOKEN="${PYPI_API_TOKEN:-}"
  REPO="pypi"
  URL="https://upload.pypi.org/legacy/"
fi

[[ -n "$TOKEN" ]] || {
  echo "error: set PYPI_API_TOKEN (or TESTPYPI_API_TOKEN for --testpypi)" >&2
  exit 3
}

echo "== Upload to $REPO =="
TWINE_USERNAME=__token__ TWINE_PASSWORD="$TOKEN" \
  python3 -m twine upload --repository-url "$URL" dist/*

echo "OK published $(basename "$PKG") to $REPO"
if [[ "$REPO" == "pypi" ]]; then
  name="$(python3 -c "
import sys
if sys.version_info >= (3, 11):
    import tomllib
    print(tomllib.load(open('pyproject.toml','rb'))['project']['name'])
else:
    import re
    m = re.search(r'^name = \"([^\"]+)\"', open('pyproject.toml').read(), re.M)
    print(m.group(1) if m else '')
" 2>/dev/null || true)"
  [[ -z "$name" ]] && name="$(grep -E '^name = ' pyproject.toml | head -1 | sed -E 's/^name = \"([^\"]+)\".*/\1/')"
  echo "Install: python3 -m pip install $name"
fi
