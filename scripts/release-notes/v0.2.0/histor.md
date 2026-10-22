# HISTOR 0.2.0 — the log as open data

HISTOR reads the tool list of every remote MCP server in the official registry, and of npm and PyPI MCP packages run in a sandbox, once a day. It pins the exact definitions by digest and writes a signed label to a public Merkle log (RFC 9162) when a tool set first appears, stays the same or changes.

## New: monthly snapshots

[histor.modelmarket.dev/datasets/](https://histor.modelmarket.dev/datasets/), CC BY 4.0 for the compilation:

| File | What |
| --- | --- |
| `servers.jsonl.gz` | every listed server (about 82,000 name and endpoint pairs, remote and packages) with status, tool count and match counts |
| `toolsets.jsonl.gz` | every tool set a server showed, and every one a change replaced, exactly as served |
| `changes.jsonl.gz` | every recorded change: tools added, removed and modified, with the signed label |
| `scans.jsonl.gz` | WARDEN pattern matches per tool set, plus the rules in `pattern-set.json` |
| `classifications.jsonl.gz` | the advisory LLM reading (never in the signed log) |
| `manifest.json` | counts and SHA-256 of every file, signed by the log's key, with the tree head the snapshot was taken under |

Also on [Hugging Face](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions) and archived on Zenodo: cite [doi:10.5281/zenodo.23512759](https://doi.org/10.5281/zenodo.23512759).

Each snapshot has a README (the dataset card) with the fields and how to load them in pandas or DuckDB. `histor export-dataset DIR` writes one from your own instance.

## Also since the log went live (2026-09-23)

- npm and PyPI MCP packages observed in a gVisor sandbox: decoy secrets, no internet, every network attempt recorded.
- Publisher-declared tool sets: a server can name, in its registry entry, the sets it lists where the sandbox cannot see them.
- What a tool list costs: across 18,204 packages the median list is about 1,300 tokens and the 90th percentile about 8,000 ([docs/tool-list-cost.md](https://github.com/alexar76/histor/blob/main/docs/tool-list-cost.md)).
- A second Merkle log for anchors of signed work receipts.

Check one server without installing anything: [modelmarket.dev/tools/histor-check](https://modelmarket.dev/tools/histor-check?utm_source=github&utm_medium=release&utm_campaign=histor-0.2.0)
