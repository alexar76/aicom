# mcp-tool-set-digest#1: the four uncovered cases through our three references — 2026-11-22

bcrypto0 opened alexar76/mcp-tool-set-digest#1 (19 Nov, independent Node reader) with four inputs no vector covers;
on 22 Nov Emmanuel Orta posted CrawlCheck's answers to them and a depth rule (comment 7084776059): a reader MUST accept
512 levels counting the tools array as 1 and a tool as 2, past that `TSD-DEPTH` for the side where the deep value sits,
no crash; edges 509/510 arrays under `inputSchema.x`, 510/511 on the extras side, 100,000 → `TSD-DEPTH`.

`run.sh <aicom> <workdir>` writes the inputs and runs the Python, JavaScript and Go references of this monorepo
(`mcp-tool-set-digest/implementations/`, main of 2026-11-22; Python 3.9.6, Node from the Mac, Go 1.2x). Output:
`results-2026-11-22.txt`.

| Case | Python | JavaScript | Go |
|---|---|---|---|
| depth, contract side (509, 510, 2,000, 100,000 arrays under `inputSchema.x`) | `RecursionError` from about 330 levels (uncaught) | digest at every depth up to 2,000; `RangeError` (uncaught) at 100,000 | digest at 509; from 510 `TSD-JSON` for the whole input ("nested too deep") |
| depth, extras side (510, 511, 100,000) | `RecursionError` | digests at 510 and 511; `RangeError` at 100,000 | digests at 510; from 511 `TSD-JSON` for the whole input |
| `{"tools": …}` wrapper, 509 arrays | `RecursionError` | digest | `TSD-JSON`: the wrapper moves Go's edge by one level |
| `"description": 1e400` | contract `sha256-88Wu…X2U=` (= the tool with no description), no extras, no `TSD-NUMBER` | same | same |
| `1e400` in an extra | contract digest kept, extras `TSD-NUMBER` | same | same |
| repeated `description` ("a" then "b") | = the tool with `"b"` | same | same |
| `tools` twice ("a" then "b") | = the list `[b]` (last wins) | same | same |
| `tools` next to `result` | = the top-level list `[a]`; `result` ignored | same | same |

Reading: Go's bound (512, top-level value counted as 0, the innermost value counted) gives exactly CrawlCheck's edges for
a bare array, but kills both digests and shifts with each wrapper. Python and JavaScript have no bound and crash; this is
the defect CrawlCheck found and fixed in its own readers. Section 6 says a 1e400 "in a contract member" leaves no digest,
while sections 4 and 8.1 read a non-string `description` as absent: our three references, CrawlCheck and bcrypto0's
reader all follow 4/8.1, so section 6 needs the fix, not the readers.

Reply draft for the owner: `PromoMaterials/outreach/tsd-issue1-crawlcheck-2026-11-22.md`.

## Fixed the same day

The three references now follow CrawlCheck's rule, written into SPEC.md (editors' draft 2026-11-22, section 12 and
`TSD-DEPTH` in section 10): levels counted from the tools array whatever wraps it, every level up to 512 accepted,
`TSD-DEPTH` for the digest that would cover a deeper array or object, no crash. Each reader replaces an array or object
deeper than 514 levels of the whole text by an empty one before building values (nothing that deep can reach a digest,
and the replacement keeps its kind and level); Python writes canonical text with an explicit stack. Edges in
`mcp-tool-set-digest/scripts/check_depth.py` (12 cases, all three readers give the same answer), run by `check.sh`; the
73 vectors, the HISTOR and the WARDEN cross-checks still pass.

Not covered by that fix, found while checking: WARDEN's own digests refuse anything nested deeper than 64 levels
(`warden/src/jcs.ts` `MAX_DEPTH = 64`, the AWR canonicalisation bound) and report the extras case as `TSD-TEXT`; HISTOR's
contract digest raises `RecursionError` at 2,000 levels and its JSON parse at 100,000.
