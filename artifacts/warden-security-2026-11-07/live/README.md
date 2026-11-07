# Live MCP interoperability — remote gVisor only

Candidate: `@aimarket/warden` source `0.23.1-dev.20261107.1`, ruleset 19.
Both Attested and Blip completed **8/8 SDK sessions**, with **4/4 direct/wrapped
tool-list digest pairs equal**. These are actual package processes, separate
from the archived-definition comparison.

| Implementation | Package version | Advertised tools per mode |
|---|---|---:|
| WARDEN | local source `0.23.1-dev.20261107.1` | 9 |
| Filesystem | `@modelcontextprotocol/server-filesystem@2.2.0` | 16 |
| Memory | `@modelcontextprotocol/server-memory@2.1.0` | 9 |
| Sequential Thinking | `@modelcontextprotocol/server-sequential-thinking@2.1.1` | 1 |

Client: official Node MCP SDK `1.32.1`. Each implementation ran directly and
through WARDEN. Checks covered nonempty discovery, one successful synthetic
tool call, refusal of an unknown tool, and a subsequent successful ping.
The synthetic data was an isolated UTF-8 text file, empty memory graph, toy
reasoning step or JSON canonicalization input. No user files or production
credentials were mounted. Package-lock hashes accompany each result.

Both hosts also completed **3/3 public HTTP discovery targets**, without errors:
DeepWiki (3 tools), Microsoft Learn (3), Cloudflare Docs (2). All three toolsets
were allowed. This phase used `initialize` and `tools/list` only, with the
client's public-address restriction; it invoked no remote advertised tool.
Discovery is not a dependency audit or a model attack-success experiment.

`attested/` and `blip/` contain copied remote result JSON, actual Docker
HostConfig and exit status. Stdio checks used `runsc`, network none, read-only
root and sources, UID 1000, dropped capabilities, no-new-privileges,
0.5 CPU/512 MiB and a separate writable result directory. HTTP checks used
the same restrictions with 256 MiB and bridge networking for the public
endpoints. Containers were removed after recording results.

Execution and original evidence paths on each host:
`/opt/warden-tests/20261107-live-interop/results/<site>/{sdk19,http19}/`.
The files in this directory are copies of remote evidence. No local package,
build, test, MCP server or benchmark was run to produce them.
