-- Counts browser-like HISTOR entry requests by UTC day, with observed PyPI referrals.
-- The tag can survive a stripped referrer and can also be carried by a shared link.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';

SELECT
    left(ts_utc, 10) AS day_utc,
    count(*) AS tagged_entry_requests,
    count(*) FILTER (
        WHERE lower(referer_domain) IN ('pypi.org', 'www.pypi.org')
    ) AS pypi_referrer_requests
FROM http_requests
WHERE host = 'histor.modelmarket.dev'
  AND ts_utc >= '2026-11-04'
  AND log_source LIKE 'file:%'
  AND path ~ '^/servers[?]([^&]*&)*from=pypi-histor(&|$)'
  AND path !~* '^/servers[?]([^&]*&)*skopos_probe(=|&|$)'
  AND method = 'GET'
  AND status IN (200, 304)
  AND coalesce(ua_is_bot, 0) = 0
  AND user_agent ~* '^Mozilla/'
  AND user_agent !~* '(bot|crawl|spider|headless|preview|scanner|skopos|probe|audit|google-safety|facebookexternalhit|lighthouse|slurp)'
GROUP BY 1
ORDER BY 1 DESC;

COMMIT;
