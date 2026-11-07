# Cross-check with CrawlCheck: daily run on admin-vps; CrawlCheck as a witness

> **Retired 2026-11-07 ~20:05 UTC.** This one-peer timer was replaced by the configurable peer list: `/etc/histor/peers.json`
> (`histor/deploy/peers.json`), `histor/peers.py`, `/usr/local/sbin/histor-peers` (`histor/deploy/peers_check.sh`) and
> `histor-peers.timer`, daily 12:00 UTC. Results moved from `/datasets/xcheck-crawlcheck/` to `/datasets/peers/crawlcheck/`
> (the old path is now a link to it); `/datasets/peers/index.json` lists every observer. The old units and
> `/opt/histor-xcheck` are kept in `/root/peers-20261107/retired/` on admin-vps; the 19:39 run of 2026-11-07 in
> `/root/peers-20261107/xcheck-crawlcheck-2026-11-07-1939.bak`. The file below is the record of the first install.

Emmanuel Orta (CrawlCheck, contact@crawlcheck.io) proposed on 2026-11-07 a regular comparison of tool-set digests,
each side publishing the disagreements, and later co-signing HISTOR's checkpoints. Owner: «делай все». The method is
described for readers in `histor/docs/cross-check.md` (and `.ru`, `.es`, `.fr`, `.zh`).

## Running since 2026-11-07 ~19:00 UTC

| What | Where |
|---|---|
| script | `/opt/histor-xcheck/xcheck_digests.py` = `histor/scripts/xcheck_digests.py` (sha256 `70f20c2c0a772867…` at install) |
| wrapper | `/opt/histor-xcheck/run.sh` = `run.sh` here (sha256 `5f9ddec46d851570…`) |
| units | `/etc/systemd/system/histor-xcheck-crawlcheck.{service,timer}` = the files here; timer daily 12:00 UTC, `Persistent=true` |
| output | `/var/lib/histor-datasets/xcheck-crawlcheck/<date>/` and `latest`, served as https://histor.modelmarket.dev/datasets/xcheck-crawlcheck/ |

**2026-11-07 ~19:39 UTC update.** His shared list is live and wired in
(`Environment=THEIRS_LIST_URL=https://crawlcheck.io/data/xcheck/histor/latest.jsonl`; edition 2026-11-07 sha256
`9271b8ac…`, byte-identical to the list he mailed); the script gained the `theirs_no_digest` verdict (digest null plus
`outcome`) and is installed as sha256 `b6f433cdbbc4a40f…`. Today's folder was rerun: list 30 `agree`; feed 14 `agree`,
1 `histor_no_digest`, 0 `disagree`. The first run's folder is kept in `/root/xcheck-2026-11-07-first-run.bak`.

Source 1, always: CrawlCheck's public change feed, `https://crawlcheck.io/api/v1/mcp/changes?limit=500`. It returns
the newest 500 events (on 2026-11-07, from 2026-11-05 00:49 to 2026-11-07 18:51 UTC) and ignores `before`,
`offset` and `since`, so the run is daily, not weekly. Source 2, when CrawlCheck publishes its shared list at a
stable URL: set `Environment=THEIRS_LIST_URL=<url>` in the service, `systemctl daemon-reload`; the next run adds
`list.input.json` and `list.report.*`.

First run, 2026-11-07 18:59 UTC: 8 events with the RFC 8785 digest; 7 `agree`, 1 `histor_no_digest`
(com.reelquoteai/survey-tool: HISTOR had not read it within 24 hours), 0 `disagree`. Python on the host is 3.12;
the script needs 3.11 or later (it uses `datetime.UTC`).

Check: `systemctl list-timers histor-xcheck-crawlcheck.timer`; `journalctl -u histor-xcheck-crawlcheck --since -1d`;
the day's folder under `/datasets/xcheck-crawlcheck/`. A run that finds disagreements still succeeds (exit 1 of the
script is a result); a failed download or HISTOR request fails the unit, and nothing is published for that day.

Remove: `systemctl disable --now histor-xcheck-crawlcheck.timer`, delete the two units, `systemctl daemon-reload`,
delete `/opt/histor-xcheck`. Published days stay unless removed from `/var/lib/histor-datasets/xcheck-crawlcheck/`.

## By hand

```bash
histor/.venv/bin/python histor/scripts/xcheck_digests.py their-list.json --out round1.json --md round1.md
```

Exit 0 means no disagreement. A `disagree` row needs both sides' tool lists for that time: HISTOR's is at
`/api/v1/toolsets/<digest>` for the digest it had.

## CrawlCheck as a witness: added 2026-11-07 19:39 UTC

Entry `crawlcheck.io/witness`, vkey `crawlcheck.io/witness+f6b056e2+BCYE6WcaJVekqxEETT9IF/pKvxP7yZM6dLW65YDWpQpE`,
url `https://crawlcheck.io/witness`. Before adding: key id recomputed (`f6b056e2`), type 0x04, and his cosignature on
our checkpoint 1760605 (served at his monitoring URL) verified together with our log signature. Backup:
`/etc/histor/witnesses.json.bak-20261107-crawlcheck`. First push, run by hand at 19:39:48: "stored 4 cosignature
line(s) at size 1761346"; his cosignature on the published checkpoint verifies. Rollback: restore the backup.

How it was done (kept for the next witness):

HISTOR pushes each new checkpoint to the witnesses in `/etc/histor/witnesses.json` on admin-vps every 10 minutes
(`histor-witness-push.timer`, c2sp.org/tlog-witness; the push POSTs `<url>/add-checkpoint`) and stores the
cosignature lines it gets back. Add one entry in the same shape as the three there:

```json
{
  "name": "<his witness name>",
  "operator": "CrawlCheck (VSNARY)",
  "vkey": "<name>+<8 hex>+<base64>",
  "url": "<submission prefix>",
  "source": "Emmanuel Orta, mail of <date>"
}
```

Before adding: the vkey's name equals `name`, its key is a cosignature/v1 key (type 0x04), and his witness has our log
configured (origin `histor.modelmarket.dev/log`, vkey
`histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU`). Back up the file, add the
entry, then watch the next push: `journalctl -u histor-witness-push --since -15min` should say "stored 4 cosignature
line(s)". A witness that does not know our log answers 404 and is skipped, as witness.gdbsecurity.com was on
2026-11-04. Rollback: restore the backup.
