"""The day-one remote cohort counted by registry entry and by host, so no single publisher sets the share.

    python3 cohort_by_host.py DIR      # needs duckdb; DIR holds servers.jsonl.gz and changes.jsonl.gz
"""
import json, sys
import duckdb

d = sys.argv[1]
base = f"""WITH base AS (SELECT id, split_part(endpoint, '/', 3) AS host FROM '{d}/servers.jsonl.gz'
  WHERE transport <> 'stdio' AND NOT delisted AND toolSetDigest IS NOT NULL AND firstPinned <= '2026-09-24T23:59:59Z'),
changed AS (SELECT DISTINCT serverId FROM '{d}/changes.jsonl.gz' WHERE json_extract_string(summaryJson, '$.detail') = 'full'),
h AS (SELECT host, count(*) n, count(*) FILTER (WHERE id IN (SELECT serverId FROM changed)) c FROM base GROUP BY host)
"""
q = lambda s: duckdb.sql(base + s).fetchall()
out = {
    'entries': q("SELECT sum(n), sum(c) FROM h")[0],
    'hosts': q("SELECT count(*), count(*) FILTER (WHERE c > 0) FROM h")[0],
    'single_entry_hosts': q("SELECT count(*), count(*) FILTER (WHERE c > 0) FROM h WHERE n = 1")[0],
    'entries_on_hosts_le10': q("SELECT sum(n), sum(c) FROM h WHERE n <= 10")[0],
    'hosts_gt10': q("SELECT count(*), sum(n), sum(c) FROM h WHERE n > 10")[0],
    'top_hosts': q("SELECT n, c FROM h ORDER BY n DESC LIMIT 5"),
}
print(json.dumps(out))
