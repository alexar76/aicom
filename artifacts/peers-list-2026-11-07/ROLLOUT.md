# HISTOR peer cross-checks as one list (admin-vps, 2026-11-07)

Owner: «должен быть список таких сверок настраиваемый», «Да, делай», then «ScraperWatch … перенос на общий таймер — делай».

## What runs now

| Piece | Where on admin-vps | Repository |
|---|---|---|
| list of observers | `/etc/histor/peers.json` | `histor/deploy/peers.json` |
| runner | `/usr/local/sbin/histor-peers` | `histor/deploy/peers_check.sh` |
| modules mounted while the image predates them | `/usr/local/lib/histor-peers/{peers.py,digest_xcheck.py,peer_xcheck.py}` | `histor/histor/` |
| timer | `histor-peers.{service,timer}`, daily 12:00 UTC | `histor/deploy/` |
| output | `/var/lib/histor-datasets/peers/<slug>/<date>/`, `latest`, `peers/index.json`; link `xcheck-crawlcheck → peers/crawlcheck` | |

Two containers per run, from the service's image: "digest" peers (CrawlCheck) on the host network with no
database; "field-diff" peers (ScraperWatch) on `histor_default` with the database settings copied from the service and
the data volume read-only, as the export does. `peer_xcheck.py` in the image equals the repository's before the text
change (sha256 `a35cc4d4…`); the mounted copy differs only in its docstring and the report's first line.

## Steps

1. 20:03 UTC: list, runner and timer installed; CrawlCheck results moved from `/datasets/xcheck-crawlcheck/` to
   `/datasets/peers/crawlcheck/` (old path now a link); the one-peer timer and `/opt/histor-xcheck` retired to
   `/root/peers-20261107/retired/`.
2. 20:28 UTC: ScraperWatch moved from the weekly export to the list (method `field-diff`, its settings from the
   former `PEER` constant into its entry, `days: 1`); `/usr/local/sbin/histor-export-dataset` no longer runs it
   (`--peers` only says where it went; `--due` still answers). First daily run: their log of 2026-11-06, 44 records,
   36 the same change in HISTOR; HISTOR changes on 104 endpoint-days of their panel, 41 in their log, the other 63
   classified in the README.
3. 20:34 UTC: corrected `peer_xcheck.py` mounted; ScraperWatch rerun for the day so its README says it runs daily.

Index after step 3: crawlcheck 2026-11-07 (list 30 agree; feed 18 agree, 2 `histor_no_digest`), scraperwatch
2026-11-07.

## Backups and rollback

`/root/peers-20261107/step2-backup/` holds the export script, runner, list and `peers.py` as they were before
step 2; `/root/peers-20261107/retired/` the one-peer timer of step 1.

```bash
ssh admin-vps 'cp -a /root/peers-20261107/step2-backup/histor-export-dataset /usr/local/sbin/histor-export-dataset && cp -a /root/peers-20261107/step2-backup/peers.json /etc/histor/peers.json && cp -a /root/peers-20261107/step2-backup/histor-peers /usr/local/sbin/histor-peers && cp -a /root/peers-20261107/step2-backup/peers.py /usr/local/lib/histor-peers/peers.py && rm -f /usr/local/lib/histor-peers/peer_xcheck.py'
```

That returns ScraperWatch to the weekly export and the list to CrawlCheck only. To drop the list entirely:
`systemctl disable --now histor-peers.timer`, and the old timer's files are in `retired/`.
