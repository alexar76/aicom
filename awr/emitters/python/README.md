# awr-emitter

Emit a signed [AWR/2](https://verify.modelmarket.dev) `WorkReceipt` in one function call.

There are two sides to AWR and they need different code. A **verifier** reads a receipt and
checks it; that is the [`awr`](https://pypi.org/project/awr/) package. An **emitter** writes
one: it takes what your system just did and signs a document saying so. That is this package.
It implements none of the format itself — every byte of canonicalization, every signature and
every identifier comes from `awr`, so an emitted receipt and a verified receipt can never
disagree about the rules.

```python
from awr_emitter import emit_receipt, generate_key, jcs_payload

key = generate_key()                      # keep this; its .did is your issuer identity

receipt = emit_receipt(
    key=key,
    model_id="claude-opus-5@anthropic",
    input_payload=jcs_payload({"prompt": "summarise this", "n": 3}),
    output_payload=b"...the model's answer...",
    latency_ms=2340,
)
```

`receipt` is a plain dict, ready for `json.dump`. Anyone can check it without this package
and without trusting you:

```bash
pip install awr
python -m awr verify receipt.json
```

The document is a W3C Verifiable Credential 2.0 with an `eddsa-jcs-2022` `DataIntegrityProof`
over [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) canonical bytes, issued under a
`did:key`. Nothing about it is specific to this implementation: an unmodified off-the-shelf VC
library verifies it, and there are two other independent verifiers (Rust and browser
JavaScript) that agree byte for byte.

## What it will not do

It does not verify. That is deliberate and the two jobs stay in different packages — a
component that both issues and judges its own work is not evidence of anything.

## Framework adapters

`awr_emitter.adapters` holds bridges to agent frameworks. Each is duck-typed against the
framework instead of importing it, so this package depends on no framework and importing the
adapters never pulls one in:

| adapter | use it for |
|---|---|
| `awr_emitter.adapters.langgraph_callback` | LangChain / LangGraph — a callback handler that emits one receipt per LLM call |

## Links

- Specification, vectors and conformance suite: <https://verify.modelmarket.dev>
- Verifier package: <https://pypi.org/project/awr/>
- Paste a receipt into a browser verifier: <https://verify.modelmarket.dev>

MIT.
