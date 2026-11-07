# HISTOR tool-set digest = CrawlCheck jcs_v1.tools_sha256 (2026-11-07)

Context: Emmanuel Orta (CrawlCheck) pointed OWASP/secure-agent-playbook#33 at his MCP lockfile spec,
https://crawlcheck.io/spec/mcp-lockfile (spec text sha256 `3cac4a345a85a5e0…`, the version its change log lists for
2026-11-07). Its `jcs_v1` contract digest is described like HISTOR's MTL/1 tool-set digest (`histor/docs/labels.md`):

| | HISTOR MTL/1 tool-set digest | CrawlCheck `jcs_v1.tools_sha256` |
|---|---|---|
| members | `name`, `description` (`""` if absent), `inputSchema` (`{}` if absent), `outputSchema` only when an object | the same |
| order | by name, UTF-16 code units | the same (equal names by canonical UTF-8 bytes) |
| bytes | RFC 8785 | RFC 8785 |
| digest | SHA-256, SRI | SHA-256, SRI |
| not digestible | a tool with no name (`MTL-SUBJ-001`), a number with no double (`MTL-NUM-001`) | the same two, `null` with a reason |

Annotations, `title` and `icons` are outside both. CrawlCheck digests them as `extras_sha256` (RFC 8785 over
`{title, annotations, icons}`). HISTOR keeps every other member, `_meta` included, under its own extras digest, which
is not RFC 8785 (prices in `_meta` are often fractions). Those two do not match and are not meant to.

## Result

`xcheck.py` (output in `results.txt`), all equal:

- both CrawlCheck vectors (empty list; `read_file` with a title and an annotation) give CrawlCheck's digests in
  `histor.subject.tool_set_digest`;
- six tool sets HISTOR recorded (3 to 28 tools; one with fractional numbers in its schemas; all with non-ASCII
  text), fetched by digest from `https://histor.modelmarket.dev/api/v1/toolsets/<sri>` and posted to CrawlCheck's
  `POST /api/v1/mcp/lock {tools}`: CrawlCheck's `jcs_v1.tools_sha256` equals HISTOR's recorded digest for each.

`POST {tools}` hashes the list it is given; CrawlCheck contacted none of the six servers. Not compared: their
change feed, whose last 100 events on 2026-11-07 carried no `tools_jcs_sha256_after` yet.
