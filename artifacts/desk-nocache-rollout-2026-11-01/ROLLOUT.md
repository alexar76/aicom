# Desk web containers: Cache-Control no-cache for pages, scripts and styles (2026-11-01)

After the pricing block went out (67bbda2bb), the owner's Firefox kept showing the old plinth page: the desks sent
no Cache-Control, so browsers cached html/js/css by heuristic for hours. `kernel/web/nginx.conf` now maps `.html`,
`.js` and `.css` to `Cache-Control: no-cache`. The browser revalidates with the ETag and gets a 304 while the file is
unchanged. The header is set at server level through a `map`, because an `add_header` inside a location would drop
the server's security headers there. API answers and fonts or images are untouched.

`rollout.sh` ran on skopos-vps, one desk after another. For each desk it:
1. built an image FROM the desk's pinned `aicom-security:<desk>-web-os-20261031` (OS patches kept), replacing only
   the config, as `aicom-security:<desk>-web-nc-20261101`;
2. ran `nginx -t` on `<desk>_default`;
3. rewrote the image line in `docker-compose.metis.yml` (backup in `/root/cite-desks-backups/nocache-20261101/`);
4. recreated the web container only;
5. checked `/app.js` for no-cache and CSP, and `/api/public/health` through the proxy, rolling back on failure.

All five passed. Checked from outside on every desk: `/`, `/app.js` and `/styles.css` answer 200 with no-cache;
`/favicon.svg` and `/api/public/status` answer 200 with no Cache-Control, as before.

Rollback per desk: copy the backed-up `docker-compose.metis.yml` back, then
`docker compose -p <desk> -f docker-compose.yml -f docker-compose.metis.yml up -d --no-deps --no-build web`.
