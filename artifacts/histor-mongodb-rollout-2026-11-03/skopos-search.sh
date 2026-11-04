#!/usr/bin/env bash
# Print a daily landing-request report from production SKOPOS.
set -euo pipefail

case "${1:-search}" in
  search|hf-dataset|pypi-histor) report="$(dirname -- "$0")/skopos-${1:-search}.sql" ;;
  *) echo "Usage: $0 [search|hf-dataset|pypi-histor]" >&2; exit 2 ;;
esac
ssh -o BatchMode=yes root@skopos.modelmarket.dev \
  "docker exec -i metis-skopos-postgres sh -c 'PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -X -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1'" \
  < "$report"
