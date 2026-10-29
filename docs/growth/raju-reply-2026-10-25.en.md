Following up, Raju — I’ve published a [complete, copyable CI example](https://dev.to/alexar76/a-copyable-mcp-tool-cost-check-for-ci-with-passing-and-failing-examples-3hl5), including the fetch script, pinned CLI/tokenizer versions, and commands that deliberately pass and fail. It needs no repository checkout or login.

The example uses a real stored textokit change: 20 tools on both sides, with the counted definitions shrinking from 5,565 to 3,776 tokens. It checks the total, descriptions and input schemas independently, so shorter descriptions cannot hide a growing schema. Reversing the comparison deliberately returns exit 1; that is a test control, not a claim that a later textokit release regressed.

For your own package, commit a reviewed baseline and run the check after the existing build:

```sh
histor tool-cost check --baseline tool-cost.json --stdio "node dist/index.js" --max-increase 10%
```

This is verified with our own Linux reproduction. I haven’t yet received an external team's run, and tool-definition token counts alone do not establish the client's actual invoice.
