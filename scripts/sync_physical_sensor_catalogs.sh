#!/usr/bin/env bash
# Sync physical-sensor catalogs: gaia (canonical) → atlas (mirror) and ATLAS's packaged copy.
#
#   ./scripts/sync_physical_sensor_catalogs.sh
#   ./scripts/sync_physical_sensor_catalogs.sh --check
#
# Catalogs:
#   gaia/config/om_mesh_cities.yaml  ↔ atlas/config/om_mesh_cities.yaml
#   gaia/config/sc_mesh_cities.yaml  ↔ atlas/config/sc_mesh_cities.yaml
#   gaia/config/extra_sensors.yaml   ↔ atlas/config/extra_sensors.yaml
#
# Each also goes to atlas/atlas/_config/, the copy the aimarket-atlas wheel carries (setuptools ships package
# data only from inside the package). GAIA's wheel takes its copies straight from gaia/config/ (hatch force-include).
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
  local dst="${ROOT}/${2:-atlas/config}/${name}"
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
      echo "error: $name out of sync (gaia/config ≠ ${2:-atlas/config})" >&2
      echo "  fix: ./scripts/sync_physical_sensor_catalogs.sh" >&2
      diff -u "$dst" "$src" | head -40 || true
      exit 1
    fi
    echo "OK: gaia/config/${name} ≡ ${2:-atlas/config}/${name}"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "Synced → $dst"
  fi
}

for name in om_mesh_cities.yaml sc_mesh_cities.yaml extra_sensors.yaml; do
  sync_one "$name"
  sync_one "$name" atlas/atlas/_config
done
