# Glama build — admin form

Listing: [glama.ai/mcp/servers/alexar76/aimarket-hub](https://glama.ai/mcp/servers/alexar76/aimarket-hub)

Admin: […/admin/dockerfile](https://glama.ai/mcp/servers/alexar76/aimarket-hub/admin/dockerfile)

Glama generates the image from this form. It does not build [`Dockerfile.standalone`](../Dockerfile.standalone). That file is the satellite image: `python:3.12-slim` (Debian Bookworm) and `python -m aimarket_hub serve --init`. CI and the published image use Python 3.12. The only Node pin in this repo is the studio build stage, `node:20-alpine`, which the Glama image does not compile.

The form only offers `debian:bookworm-slim` and `debian:trixie-slim`.

| Field | Value |
| --- | --- |
| Base image | `debian:bookworm-slim` |
| Node.js version | `20` |
| Python version | `3.12` |
| Build steps | `["uv sync --frozen --no-dev --extra escrow --extra pqc"]` |
| CMD arguments | `[".venv/bin/python", "-m", "aimarket_hub", "mcp", "--init"]` |
| Environment variables | `{"type":"object","properties":{},"required":[]}` |
| Pinned commit SHA | empty |

Leave every key empty. The hub creates its own dev signing key on `--init`. Production settings are not part of this form.

The `mcp --init` command runs the local hub's existing MCP gateway over stdin/stdout.
It opens no HTTP listener. Search, invoke, payment checks and account reads use the same
local handlers as HTTP. Diagnostics go to stderr; stdout contains only MCP JSON-RPC.
An optional `AIMARKET_MCP_API_KEY` environment variable supplies a buyer API key; never
put it in CMD arguments. Ordinary `serve --init` remains the HTTP deployment command.

For a local smoke check, run `.venv/bin/python -m aimarket_hub mcp --init` from the repo
and send newline-delimited `initialize`, `notifications/initialized`, `tools/list` and
`tools/call` messages. EOF closes the session. `AIMARKET_AUTO_CRAWL=0` disables background
federation crawling for offline checks; otherwise the normal hub crawl settings apply.

After uploading the source, sync the Glama repository and replace the saved CMD with
the value above before clicking Build: an existing saved `serve` command does not
become `mcp` merely because the source changed.
