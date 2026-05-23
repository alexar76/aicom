#!/usr/bin/env bash
# =============================================================================
# mirror_satellites.sh — Export one or all satellites from aicom monorepo
# to their GitHub repos, applying per-satellite layout transforms.
#
# Source of truth: scripts/satellite-map.yaml
#
# Usage:
#   ./scripts/mirror_satellites.sh                          # all satellites
#   ./scripts/mirror_satellites.sh aimarket-desktop         # single satellite
#   ./scripts/mirror_satellites.sh --dry-run                # preview only
#   ./scripts/mirror_satellites.sh --satellite acex         # single via flag
#   ./scripts/mirror_satellites.sh --no-push                # commit locally, don't push
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Defaults ────────────────────────────────────────────────────────────────
GITHUB_ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
GITHUB_HOST="${SATELLITE_GITHUB_HOST:-github.com}"
BRANCH="${SATELLITE_BRANCH:-main}"
DRY_RUN=0
NO_PUSH=0
SINGLE_SATELLITE=""
WORKDIR=""
KEEP_WORKDIR=0

# ── Python helpers ──────────────────────────────────────────────────────────
_python_map() {
  python3 - "$@" <<'PYEOF'
import sys, json, yaml
from pathlib import Path

MAP = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text())
cmd = sys.argv[1]

if cmd == "list-ids":
    for s in MAP.get("satellites", []):
        if not s.get("optional"):
            print(s["id"])
elif cmd == "list-all-ids":
    for s in MAP.get("satellites", []):
        opt = " (optional)" if s.get("optional") else ""
        print(f"{s['id']}{opt}")
elif cmd == "get":
    sid = sys.argv[2]
    for s in MAP.get("satellites", []):
        if s["id"] == sid:
            print(json.dumps(s))
            raise SystemExit(0)
    print(f"ERROR: unknown satellite {sid}", file=sys.stderr)
    raise SystemExit(1)
elif cmd == "org":
    print(MAP.get("org", "alexar76"))
elif cmd == "desktop-skus":
    # SKU slugs from desktop_sku_manifest.py
    try:
        from desktop_sku_manifest import MANIFEST
        print(" ".join(MANIFEST.keys()))
    except ImportError:
        # Fallback to listing desktop-integrations dirs
        di = Path("desktop-integrations")
        skus = [
            d.name for d in sorted(di.iterdir())
            if d.is_dir() and d.name not in ("packages",)
            and not d.name.startswith(".")
        ]
        print(" ".join(skus))
PYEOF
}

# ── CLI parsing ─────────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
mirror_satellites.sh — export satellites from aicom monorepo → GitHub repos

Usage:
  ./scripts/mirror_satellites.sh [OPTIONS] [SATELLITE_ID]

  Without SATELLITE_ID, mirrors ALL non-optional satellites.
  With SATELLITE_ID, mirrors only that one (for CI matrix use).

Options:
  --dry-run        Preview exports without modifying anything
  --no-push        Commit locally in temp clone but do not push
  --satellite ID   Mirror single satellite by id
  --branch NAME    Target branch (default: main)
  --keep-workdir   Keep temp workdir for inspection
  -h, --help       This help

Environment:
  SATELLITE_GITHUB_ORG    GitHub org/user (default: alexar76)
  SATELLITE_GITHUB_HOST   GitHub host (default: github.com)
  SATELLITE_BRANCH        Target branch (default: main)
  GH_PAT / GITHUB_TOKEN   GitHub Personal Access Token for auth
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY_RUN=1; shift ;;
    --no-push)      NO_PUSH=1; shift ;;
    --satellite)    SINGLE_SATELLITE="${2:-}"; shift 2 ;;
    --branch)       BRANCH="${2:-}"; shift 2 ;;
    --keep-workdir) KEEP_WORKDIR=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    --*)            echo "unknown option: $1" >&2; usage; exit 1 ;;
    *)              SINGLE_SATELLITE="$1"; shift ;;
  esac
done

# ── Auth setup ──────────────────────────────────────────────────────────────
TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
if [[ -z "$TOKEN" && "$DRY_RUN" -eq 0 ]]; then
  echo "⚠️  GH_PAT / GITHUB_TOKEN not set — will attempt unauthenticated git push"
  echo "   Set GH_PAT or GITHUB_TOKEN in environment for authenticated pushes."
  AUTH_PREFIX=""
  AUTH_SUFFIX=""
else
  AUTH_PREFIX="https://${TOKEN}@${GITHUB_HOST}/"
  AUTH_SUFFIX=""
fi

# ── Workdir setup ───────────────────────────────────────────────────────────
if [[ "$DRY_RUN" -eq 0 ]]; then
  WORKDIR="$(mktemp -d)"
  if [[ "$KEEP_WORKDIR" -eq 0 ]]; then
    trap 'rm -rf "$WORKDIR"' EXIT
  else
    echo "Workdir: $WORKDIR (kept for inspection)"
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════
#  Satellite-specific export functions
# ═══════════════════════════════════════════════════════════════════════════

export_simple() {
  # Generic export: rsync monorepo path → satellite root
  local sat_id="$1"
  local src_rel="$2"
  local repo="$3"
  local license="$4"
  local extra_excludes="${5:-}"

  local src="$ROOT/$src_rel"
  local remote_url="${AUTH_PREFIX}${GITHUB_HOST}/${GITHUB_ORG}/${repo}.git"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Source:  $src_rel"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  [[ -d "$src" ]] || { echo "  ⚠️  SKIP: source missing: $src"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would rsync $src_rel/ → $repo/"
    return 0
  fi

  local clone="$WORKDIR/${repo}"

  # Clone or init
  if git ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo not found — initializing fresh"
  fi

  # Clean existing files (preserve .git)
  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  # Build rsync exclude args
  local rsync_args=(-a)
  for pat in .git .venv venv node_modules __pycache__ .pytest_cache .mypy_cache .dart_tool build dist .mesh_data "*.egg-info" .DS_Store; do
    rsync_args+=(--exclude "$pat")
  done
  if [[ -n "$extra_excludes" ]]; then
    IFS=' ' read -ra EXTRA <<< "$extra_excludes"
    for e in "${EXTRA[@]}"; do
      rsync_args+=(--exclude "$e")
    done
  fi

  rsync "${rsync_args[@]}" "$src/" "$clone/"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "$license"
}

export_desktop_monorepo() {
  local sat_id="aimarket-desktop"
  local repo="aimarket-desktop"
  local remote_url="${AUTH_PREFIX}${GITHUB_HOST}/${GITHUB_ORG}/${repo}.git"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Layout:  desktop-integrations/{app} → apps/{app}"
  echo "           desktop-integrations/packages → packages/"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would build desktop monorepo layout → $repo/"
    return 0
  fi

  local clone="$WORKDIR/${repo}"

  if git ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo not found — initializing fresh"
  fi

  # Clean existing files (preserve .git)
  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  # Build apps/ from desktop-integrations SKUs
  mkdir -p "$clone/apps"
  local skus
  skus=$(_python_map desktop-skus 2>/dev/null || echo "")
  if [[ -z "$skus" ]]; then
    # Fallback: list dirs
    for d in "$ROOT"/desktop-integrations/*/; do
      local name
      name=$(basename "$d")
      [[ "$name" == "packages" ]] && continue
      [[ "$name" == .* ]] && continue
      skus="$skus $name"
    done
  fi

  local rsync_base_args=(-a --exclude .git --exclude .venv --exclude venv --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude .dart_tool --exclude build --exclude dist --exclude .DS_Store)

  for sku in $skus; do
    local src_dir="$ROOT/desktop-integrations/$sku"
    local dst_dir="$clone/apps/$sku"
    if [[ -d "$src_dir" ]]; then
      mkdir -p "$dst_dir"
      rsync "${rsync_base_args[@]}" "$src_dir/" "$dst_dir/"
      echo "  ✓ apps/$sku"

      # ── Language packs (colocated) ──
      local lp_src="$ROOT/desktop-integrations/$sku/language-packs"
      local lp_legacy="$ROOT/language-packs/$sku"
      local lp_dst="$dst_dir/language-packs"
      mkdir -p "$lp_dst"

      if [[ -d "$lp_src" ]]; then
        rsync "${rsync_base_args[@]}" "$lp_src/" "$lp_dst/"
        echo "    ↳ language-packs from desktop-integrations/$sku/"
      elif [[ -d "$lp_legacy" ]]; then
        rsync "${rsync_base_args[@]}" "$lp_legacy/" "$lp_dst/"
        echo "    ↳ language-packs from legacy language-packs/$sku/"
      fi
    else
      echo "  ⚠️  SKU directory missing: desktop-integrations/$sku"
    fi
  done

  # Packages
  local pkgs_src="$ROOT/desktop-integrations/packages"
  if [[ -d "$pkgs_src" ]]; then
    mkdir -p "$clone/packages"
    rsync "${rsync_base_args[@]}" "$pkgs_src/" "$clone/packages/"
    echo "  ✓ packages/ (aicom_desktop_core, aicom_platform_init)"
  fi

  # ── Generate melos.yaml ──
  _generate_melos_yaml "$clone" "$skus"

  # ── Governance files ──
  _copy_governance "$clone" "mit" "aimarket-desktop" "desktop-monorepo"

  # ── CI workflow ──
  mkdir -p "$clone/.github/workflows"
  _generate_desktop_ci "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

export_plugins() {
  local sat_id="aimarket-plugins"
  local repo="aimarket-plugins"
  local remote_url="${AUTH_PREFIX}${GITHUB_HOST}/${GITHUB_ORG}/${repo}.git"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Source:  plugins/ → plugins/"
  echo "           aimarket-hub/plugins/aimarket-provenance → plugins/aimarket-provenance"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would build plugins layout → $repo/"
    return 0
  fi

  local clone="$WORKDIR/${repo}"

  if git ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
  fi

  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_args=(-a --exclude .git --exclude .venv --exclude venv --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude build --exclude dist --exclude .DS_Store)

  # Main plugins
  mkdir -p "$clone/plugins"
  if [[ -d "$ROOT/plugins" ]]; then
    rsync "${rsync_args[@]}" "$ROOT/plugins/" "$clone/plugins/"
    echo "  ✓ plugins/"
  fi

  # Extra: aimarket-provenance from aimarket-hub
  local provenance_src="$ROOT/aimarket-hub/plugins/aimarket-provenance"
  if [[ -d "$provenance_src" ]]; then
    mkdir -p "$clone/plugins/aimarket-provenance"
    rsync "${rsync_args[@]}" "$provenance_src/" "$clone/plugins/aimarket-provenance/"
    echo "  ✓ plugins/aimarket-provenance (from aimarket-hub)"
  fi

  _copy_governance "$clone" "mit" "aimarket-plugins"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

# ── Governance helpers ──────────────────────────────────────────────────────

_copy_governance() {
  local target="$1"
  local license="$2"
  local name="$3"
  local kind="${4:-package}"

  # LICENSE
  if [[ "$license" == "apache-2.0" || "$license" == "apache" ]]; then
    if [[ -f "$ROOT/aimarket-hub/LICENSE" ]]; then
      cp "$ROOT/aimarket-hub/LICENSE" "$target/LICENSE"
    elif [[ -f "$ROOT/acex/LICENSE" ]]; then
      cp "$ROOT/acex/LICENSE" "$target/LICENSE"
    else
      echo "  ⚠️  Apache-2.0 LICENSE not found in monorepo"
    fi
  else
    if [[ -f "$ROOT/LICENSE" ]]; then
      cp "$ROOT/LICENSE" "$target/LICENSE"
    else
      echo "  ⚠️  MIT LICENSE not found in monorepo"
    fi
  fi

  # SECURITY.md
  python3 - "$name" "$kind" > "$target/SECURITY.md" <<'PYEOF'
import sys
name = sys.argv[1]
kind = sys.argv[2]

scope_map = {
    "plugin": f"- `{name}` hub plugin routes and invoke hooks\n- Ed25519 signing and payment channel interactions",
    "desktop": f"- `{name}` Flutter desktop/web application\n- Local data storage and wallet key handling\n- `aimarket_agent` SDK integration",
    "package": f"- `{name}` shared library\n- API surface exported to desktop SKUs",
    "hub": "- AIMarket Hub core API, plugins loader, payment channels, federation",
    "widget": (
        f"- `{name}` embed script (`widget.js`), themes, and demo pages\n"
        "- DOM XSS safety, hub v2 API calls, payment channel / affiliate headers\n"
        "- Unsafe `data-hub-url` or fetch targets"
    ),
    "pulse-terminal": (
        f"- `{name}` ACEX dashboard (Vite/React)\n"
        "- WebSocket/SSE pricing feed, API proxy config\n"
        "- XSS via hub pricing payloads rendered in DOM"
    ),
    "sdks": (
        f"- `{name}` consumer SDKs (Dart, TypeScript, Rust)\n"
        "- Wallet key handling, hub HTTP client, TEE verification helpers"
    ),
    "desktop-monorepo": (
        f"- `{name}` Flutter desktop/web applications\n"
        "- Local SQLite, wallet keys, language pack JSON loading"
    ),
}
scope = scope_map.get(kind, f"- `{name}`")

print(f"""# Security Policy — {name}

## Reporting a Vulnerability

**Do not open a public issue for security bugs.**

Email: **security@aicom.io**

We acknowledge within 48 hours and share a fix timeline.

## Scope

{scope}

## Out of Scope

- Third-party dependencies (report upstream)
- Issues requiring physical access to user hardware
- Social engineering

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest main | yes |
| older tags | best effort |

## Disclosure

Coordinated disclosure preferred. We credit researchers in release notes when permitted.
""")
PYEOF

  # CONTRIBUTING.md
  if [[ -f "$ROOT/CONTRIBUTING.md" ]]; then
    cp "$ROOT/CONTRIBUTING.md" "$target/CONTRIBUTING.md"
  fi

  # CONTRIBUTORS.md
  cat > "$target/CONTRIBUTORS.md" <<EOF
# Contributors — ${name}

## Maintainers

- **AI Commons / AI-Factory** — primary maintainers ([security@aicom.io](mailto:security@aicom.io))

## Contributing

1. Fork the repository (when published as a standalone repo)
2. Open a PR with tests and documentation updates
3. Sign off commits (\`Signed-off-by:\`) for DCO traceability

## Recognition

Contributors are listed in git history. For release notes, see the monorepo tag or GitHub Releases page.
EOF

  # README placeholder if missing
  if [[ ! -f "$target/README.md" ]]; then
    cat > "$target/README.md" <<EOF
# ${name}

Part of the [AI-Factory](https://github.com/${GITHUB_ORG}/aicom) ecosystem.

## License

See [LICENSE](./LICENSE).
EOF
  fi

  echo "  ✓ Governance (LICENSE, SECURITY.md, CONTRIBUTING.md, CONTRIBUTORS.md, README.md)"
}

# ── melos.yaml generator ────────────────────────────────────────────────────

_generate_melos_yaml() {
  local target="$1"
  local skus="$2"

  local packages_json=""
  local first=1
  for sku in $skus; do
    if [[ $first -eq 1 ]]; then
      first=0
      packages_json+="    \"apps/$sku\""
    else
      packages_json+=",\n    \"apps/$sku\""
    fi
  done

  # Add shared packages
  for pkg in aicom_desktop_core aicom_platform_init; do
    if [[ -d "$target/packages/$pkg" ]]; then
      packages_json+=",\n    \"packages/$pkg\""
    fi
  done

  cat > "$target/melos.yaml" <<MELOSEOF
name: aimarket-desktop
repository: https://github.com/${GITHUB_ORG}/aimarket-desktop.git

packages:
${packages_json}

command:
  bootstrap:
    usePubspecOverrides: true

scripts:
  analyze:
    run: melos exec -- dart analyze
    description: Run static analysis across all packages.
  test:
    run: melos exec -- dart test
    description: Run tests across all packages.
MELOSEOF

  echo "  ✓ melos.yaml"
}

# ── Desktop CI generator ────────────────────────────────────────────────────

_generate_desktop_ci() {
  local target="$1"
  cat > "$target/.github/workflows/ci.yml" <<'CIEOF'
name: CI

on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  flutter-analyze:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        app:
          - apps/interview-prep-coach
          - apps/personal-finance-coach
          - apps/capability-composer
          - apps/cold-outreach-coach
          - apps/creator-algorithm-coach
          - apps/discovery-prospector
          - apps/freelance-contract-reviewer
          - apps/reputation-dashboard
    steps:
      - uses: actions/checkout@v4

      - uses: subosito/flutter-action@v2
        with:
          flutter-version: "3.24.x"
          channel: stable

      - name: Install dependencies
        working-directory: ${{ matrix.app }}
        run: flutter pub get

      - name: Analyze
        working-directory: ${{ matrix.app }}
        run: flutter analyze

  flutter-build-web:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        app:
          - apps/interview-prep-coach
          - apps/personal-finance-coach
          - apps/capability-composer
          - apps/cold-outreach-coach
          - apps/creator-algorithm-coach
          - apps/discovery-prospector
          - apps/freelance-contract-reviewer
          - apps/reputation-dashboard
    steps:
      - uses: actions/checkout@v4

      - uses: subosito/flutter-action@v2
        with:
          flutter-version: "3.24.x"
          channel: stable

      - name: Install dependencies
        working-directory: ${{ matrix.app }}
        run: flutter pub get

      - name: Build web
        working-directory: ${{ matrix.app }}
        run: flutter build web --release
CIEOF
  echo "  ✓ .github/workflows/ci.yml (flutter-analyze + flutter-build-web matrix)"
}

# ── Commit & Push ───────────────────────────────────────────────────────────

_commit_and_push() {
  local clone="$1"
  local sat_id="$2"
  local remote_url="$3"
  local repo="$4"
  local license="${5:-mit}"

  cd "$clone"

  # Set remote
  if git remote get-url origin &>/dev/null; then
    git remote set-url origin "$remote_url"
  else
    git remote add origin "$remote_url"
  fi

  git add -A

  if git diff --cached --quiet && git diff --quiet; then
    echo "  ✓ No changes — already in sync"
    return 0
  fi

  git commit -m "chore(satellite): sync ${sat_id} from aicom monorepo

Auto-generated by scripts/mirror_satellites.sh"

  if [[ "$NO_PUSH" -eq 1 ]]; then
    echo "  📦 Committed locally (--no-push): $clone"
    return 0
  fi

  echo "  🚀 Pushing to ${GITHUB_HOST}/${GITHUB_ORG}/${repo} ..."
  git push origin "HEAD:$BRANCH" 2>&1 || {
    echo "  ⚠️  Push failed — check GH_PAT/GITHUB_TOKEN permissions"
    return 1
  }
  echo "  ✅ Pushed ${sat_id}"
}

# ═══════════════════════════════════════════════════════════════════════════
#  Main dispatch
# ═══════════════════════════════════════════════════════════════════════════

export_satellite() {
  local sat_id="$1"

  case "$sat_id" in
    aimarket-desktop)
      export_desktop_monorepo
      ;;
    aimarket-plugins)
      export_plugins
      ;;
    aimarket-sdks)
      export_simple "$sat_id" "aimarket-sdks" "aimarket-sdks" "mit"
      ;;
    pulse-terminal)
      export_simple "$sat_id" "apps/pulse-terminal" "pulse-terminal" "mit"
      ;;
    acex)
      export_simple "$sat_id" "acex" "acex" "apache-2.0"
      ;;
    ai-service-mesh)
      export_simple "$sat_id" "ai-service-mesh" "ai-service-mesh" "mit"
      ;;
    aimarket-hub)
      export_simple "$sat_id" "aimarket-hub" "aimarket-hub" "apache-2.0"
      ;;
    aimarket-widget)
      export_simple "$sat_id" "aimarket-widget" "aimarket-widget" "mit"
      ;;
    aimarket-protocol)
      export_simple "$sat_id" "aimarket-protocol" "aimarket-protocol" "mit"
      ;;
    aimarket-agent)
      export_simple "$sat_id" "aimarket-agent" "aimarket-agent" "mit"
      ;;
    aicom)
      echo ""
      echo "━━━ aicom (trimmed factory) ━━━"
      echo "  Use scripts/publish_aicom_factory.sh for trimmed factory push."
      ;;
    *)
      echo "ERROR: unknown satellite: $sat_id" >&2
      echo "Run: $0 --list  to see available satellites" >&2
      return 1
      ;;
  esac
}

# ── Main ────────────────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  AI-Factory Satellite Mirror                                 ║"
echo "║  Org: ${GITHUB_ORG} / Host: ${GITHUB_HOST}                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [[ -n "$SINGLE_SATELLITE" ]]; then
  export_satellite "$SINGLE_SATELLITE"
else
  echo "Mirroring all non-optional satellites …"
  echo ""

  errors=0
  while IFS= read -r sat_id; do
    export_satellite "$sat_id" || errors=$((errors + 1))
  done < <(_python_map list-ids)

  echo ""
  echo "══════════════════════════════════════════════════════════════"
  if [[ $errors -eq 0 ]]; then
    echo "✅ All satellites mirrored successfully."
  else
    echo "⚠️  ${errors} satellite(s) had errors."
  fi
fi

echo ""
echo "Satellite URLs:"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-desktop"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-sdks"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/pulse-terminal"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/acex"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/ai-service-mesh"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-hub"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-widget"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-protocol"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-agent"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-plugins"
echo ""
echo "Workflow: .github/workflows/mirror-satellites.yml"
