#!/usr/bin/env bash
# Print the daily landing-request report from production SKOPOS.
set -euo pipefail

report="$(dirname -- "$0")/skopos-search.sql"
ssh -o BatchMode=yes root@skopos.modelmarket.dev \
  "docker exec -i metis-skopos-postgres sh -c 'PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -X -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1'" \
  < "$report"
