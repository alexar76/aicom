# HISTOR: new outside addresses no longer list a field of an object — live 2026-11-22

Owner, 2026-11-22: «почини детектор адресов в HISTOR», «полностью закрываем проблему, выкатываем исправление».

**What was wrong.** `newAddresses` in a change record listed any dotted word. In the last 2,000 changes of that day
94 records listed an "address" and 36 of them named none: `versions.kitversion`, `asm.part`, `data.company`.

**The fix.** aicom `30a9b8abf` (rules, vendored IANA list `histor/tlds.txt`, tests) and `35a1b63cf` (the recount reads
only records that list an address). The rules are in the comment block above `_bare_host` in `histor/histor/diffing.py`.

**Measured before the rollout.** `corpus-253-servers.json`: the current tools of 253 servers (15,963 tools) read by the
old and the new detector — 6,164 addresses before, 3,414 after; the names dropped and kept are listed in the file.

## Production

| | |
|---|---|
| Image | `histor-histor:addresses-20261122` = `sha256:c44951f59d00dd8d0a13d2d5d12093a945526d0e70a193b1e49c51d2a1959f90` |
| Built from | `histor-histor:warden-0.37.1-prod` = `sha256:cf11d410…` (production since 15:06Z) plus `histor/diffing.py`, `histor/tlds.txt`, `histor/recount_addresses.py` of `30a9b8abf`; sha256 of each file equal on the host and in git. WARDEN inside is byte-identical (`package.json` `47b06fda…`) |
| Switch | `switch.sh` (sha256 `7a22eb07…`), unit `histor-addresses-switch`: started 18:07:58Z with no open crawl, healthy 18:08:35Z, five routes 200, detector check inside the container, `SWITCH-OK` 18:09:04Z (`switch.log`) |
| MOMUS | `skopos-warden-quality rebind sha256:c44951f5…` on admin-vps, 18:09:24Z; the package's `check-quality-gate.mjs` passes for build `1672b95c…` |
| Rollback | HISTOR host `/root/histor-addresses-20261122/switch.sh rollback`, then admin-vps `skopos-warden-quality rebind sha256:cf11d410c06ee1ef073f2d0afc1485f9d399e8f012faee4cfc40a8833c46ee63` |

## Stored records

`python -m histor.recount_addresses apply` in a one-off container of the production image, beside the live one
(`recount.sh`; the module file of `35a1b63cf` mounted over the image's first version), 18:35:23Z–19:45:02Z:
178,010 change records, 12,228 listing an address, **8,885 rewritten, 8,025 of them to an empty list**
(`recount-result.txt`). The values replaced are kept on the host in
`/root/histor-addresses-20261122/backup/replaced.jsonl` (id, old list, old total). HISTOR stayed healthy throughout.
Nothing signed changed: the list is in the change summary, not in a label, the log or a security event.

After it, the last 2,000 changes (02:54–19:50Z) have 58 records with an address, where the same day's window had 94.

## Left as it is

- A host in a newer word-like zone or under a field-word country code, written without a scheme (`bsky.social`,
  `alexjung.at`), is no longer listed. Written with `https://` it is.
- One field name under a plain country code still passes (`data.sa`).
- The production image carries the first version of `recount_addresses.py`; main has the faster one. The next HISTOR
  image must be built from `histor-histor:addresses-20261122`, or it puts the old detector back.
- Not released to PyPI: `aimarket-histor` is 0.10.0 there.
