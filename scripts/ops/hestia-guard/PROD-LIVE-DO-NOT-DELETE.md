# Live production: do not delete, move or "reclaim"

`/root/claudecode/aicom/hestia` is the compose project of the HESTIA hearth (hestia.modelmarket.dev): the
docker-compose files, the only copy of its settings (`hestia/.env`) and the tree `scripts/deploy_hestia.sh`
deploys from. The three `hestia-*` containers are started from it. A dated or old-looking name is not scrap.

This folder was found missing on 2026-11-19 and rebuilt on 2026-11-20. `aicom-hestia-guard` copies it to
`/var/lib/aicom-hestia-keep` every hour and puts back anything missing every 5 minutes, logging each restore
(`journalctl -u 'aicom-hestia-guard*'`). `/var/lib/aicom-hestia-keep` is that copy: do not delete it either.

Rules: AGENTS.md, "Server disk cleanup" and "Deleting files on servers", in the aicom repository.
