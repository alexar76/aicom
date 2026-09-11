# AWR emitters — the ten-minute path

## What is an "emitter"?

There are exactly two sides to AWR, and they need different code:

| | what it does | who runs it | in this repo |
|---|---|---|---|
| **emitter** (issuer) | **writes** a receipt: takes what your system just did and signs a document saying so | whoever ran the work — the producer | this directory |
| **verifier** | **reads** a receipt: checks the signature and the rules, and reports why not | anyone who receives the document — the consumer | [`reference/python`](../reference/python), [`rust`](../rust), [`docs/verifier`](../../docs/verifier) |

Everything before this directory was for the *reading* side: a specification, three
verifiers, 118 test vectors and a conformance suite. All of it is useless until something
*writes* a receipt in the first place — and until now, doing that meant reading the
specification and assembling the document by hand. An emitter is the small piece that turns
"I just called a model" into a signed document, so producing a receipt costs one function
call instead of an afternoon.

The name is the standards-world word for the producing side; if it helps, read it as
"receipt writer". Nothing here verifies anything — that is deliberate, and the two jobs stay
in different files.

---

You ran a model. You want a signed receipt that says what happened, which anyone can check
offline, without a wallet, an account, a registry or a network call.

Two emitters, one adapter each. Neither implements the format: canonicalization, the proof
and `did:key` live in the [reference implementation](../reference/python) and, for the
zero-dependency JavaScript build, in one file you can read in ten minutes.

| | path | dependencies |
|---|---|---|
| Python | [`python/`](python) | the `awr` reference package |
| JavaScript / TypeScript | [`typescript/`](typescript) | **none** — Node 22's `node:crypto` |
| LangChain / LangGraph callback | [`python/awr_emitter/adapters/langgraph_callback.py`](python/awr_emitter/adapters/langgraph_callback.py) | the above |
| MCP tool-call wrapper | [`typescript/mcp-middleware.mjs`](typescript/mcp-middleware.mjs) | the above |

The two emitters produce **byte-identical documents** for the same inputs and key. That is
not a claim, it is a test: `test_the_typescript_emitter_agrees_byte_for_byte` runs Node from
pytest and compares the bytes.

## Python

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

`receipt` is a signed AWR/2 `WorkReceipt` — a plain dict, ready for `json.dump`. Check it
with any of the three implementations:

```bash
python -m awr verify receipt.json          # reference
awr/rust/target/release/awr verify receipt.json
node docs/verifier/js/cli.js verify receipt.json
```

## JavaScript, with nothing installed

```js
import { emitReceipt, generateKey, jcsPayload } from './awr-emit.mjs';

const key = generateKey();
const receipt = emitReceipt({
  key,
  modelId: 'claude-opus-5@anthropic',
  inputPayload: jcsPayload({ prompt: 'summarise this', n: 3 }),
  outputPayload: '...the model\'s answer...',
  latencyMs: 2340,
});
```

Copy `awr-emit.mjs` into your project. There is no package to install and no build step.

## The one decision you cannot avoid: what gets digested

`inputDigest` and `outputDigest` are digests of **application payload bytes**, and
[SPEC.md §3.3](../SPEC.md) deliberately leaves the serialization to you. Both emitters make
the same choice and state it:

* **They digest exactly the bytes you pass.** A `str` is encoded UTF-8 — no normalization,
  no trailing newline, no BOM.
* **If your payload is JSON and a third party must be able to recompute the digest, wrap it
  in `jcs_payload` / `jcsPayload` first.** That canonicalizes with RFC 8785, so someone
  holding the same object computes the same digest however their JSON library ordered the
  keys.

A receipt whose digest nobody else can reproduce is still a valid receipt — it just can only
ever be checked by whoever kept the original bytes. That is a choice, not an accident, and
it should be a deliberate one.

## Chains

A hop commits to its parent's exact bytes, proof included:

```python
from awr_emitter import receipt_reference

retrieval = emit_receipt(key=key, model_id="retriever@v1", input_payload=q, output_payload=docs)
answer = emit_receipt(
    key=key, model_id="claude-opus-5@anthropic",
    input_payload=docs, output_payload=text,
    parents=[dict(receipt_reference(retrieval), role="retrieval")],
)
```

Tamper with the parent afterwards and a verifier that has both reports `AWR-CHAIN-003`.

## The adapters, and what they were actually tested against

Neither LangChain nor the MCP SDK is installed in this repository, so **both adapters are
duck-typed against the documented callback shape and tested with a local fake that
implements it**. That is enough to test the adapter's own logic and it is *not* evidence
that the shape still matches the package you are using:

* `langgraph_callback.py` targets `langchain_core.callbacks.BaseCallbackHandler` as
  documented for **langchain-core 0.3.x** — `on_llm_start(serialized, prompts, run_id=…)`,
  `on_llm_end(LLMResult, run_id=…)`, `on_llm_error(exc, run_id=…)`.
* `mcp-middleware.mjs` targets the `CallToolRequest` handler of
  **`@modelcontextprotocol/sdk` 1.x** — `async ({ params: { name, arguments } }) => ({ content, isError? })`.

Run each once against your real versions before relying on it. Both refuse to invent
anything they were not told: a failed call still produces a receipt, and the thrown error
text is **not** digested as the model's output, because it is our narration of the failure
rather than something the model produced.

## Running the tests

```bash
cd awr/emitters/python && PYTHONPATH=../../reference/python:. python -m pytest -q
node --test awr/emitters/typescript/test.mjs
```

The Python suite includes the cross-language byte-equality check; the JavaScript suite hands
every document it produces to the Rust CLI, so a document that only its own emitter accepts
fails the build.

## What this does not do

No verdicts, no blame attestations, no bundles, no profiles above L0 — those need a second
party, and an emitter is by definition the first one. Issue them with the reference
implementation directly. And nothing here contacts the network: an emitter that phoned home
would defeat the property that makes the format adoptable.
