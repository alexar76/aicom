# @alexar76/awr-verify

Verify an [AWR/2](https://github.com/alexar76/aicom/blob/main/awr/SPEC.md) work receipt. **Zero
dependencies**, runs in Node and unchanged in a browser.

This is the same code that runs at <https://verify.modelmarket.dev>, and one of the three
implementations that pass the AWR/2 conformance suite — the others are the Python reference and a
Rust implementation written from the specification text alone. All three agree on 354 vectors.

```bash
npm install @alexar76/awr-verify
```

```js
const awr = require('@alexar76/awr-verify');

// async: the Ed25519 check goes through WebCrypto, which is promise-based
const result = await awr.verify(receipt);
result.valid       // true | false
result.reasons     // [{ code: 'AWR-PROOF-006', severity: 'error', detail: '…' }, …]
result.warnings    // same shape; does not invalidate the document
result.profile     // 'L0' | 'L1' | 'L2' | null
```

Forgetting the `await` gives you a `Promise` whose `.valid` is `undefined` — which is falsy, so a
naive `if (result.valid)` fails closed rather than passing a bad receipt. It is still a bug, and
that is the one to check first if a receipt you believe in comes back invalid.

Or from the command line, which implements the §17 CLI contract — exit 0 valid, 1 invalid,
2 usage/IO, 3 unimplemented:

```bash
npx awr-verify verify receipt.json
npx awr-verify canonicalize receipt.json    # the RFC 8785 canonical bytes
npx awr-verify digest receipt.json          # sha256-<base64> over those bytes
npx awr-verify hashdata receipt.json        # proofConfigHash, documentHash, hashData
```

## What a valid receipt means

Exactly this: **this issuer signed these claims, and the bytes are intact.** Attribution, and
nothing more. It does not mean the model ran, that the digests correspond to real payloads, that
the price was paid, or that the output is correct. A verifier that told you otherwise would be
lying to you, so this one does not.

Verification is offline. It makes no network request — no registry, no blockchain, no call home,
not even to the AWR namespace URI in `@context`, which the specification forbids fetching (§13.5).
Nothing about the receipt you check is reported anywhere.

## Reading the result

`reasons` carries error codes; `warnings` carries things you should know but that do not invalidate
the document. Age is a warning on purpose: a receipt from two years ago is exactly as
cryptographically sound as one from today, and audit is the main reason old receipts get read.

Receipts issued under AWR/1, the pre-standard format, still verify — under explicit warnings
saying which fields that older signature did *not* cover, because they are not the same guarantee.

## The other half

To *write* receipts rather than read them, see
[`@alexar76/awr-emit`](https://www.npmjs.com/package/@alexar76/awr-emit) — also zero-dependency,
and it ships an MCP tool-call wrapper. They are separate packages deliberately: a component that
both issues and judges its own work is not evidence of anything.

## Links

- Specification: <https://github.com/alexar76/aicom/blob/main/awr/SPEC.md>
- Paste a receipt into the browser build: <https://verify.modelmarket.dev>
- Python verifier: <https://pypi.org/project/awr/>

MIT.
