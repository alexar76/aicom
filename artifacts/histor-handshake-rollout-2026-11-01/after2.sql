SET statement_timeout = '120s';
SET default_transaction_read_only = on;
WITH lost AS (
  SELECT t.id, t.last_status, t.last_detail FROM targets t
  WHERE t.delisted=0 AND t.transport <> 'stdio'
    AND t.id IN (SELECT DISTINCT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-10-28' AND observed_at < '2026-10-29')
    AND t.id NOT IN (SELECT DISTINCT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-10-30' AND observed_at < '2026-11-01T08:44:57Z'))
SELECT count(*) AS lost,
  count(*) FILTER (WHERE id IN (SELECT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-11-01T08:44:57Z')) AS ok_since_deploy,
  count(*) FILTER (WHERE id IN (SELECT target_id FROM observations WHERE observed_at >= '2026-11-01T08:44:57Z' AND status <> 'ok')) AS failed_since_deploy,
  count(*) FILTER (WHERE s.next_due <= '2026-11-01T12:00:00Z') AS due_by_12z,
  count(*) FILTER (WHERE s.next_due <= '2026-11-01T18:00:00Z') AS due_by_18z,
  count(*) FILTER (WHERE s.next_due <= '2026-11-02T09:00:00Z') AS due_by_tomorrow_09z,
  max(s.next_due) AS last_due
FROM lost LEFT JOIN remote_schedule s ON s.target_id = lost.id;
SELECT now() AT TIME ZONE 'UTC';
