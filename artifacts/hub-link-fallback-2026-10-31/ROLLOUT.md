# modelmarket.dev: every bare link in the site's cyan — 2026-10-31

Owner: «Да, выкатывай» (after the auto-mode classifier refused the first attempt without it). Code: aicom 0f438972e
(`aimarket_hub/theme.py`: `:where(a[href]) { color: var(--cyan); }` and a hover colour, zero specificity, so every
styled link keeps its own colour). Before it, "operator guide" on /examples and any other bare link took the
browser's default blue, about 2:1 on the dark field. Checked on the live /developers, /examples, /start, /operator,
/widget/demo, /plugins/demo: of 216 links only "operator guide" changed. Hub tests 517 passed.

Apex hub on factory-vps. First roll refused by roll.sh itself (`roll-apex-1-refused-image-changed.log`): another
session had moved the hub to `aicom-security:modelmarket-hub-os-20261031` (OS package updates built FROM our
`examples-links-20261031`, which it kept). It was rolling OS images on factory-vps (themis among them), so we
waited for `rollout_os_candidates.py` to finish, rebuilt the overlay FROM the new image (`build.sh` takes the
running image) and smoke-tested it again. Rolled 19:36Z with roll.sh (SQLite backup
`/app/data/hub-backup-pre-3160-20261031T193642Z.db`, health :9083 and THEMIS :9460): healthy; THEMIS recreated on
its OS-updated image (0548e7df5325 = `aicom-security:themis-os-20261031`).

Verified live: /assets/site.css carries the rule; "operator guide" and the route links compute to rgb(56,224,255),
buttons keep rgb(56,224,255), the LIVE nav item keeps its green; /ai-market/v2/health 200.

Rollback: previous container `modelmarket-hub-security-prev-1793475403313210073` (+ `themis-security-prev-1793475403313210073`)
via rollout_container.py, or roll onto `aicom-security:modelmarket-hub-os-20261031`. Other hubs get it with their
next rollout.
