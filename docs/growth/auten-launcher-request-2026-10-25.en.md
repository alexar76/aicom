Thanks — I’ve recovered HISTOR’s stored sandbox tool list for `@autenai/mcp`: one `install_auten` tool. The pinned launcher selected for a new comparison is `@autenai/mcp@0.1.5`. I’ve also prepared and tested a [capture helper with instructions](https://github.com/alexar76/warden/blob/main/examples/launcher-evidence/README.md). It saves the full tool list, initialize metadata, exact command, runtime information and verified hashes without calling tools, creating pins or uploading anything.

For a concrete launcher comparison, could you share two captures from the differing environments, ideally with the same pinned launcher version? Please include the runner release/build and OS for each, whether the runner is absent or present, and whether the command uses the npm launcher or direct `auten mcp-bridge`.

The useful files are `tools.json`, `initialize.json`, `capture.json` and `SHA256SUMS`. Please review them before sharing; no keys, environment values, complete client configs or personal SSE URLs are needed. A declaration file alone contains digest/count/conditions, so it cannot replace these snapshots.

I can then compare the actual names, descriptions and schemas, and check the declaration separately as publisher-provided information. Our synthetic tests won’t be presented as a second real Auten environment.
