SET statement_timeout = '120s';
SET default_transaction_read_only = on;
SELECT last_status, left(coalesce(last_detail,''),70) AS detail, count(*) FROM targets
 WHERE delisted = 0 AND transport <> 'stdio' AND (last_status = 'protocol' OR last_status LIKE 'http-4%')
 GROUP BY 1,2 ORDER BY 3 DESC LIMIT 25;
SELECT count(*) FILTER (WHERE last_status='ok') AS ok, count(*) AS remote_listed FROM targets WHERE delisted = 0 AND transport <> 'stdio';
SELECT transport, count(*) FROM targets WHERE delisted=0 GROUP BY 1;
