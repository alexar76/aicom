SET statement_timeout = '120s';
SET default_transaction_read_only = on;
SELECT CASE WHEN o.observed_at >= '2026-11-01T08:44:57Z' THEN 'after' ELSE 'before' END AS phase,
  count(*) AS obs, count(*) FILTER (WHERE o.status='ok') AS ok,
  count(*) FILTER (WHERE o.status='protocol') AS protocol, count(*) FILTER (WHERE o.status IN ('http-401','http-403')) AS h401_403,
  min(o.observed_at), max(o.observed_at)
FROM observations o JOIN targets t ON t.id=o.target_id AND t.transport <> 'stdio'
WHERE o.observed_at >= '2026-11-01T07:44:57Z' GROUP BY 1 ORDER BY 1 DESC;
