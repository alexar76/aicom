# HISTOR subregistry: checks of 2026-11-19

Code: `histor/histor/subregistry.py` (migration 026), guide `histor/docs/subregistry.md`. Not deployed: the routes are
off unless `HISTOR_SUBREGISTRY=1`, and production was not touched.

Run on a Mac against the official registry, evening of 2026-11-19 (the Mac's clock ran about an hour fast, so the
`at` in the sync record is not UTC to the minute).

| Check | Result |
|---|---|
| HISTOR test suite, SQLite (`pytest -m "not integration"`) | 1649 passed, 331 skipped (the Postgres halves: no `HISTOR_TEST_DATABASE_URL`), 0 failed; 16 of them new in `tests/test_subregistry.py` |
| Full sync from `registry.modelcontextprotocol.io` into an empty SQLite store | 678 pages, 67,768 latest entries read, 67,767 stored, 1 skipped; 4 min 22 s; store file 92 MB |
| First 300 latest entries, three pages of 100, ours against the official registry (`compare.py`) | 300 of 300: `server` object and the official `_meta` block equal, the three `nextCursor` values equal |
| `versions/latest`, the exact version, the plain-slash name and `versions` for 4 servers | all 200; equal to the official answer; CORS headers present |
| Unknown server | 404 `application/problem+json`, the official body plus `error` |
| `search=alexar76&version=latest` | 8 servers on both sides, same names |
| `OPTIONS /v0.1/servers` with an Origin | 204 |
| Latency on the local store | first page of 100: 7 ms; a page deep in the order: 44 ms; a search: 23 ms |

Validation against the registry's OpenAPI (`ServerList`, `ServerResponse`): single entries pass. The list pages report
`server.repository` without `url` and `source` on a few entries (an empty `repository: {}`); those entries are the
official registry's own data, served unchanged, and the official answer has the same members.

Not checked: Postgres (the migration and the SQL are written for both engines and the test file runs on both, but
only the SQLite half ran here); a real host application (VS Code, Copilot) reading the address; the routes behind
production nginx; the `_meta` observation block on live data (the local store had no crawl; it is covered by a test
with a crawled fixture).
