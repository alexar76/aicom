# heldfast on HISTOR's observer list: per-tool fingerprints, 1,000 servers a day — 2026-11-27

**Why.** modelcontextprotocol/registry#82, 2026-11-26:
- 16:51Z, we (alexar76) offered rufat325 a daily comparison of the remotes heldfast and HISTOR both read, with the
  counts published;
- 17:12Z, rufat325 answered «sure».

The answer had not reached our notes. The 27 November links sweep found it
(PromoMaterials/outreach/ecosystem-links-2026-11-27). Owner: «делай».

## What heldfast publishes

heldfast keeps no tool-set digest. It pins every tool on its own (docs/LOCK.md): SHA-256 of RFC 8785 over name,
title, description, input_schema, annotations, output_schema and icons. rufat325/heldfast-feed `state/` holds 61,366
files at 0b36265b (2026-11-27 09:19Z). 43,790 of them are hosted servers (`remote__<registry name>.json`):

```json
{"package": "remote/<name>", "url": "...", "published": "<time of the read that produced the list>",
 "version": "...", "tools": {"<tool>": "<fingerprint>"}, "attempted": {"at": "...", "why": "HTTP 401"}}
```

`attempted` is a later read that failed. A server never read has only `attempted` and `tools: {}`. An npm package's
file has `checked_at` instead of `published`.

HISTOR already computes heldfast's format, checked against heldfast's golden vectors on 2026-10-31
(`/api/v1/servers/<id>/fingerprints?format=heldfast`, histor/fingerprints.py). So the comparison is tool by tool, with
no conversion on either side.

## Change (HISTOR, main)

- `histor/fingerprint_xcheck.py` (new, standard library only):
  - lists the folder at the commit `main` names (3 GitHub API requests) and reads each chosen file from
    raw.githubusercontent.com at that commit;
  - compares the file with HISTOR's fingerprints (one request);
  - for a server whose fingerprints differ, reads the server record once more for its newest title/annotation change.
- Verdicts: agree, disagree, changed_after, read_after, histor_no_extras, histor_no_toolset, not_listed,
  theirs_no_tools, bad_row (histor/docs/cross-check.md).
- `histor/peers.py`: method `fingerprints` (`format`, `github` {repo, ref, folder, prefix}, `max_rows`). `daily_share`
  takes a key: here sha256(file name), with the same parts rule as the digest peers. The rule for digest rows is
  unchanged (test).
- `deploy/peers.json`: heldfast, `max_rows` 1000 (49 parts for 43,790 files).
- `deploy/peers_check.sh`: the `fingerprints` run gets its own container, with the digest run's isolation (host
  network for the loopback API, no database, no volume, 256 MB).
- Docs `cross-check*.md` (5 languages): observer row and method section. READMEs ×5 name heldfast.
- Tests: `tests/test_fingerprint_xcheck.py` (11) plus the shipped-config test.

## Trial before deploying (HISTOR host, throw-away container, nothing published), 14:21:58–14:24:07Z

200 files (part 78 of 241), 129 s:
- 97 agree, 0 disagree;
- 9 changed_after, 6 read_after;
- 3 histor_no_extras, 6 histor_no_toolset;
- 79 theirs_no_tools (HTTP 401 and similar).

The first trial read `checked_at` only and gave 200 bad_row. Hosted-server files say `published`; fixed before
deploying.

## Deploy, 14:26:32Z (HISTOR app not restarted)

`kit/deploy.sh`:
- `build`: `histor-histor:heldfast-peer-20261127` = FROM `histor-histor:pre-heldfast-peer-20261127`, which is the
  app's image `sha256:9414eb56…` (other-revision-20261127), plus main's `peers.py` and `fingerprint_xcheck.py`.
  Checked: the new image loads the new list (4 peers).
- `install`: in this order, because an image without the method rejects the new list:
  1. `histor-histor` tag → the new image `sha256:4dde0f5b…`;
  2. `/usr/local/sbin/histor-peers`;
  3. `/etc/histor/peers.json`;
  4. the build source `/opt/histor/histor/{peers.py,fingerprint_xcheck.py}` and
     `/opt/histor/deploy/{peers_check.sh,peers.json}`.
  Backups: `/root/peers-heldfast-20261127/backup/`.
- The app keeps running `9414eb56`.

Rollback: `bash /root/peers-heldfast-20261127/deploy.sh rollback` (tag and files back; fingerprint_xcheck.py removed
from the build source).

## First published comparison

`histor-peers --peer heldfast`, 14:26:34–14:39:30Z, published
https://histor.modelmarket.dev/datasets/peers/heldfast/2026-11-27/. The rerun 14:41:56–14:54:54Z replaced that day
with the same share and the same feed commit, adding HISTOR's status now to each differing row
(`histor_last_status`).

Source rufat325/heldfast-feed@0b36265b110e (2026-11-27T09:19:02Z), part 48 of 49, 897 files of 43,790. HISTOR's
loopback API took 0.1–0.2 s per server; the run took 13 minutes.

| verdict | servers | note |
|---|---|---|
| agree | 427 | 5,678 tools compared, all equal |
| disagree | 0 | |
| changed_after | 57 | HISTOR's tool set or titles/annotations newer than heldfast's `published` |
| read_after | 37 | HISTOR's status now: robots-disallowed 33, ok 2, too-large 1, http-500 1 |
| histor_no_extras | 8 | read before HISTOR kept titles and annotations |
| histor_no_toolset | 21 | |
| not_listed | 10 | |
| theirs_no_tools | 337 | heldfast's `attempted.why`: HTTP 401 262, no tools/list answer 23, HTTP 404 18, URLError 17, HTTP 502 4, HTTP 402 3 |

`read_after` and robots.txt: since 2026-11-02 HISTOR honours robots.txt (RFC 9309). A server whose robots.txt
disallows the MCP path for every agent is not read again, and its page says how to allow `histor`. heldfast still
reads those servers, so their file is newer than HISTOR's last read. 33 of the 37 are that. Not a disagreement and
not a bug; it is reported so the reason is visible.

Two `read_after` rows with status `ok` (for example ai.harny/context, HISTOR's last check 2026-11-11) are servers
HISTOR has not checked for weeks. Their schedule is a HISTOR question to look at separately.

The 12:00 UTC timer now runs four peers: digest (2), fingerprints (1), field-diff (1). The heldfast share adds
about 13 minutes.

Public: `/datasets/peers/heldfast/2026-11-27/` (report .md/.json, `state.input.jsonl`, SHA256SUMS), `latest/`, and
`/datasets/peers/index.json` listing four peers. All returned 200 from outside, checked from factory-vps.

My test folder `/root/peers-heldfast-test-20261127` was removed after the run. `/root/peers-heldfast-20261127` (kit,
backups, run2.log) is kept.
