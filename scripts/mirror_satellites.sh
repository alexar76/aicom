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
elif cmd == "exclude-paths":
    sid = sys.argv[2]
    for s in MAP.get("satellites", []):
        if s["id"] == sid:
            print(" ".join(str(p) for p in (s.get("exclude_paths") or [])))
            raise SystemExit(0)
    print(f"ERROR: unknown satellite {sid}", file=sys.stderr)
    raise SystemExit(1)
elif cmd == "org":
    print(MAP.get("org", "alexar76"))
elif cmd == "desktop-skus":
    di = Path("desktop-integrations")
    if not di.is_dir():
        print("", end="")
        raise SystemExit(0)
    # SKU slugs from desktop_sku_manifest.py
    try:
        sys.path.insert(0, str(Path("scripts").resolve()))
        from desktop_sku_manifest import MANIFEST
        print(" ".join(MANIFEST.keys()))
    except ImportError:
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
if [[ -z "$TOKEN" ]]; then
  _origin_url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$_origin_url" =~ https://[^:/]+:([^@]+)@ ]]; then
    TOKEN="${BASH_REMATCH[1]}"
  fi
  unset _origin_url
fi

if [[ -z "$TOKEN" && "$DRY_RUN" -eq 0 ]]; then
  echo "⚠️  GH_PAT / GITHUB_TOKEN not set — will attempt unauthenticated git push"
  echo "   Set GH_PAT or GITHUB_TOKEN in environment for authenticated pushes."
fi

export AICOM_MIRROR_GH_TOKEN="$TOKEN"

satellite_remote_url() {
  local repo="$1"
  echo "https://${GITHUB_HOST}/${GITHUB_ORG}/${repo}.git"
}

git_auth() {
  if [[ -n "${AICOM_MIRROR_GH_TOKEN:-}" ]]; then
    local auth_header="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$AICOM_MIRROR_GH_TOKEN" | base64 | tr -d '\n')"
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=http.extraHeader \
    GIT_CONFIG_VALUE_0="$auth_header" \
    git "$@"
  else
    git "$@"
  fi
}

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
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Source:  $src_rel"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  [[ -d "$src" ]] || { echo "  ⚠️  SKIP: source missing: $src"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would rsync $src_rel/ → $repo/"
    return 0
  fi

  local desc=""
  desc="$(python3 - <<PY
import yaml
from pathlib import Path
m = yaml.safe_load(Path("${ROOT}/scripts/satellite-map.yaml").read_text(encoding="utf-8"))
for s in m.get("satellites") or []:
    if s.get("id") == "${sat_id}":
        print(s.get("description") or "")
        break
PY
)"
  python3 "$ROOT/scripts/ensure_github_repo.py" "$GITHUB_ORG" "$repo" "$desc" || return 1

  local clone="$WORKDIR/${repo}"

  # Clone or init
  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
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
  # VCS/build/cache + secrets. Secret patterns are excluded regardless of
  # per-satellite config so local secrets never reach a public mirror
  # (rsync copies the working tree, so .gitignore does NOT protect it).
  # Keep aligned with scripts/aicom_publish_config.py.
  for pat in .git .claude .cursor .venv venv node_modules __pycache__ .pytest_cache .mypy_cache .dart_tool build dist .mesh_data "*.egg-info" .DS_Store \
             .env ".env.*" "*.key" "*.pem" "*.enc" data/secrets "*_signing_key" "*_vrf_sk" dataset_salt \
             ":memory:" ":memory:-wal" ":memory:-shm" "*.sqlite3" "*.sqlite3-wal" "*.sqlite3-shm"; do
    rsync_args+=(--exclude "$pat")
  done
  if [[ -n "$extra_excludes" ]]; then
    IFS=' ' read -ra EXTRA <<< "$extra_excludes"
    for e in "${EXTRA[@]}"; do
      rsync_args+=(--exclude "$e")
    done
  fi

  rsync "${rsync_args[@]}" "$src/" "$clone/"

  bash "$ROOT/scripts/purge_mirror_runtime_artifacts.sh" "$clone"
  bash "$ROOT/scripts/verify_mirror_secrets.sh" "$clone"

  _copy_governance "$clone" "$license" "$repo" "${sat_id}"
  _copy_github_templates "$clone"

  _inject_mirror_banner "$clone" "$sat_id" "$repo"
  if [[ -f "$src/docs/badges/coverage.svg" ]]; then
    _copy_badge_tooling "$clone" "$src/docs/badges/coverage.svg"
  fi
  _inject_readme_badges "$sat_id" "$clone"

  _post_rsync_satellite_hook "$sat_id" "$clone" "$repo"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "$license"
}

_post_rsync_satellite_hook() {
  # Satellite-specific fixes after rsync, before commit (e.g. GitHub Pages root).
  local sat_id="$1"
  local clone="$2"
  local repo="$3"

  case "$sat_id" in
    dioscuri)
      _purge_dioscuri_mirror_clone "$clone"
      _mirror_landing_pages_root "$clone"
      python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" --dispatch-pages || true
      ;;
    theoros)
      _mirror_landing_pages_root "$clone"
      python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" --dispatch-pages || true
      ;;
    helios)
      _mirror_landing_pages_root "$clone"
      python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" --dispatch-pages || true
      ;;
    metis)
      if [[ -f "$clone/docs/landing/index.html" ]]; then
        : > "$clone/docs/landing/.nojekyll"
        echo "  ✓ docs/landing/ → GitHub Pages (workflow uploads folder)"
      fi
      python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" --dispatch-pages || true
      ;;
    skopos)
      if [[ -f "$clone/docs/landing/index.html" ]]; then
        : > "$clone/docs/landing/.nojekyll"
        echo "  ✓ docs/landing/ → GitHub Pages (workflow uploads folder)"
      fi
      python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" --dispatch-pages || true
      ;;
    alien-monitor)
      # AI registry loader reads scripts/satellite-map.yaml on the satellite.
      mkdir -p "$clone/scripts"
      if [[ -f "$ROOT/scripts/satellite-map.yaml" ]]; then
        cp "$ROOT/scripts/satellite-map.yaml" "$clone/scripts/satellite-map.yaml"
        echo "  ✓ scripts/satellite-map.yaml → satellite scripts/"
      fi
      ;;
    gaia)
      # Satellite Docker build needs oracle-core without the monorepo path.
      mkdir -p "$clone/vendor"
      if [[ -d "$ROOT/oracles/core" ]]; then
        rsync -a --delete \
          --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
          --exclude '*.egg-info' --exclude '.mypy_cache' \
          "$ROOT/oracles/core/" "$clone/vendor/oracle-core/"
        echo "  ✓ vendored oracles/core → vendor/oracle-core (GHCR standalone)"
      else
        echo "  ⚠️  oracles/core missing — Dockerfile.standalone will fail until vendored"
      fi
      if [[ -f "$clone/docs/landing/index.html" ]]; then
        : > "$clone/docs/landing/.nojekyll"
        echo "  ✓ docs/landing/ → GitHub Pages (workflow uploads folder)"
      fi
      python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" --dispatch-pages || true
      ;;
    aimarket-mcp)
      echo "  Glama:   https://glama.ai/mcp/servers/${GITHUB_ORG}/aimarket-mcp"
      echo "  MCP Registry: io.github.alexar76/aimarket-mcp"
      ;;
  esac
}

_mirror_landing_pages_root() {
  local clone="$1"
  if [[ -f "$clone/landing/index.html" ]]; then
    cp "$clone/landing/index.html" "$clone/index.html"
    if [[ -f "$clone/landing/.nojekyll" ]]; then
      cp "$clone/landing/.nojekyll" "$clone/.nojekyll"
    else
      : > "$clone/.nojekyll"
    fi
    echo "  ✓ landing/index.html → index.html (GitHub Pages branch / root)"
  fi
}

_purge_dioscuri_stray_source() {
  local src="$ROOT/dioscuri"
  local stray
  for stray in main.py config.yaml pipeline_worker.py finance_schemas.py finance_stats.py marketplace_taxonomy.py product_pnl.py; do
    if [[ -f "$src/$stray" ]]; then
      echo "  ⚠️  Removing stray dioscuri/$stray (factory file — not part of satellite)"
      rm -f "$src/$stray"
    fi
  done
  for stray in acex web agents ai-service-mesh aimarket-hub alien-monitor argus lottery oracles platon plugins ecosystem-landing dioscuri contracts deploy config core; do
    if [[ -d "$src/$stray" ]]; then
      echo "  ⚠️  Removing stray dioscuri/$stray/ (wrong publish target — not part of satellite)"
      rm -rf "$src/$stray"
    fi
  done
  for stray in scripts/mirror_satellites.sh scripts/publish_all_repos.sh scripts/satellite-map.yaml; do
    if [[ -f "$src/$stray" ]]; then
      echo "  ⚠️  Removing stray dioscuri/$stray (factory script — not part of satellite)"
      rm -f "$src/$stray"
    fi
  done
}

_purge_dioscuri_mirror_clone() {
  local clone="$1"
  local stray
  for stray in main.py config.yaml pipeline_worker.py; do
    rm -f "$clone/$stray"
  done
  for stray in acex web agents ai-service-mesh aimarket-hub alien-monitor argus lottery oracles platon plugins ecosystem-landing dioscuri contracts; do
    rm -rf "$clone/$stray"
  done
  rm -f "$clone/scripts/mirror_satellites.sh" "$clone/scripts/publish_all_repos.sh" "$clone/scripts/satellite-map.yaml"
}

export_dioscuri() {
  local sat_id="dioscuri"
  local extra_excludes
  extra_excludes="$(_python_map exclude-paths dioscuri)"
  _purge_dioscuri_stray_source
  export_simple "$sat_id" "dioscuri" "dioscuri" "mit" "$extra_excludes"
}

export_helios() {
  local sat_id="helios"
  local extra_excludes
  extra_excludes="$(_python_map exclude-paths helios)"
  export_simple "$sat_id" "helios" "helios" "mit" "$extra_excludes"
}

export_course() {
  # Build GitHub Pages + Colab assets, then rsync a courses/<name>/ folder to its satellite repo.
  local sat_id="$1"
  local src_rel="$2"
  local repo="$3"

  if [[ ! -d "$ROOT/$src_rel" ]]; then
    echo "  ⚠️  SKIP: $src_rel missing (full monorepo required)"
    return 1
  fi
  echo "  Building course site + Colab notebooks …"
  python3 "$ROOT/$src_rel/scripts/build_course_assets.py"
  export_simple "$sat_id" "$src_rel" "$repo" "mit"
}

# ── Mirror notice for read-only satellites ─────────────────────────────────
# See docs/repository-canonical-policy.md — the monorepo is canonical for
# every satellite. These are read-only mirrors: PRs are NOT accepted (a push
# here is overwritten on the next sync). Prepend a short banner to the
# satellite's README.md so visitors report bugs via Issues instead of PRs.
# Idempotent — re-running does not re-inject.
_inject_mirror_banner() {
  local target="$1"
  local sat_id="$2"
  local repo="$3"
  local readme="$target/README.md"
  local banner_marker="<!-- aicom-mirror-notice -->"

  [[ -f "$readme" ]] || return 0
  if grep -qF "$banner_marker" "$readme" 2>/dev/null; then
    return 0
  fi

  local mode
  mode="$(_satellite_history_mode "$sat_id")"

  local tmp
  tmp="$(mktemp)"
  {
    printf '%s\n' "$banner_marker"
    if [[ "$mode" == "live" ]]; then
      printf '> **🔄 Synced from a monorepo — but with a live history.** `%s` mirrors the\n' "$sat_id"
      printf '> canonical AI-Factory monorepo. History here is append-only (no force-push).\n'
      printf '> **Pull requests are welcome** — merged PRs are imported back into the monorepo\n'
      printf '> and re-synced here, so your contribution becomes canonical.\n'
      printf '> 💬 **[Issues](https://github.com/%s/%s/issues)** · **[Pull requests](https://github.com/%s/%s/pulls)** both welcome.\n' "$GITHUB_ORG" "$repo" "$GITHUB_ORG" "$repo"
    else
      printf '> **📖 Read-only mirror.** `%s` is published from the canonical AI-Factory monorepo.\n' "$sat_id"
      printf '> **Pull requests are not accepted** — any commit pushed here is overwritten by\n'
      printf '> `scripts/mirror_satellites.sh` on the next sync.\n'
      printf '> 🐞 Found a bug or have a request? Please **[open an issue](https://github.com/%s/%s/issues)**.\n' "$GITHUB_ORG" "$repo"
    fi
    printf '\n'
    cat "$readme"
  } > "$tmp"
  mv "$tmp" "$readme"
  echo "  ✓ $([ "$mode" = live ] && echo LIVE || echo MIRROR) banner injected into README.md"
}

# README + CI expect docs/badges/coverage.svg and scripts/ at satellite repo root.
_copy_badge_tooling() {
  local clone="$1"
  local svg_src="${2:-}"
  local script_src="${3:-$ROOT/scripts}"

  if [[ -f "$script_src/ci_static_badge.sh" && -f "$script_src/generate_static_badge.py" ]]; then
    mkdir -p "$clone/scripts"
    cp "$script_src/ci_static_badge.sh" "$script_src/generate_static_badge.py" "$clone/scripts/"
    chmod +x "$clone/scripts/ci_static_badge.sh"
    if [[ -f "$script_src/ci_coverage_badge.sh" && -f "$script_src/generate_coverage_badge.py" ]]; then
      cp "$script_src/ci_coverage_badge.sh" "$script_src/generate_coverage_badge.py" "$clone/scripts/"
      chmod +x "$clone/scripts/ci_coverage_badge.sh"
    fi
    echo "  ✓ scripts/ (coverage badge CI at repo root)"
  fi
  if [[ -n "$svg_src" && -f "$svg_src" ]]; then
    mkdir -p "$clone/docs/badges"
    local badge_dir
    badge_dir="$(dirname "$svg_src")"
    # Copy all self-hosted badge SVGs (ci/license/extras), not only coverage.
    shopt -s nullglob
    local svg
    for svg in "$badge_dir"/*.svg; do
      cp "$svg" "$clone/docs/badges/"
    done
    shopt -u nullglob
    # Ensure coverage.svg exists even if source used a different name path.
    [[ -f "$clone/docs/badges/coverage.svg" ]] || cp "$svg_src" "$clone/docs/badges/coverage.svg"
    echo "  ✓ docs/badges/*.svg (repo root)"
  fi
}

# CI + coverage badges (scripts/inject_readme_badges.py) — idempotent on mirror clone.
_inject_readme_badges() {
  local sat_id="$1"
  local target="$2"
  local readme="$target/README.md"
  [[ -f "$readme" ]] || return 0
  if python3 "$ROOT/scripts/inject_readme_badges.py" --satellite "$sat_id" --readme "$readme" 2>/dev/null; then
    echo "  ✓ README badges (CI + coverage)"
  fi
}

export_desktop_monorepo() {
  local sat_id="aimarket-desktop"
  local repo="aimarket-desktop"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Layout:  desktop-integrations/{app} → apps/{app}"
  echo "           desktop-integrations/packages → packages/"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  if [[ ! -d "$ROOT/desktop-integrations" ]]; then
    echo "  ⚠️  SKIP: desktop-integrations missing (full monorepo required)"
    return 1
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would build desktop monorepo layout → $repo/"
    return 0
  fi

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
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

  local rsync_base_args=(-a --exclude .git --exclude .claude --exclude .cursor --exclude .venv --exclude venv --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude .dart_tool --exclude build --exclude dist --exclude .DS_Store \
    --exclude .env --exclude '.env.*' --exclude '*.key' --exclude '*.pem' --exclude '*.enc' --exclude data/secrets --exclude '*_signing_key' --exclude '*_vrf_sk' --exclude dataset_salt)

  for sku in $skus; do
    # Allowlist sku names — prevents path traversal via rogue manifest entries (SH-1).
    if [[ ! "$sku" =~ ^[a-z0-9-]+$ ]]; then
      echo "  ⚠️  Skipping invalid sku name: $sku"
      continue
    fi
    local src_dir="$ROOT/desktop-integrations/$sku"
    local dst_dir="$clone/apps/$sku"
    if [[ -d "$src_dir" ]]; then
      mkdir -p "$dst_dir"
      rsync "${rsync_base_args[@]}" "$src_dir/" "$dst_dir/"
      echo "  ✓ apps/$sku"

      # ── Language packs (colocated) ──
      local lp_src="$ROOT/desktop-integrations/$sku/language-packs"
      local lp_dst="$dst_dir/language-packs"
      if [[ -d "$lp_src" ]]; then
        mkdir -p "$lp_dst"
        rsync "${rsync_base_args[@]}" "$lp_src/" "$lp_dst/"
        echo "    ↳ language-packs from desktop-integrations/$sku/"
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

  # Root README from monorepo (product gallery + ecosystem)
  if [[ -f "$ROOT/desktop-integrations/README.md" ]]; then
    cp "$ROOT/desktop-integrations/README.md" "$clone/README.md"
    echo "  ✓ README.md (from desktop-integrations/)"
  fi

  # ── Governance files ──
  _copy_governance "$clone" "mit" "aimarket-desktop" "desktop-monorepo"
  _copy_github_templates "$clone"

  # ── CI workflow ──
  mkdir -p "$clone/.github/workflows"
  _generate_desktop_ci "$clone"

  _copy_badge_tooling "$clone" "$ROOT/desktop-integrations/docs/badges/coverage.svg"

  _inject_mirror_banner "$clone" "$sat_id" "$repo"
  _inject_readme_badges "$sat_id" "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

_courses_skus() {
  local skus=""
  for d in "$ROOT/courses"/*-course/; do
    [[ -d "$d" ]] || continue
    skus="$skus $(basename "$d")"
  done
  echo "$skus"
}

export_courses_monorepo() {
  local sat_id="aimarket-courses"
  local repo="aimarket-courses"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Layout:  courses/*-course/ → {course}/ (monorepo root, like desktop apps/)"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  if [[ ! -d "$ROOT/courses" ]]; then
    echo "  ⚠️  SKIP: courses/ missing (full monorepo required)"
    return 1
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would build course monorepo → $repo/"
    return 0
  fi

  local desc=""
  desc="$(python3 - <<PY
import yaml
from pathlib import Path
m = yaml.safe_load(Path("${ROOT}/scripts/satellite-map.yaml").read_text(encoding="utf-8"))
for s in m.get("satellites") or []:
    if s.get("id") == "${sat_id}":
        print(s.get("description") or "")
        break
PY
)"
  python3 "$ROOT/scripts/ensure_github_repo.py" "$GITHUB_ORG" "$repo" "$desc" || return 1
  python3 "$ROOT/scripts/ensure_github_pages.py" "$GITHUB_ORG" "$repo" || true

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo not found — initializing fresh"
  fi

  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_base=(-a --exclude .git --exclude .claude --exclude .cursor --exclude .venv --exclude venv
    --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude .mypy_cache
    --exclude build --exclude dist --exclude .DS_Store --exclude site --exclude .github
    --exclude .coverage --exclude coverage.json
    --exclude .env --exclude '.env.*' --exclude '*.key' --exclude '*.pem' --exclude '*.enc'
    --exclude data/secrets --exclude '*_signing_key' --exclude '*_vrf_sk' --exclude dataset_salt)

  for sku in $(_courses_skus); do
    echo "  Building $sku (notebooks + site) …"
    python3 "$ROOT/courses/$sku/scripts/build_course_assets.py"
  done

  python3 "$ROOT/courses/_tooling/sync_course_readmes.py"
  python3 "$ROOT/courses/_tooling/sync_site_assets.py"
  python3 "$ROOT/courses/_tooling/update_monorepo_coverage.py" || true
  python3 "$ROOT/courses/_tooling/verify_course_readmes.py" || return 1
  echo "  ✓ README badges, site assets, coverage badge"

  cp "$ROOT/courses/README.md" "$clone/README.md"
  cp "$ROOT/courses/catalog.yaml" "$clone/catalog.yaml"
  cp "$ROOT/courses/.gitignore" "$clone/.gitignore" 2>/dev/null || true
  rsync "${rsync_base[@]}" "$ROOT/courses/_shared/" "$clone/_shared/"
  rsync "${rsync_base[@]}" "$ROOT/courses/_tooling/" "$clone/_tooling/"
  echo "  ✓ README.md, catalog.yaml, _shared/, _tooling/"

  for sku in $(_courses_skus); do
    mkdir -p "$clone/$sku"
    rsync "${rsync_base[@]}" "$ROOT/courses/$sku/" "$clone/$sku/"
    echo "  ✓ $sku/"
  done

  python3 "$clone/_tooling/build_monorepo_pages.py"
  echo "  ✓ site/ (portal + per-course Pages)"

  _copy_governance "$clone" "mit" "$repo" "courses-monorepo"
  _copy_github_templates "$clone"
  mkdir -p "$clone/.github/workflows"
  _generate_courses_ci "$clone"

  _copy_badge_tooling "$clone" "$ROOT/courses/docs/badges/coverage.svg"

  _inject_mirror_banner "$clone" "$sat_id" "$repo"
  _inject_readme_badges "$sat_id" "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

_generate_courses_ci() {
  local target="$1"
  cat > "$target/.github/workflows/ci.yml" <<'CIEOF'
name: CI

on:
  push:
    branches: ["main"]
  pull_request:
  workflow_dispatch:

jobs:
  pytest-courses:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        course:
          - orchestration-course
          - verifiable-randomness-course
          - mcp-security-course
          - agent-economy-course
          - mathematics-of-trust-course
          - optimization-with-proofs-course
          - smart-contracts-course
          - ai-factory-course
          - 3d-data-viz-course
          - physics-inspired-computing-course
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install & test course
        working-directory: ${{ matrix.course }}
        run: |
          python -m pip install --upgrade pip
          if [[ "${{ matrix.course }}" == orchestration-course || "${{ matrix.course }}" == agent-economy-course ]]; then
            mkdir -p _deps
            git clone --depth 1 https://github.com/alexar76/acex.git _deps/acex
            git clone --depth 1 https://github.com/alexar76/aimarket-hub.git _deps/aimarket-hub
            git clone --depth 1 https://github.com/alexar76/aimarket-agent.git _deps/aimarket-agent
            python3 scripts/patch_aimarket_hub.py _deps/aimarket-hub 2>/dev/null || true
            pip install -e _deps/aimarket-agent -e _deps/aimarket-hub
          fi
          ORACLES=$(python3 -c "import json; print(len(json.load(open('course.config.json')).get('oracles') or []))")
          if [[ "$ORACLES" != "0" ]]; then
            git clone --depth 1 https://github.com/alexar76/oracles.git _deps/oracles
            python3 <<'PY'
          import json, subprocess, sys
          cfg = json.load(open("course.config.json"))
          for pkg in cfg.get("oracles") or []:
              subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-e", f"_deps/oracles/{pkg}"])
          PY
          fi
          EXTRAS=$(python3 -c "import json; print(json.load(open('course.config.json')).get('pip_extras_default','[dev]'))")
          pip install -e ".${EXTRAS}"
          pytest -q --maxfail=3
          python3 scripts/build_course_assets.py

  portal-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build unified Pages tree
        run: python3 _tooling/build_monorepo_pages.py
CIEOF
  cat > "$target/.github/workflows/pages.yml" <<'PAGESEOF'
name: Deploy Pages

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build portal + all course sites
        run: |
          for d in *-course; do python3 "$d/scripts/build_course_assets.py"; done
          python3 _tooling/build_monorepo_pages.py
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
PAGESEOF
  echo "  ✓ .github/workflows/ci.yml + pages.yml (course matrix)"
}

export_plugins() {
  local sat_id="aimarket-plugins"
  local repo="aimarket-plugins"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

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

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
  fi

  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_args=(-a --exclude .git --exclude .claude --exclude .cursor --exclude .venv --exclude venv --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude build --exclude dist --exclude '*.egg-info' --exclude .DS_Store \
    --exclude .env --exclude '.env.*' --exclude '*.key' --exclude '*.pem' --exclude '*.enc' --exclude data/secrets --exclude '*_signing_key' --exclude '*_vrf_sk' --exclude dataset_salt)

  # Main plugins
  mkdir -p "$clone/plugins"
  if [[ -d "$ROOT/plugins" ]]; then
    rsync "${rsync_args[@]}" --exclude .github "$ROOT/plugins/" "$clone/plugins/"
    echo "  ✓ plugins/"
  fi

  # Extra: aimarket-provenance from aimarket-hub
  local provenance_src="$ROOT/aimarket-hub/plugins/aimarket-provenance"
  if [[ -d "$provenance_src" ]]; then
    mkdir -p "$clone/plugins/aimarket-provenance"
    rsync "${rsync_args[@]}" "$provenance_src/" "$clone/plugins/aimarket-provenance/"
    echo "  ✓ plugins/aimarket-provenance (from aimarket-hub)"
  fi

  # Glama / Docker: root Dockerfile + glama.json (MCP stdio server for registry checks)
  local mcp_packager="$ROOT/plugins/aimarket-mcp-packager"
  if [[ -f "$mcp_packager/Dockerfile.root-context" ]]; then
    cp "$mcp_packager/Dockerfile.root-context" "$clone/Dockerfile"
    echo "  ✓ Dockerfile (from aimarket-mcp-packager/Dockerfile.root-context)"
  fi
  if [[ -f "$mcp_packager/glama.json" ]]; then
    cp "$mcp_packager/glama.json" "$clone/glama.json"
    echo "  ✓ glama.json"
  fi
  if [[ -f "$mcp_packager/server.json" ]]; then
    cp "$mcp_packager/server.json" "$clone/server.json"
    echo "  ✓ server.json (Official MCP Registry)"
  fi

  _copy_governance "$clone" "mit" "aimarket-plugins"
  _copy_github_templates "$clone"

  # Repo-root README = the 15-plugin catalog with root-relative links, generated
  # from the single source of truth (plugins/README.md). It stays MCP-forward (a
  # dedicated MCP-server section), so the Glama registry — which indexes the
  # repo-root README alongside glama.json + Dockerfile — still surfaces the
  # aimarket-mcp-packager MCP server. The packager's own full README lives at
  # plugins/aimarket-mcp-packager/README.md and is no longer hoisted to the root.
  if [[ -f "$ROOT/plugins/README.md" ]]; then
    python3 "$ROOT/scripts/build_plugins_root_readme.py" \
      "$ROOT/plugins/README.md" "$clone/README.md"
    echo "  ✓ README.md (15-plugin catalog, MCP-forward, root-relative links)"
  fi
  _inject_mirror_banner "$clone" "$sat_id" "$repo"

  if [[ -f "$ROOT/plugins/.github/workflows/ci.yml" ]]; then
    mkdir -p "$clone/.github/workflows"
    cp "$ROOT/plugins/.github/workflows/ci.yml" "$clone/.github/workflows/ci.yml"
    echo "  ✓ .github/workflows/ci.yml (plugin smoke tests)"
  fi
  # Freshness: release-on-change so the Glama maintenance signal stays current
  # (GitHub Release only on real plugin changes — never a PyPI publish).
  if [[ -f "$ROOT/plugins/.github/workflows/freshness.yml" ]]; then
    mkdir -p "$clone/.github/workflows"
    cp "$ROOT/plugins/.github/workflows/freshness.yml" "$clone/.github/workflows/freshness.yml"
    echo "  ✓ .github/workflows/freshness.yml (release-on-change keepalive)"
  fi
  if [[ -f "$ROOT/plugins/.github/workflows/publish-mcp-registry.yml" ]]; then
    mkdir -p "$clone/.github/workflows"
    cp "$ROOT/plugins/.github/workflows/publish-mcp-registry.yml" "$clone/.github/workflows/publish-mcp-registry.yml"
    echo "  ✓ .github/workflows/publish-mcp-registry.yml"
  fi

  _copy_badge_tooling "$clone" "$mcp_packager/docs/badges/coverage.svg" "$ROOT/plugins/scripts"

  _inject_readme_badges "$sat_id" "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

export_oracles() {
  local sat_id="oracles"
  local repo="oracles"
  local src_rel="oracles"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Source:  $src_rel/ (17 oracles + oracle-core monorepo)"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"

  local src="$ROOT/$src_rel"
  [[ -d "$src" ]] || { echo "  ⚠️  SKIP: source missing: $src"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would rsync $src_rel/ → $repo/ (exclude .git, .gitea, .claude, .cursor)"
    return 0
  fi

  python3 "$ROOT/scripts/ensure_github_repo.py" "$GITHUB_ORG" "$repo" \
    "Verifiable AI-economy oracles — Platon, Chronos, Lattice, Murmuration, Lumen, Colony, and Turing on shared oracle-core." \
    || return 1

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo not found — initializing fresh"
  fi

  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_args=(-a)
  for pat in .git .gitea .claude .cursor .venv venv node_modules __pycache__ .pytest_cache .mypy_cache .dart_tool build dist .mesh_data "*.egg-info" .DS_Store .github .coverage coverage.json \
             .env ".env.*" "*.key" "*.pem" "*.enc" data/secrets "*_signing_key" "*_vrf_sk" dataset_salt; do
    rsync_args+=(--exclude "$pat")
  done

  rsync "${rsync_args[@]}" "$src/" "$clone/"

  _copy_governance "$clone" "mit" "$repo" "oracles"
  _copy_github_templates "$clone"

  mkdir -p "$clone/.github/workflows"
  cat > "$clone/.github/workflows/ci.yml" <<'CIEOF'
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install oracle-core + all oracles
        run: |
          python -m pip install --upgrade pip
          pip install -e "core[dev,pqc]"
          for o in chronos lattice murmuration lumen colony turing; do
            pip install -e "oracles/$o"
          done
          pip install -e "oracles/platon/backend[dev]"

      - name: Run the whole family test suite + coverage badge
        env:
          PLATON_TESTING: "1"
          AICOM_CI_ENFORCE_BADGE_SYNC: "1"
        run: |
          bash scripts/ci_coverage_badge.sh -- \
            core/tests \
            oracles/chronos/tests \
            oracles/lattice/tests \
            oracles/murmuration/tests \
            oracles/lumen/tests \
            oracles/colony/tests \
            oracles/turing/tests \
            oracles/platon/backend/tests \
            -q --cov=core --cov=oracles
CIEOF
  echo "  ✓ .github/workflows/ci.yml (oracle family tests)"

  _copy_badge_tooling "$clone" "$src/docs/badges/coverage.svg"

  _inject_mirror_banner "$clone" "$sat_id" "$repo"
  _inject_readme_badges "$sat_id" "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

export_platon() {
  local sat_id="platon"
  local repo="platon"
  local src_rel="platon"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} (Platon UMBRAL cave) ━━━"
  echo "  Source:  $src_rel/ — standalone educational app for oracle #1"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"
  echo "  Live:    oracles.modelmarket.dev/platon/umbral"

  local src="$ROOT/$src_rel"
  [[ -d "$src" ]] || { echo "  ⚠️  SKIP: source missing: $src"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would rsync $src_rel/ → $repo/ (exclude .git, data, gitea, ecosystem)"
    return 0
  fi

  python3 "$ROOT/scripts/ensure_github_repo.py" "$GITHUB_ORG" "$repo" \
    "Platon UMBRAL — educational cave app for oracle #1: 32D dynamical shadow oracle with live AIMarket backend." \
    || return 1

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo not found — initializing fresh"
  fi

  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_args=(-a)
  for pat in .git .gitea .claude .cursor .venv venv node_modules __pycache__ .pytest_cache .mypy_cache .dart_tool build dist .mesh_data "*.egg-info" .DS_Store data gitea ecosystem .github .coverage coverage.json \
             .env ".env.*" "*.key" "*.pem" "*.enc" data/secrets "*_signing_key" "*_vrf_sk" dataset_salt; do
    rsync_args+=(--exclude "$pat")
  done

  rsync "${rsync_args[@]}" "$src/" "$clone/"

  _copy_governance "$clone" "mit" "$repo" "platon"
  _copy_github_templates "$clone"

  mkdir -p "$clone/.github/workflows"
  cat > "$clone/.github/workflows/ci.yml" <<'CIEOF'
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Backend tests + coverage badge
        env:
          PLATON_TESTING: "1"
          AICOM_CI_ENFORCE_BADGE_SYNC: "1"
        run: |
          python -m pip install --upgrade pip
          pip install -e "backend[dev]"
          bash scripts/ci_coverage_badge.sh -- backend/tests -q --cov=backend

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Frontend build
        working-directory: frontend
        run: npm ci && npm run build
CIEOF
  echo "  ✓ .github/workflows/ci.yml (backend + frontend build)"

  local badge_svg="$src/docs/badges/coverage.svg"
  [[ -f "$badge_svg" ]] || badge_svg="$ROOT/oracles/docs/badges/coverage.svg"
  _copy_badge_tooling "$clone" "$badge_svg"

  _inject_mirror_banner "$clone" "$sat_id" "$repo"
  _inject_readme_badges "$sat_id" "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

export_lottery() {
  local sat_id="lottery"
  local repo="lottery"
  local src_rel="lottery"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} (AI-Agent Oracle Lottery) ━━━"
  echo "  Source:  $src_rel/ — on-chain lottery dApp (contracts + relayer + showcase)"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"
  echo "  Live:    lottery.modelmarket.dev"

  local src="$ROOT/$src_rel"
  [[ -d "$src" ]] || { echo "  ⚠️  SKIP: source missing: $src"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would rsync $src_rel/ → $repo/ (exclude .git, .github, .env)"
    return 0
  fi

  python3 "$ROOT/scripts/ensure_github_repo.py" "$GITHUB_ORG" "$repo" \
    "AI-Agent Oracle Lottery — an on-chain lottery that is an economic actor of the AI ecosystem: agents buy tickets, an unbiasable Platon+Chronos oracle beacon draws a LUMEN-reputation-weighted winner." \
    || return 1

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo created — initializing fresh mirror"
  fi

  find "$clone" -mindepth 1 -not -name '.git' -not -path '*/.git/*' -exec rm -rf {} + 2>/dev/null || true

  local rsync_args=(-a)
  for pat in .git .gitea .claude .cursor .venv venv node_modules __pycache__ .pytest_cache .mypy_cache .dart_tool build dist .mesh_data "*.egg-info" .DS_Store .github .env .coverage coverage.json \
             ".env.*" "*.key" "*.pem" "*.enc" data/secrets "*_signing_key" "*_vrf_sk" dataset_salt; do
    rsync_args+=(--exclude "$pat")
  done

  rsync "${rsync_args[@]}" "$src/" "$clone/"

  # Standalone mirror: use self-contained foundry profile (monorepo dev keeps foundry.toml).
  if [[ -f "$clone/contracts/foundry.docker.toml" ]]; then
    cp "$clone/contracts/foundry.docker.toml" "$clone/contracts/foundry.toml"
    echo "  ✓ contracts/foundry.toml (standalone lib/ profile for GitHub CI)"
  fi

  _copy_governance "$clone" "apache-2.0" "$repo" "lottery"
  _copy_github_templates "$clone"

  mkdir -p "$clone/.github/workflows"
  cat > "$clone/.github/workflows/ci.yml" <<'CIEOF'
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  forge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: foundry-rs/foundry-toolchain@v1
        with:
          version: stable

      - name: Install Foundry libraries
        working-directory: contracts
        run: |
          forge install OpenZeppelin/openzeppelin-contracts@v5.6.1 foundry-rs/forge-std@v1.9.4 --no-git

      - name: Forge test
        working-directory: contracts
        run: forge test -vv

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Relayer tests + coverage badge
        env:
          AICOM_CI_ENFORCE_BADGE_SYNC: "1"
        run: bash scripts/ci_lottery_coverage_badge.sh
CIEOF
  echo "  ✓ .github/workflows/ci.yml (Foundry tests + badge sync)"

  local badge_svg="$src/docs/badges/coverage.svg"
  _copy_badge_tooling "$clone" "$badge_svg"

  _inject_mirror_banner "$clone" "$sat_id" "$repo"
  _inject_readme_badges "$sat_id" "$clone"

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "apache-2.0"
}

export_oracle_gateway() {
  local sat_id="aimarket-oracle-gateway"
  local repo="aimarket-oracle-gateway"
  local src_rel="plugins/aimarket-oracle-gateway"

  echo ""
  echo "━━━ ${sat_id} (MCP Oracle Gateway) ━━━"
  echo "  Source:  $src_rel/ — stdio MCP server (Platon/Chronos/Lumen tools for Glama)"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo}"
  echo "  Glama:   https://glama.ai/mcp/servers/${GITHUB_ORG}/${repo}"

  [[ -d "$ROOT/$src_rel" ]] || { echo "  ⚠️  SKIP: source missing: $ROOT/$src_rel"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would rsync $src_rel/ → $repo/ (glama.json + Dockerfile at repo root)"
    return 0
  fi

  python3 "$ROOT/scripts/ensure_github_repo.py" "$GITHUB_ORG" "$repo" \
    "MCP server: verifiable oracle services (Platon VRF, Chronos VDF, LUMEN reputation) for AI agents — pay-per-call over the AIMarket protocol, every result independently verifiable." \
    || return 1

  export_simple "$sat_id" "$src_rel" "$repo" "mit"
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
    "oracles": (
        f"- `{name}` oracle monorepo (oracle-core + member oracles)\n"
        "- AIMarket v2 signed manifests, invoke API, post-quantum signing"
    ),
    "platon": (
        f"- `{name}` UMBRAL cave (32D dynamical oracle + educational cockpit)\n"
        "- AIMarket v2 platon.* capabilities, WebSocket telemetry, signing keys"
    ),
}
scope = scope_map.get(kind, f"- `{name}`")

print(f"""# Security Policy — {name}

## Reporting a Vulnerability

**Do not open a public issue for security bugs.**

Email: **alexar76@rambler.ru**

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

  # CODE_OF_CONDUCT.md
  if [[ -f "$ROOT/scripts/satellite-github-templates/CODE_OF_CONDUCT.md" ]]; then
    cp "$ROOT/scripts/satellite-github-templates/CODE_OF_CONDUCT.md" "$target/CODE_OF_CONDUCT.md"
  elif [[ -f "$ROOT/CODE_OF_CONDUCT.md" ]]; then
    cp "$ROOT/CODE_OF_CONDUCT.md" "$target/CODE_OF_CONDUCT.md"
  fi

  # CONTRIBUTORS.md
  cat > "$target/CONTRIBUTORS.md" <<EOF
# Contributors — ${name}

## Maintainers

- **AI Commons / AI-Factory** — primary maintainers ([alexar76@rambler.ru](mailto:alexar76@rambler.ru))

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

  echo "  ✓ Governance (LICENSE, SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, CONTRIBUTORS.md, README.md)"
}

_copy_github_templates() {
  local target="$1"
  local src_tpl="$ROOT/scripts/satellite-github-templates/.github"
  [[ -d "$src_tpl" ]] || return 0
  mkdir -p "$target/.github"
  # Merge templates; do not delete satellite-specific workflows from rsync.
  cp -R "$src_tpl/"* "$target/.github/" 2>/dev/null || true
  if [[ -f "$src_tpl/pull_request_template.md" ]]; then
    cp "$src_tpl/pull_request_template.md" "$target/pull_request_template.md"
  fi
  echo "  ✓ GitHub templates (ISSUE_TEMPLATE, pull_request_template)"
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

      - name: Fetch Dart SDK (path dependency)
        run: |
          git clone --depth 1 https://github.com/alexar76/aimarket-sdks.git /tmp/aimarket-sdks
          mkdir -p aimarket-sdks
          cp -R /tmp/aimarket-sdks/dart aimarket-sdks/dart

      - name: Wire apps/* → packages/ path deps
        run: |
          mkdir -p apps/packages
          ln -sf ../../packages/aicom_desktop_core apps/packages/aicom_desktop_core
          ln -sf ../../packages/aicom_platform_init apps/packages/aicom_platform_init

      - uses: subosito/flutter-action@v2
        with:
          channel: stable
          cache: true

      - name: Install dependencies
        working-directory: ${{ matrix.app }}
        run: flutter pub get

      - name: Build web
        working-directory: ${{ matrix.app }}
        run: flutter build web --release

  coverage-badge:
    runs-on: ubuntu-latest
    needs: flutter-build-web
    steps:
      - uses: actions/checkout@v4
      - name: Verify coverage badge (no git push)
        run: bash scripts/ci_static_badge.sh builds pass
CIEOF
  echo "  ✓ .github/workflows/ci.yml (flutter-build-web matrix)"
}

export_wiki_generic() {
  local sat_id="$1"
  local repo="$2"
  local src="$3"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"
  local wiki_branch="master"

  echo ""
  echo "━━━ ${sat_id} ━━━"
  echo "  Source:  ${src#"$ROOT/"}/*.md"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo} (branch ${wiki_branch})"
  echo "  Note:    wiki/ is local-only — not exported"

  [[ -d "$src" ]] || { echo "  ⚠️  SKIP: wiki source missing: $src"; return 1; }

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would sync wiki pages → $repo/ ($wiki_branch)"
    return 0
  fi

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$wiki_branch" &>/dev/null; then
    git_auth clone --depth 1 --branch "$wiki_branch" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$wiki_branch" 2>/dev/null || git checkout -b "$wiki_branch")
    }
  elif git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    wiki_branch="$BRANCH"
    git_auth clone --depth 1 --branch "$wiki_branch" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$wiki_branch" 2>/dev/null || git checkout -b "$wiki_branch")
    }
    echo "  ℹ️  Using branch $wiki_branch (master not found yet)"
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$wiki_branch")
    echo "  ℹ️  Remote wiki empty — initializing on $wiki_branch"
  fi

  find "$src" -maxdepth 1 -name '*.md' \
    ! -name 'README.md' \
    ! -name 'CODE_OF_CONDUCT.md' \
    ! -name 'pull_request_template.md' \
    ! -name '*-RU.md' \
    ! -name '*-ES.md' \
    ! -name 'FAQ-RU.md' \
    ! -name 'FAQ-ES.md' \
    -print0 | while IFS= read -r -d '' f; do
    cp -f "$f" "$clone/"
  done

  for old in "$clone"/*.md; do
    [[ -e "$old" ]] || continue
    local base
    base=$(basename "$old")
    [[ "$base" == "README.md" ]] && continue
    [[ -f "$src/$base" ]] || rm -f "$old"
    case "$base" in
      *-RU.md|*-ES.md|FAQ-RU.md|FAQ-ES.md) rm -f "$old" ;;
    esac
  done

  local saved_branch="$BRANCH"
  BRANCH="$wiki_branch"
  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
  BRANCH="$saved_branch"

  if [[ "$wiki_branch" == "master" ]] \
     && git_auth ls-remote "$remote_url" "refs/heads/main" &>/dev/null; then
    echo "  ↳ syncing main branch from master …"
    git_auth push --force origin "HEAD:main" 2>/dev/null || true
  fi
}

export_wiki() {
  export_wiki_generic "aicom-wiki" "aicom.wiki" "$ROOT/scripts/wiki-gitea"
}

export_wiki_argus() {
  export_wiki_generic "argus-wiki" "argus.wiki" "$ROOT/scripts/wiki-argus"
}

# ── GitHub profile README ───────────────────────────────────────────────────
# Special satellite: target repo is the profile repo (alexar76/alexar76).
# Publishes ONLY README.md — no governance, no LICENSE, no mirror banner.
# Existing files in the profile repo are preserved; only README.md is updated.
export_profile() {
  local sat_id="profile"
  local repo="alexar76"
  local src="$ROOT/scripts/profile-readme/README.md"
  local remote_url
  remote_url="$(satellite_remote_url "$repo")"

  echo ""
  echo "━━━ ${sat_id} (GitHub profile README) ━━━"
  echo "  Source:  scripts/profile-readme/README.md"
  echo "  Remote:  ${GITHUB_HOST}/${GITHUB_ORG}/${repo} (profile repo)"

  [[ -f "$src" ]] || { echo "  ⚠️  SKIP: profile README source missing: $src"; return 1; }

  if ! git_auth ls-remote "$remote_url" &>/dev/null; then
    echo "  ⏭  SKIP: profile repo ${GITHUB_ORG}/${repo} not found on GitHub"
    return 0
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would update README.md in ${GITHUB_ORG}/${repo}"
    return 0
  fi

  local clone="$WORKDIR/${repo}"

  if git_auth ls-remote "$remote_url" "refs/heads/$BRANCH" &>/dev/null; then
    git_auth clone --depth 1 --branch "$BRANCH" "$remote_url" "$clone" 2>/dev/null || {
      git_auth clone --depth 1 "$remote_url" "$clone"
      (cd "$clone" && git checkout -B "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH")
    }
  else
    mkdir -p "$clone"
    (cd "$clone" && git init && git checkout -b "$BRANCH")
    echo "  ℹ️  Remote repo not found — initializing fresh"
  fi

  # Only manage README.md + assets — do NOT wipe the repo (no banner / governance here).
  cp -f "$src" "$clone/README.md"
  echo "  ✓ README.md updated"

  # Sync hero/media assets referenced by the README (raw.githubusercontent URLs).
  local assets_src="$ROOT/scripts/profile-readme/assets"
  if [[ -d "$assets_src" ]]; then
    rm -rf "$clone/assets"
    cp -R "$assets_src" "$clone/assets"
    echo "  ✓ assets/ synced ($(find "$assets_src" -type f | wc -l | tr -d ' ') file(s))"
  fi

  _commit_and_push "$clone" "$sat_id" "$remote_url" "$repo" "mit"
}

# ── Commit & Push ───────────────────────────────────────────────────────────

_mirror_git_identity() {
  # Must match alexar76 GitHub account — otherwise Contributors shows empty or bots.
  export GIT_AUTHOR_NAME="${AICOM_MIRROR_GIT_AUTHOR_NAME:-Aleksandr Artamokhov}"
  export GIT_AUTHOR_EMAIL="${AICOM_MIRROR_GIT_AUTHOR_EMAIL:-86793359+alexar76@users.noreply.github.com}"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
  python3 "$ROOT/scripts/sanitize_git_commit_meta.py" \
    --check-author "$GIT_AUTHOR_NAME" "$GIT_AUTHOR_EMAIL"
}

# Publish history mode for a satellite: "live" or "mirror" (default).
#   mirror = squashed orphan snapshot, force-pushed (read-only; PRs overwritten).
#   live   = append-only real history, normal commit + push (PRs accepted).
# Source of truth: the per-satellite `history:` field in scripts/satellite-map.yaml.
_satellite_history_mode() {
  local sat_id="$1"
  python3 - "$sat_id" <<PY 2>/dev/null || echo mirror
import sys, yaml
from pathlib import Path
sat = sys.argv[1]
m = yaml.safe_load(Path("${ROOT}/scripts/satellite-map.yaml").read_text(encoding="utf-8"))
for s in m.get("satellites") or []:
    if s.get("id") == sat:
        print("live" if str(s.get("history", "mirror")).strip().lower() == "live" else "mirror")
        break
else:
    print("mirror")
PY
}

_commit_and_push() {
  local clone="$1"
  local sat_id="$2"
  local remote_url="$3"
  local repo="$4"
  local license="${5:-mit}"

  local mode
  mode="$(_satellite_history_mode "$sat_id")"

  # SAFETY: satellites publish to GitHub ONLY. A misconfigured SATELLITE_GITHUB_HOST
  # must never force-push a satellite onto Gitea (canon) or anywhere else.
  case "$remote_url" in
    *github.com/*|*github.com:*) : ;;
    *)
      echo "  ⛔ ${repo}: refusing to push — target is not a GitHub remote: ${remote_url}" >&2
      echo "     mirror_satellites.sh publishes to GitHub; check SATELLITE_GITHUB_HOST." >&2
      return 1
      ;;
  esac

  cd "$clone"

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

  _mirror_git_identity

  local msg_file
  msg_file="$(mktemp)"
  cat > "$msg_file" <<EOF
chore(satellite): sync ${sat_id} from aicom monorepo

Auto-generated by scripts/mirror_satellites.sh
EOF
  python3 "$ROOT/scripts/sanitize_git_commit_meta.py" < "$msg_file" > "${msg_file}.clean"
  mv "${msg_file}.clean" "$msg_file"

  # ═══════════════════════════════════════════════════════════════════════
  #  LIVE mode — append-only real history, PRs accepted (never orphan/force).
  # ═══════════════════════════════════════════════════════════════════════
  if [[ "$mode" == "live" ]]; then
    # Full history so we can inspect the tip and push a real fast-forward.
    git_auth fetch --unshallow 2>/dev/null || true

    # ── Divergence guard ──────────────────────────────────────────────────
    # Every outbound sync leaves a "chore(satellite): sync …" commit at the tip.
    # If the tip is anything else, a PR was merged (or someone pushed) on GitHub.
    # Refuse to sync — an rsync-overwrite would silently revert it. The operator
    # must reverse-import first, then opt in with ALLOW_DIVERGENCE=1.
    local head_subj
    head_subj="$(git log -1 --format=%s 2>/dev/null || true)"
    case "$head_subj" in
      "chore(satellite): sync"* | "") : ;;  # our own tip, or empty repo → ok
      *)
        if [[ "${ALLOW_DIVERGENCE:-0}" != "1" ]]; then
          rm -f "$msg_file"
          echo "  ⛔ ${repo}: satellite tip is NOT a monorepo-sync commit — a PR was likely merged:"
          echo "         \"$head_subj\""
          echo "     Refusing to sync (an overwrite would revert it). Import it first:"
          echo "         ./scripts/import_satellite_pr.sh ${sat_id}"
          echo "     …review + commit into the monorepo, then re-run with ALLOW_DIVERGENCE=1."
          return 1
        fi
        echo "  ⚠️  ${repo}: proceeding over external tip (ALLOW_DIVERGENCE=1): \"$head_subj\""
        ;;
    esac

    # ── Hard secret gate ──────────────────────────────────────────────────
    # Live history is permanent — a leaked secret cannot be scrubbed without a
    # force-push (which breaks the PR premise). Abort the push on any hit.
    if ! bash "$ROOT/scripts/verify_mirror_secrets.sh" "$clone"; then
      rm -f "$msg_file"
      echo "  ⛔ ${repo}: secret scan failed — refusing to push (live history is permanent)."
      return 1
    fi

    # Normal commit ON TOP of the existing history — no orphan.
    git add -A
    git -c user.name="$GIT_AUTHOR_NAME" -c user.email="$GIT_AUTHOR_EMAIL" \
      commit --author="$GIT_AUTHOR_NAME <$GIT_AUTHOR_EMAIL>" -F "$msg_file"
    rm -f "$msg_file"

    if [[ "$NO_PUSH" -eq 1 ]]; then
      echo "  📦 Committed locally (--no-push, live): $clone"
      return 0
    fi

    echo "  🚀 Pushing (append-only, no --force) to ${GITHUB_HOST}/${GITHUB_ORG}/${repo} ..."
    git_auth push origin "HEAD:$BRANCH" 2>&1 || {
      echo "  ⚠️  Push rejected (non-fast-forward means the remote advanced —"
      echo "       likely a just-merged PR). Do NOT --force. Reverse-import, then retry:"
      echo "         ./scripts/import_satellite_pr.sh ${sat_id}"
      return 1
    }
    if command -v python3 >/dev/null 2>&1; then
      python3 "$ROOT/scripts/prune_github_collaborators.py" "$GITHUB_ORG" "$repo" 2>/dev/null || true
    fi
    echo "  ✅ Pushed ${sat_id} (live history)"
    return 0
  fi

  # ═══════════════════════════════════════════════════════════════════════
  #  MIRROR mode (default) — one squashed orphan commit, force-pushed.
  #  Read-only: no github-actions[bot] / AI co-author history; PRs overwritten.
  # ═══════════════════════════════════════════════════════════════════════
  git checkout --orphan "mirror-${BRANCH}" 2>/dev/null || git checkout --orphan "mirror-${BRANCH}"
  git add -A
  git -c user.name="$GIT_AUTHOR_NAME" -c user.email="$GIT_AUTHOR_EMAIL" \
    commit --author="$GIT_AUTHOR_NAME <$GIT_AUTHOR_EMAIL>" -F "$msg_file"
  rm -f "$msg_file"
  git branch -M "$BRANCH"

  if [[ "$NO_PUSH" -eq 1 ]]; then
    echo "  📦 Committed locally (--no-push): $clone"
    return 0
  fi

  echo "  🚀 Force-pushing squashed mirror to ${GITHUB_HOST}/${GITHUB_ORG}/${repo} ..."
  git_auth push --force origin "HEAD:$BRANCH" 2>&1 || {
    echo "  ⚠️  Push failed — check GH_PAT/GITHUB_TOKEN permissions"
    return 1
  }
  # Glama (and similar) pin commit SHAs — squashed force-push invalidates old SHAs.
  # Move a stable tag so admins can pin refs/tags/glama-build instead of a dead hash.
  if [[ "$sat_id" == "aimarket-mcp" || "$sat_id" == "aimarket-oracle-gateway" ]]; then
    git tag -f glama-build HEAD
    git_auth push --force origin refs/tags/glama-build 2>/dev/null || true
    echo "  🏷️  Updated tag glama-build (pin this on Glama, not an old commit SHA)"
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 "$ROOT/scripts/prune_github_collaborators.py" "$GITHUB_ORG" "$repo" 2>/dev/null || true
  fi
  echo "  ✅ Pushed ${sat_id}"
}

# ═══════════════════════════════════════════════════════════════════════════
#  Main dispatch
# ═══════════════════════════════════════════════════════════════════════════

export_satellite() {
  local sat_id="$1"
  if [[ "$sat_id" == "course" ]]; then
    sat_id="aimarket-courses"
  fi

  case "$sat_id" in
    profile)
      export_profile
      ;;
    aimarket-courses)
      export_courses_monorepo
      ;;
    aimarket-desktop)
      export_desktop_monorepo
      ;;
    aimarket-plugins)
      export_plugins
      ;;
    aimarket-oracle-gateway)
      export_oracle_gateway
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
    linkedin-profile-coach)
      export_simple "$sat_id" "coach" "linked-in-profile-coach" "mit"
      ;;
    aicom-landing)
      export_simple "$sat_id" "aicom-landing" "aicom-landing" "mit"
      ;;
    aimarket-protocol)
      export_simple "$sat_id" "aimarket-protocol" "aimarket-protocol" "mit"
      ;;
    aimarket-agent)
      export_simple "$sat_id" "aimarket-agent" "aimarket-agent" "mit"
      ;;
    aicom-wiki)
      export_wiki
      ;;
    argus-wiki)
      export_wiki_argus
      ;;
    alien-monitor)
      local extra_excludes
      extra_excludes="$(_python_map exclude-paths alien-monitor)"
      export_simple "$sat_id" "alien-monitor" "alien-monitor" "mit" "$extra_excludes"
      ;;
    oracles)
      export_oracles
      ;;
    platon)
      export_platon
      ;;
    lottery)
      export_lottery
      ;;
    argus)
      local extra_excludes
      extra_excludes="$(_python_map exclude-paths argus)"
      export_simple "$sat_id" "argus" "argus" "mit" "$extra_excludes"
      ;;
    dioscuri)
      export_dioscuri
      ;;
    theoros)
      export_simple "$sat_id" "theoros" "theoros" "mit"
      ;;
    helios)
      export_helios
      ;;
    metis)
      local extra_excludes
      extra_excludes="$(_python_map exclude-paths metis)"
      export_simple "$sat_id" "metis" "metis" "mit" "$extra_excludes"
      ;;
    skopos)
      local extra_excludes
      extra_excludes="$(_python_map exclude-paths skopos)"
      export_simple "$sat_id" "skopos" "skopos" "mit" "$extra_excludes"
      ;;
    gaia)
      local extra_excludes
      extra_excludes="$(_python_map exclude-paths gaia)"
      export_simple "$sat_id" "gaia" "gaia" "mit" "$extra_excludes"
      ;;
    aimarket-mcp)
      local extra_excludes
      extra_excludes="$(_python_map exclude-paths aimarket-mcp)"
      export_simple "$sat_id" "aimarket-mcp" "aimarket-mcp" "mit" "$extra_excludes"
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
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-oracle-gateway"
  echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aicom.wiki"
  echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/argus.wiki"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/linked-in-profile-coach"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aicom-landing"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/alien-monitor"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/oracles"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/platon"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/lottery"
echo "  https://${GITHUB_HOST}/${GITHUB_ORG}/aimarket-courses"
echo "  https://${GITHUB_ORG}.github.io/aimarket-courses/"
echo ""
echo "All repos: ./scripts/publish_all_repos.sh"
echo "Workflow:  .github/workflows/mirror-satellites.yml"
