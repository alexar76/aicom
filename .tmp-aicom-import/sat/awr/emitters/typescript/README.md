# @alexar76/awr-emit

Emit a signed [AWR/2](https://github.com/alexar76/aicom/blob/main/awr/SPEC.md) `WorkReceipt`
from Node. **Zero runtime dependencies** — the RFC 8785 canonicalizer, base58btc, `did:key`
derivation and the Ed25519 signing all sit in one file over `node:crypto`.

There are two sides to AWR and they need different code. A **verifier** reads a receipt and
checks it. An **emitter** writes one: it takes what your system just did and signs a document
saying so. This is an emitter, and it verifies nothing — deliberately, because a component that
both issues and judges its own work is not evidence of anything.

```bash
npm install @alexar76/awr-emit
```

```js
import { emitReceipt, generateKey, jcsPayload } from '@alexar76/awr-emit';

const key = generateKey();              // keep this; its .did is your issuer identity

const receipt = emitReceipt({
  key,
  modelId: 'claude-opus-5@anthropic',
  inputPayload: jcsPayload({ prompt: 'summarise this', n: 3 }),
  outputPayload: '...the model\'s answer...',
  latencyMs: 2340,
});
```

`receipt` is a plain object, ready for `JSON.stringify`. Anyone can check it without this
package and without trusting you:

```bash
pip install awr
python -m awr verify receipt.json
```

## MCP tool calls

`./mcp` wraps an MCP tool handler so every call it serves produces a receipt — including the
calls that fail, because an unverifiable failure is what a dispute usually turns on.

```js
import { withAwrReceipts } from '@alexar76/awr-emit/mcp';

const handler = withAwrReceipts(myToolHandler, {
  key,
  modelId: 'my-server@v1',
  onReceipt: (doc, err) => save(doc),   // required: a receipt nobody keeps is not evidence
});
```

## Cross-implementation agreement

The [Python emitter](https://github.com/alexar76/aicom/tree/main/awr/emitters/python) and this
one produce **byte-identical documents** for the same inputs and key. That is not a claim, it is
a test:
`test_the_typescript_emitter_agrees_byte_for_byte` runs Node from pytest and compares the bytes,
and the timestamp-derivation rules are pinned on both sides after a real divergence was found by
diffing partial inputs.

The format itself has three independent verifiers — Python, Rust and browser JavaScript — that
agree on 354 conformance cases, and an unmodified off-the-shelf W3C VC library verifies these
documents given nothing but a `did:key` resolver.

## Links

- Specification: <https://github.com/alexar76/aicom/blob/main/awr/SPEC.md>
- Paste a receipt into a browser verifier: <https://verify.modelmarket.dev>
- Verifier package for Python: <https://pypi.org/project/awr/>

MIT.
