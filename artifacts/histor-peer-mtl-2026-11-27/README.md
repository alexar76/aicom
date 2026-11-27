# MCP Transparency Log on HISTOR's observer list, in bounded daily parts — 2026-11-27

**Why.** yassinht (Surfacelog) on alexar76/histor#13, 2026-11-26 20:59Z: happy to be listed as "MCP Transparency
Log"; list https://yassinht.github.io/mcp-transparency-log/data/peers/tool-digests-latest.jsonl (rewritten after the
nightly census, ~04:00 UTC), index.json, dated.json. Owner: «Да, делай». The peer entry had been in main since
a7ce22bba (2026-11-21) but never on the HISTOR host.

## First attempt, stopped (all times server UTC)

- 04:36:11Z installed main's peers.json as /etc/histor/peers.json and ran `histor-peers --peer mcp-transparency-log`.
- The digest method makes one `GET /api/v1/servers/<id>` per row: fine for CrawlCheck's change feed (at most 500 rows),
  not for his census of the whole registry (51,525 rows on 2026-11-26): hours of sequential API calls on a host already
  at load ~6.
- 04:48:17Z stopped the run (`docker stop histor-peers-digest-2026-11-27`) and restored the old list
  (/root/peers-mtl-20261127/peers.json.pre-20261127T043610Z). Nothing published; staging empty. The front page and the
  peer index answered in 0.1 s throughout (only /api/v1/stats is slow, 8–10 s, as it is anyway).
- Mistake on the way: `pkill -f "<the script's command line>"` over ssh killed the remote shell running it (its own
  command line contained the pattern), so the first stop did nothing; the container was then stopped by name.

## Change (main e057d7618)

`max_rows` in a digest peer's entry: a source with more rows is split into `ceil(1.1 × rows / max_rows)` parts by the
first 8 bytes of `sha256(name + "\n" + endpoint)` mod parts, and each day compares the part numbered by the day's
ordinal mod parts. Every row comes round once in `parts` days; the report's `sample` gives the rule, the part and the
rows in the source. deploy/peers.json: 1,000 for mcp-transparency-log (57 parts of 841–971 rows for his 2026-11-26 file,
no part cut over 60 simulated days). Docs in 5 languages, READMEs name the third observer. HISTOR suite 1721 passed.

Timed before deploying (throw-away container with the new modules mounted, nothing published), 04:57:58–05:12:01Z:
1,000 rows of his 2026-11-27 file (52,326 rows; that run still used ceil(rows / max_rows), 53 parts, a cut part),
843 s; 509 agree, 0 nearby, 10 disagree, 74 histor_no_digest, 3 not_listed, 404 theirs_no_digest. HISTOR's own API
answered 0.2–0.9 s per timeline meanwhile; front page 0.1 s.

## Deploy, 05:14:21Z (HISTOR app not restarted)

The peer check runs in throw-away containers from the image tagged `histor-histor`; the HISTOR app container holds its
image by ID. So:

- `histor-histor:peers-sample-20261127` = FROM the running image (`sha256:feabed44…`, also tagged
  `histor-histor:pre-peers-sample-20261127`) + main's peers.py and digest_xcheck.py; `histor-histor` now points to it
  (`sha256:745fac7b…`). The app keeps running `feabed44`.
- /opt/histor/histor/{peers.py,digest_xcheck.py} (the build source of the next HISTOR image) updated to main.
- /etc/histor/peers.json = main's (three peers; mcp-transparency-log max_rows 1000).
- Backups: /root/peers-sample-20261127/backup/ (the three replaced files).

Rollback: `docker tag histor-histor:pre-peers-sample-20261127 histor-histor` and copy the three files back from
/root/peers-sample-20261127/backup/ (peers.json to /etc/histor/, the two .py to /opt/histor/histor/).

## First published comparison, 05:14:35–05:28:49Z (854 s)

`histor-peers --peer mcp-transparency-log` → https://histor.modelmarket.dev/datasets/peers/mcp-transparency-log/2026-11-27/
His 2026-11-27 file (run 2026-11-27T030808Z, 52,326 rows, sha256 `a406c4f9db213db8…`, equal to the `sha256` his
index.json now carries), part 42 of 58, 933 rows: 498 agree, 0 agree_nearby, 7 disagree, 64 histor_no_digest,
6 not_listed, 358 theirs_no_digest, 0 bad_row. The public index lists all three observers. In several of the 7
disagreements HISTOR's current digest period began days before his read (16, 22, 25 Nov).

## The seven disagreements, examined 05:46Z

Fresh `tools/list` reads with HISTOR's own reader (`McpReader`, `tool_set_digest`) in a throw-away container on the
HISTOR host (folder removed afterwards):

- Timing, 3: co.golfdata/golfdata, io.github.akihidem/kuchiyose, ru.paydadosh/dictionary changed after HISTOR's last
  read and before his; the fresh read gives HISTOR his digest; kuchiyose HISTOR had already re-read at 05:30:49Z (after
  the 05:28Z comparison). The 12:00 run compares the same part again and should count them nearby.
- Persistent, 4: com.stackerscan/stackerscan, io.github.adriancasas/geo360-concierge, io.github.phreakocious/ebcdic,
  io.github.rajeswaran140/crowvault: HISTOR's reads before and after his and the fresh one all give HISTOR's digest.
  Variants tried on our reads (no outputSchema; +title; +annotations; code-point order; listed order): none gives his.
  One page each; protocol versions 2026-07-28 (stackerscan, ebcdic), 2025-06-18 (crowvault), 2024-11-05 (geo360).
  Asked him (reply draft) for his reader's tools/list of ebcdic (4 tools) and the protocolVersion his client sends.
His dated.json: 17, 18 and 26 Nov checked (sha256 + bytes match); 27 Nov not in it yet at 05:30Z.

The 12:00 UTC timer now runs all three (this one ~15 min more). My test folder /root/peers-sample-test removed;
/root/peers-mtl-20261127 and /root/peers-sample-20261127 (backups) kept.
