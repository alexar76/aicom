#!/usr/bin/env bash
# Publish selected factory products into the GitHub catalog monorepo
#   https://github.com/alexar76/aicom-products
#
# Each product lands under products/<product_id>/ (full tree, minus build junk).
# Selective: pass one or more --product ids. Never force-pushes the whole factory.
#
# Catalog shell (README/CONTRIBUTING) is a normal satellite — like oracles:
#   GH_PAT=… ./scripts/publish_all_repos.sh --satellite aicom-products
#
# Usage:
#   GH_PAT=… ./scripts/publish_factory_product_catalog.sh --product prod-bdb1634806de \
#     --source /path/to/data/code/prod-bdb1634806de
#   ./scripts/publish_factory_product_catalog.sh --product prod-x --from-factory-host
#
# Env:
#   AICOM_PRODUCTS_CATALOG_REMOTE  default https://github.com/alexar76/aicom-products.git
#   GH_PAT / GITHUB_TOKEN          alexar76 write access
#   AICOM_FACTORY_SSH              default my-vps (for --from-factory-host)
#   AICOM_FACTORY_CODE_ROOT        default /root/claudecode/aicom/data/code
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REMOTE="${AICOM_PRODUCTS_CATALOG_REMOTE:-https://github.com/alexar76/aicom-products.git}"
BRANCH="${AICOM_PRODUCTS_CATALOG_BRANCH:-main}"
FACTORY_SSH="${AICOM_FACTORY_SSH:-my-vps}"
FACTORY_CODE_ROOT="${AICOM_FACTORY_CODE_ROOT:-/root/claudecode/aicom/data/code}"
FACTORY_SSH_KEY="${AICOM_FACTORY_SSH_KEY:-$HOME/.ssh/id_ed25519_factory}"
DRY_RUN=0
FROM_HOST=0
PRODUCTS=()
SOURCE_OVERRIDES=()
LIVE_URL_OVERRIDES=()

usage() {
  cat <<'EOF'
publish_factory_product_catalog.sh — selective product → alexar76/aicom-products

  --product ID           Product id (repeatable), e.g. prod-bdb1634806de
  --source PATH          Local path to that product's code tree (once, applies to last --product)
  --live-url URL         Public demo URL (Vercel etc.) for last --product; else auto_publish.json
  --from-factory-host    rsync product trees from the factory host before publish
  --remote URL           Catalog remote (default AICOM_PRODUCTS_CATALOG_REMOTE / alexar76)
  --branch NAME          Target branch (default main)
  --dry-run              Print plan only
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --product) PRODUCTS+=("$2"); SOURCE_OVERRIDES+=(""); LIVE_URL_OVERRIDES+=(""); shift 2 ;;
    --source)
      if [[ ${#PRODUCTS[@]} -eq 0 ]]; then
        echo "error: --source must follow --product" >&2
        exit 2
      fi
      SOURCE_OVERRIDES[$((${#PRODUCTS[@]} - 1))]="$2"
      shift 2
      ;;
    --live-url)
      if [[ ${#PRODUCTS[@]} -eq 0 ]]; then
        echo "error: --live-url must follow --product" >&2
        exit 2
      fi
      LIVE_URL_OVERRIDES[$((${#PRODUCTS[@]} - 1))]="$2"
      shift 2
      ;;
    --from-factory-host) FROM_HOST=1; shift ;;
    --remote) REMOTE="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

[[ ${#PRODUCTS[@]} -gt 0 ]] || { usage; exit 2; }

TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
[[ -n "$TOKEN" || "$DRY_RUN" -eq 1 ]] || {
  echo "error: set GH_PAT or GITHUB_TOKEN for alexar76" >&2
  exit 2
}

# Refuse freestyle remotes outside alexar76 catalog.
case "$REMOTE" in
  *github.com/alexar76/aicom-products*) ;;
  *)
    echo "error: catalog remote must be alexar76/aicom-products (got: $REMOTE)" >&2
    exit 2
    ;;
esac

auth_remote() {
  local url="$1"
  if [[ -n "$TOKEN" && "$url" =~ ^https://github.com/ ]]; then
    echo "https://x-access-token:${TOKEN}@github.com/${url#https://github.com/}"
  else
    echo "$url"
  fi
}

RSYNC_EXCLUDES=(
  --exclude '.git/'
  --exclude '.aicom_sandbox/'
  --exclude 'node_modules/'
  --exclude '.venv/'
  --exclude 'venv/'
  --exclude '__pycache__/'
  --exclude '.pytest_cache/'
  --exclude '.mypy_cache/'
  --exclude '.ruff_cache/'
  --exclude '.next/'
  --exclude 'coverage/'
  --exclude 'htmlcov/'
  --exclude '*.pyc'
  --exclude '.DS_Store'
  --exclude '.env'
  --exclude '.env.*'
  --exclude '*.db'
  --exclude '*.db-shm'
  --exclude '*.db-wal'
)

ensure_contributing() {
  local dest="$1"
  if [[ ! -f "$dest/CONTRIBUTING.md" ]]; then
    cat >"$dest/CONTRIBUTING.md" <<'EOF'
# Contributing

Thanks for helping improve this factory-built product.

## Development

1. Install backend and frontend deps from their respective directories.
2. Copy `.env.example` if present; never commit secrets.
3. Run the test commands listed in `README.md`.

## Pull requests

- Keep changes focused; include tests when behavior changes.
- Update `CHANGELOG.md` for user-visible changes.
- Do not commit `node_modules/`, `.venv/`, or `.env`.

## Security

See `SECURITY.md` for vulnerability reports.
EOF
  fi
}

ensure_readme_badge_markers() {
  local dest="$1"
  local readme="$dest/README.md"
  [[ -f "$readme" ]] || return 0
  if ! grep -q 'aicom-readme-badges' "$readme"; then
    local tmp
    tmp="$(mktemp)"
    {
      echo '<!-- aicom-readme-badges -->'
      echo '![CI](docs/badges/ci.svg) ![License](docs/badges/license.svg)'
      echo '<!-- /aicom-readme-badges -->'
      echo
      cat "$readme"
    } >"$tmp"
    mv "$tmp" "$readme"
  fi
  mkdir -p "$dest/docs/badges"
  if [[ ! -f "$dest/docs/badges/ci.svg" ]]; then
    cat >"$dest/docs/badges/ci.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="90" height="20"><linearGradient id="b" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient><mask id="a"><rect width="90" height="20" rx="3" fill="#fff"/></mask><g mask="url(#a)"><path fill="#555" d="M0 0h37v20H0z"/><path fill="#4c1" d="M37 0h53v20H37z"/><path fill="url(#b)" d="M0 0h90v20H0z"/></g><g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11"><text x="18.5" y="14">ci</text><text x="62.5" y="14">passing</text></g></svg>
EOF
  fi
  if [[ ! -f "$dest/docs/badges/license.svg" ]]; then
    cat >"$dest/docs/badges/license.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20"><linearGradient id="b" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient><mask id="a"><rect width="100" height="20" rx="3" fill="#fff"/></mask><g mask="url(#a)"><path fill="#555" d="M0 0h55v20H0z"/><path fill="#007ec6" d="M55 0h45v20H55z"/><path fill="url(#b)" d="M0 0h100v20H0z"/></g><g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11"><text x="27.5" y="14">license</text><text x="76.5" y="14">MIT</text></g></svg>
EOF
  fi
  # Fill any other README-linked badge SVGs; refuse a catalog push that would 404 a hero.
  python3 - "$ROOT" "$dest" <<'PY' || return 1
import sys
from pathlib import Path

root = Path(sys.argv[1])
dest = Path(sys.argv[2])
sys.path.insert(0, str(root))
from web.backend.services.github_house_assets import (
    apply_github_house_asset_autofix,
    missing_readme_assets,
)

notes = apply_github_house_asset_autofix(dest)
if notes:
    print("  github-house assets:", ", ".join(notes[:12]))
missing = missing_readme_assets(dest)
if missing:
    print(
        "error: README references files that are not in the product tree "
        "(GitHub would show alt text): " + ", ".join(missing),
        file=sys.stderr,
    )
    sys.exit(1)
PY
}

# Insert or refresh a Live demo line when a public Vercel (or other HTTPS) URL is known.
ensure_readme_live_url() {
  local dest="$1"
  local url="$2"
  [[ -n "$url" ]] || return 0
  case "$url" in
    https://*) ;;
    *)
      echo "  skip live URL (not https): $url" >&2
      return 0
      ;;
  esac
  case "$url" in
    *localhost*|*127.0.0.1*|*0.0.0.0*|*.local/*|*.local)
      echo "  skip live URL (local host): $url" >&2
      return 0
      ;;
  esac
  python3 - "$dest" "$url" <<'PY'
import re
import sys
from pathlib import Path

dest = Path(sys.argv[1])
url = sys.argv[2].strip()
block = (
    "<!-- aicom-live-url -->\n"
    f"**Live:** [{url}]({url})\n"
    "<!-- /aicom-live-url -->"
)
pat = re.compile(
    r"<!--\s*aicom-live-url\s*-->.*?<!--\s*/aicom-live-url\s*-->",
    re.DOTALL | re.IGNORECASE,
)
for name in ("README.md", "README.ru.md"):
    path = dest / name
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if pat.search(text):
        text = pat.sub(block, text, count=1)
    else:
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        i = 0
        if lines and lines[0].startswith("# "):
            out.append(lines[0])
            i = 1
            while i < len(lines) and (
                lines[i].strip() == "" or lines[i].lstrip().startswith(">")
            ):
                out.append(lines[i])
                i += 1
            if out and out[-1].strip() != "":
                out.append("\n")
            out.append(block + "\n\n")
            out.extend(lines[i:])
            text = "".join(out)
        else:
            text = block + "\n\n" + text
    path.write_text(text, encoding="utf-8")
print(f"  ✓ Live URL in README: {url}")
PY
}

resolve_live_url() {
  # Prefer explicit --live-url for this product index; else auto_publish.json.
  local idx="$1"
  local pid="$2"
  local explicit="${LIVE_URL_OVERRIDES[$idx]:-}"
  if [[ -n "$explicit" ]]; then
    echo "$explicit"
    return 0
  fi
  local candidates=(
    "$ROOT/data/state/${pid}/auto_publish.json"
  )
  if [[ "$FROM_HOST" -eq 1 ]]; then
    local remote_state
    remote_state="$(dirname "$FACTORY_CODE_ROOT")/state/${pid}/auto_publish.json"
    local tmpj
    tmpj="$(mktemp)"
    if ssh -i "${FACTORY_SSH_KEY}" -o BatchMode=yes "$FACTORY_SSH" \
      "cat ${remote_state} 2>/dev/null || docker exec aicom-app-1 cat /app/data/state/${pid}/auto_publish.json 2>/dev/null" \
      >"$tmpj" 2>/dev/null; then
      candidates+=("$tmpj")
    fi
  fi
  local j
  for j in "${candidates[@]}"; do
    [[ -f "$j" ]] || continue
    local url
    url="$(python3 - "$j" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    d = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)
for key in ("vercel_url", "published_url", "url", "public_url"):
    v = d.get(key)
    if isinstance(v, str) and v.startswith("https://"):
        print(v.strip())
        sys.exit(0)
lg = d.get("live_gate")
if isinstance(lg, dict):
    v = lg.get("url")
    if isinstance(v, str) and v.startswith("https://"):
        print(v.strip())
PY
)"
    if [[ -n "$url" ]]; then
      echo "$url"
      return 0
    fi
  done
  return 0
}

fetch_from_host() {
  local pid="$1"
  local dest="$2"
  mkdir -p "$dest"
  rsync -az --delete \
    -e "ssh -i ${FACTORY_SSH_KEY} -o BatchMode=yes" \
    "${RSYNC_EXCLUDES[@]}" \
    "${FACTORY_SSH}:${FACTORY_CODE_ROOT}/${pid}/" \
    "${dest}/"
}

echo "Catalog → ${REMOTE} (branch=${BRANCH})"
echo "Products: ${PRODUCTS[*]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "(dry-run) would sync and push"
  exit 0
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/aicom-products.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

AUTH_REMOTE="$(auth_remote "$REMOTE")"
git clone --depth 1 --branch "$BRANCH" "$AUTH_REMOTE" "$WORK/repo" 2>/dev/null \
  || {
    # Empty / missing branch: init
    git clone --depth 1 "$AUTH_REMOTE" "$WORK/repo" 2>/dev/null \
      || {
        mkdir -p "$WORK/repo"
        git -C "$WORK/repo" init -b "$BRANCH"
        git -C "$WORK/repo" remote add origin "$AUTH_REMOTE"
      }
  }

REPO="$WORK/repo"
mkdir -p "$REPO/products"

if [[ ! -f "$REPO/README.md" ]]; then
  cat >"$REPO/README.md" <<'EOF'
# aicom-products

Selective catalog of **full** products built by [AI-Factory](https://github.com/alexar76/aicom).

Each subdirectory under `products/` is one factory product id (`prod-…`), published on demand — not every pipeline run, and never the whole monorepo.

## Product map

<!-- aicom-product-map -->
| Folder | Product | Description | Live |
| --- | --- | --- | --- |
<!-- /aicom-product-map -->

## Layout

```
products/<product_id>/   # full product tree (source + docs; no node_modules / .venv)
```

## Publish

From the factory monorepo:

```bash
GH_PAT=… ./scripts/publish_factory_product_catalog.sh \
  --product prod-XXXXXXXXXXXX --from-factory-host
```

Auth: `GH_PAT` for **alexar76**. Remote: `https://github.com/alexar76/aicom-products.git`.
EOF
fi

if [[ ! -f "$REPO/CONTRIBUTING.md" ]]; then
  cat >"$REPO/CONTRIBUTING.md" <<'EOF'
# Contributing to the product catalog

This repo is a **mirror of selected factory products**. Prefer opening issues and PRs against the product subtree you care about (`products/<id>/`).

Do not commit secrets, `node_modules/`, or `.aicom_sandbox/`.
EOF
fi

STAGED=()
for i in "${!PRODUCTS[@]}"; do
  pid="${PRODUCTS[$i]}"
  [[ "$pid" =~ ^[a-zA-Z0-9._-]+$ ]] || { echo "bad product id: $pid" >&2; exit 2; }
  src="${SOURCE_OVERRIDES[$i]:-}"
  staging="$WORK/src/$pid"
  mkdir -p "$staging"

  if [[ -n "$src" ]]; then
    [[ -d "$src" ]] || { echo "missing source: $src" >&2; exit 2; }
    rsync -a --delete "${RSYNC_EXCLUDES[@]}" "${src%/}/" "$staging/"
  elif [[ "$FROM_HOST" -eq 1 ]]; then
    echo "rsync from factory host: $pid"
    fetch_from_host "$pid" "$staging"
  else
    # Local factory data path convention
    local_guess="$ROOT/data/code/$pid"
    if [[ -d "$local_guess" ]]; then
      rsync -a --delete "${RSYNC_EXCLUDES[@]}" "${local_guess%/}/" "$staging/"
    else
      echo "error: no --source and no local data/code/$pid; use --from-factory-host" >&2
      exit 2
    fi
  fi

  ensure_contributing "$staging"
  ensure_readme_badge_markers "$staging"
  live_url="$(resolve_live_url "$i" "$pid" || true)"
  if [[ -n "$live_url" ]]; then
    ensure_readme_live_url "$staging" "$live_url"
  else
    echo "  (no live/Vercel URL found for $pid — README unchanged)"
  fi

  dest="$REPO/products/$pid"
  mkdir -p "$dest"
  rsync -a --delete "${RSYNC_EXCLUDES[@]}" "${staging%/}/" "$dest/"
  STAGED+=("$pid")
done

# Refresh root product map (table): folder → name → description → live
# Also patches README.md between <!-- aicom-product-map --> markers when present.
refresh_product_map() {
  local products_dir="$1"
  local out_md="$2"
  local readme="$3"
  local table_file
  table_file="$(mktemp)"
  python3 - "$products_dir" "$table_file" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

products = Path(sys.argv[1])
out = Path(sys.argv[2])
rows: list[tuple[str, str, str, str]] = []
if products.is_dir():
    for d in sorted(p for p in products.iterdir() if p.is_dir() and not p.name.startswith(".")):
        pid = d.name
        title = pid
        desc = ""
        live = ""
        readme_path = d / "README.md"
        if readme_path.is_file():
            text = readme_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or pid
                    break
            for line in text.splitlines():
                s = line.strip()
                if s.startswith(">") and not s.startswith("> 🌐") and not s.startswith("> :"):
                    body = s.lstrip(">").strip()
                    if body and not body.startswith("[") and "English" not in body:
                        desc = body
                        break
            m = re.search(r"\*\*Live:\*\*\s*\[([^\]]+)\]", text)
            if m:
                live = m.group(1).strip()
            if not live:
                m = re.search(r"https://prod-[a-z0-9]+\.vercel\.app/?", text)
                if m:
                    live = m.group(0).rstrip("/") + "/"

        def clean(s: str) -> str:
            return " ".join(s.replace("|", "/").split())

        rows.append((pid, clean(title), clean(desc) or "—", live))

lines = [
    "| Folder | Product | Description | Live |",
    "| --- | --- | --- | --- |",
]
for pid, title, desc, live in rows:
    live_cell = f"[demo]({live})" if live else "—"
    lines.append(f"| [`products/{pid}/`](products/{pid}/) | {title} | {desc} | {live_cell} |")
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

  {
    echo "# Products"
    echo
    echo "Factory-built apps published into this catalog. Folder = product id under \`products/\`."
    echo
    cat "$table_file"
  } >"$out_md"

  if [[ -f "$readme" ]] && grep -q '<!-- aicom-product-map -->' "$readme"; then
    python3 - "$readme" "$table_file" <<'PY'
from pathlib import Path
import re
import sys

readme = Path(sys.argv[1])
table = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
text = readme.read_text(encoding="utf-8")
start = "<!-- aicom-product-map -->"
end = "<!-- /aicom-product-map -->"
if start not in text or end not in text:
    raise SystemExit(0)
block = f"{start}\n{table}\n{end}"
readme.write_text(
    re.sub(re.escape(start) + r".*?" + re.escape(end), block, text, count=1, flags=re.S),
    encoding="utf-8",
)
print("  ✓ README product map refreshed")
PY
  fi
  rm -f "$table_file"
}

refresh_product_map "$REPO/products" "$REPO/PRODUCTS.md" "$REPO/README.md"

git -C "$REPO" add -A
if git -C "$REPO" diff --cached --quiet; then
  echo "No catalog changes to publish."
  exit 0
fi

git -C "$REPO" -c user.email="factory@alexar76.github.io" -c user.name="AI-Factory catalog" \
  commit -m "Publish products: ${STAGED[*]}"

git -C "$REPO" push -u origin "HEAD:${BRANCH}"
echo "OK → ${REMOTE} products/${STAGED[*]}"
echo "https://github.com/alexar76/aicom-products/tree/${BRANCH}/products/${STAGED[0]}"
