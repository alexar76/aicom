# HISTOR Watch button rollout — 11 November 2026

Applied the `/check` button and five translated labels to the six JavaScript files already served by production. The production baseline differed from the workspace, so the rollout applied the feature diff to the production files. All six deployed hashes matched on the public HTTPS endpoint. The deploy used a direct SSH transfer and an nginx reload.

In the browser, `/check?lang=ru` resolved `https://homouniversalis.ai/mcp` to `ai.homouniversalis/viveka-oracle`, ID `4604b80f59f25096`, and displayed a valid signature. Clicking «Следить за изменениями» opened the [server’s feed](https://histor.modelmarket.dev/feed.xml?watch=4604b80f59f25096). The public response was `application/atom+xml`. The Atom ID and self link matched the URL, and each of its 10 entries linked to `/s/4604b80f59f25096`.

The production container kept its image and start time. `/health` reported PostgreSQL and an active crawl before and after the reload.

## Nginx configuration and rollback

- The active vhost includes `/etc/nginx/snippets/histor-watch-cta.conf`, which serves the six files from `/var/www/histor-watch-cta-20261111/`.
- The pre-rollout vhost, added snippet and both sets of asset hashes are in `/root/histor-backups/watch-cta-20261111.smDBI4/` on the production host.
- To roll back, remove the `histor-watch-cta.conf` include from `/etc/nginx/sites-available/histor.modelmarket.dev`, run `nginx -t`, then reload nginx. After a future image serves the updated files, remove the same include so later image versions serve their own assets.
