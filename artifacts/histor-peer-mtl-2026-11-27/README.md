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

## The four persistent disagreements traced, 08:50–09:05Z (another session; reads from the Mac, not the HISTOR host)

Folder `era-reads/`. Method: read his public source (58dc54f); read each server once per protocol era with our own
identity (`read_eras.py`: `server/discover` + `tools/list` in 2026-07-28, then `initialize` asking 2025-11-25,
2025-06-18, 2025-03-26, 2024-11-05; read-only; raw lists in `reads-2026-11-27/`); run his own `JCSToolsDigest`
(`pkg/canon`, copied unchanged) over our lists (`mtlrun/`, the two copied files are not kept here).

His digest code over our lists gives HISTOR's digest for all four servers: the rule is implemented the same on both
sides. Each disagreement has its own cause:

| server | cause | proof |
|---|---|---|
| com.stackerscan/stackerscan | the list depends on the protocol revision; he reads after `initialize`, HISTOR in 2026-07-28 | our 2026-07-28 read = HISTOR's digest, each of our four handshake reads = his digest; one member differs: `get_price_history.outputSchema` is the schema itself in 2026-07-28 and `{type: object, properties: {result: <it>}, required: [result]}` to a handshake client |
| io.github.phreakocious/ebcdic | one tool is named differently for each reader (`ebcdic_ref_<10 hex>`, "exists to measure which directories republish this tool list") | HISTOR holds `ebcdic_ref_3c5d0f47ef`, the Mac was given `ebcdic_ref_929b481f22`; a third digest |
| io.github.rajeswaran140/crowvault | ten of the 379 tools are named `server_health`; his `toolsOf` (cmd/mcpobs/classify.go) gathers tools into a map by name, so one survives | the 369 others + only the `server_health` that starts "Check security MCP server health" = his digest exactly |
| io.github.adriancasas/geo360-concierge | he was sent six tools, we are sent seven | our seven without `1hlabs_shadow_solana_b2b_checkout` = his digest exactly; why the server leaves it out for him is not visible from here |

Consequence on our side, checked live: `POST /api/v1/check` with stackerscan's endpoint and the handshake-era digest
answers `different` ("differs from every set HISTOR has observed"), with the 2026-07-28 digest `same`. A handshake
client (WARDEN `scan --histor` among them) is told a server changed when it is only being read in another revision.
The answer carries no protocol version.

A second mechanism met in the sample below (io.github.ValmoDev/joomil): `$schema` in every input and output schema
is `https://json-schema.org/draft/2020-12/schema` in 2026-07-28 and `http://json-schema.org/draft-07/schema#` after
`initialize` (and `execution.taskSupport` is present only after `initialize`, outside the contract).

Sample to size it: `era_sample.py` reads 300 servers whose last HISTOR read was on 2026-07-28 (one per registrable
domain, seed 20261127, from the 26 Nov export) once in each era; rows in `era-sample-2026-11-27.jsonl`, counts with
`summarize_sample.py`.

### Sample result, reads 08:55:42–09:29:02Z

300 servers on 300 registrable domains. 277 gave a digest in both eras; 273 the same one, **4 a different one (1.4 %)**.
Of the other 23: 4 answer 2026-07-28 and refuse or fail the handshake (HTTP 400 twice, one with `-32020`; 401; a
`tools/list` error), 2 answered only the handshake today, 17 answered neither (503, 500, 530, 404, 410, 403, 308, DNS).
The handshake was answered as 2025-06-18 by 268, 2025-11-25 by 5, 2025-03-26 by 1, and as 2026-07-28 by 3.

The four, each re-read with raw lists saved (`reads-2026-11-27/`):

| server | what a handshake client gets instead |
|---|---|
| io.github.birdwell/runescape-wiki-mcp | `get_ge_info.outputSchema` wrapped as `{type: object, properties: {result: <schema with anyOf at the root>}, required: [result]}`: the stackerscan case |
| io.github.ValmoDev/joomil | `$schema` draft-07 in place of 2020-12 in all five tools' input and output schemas |
| com.producthunt/mcp | 32 tools in place of 30: `get_launch_preview_view` and `open_launch_editor` are listed only after `initialize` |
| au.com.ftcapital/ftus-mcp | no tools: `initialize` is answered with `protocolVersion: 2026-07-28` whatever was asked, and `tools/list` in that session returns an empty list (nine tools in 2026-07-28) |

One sample, one day, one reader from one address; a server that differs per reader rather than per revision would
look the same here. 4 of 277 gives a 95 % interval of about 0.6–3.7 % (Wilson).

Reply draft: PromoMaterials/outreach/standard-track-2026-11-27/histor13-yassinht-reply-2.md (colleague §181).
