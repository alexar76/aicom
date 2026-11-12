# Live MCP interoperability: frozen candidate .1

This phase used `@aimarket/warden` source `0.23.1-dev.20261107.1`, ruleset19,
and official Node MCP SDK1.32.1. It is separate from archived definition scans.
Each host completed8/8 direct/wrapped SDK sessions and4/4 equal tool-list
digest pairs, with one safe synthetic call, unknown-tool refusal and a later
successful ping in each session.

| Implementation | Version | Advertised tools per mode |
|---|---|---:|
| WARDEN | frozen source0.23.1-dev.20261107.1 |9|
| @modelcontextprotocol/server-filesystem |2.2.0|16|
| @modelcontextprotocol/server-memory |2.1.0|9|
| @modelcontextprotocol/server-sequential-thinking |2.1.1|1|

Both hosts also completed public HTTP discovery for DeepWiki, Microsoft Learn
and Cloudflare Docs (3/3/2 tools), with all three toolsets allowed. Only
`initialize` and `tools/list` ran; no remote advertised tools were called.

Execution used remote gVisor/runsc with read-only roots and sources,
unprivileged UID1000, dropped capabilities, no-new-privileges,0.5CPU and
dedicated result directories. Stdio sessions had network none/512MiB;
public HTTP discovery used bridge networking/256MiB and public-address
restrictions. Synthetic inputs contained no user files or credentials.

Full execution receipts and package-lock hashes are retained in the technical
evidence at `artifacts/warden-security-2026-11-07/live/` and on both remote
hosts under `/opt/warden-tests/20261107-live-interop/results/<site>/`.
This public summary does not redistribute those raw receipts. Discovery and
synthetic interoperability do not measure dependency safety or model attack
success. Frozen .2 compatibility is documented separately in this bundle.
