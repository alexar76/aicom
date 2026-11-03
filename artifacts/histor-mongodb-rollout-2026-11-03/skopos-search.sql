-- Run against the SKOPOS PostgreSQL database with psql -X.
-- Counts landing requests, not people. Missing referrers cannot be attributed.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';

WITH landing AS (
    SELECT left(ts_utc, 10) AS day_utc,
           lower(coalesce(referer_domain, '')) AS referrer,
           lower(coalesce(referer, '')) AS referrer_url,
           path
    FROM http_requests
    WHERE host = 'histor.modelmarket.dev'
      AND ts_utc >= '2026-11-03'
      AND (path = '/mongodb-mcp-read-only-tools.html'
           OR path LIKE '/mongodb-mcp-read-only-tools.html?%')
      AND method = 'GET'
      AND status IN (200, 304)
      AND coalesce(ua_is_bot, 0) = 0
      AND coalesce(user_agent, '') ~* 'Mozilla/'
      AND user_agent !~* '(bot|crawl|spider|headless|preview|scanner|skopos)'
      AND path !~* '[?&]skopos_probe='
),
classified AS (
    SELECT day_utc, CASE
        WHEN path ~* '[?&](gclid|dclid|msclkid|gbraid|wbraid)='
          OR path ~* '[?&]utm_medium=(cpc|ppc|paidsearch|paid_search|paid)([&]|$)' THEN 'paid-tagged'
        WHEN referrer ~ '^(www\.)?google\.(com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})$' THEN 'google'
        WHEN referrer IN ('bing.com', 'www.bing.com') THEN 'bing'
        WHEN referrer IN ('duckduckgo.com', 'www.duckduckgo.com', 'html.duckduckgo.com', 'lite.duckduckgo.com') THEN 'duckduckgo'
        WHEN referrer_url ~ '^https?://search\.brave\.com(/|$)' THEN 'brave'
        WHEN referrer_url ~ '^https?://([a-z]{2}\.)?search\.yahoo\.com(/|$)' THEN 'yahoo'
        WHEN referrer IN ('yandex.ru', 'yandex.com', 'ya.ru') THEN 'yandex'
        WHEN referrer IN ('ecosia.org', 'www.ecosia.org') THEN 'ecosia'
        WHEN referrer IN ('', '-') THEN 'unattributed'
        ELSE 'other'
    END AS source
    FROM landing
)
SELECT day_utc, source, count(*) AS landing_requests
FROM classified
GROUP BY day_utc, source
ORDER BY day_utc DESC, source;

COMMIT;
