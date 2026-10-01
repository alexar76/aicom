#!/usr/bin/env bash
# Deprecated wrapper — prefer:
#   python3 scripts/add_gaia_atlas_sensor.py --kind open-meteo-pair ...
# Still syncs Open-Meteo mesh + extra_sensors catalogs.
exec "$(cd "$(dirname "$0")" && pwd)/sync_physical_sensor_catalogs.sh" "$@"
