-- Remote servers read ok on 2026-10-28 with no ok read from 2026-10-30 until the reader fix went live
-- (2026-11-01T08:44:57Z): their last failure before the fix, and their first ok read after it up to the as-of time
-- (2026-11-01T09:15:00Z). Some broke for their own reasons; failed_status and failed_detail tell them apart.
SET statement_timeout = '300s';
SET default_transaction_read_only = on;
COPY (
  WITH ok28 AS (SELECT DISTINCT target_id FROM observations WHERE status = 'ok'
                AND observed_at >= '2026-10-28T00:00:00Z' AND observed_at < '2026-10-29T00:00:00Z'),
  okgap AS (SELECT DISTINCT target_id FROM observations WHERE status = 'ok'
            AND observed_at >= '2026-10-30T00:00:00Z' AND observed_at < '2026-11-01T08:44:57Z'),
  lastfail AS (SELECT DISTINCT ON (target_id) target_id, status, detail, observed_at FROM observations
               WHERE status <> 'ok' AND observed_at >= '2026-10-30T00:00:00Z' AND observed_at < '2026-11-01T08:44:57Z'
               ORDER BY target_id, observed_at DESC),
  firstok AS (SELECT DISTINCT ON (target_id) target_id, observed_at, protocol FROM observations
              WHERE status = 'ok' AND observed_at >= '2026-11-01T08:44:57Z' AND observed_at <= '2026-11-01T09:15:00Z'
              ORDER BY target_id, observed_at)
  SELECT t.id AS server_id, t.name, t.endpoint, f.status AS failed_status, f.detail AS failed_detail,
         f.observed_at AS failed_at, k.observed_at AS first_ok_after_fix, k.protocol AS protocol_after_fix
  FROM ok28 JOIN targets t ON t.id = ok28.target_id AND t.transport <> 'stdio' AND t.delisted = 0
  LEFT JOIN lastfail f ON f.target_id = t.id LEFT JOIN firstok k ON k.target_id = t.id
  WHERE t.id NOT IN (SELECT target_id FROM okgap)
  ORDER BY t.id
) TO STDOUT WITH (FORMAT csv, HEADER);
