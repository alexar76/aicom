#!/usr/bin/env bash
# Sync physical-sensor catalogs: gaia (canonical) → atlas (mirror).
#
#   ./scripts/sync_physical_sensor_catalogs.sh
#   ./scripts/sync_physical_sensor_catalogs.sh --check
#
# Catalogs:
#   gaia/config/om_mesh_cities.yaml  ↔ atlas/config/om_mesh_cities.yaml
#   gaia/config/extra_sensors.yaml   ↔ atlas/config/extra_sensors.yaml
#
# Prefer one-command add: python3 scripts/add_gaia_atlas_sensor.py
# Guide: docs/add-gaia-atlas-sensor.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK=1
fi

sync_one() {
  local name="$1"
  local src="${ROOT}/gaia/config/${name}"
  local dst="${ROOT}/atlas/config/${name}"
  if [[ ! -f "$src" ]]; then
    echo "error: missing canonical $src" >&2
    exit 1
  fi
  if [[ "$CHECK" -eq 1 ]]; then
    if [[ ! -f "$dst" ]]; then
      echo "error: missing mirror $dst — run without --check" >&2
      exit 1
    fi
    if ! cmp -s "$src" "$dst"; then
      echo "error: $name out of sync (gaia ≠ atlas)" >&2
      echo "  fix: ./scripts/sync_physical_sensor_catalogs.sh" >&2
      diff -u "$dst" "$src" | head -40 || true
      exit 1
    fi
    echo "OK: gaia/config/${name} ≡ atlas/config/${name}"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "Synced → $dst"
  fi
}

sync_one om_mesh_cities.yaml
sync_one extra_sensors.yaml
