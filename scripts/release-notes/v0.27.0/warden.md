# WARDEN 0.27.0 — MCP interceptor, tool-set digests, ruleset 20

```bash
npx -y @aimarket/warden@0.27.0 scan
```

0.26.1 was cut from a tree without the interceptor and the tool-set digests, so this release puts them on npm for the first time. The full list is in the [CHANGELOG](https://github.com/alexar76/warden/blob/v0.27.0/CHANGELOG.md).

- **Ruleset 20: "mnemonic" as an EVM opcode name** ([#14](https://github.com/alexar76/warden/issues/14), reported with a ready regression set).
  - `TOOL_DEF_SECRET_REQUEST` no longer blocks an opcode lookup that returns "hex, mnemonic and description". In EVM, the mnemonic is the name of an instruction, such as `PUSH1`.
  - A bare "mnemonic" is cleared only when its clause names opcodes, bytecode, a disassembler or the EVM, and nothing in the clause asks for the secret: no "your mnemonic", no wallet words, and no request whose object is the mnemonic.
  - A request verb aimed at the tool's input does not count: "Paste your bytecode and get the mnemonic of each opcode" clears. This came from the reporter's follow-up.
  - "Seed phrase" is unchanged.
  - Fifteen requests that carry an EVM word are in the tests and still block, for example "Provide your wallet mnemonic to sign the EVM transaction" and "To deploy the bytecode, enter the mnemonic of the deployer".
  - Ruleset digest `sha256-s6KT1C2YyL3XbyqasSyExSh+0U8lsUjtypaSYo5bckA=`.
- **A finding names the clause that fired.** Static-scan messages end with `in "<clause>"`, so the author of a blocked tool sees which sentence to rewrite.
- **`warden-mcp interceptor` (experimental).** WARDEN as an MCP Interceptor Server, following the working group's proposal (SEP-2624). It runs two validators on the response to `tools/list`:
  - `warden.tool-definition-integrity` compares the tool set with the approved one and names added, removed and changed tools;
  - `warden.tool-definition-scan` runs the static scan.
  
  The server keeps no state and offers no tools. See [docs/interceptor.md](https://github.com/alexar76/warden/blob/v0.27.0/docs/interceptor.md).
- **The digests of `mcp-tool-set-digest/1`**: `contractDigest`, `extrasDigest` and `perToolContract`. The specification's 73 test vectors run in the test suite.

Checks for this build:

| Check | Result |
|---|---|
| Tests | 1788 of 1788 |
| Red team, Claude Code profile | 0 of 28 attacks delivered; field regressions 0 of 4 |
| Red team, Codex and OpenCode, `all` | 0 of 28 |
| Red team, Codex and OpenCode, `data` | 3 of 28 (the same three action-only attacks as in 0.26.0) |
| Clean install of the tarball | pass |
| MOMUS release gate | the evidence folder in the monorepo records the run |
