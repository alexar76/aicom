SET statement_timeout = '240s';
SET default_transaction_read_only = on;
SELECT left(observed_at,10) AS day,
  count(DISTINCT target_id) FILTER (WHERE status='http-401') AS h401,
  count(DISTINCT target_id) FILTER (WHERE status='protocol') AS proto,
  count(DISTINCT target_id) FILTER (WHERE status NOT IN ('ok','http-401','protocol')) AS other_fail,
  count(DISTINCT target_id) AS any_read,
  count(DISTINCT target_id) FILTER (WHERE protocol='2026-07-28') AS modern_ok
FROM observations o JOIN targets t ON t.id=o.target_id AND t.transport <> 'stdio'
WHERE observed_at >= '2026-10-26' AND observed_at < '2026-11-02' GROUP BY 1 ORDER BY 1;
-- remote targets ok on 10-28 that never got ok since 10-30, by their latest status
WITH before AS (SELECT DISTINCT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-10-28' AND observed_at < '2026-10-29'),
 after_ok AS (SELECT DISTINCT target_id FROM observations WHERE status='ok' AND observed_at >= '2026-10-30')
SELECT t.last_status, left(coalesce(t.last_detail,''),60), count(*) FROM before b JOIN targets t ON t.id=b.target_id AND t.transport<>'stdio'
WHERE b.target_id NOT IN (SELECT target_id FROM after_ok) GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12;
