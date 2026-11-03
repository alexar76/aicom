-- Read-only: the lost remote targets (ok on 10-28, no ok from 10-30 until the fix) that have NOT read ok since the
-- fix went live, grouped by their current status and detail.
SET statement_timeout = '120s';
SET default_transaction_read_only = on;
WITH lost AS (
  SELECT t.id, t.last_status, t.last_detail FROM targets t
  WHERE t.delisted=0 AND t.transport <> 'stdio'
    AND t.id IN (SELECT DISTINCT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-10-28' AND observed_at < '2026-10-29')
    AND t.id NOT IN (SELECT DISTINCT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-10-30' AND observed_at < '2026-11-01T08:44:57Z'))
SELECT coalesce(last_status, '?') AS status, left(coalesce(last_detail, ''), 70) AS detail, count(*) AS targets
FROM lost
WHERE id NOT IN (SELECT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-11-01T08:44:57Z')
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15;
SELECT now() AT TIME ZONE 'UTC';
