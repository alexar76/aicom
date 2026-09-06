/**
 * Wrap an MCP tool-call handler so every call leaves a signed AWR/2 receipt.
 *
 * WHAT THIS WAS WRITTEN AGAINST, AND WHAT IT WAS TESTED AGAINST. The shape here is the
 * `CallToolRequest` handler of the MCP TypeScript SDK (`@modelcontextprotocol/sdk` 1.x):
 * an async function taking `{ params: { name, arguments } }` and returning
 * `{ content: [...], isError? }`, the thing you pass to
 * `server.setRequestHandler(CallToolRequestSchema, handler)`. The SDK is **not installed
 * here and is not imported** — this wrapper is duck-typed against that shape and its test
 * drives it with a local fake. If the SDK has moved, this file is where it breaks and the
 * test will not tell you; run it once against your actual version.
 *
 * Zero dependencies, like the emitter it builds on: it imports one local file.
 */

import { emitReceipt, jcsPayload } from './awr-emit.mjs';

/**
 * @param handler the MCP CallTool handler to wrap
 * @param opts.key         signing key from `keyFromSeed` / `generateKey`
 * @param opts.modelId     recorded as `work.modelId`; for a tool server this is the tool
 *                         host's identity, not a model — say so honestly, e.g. "my-mcp-server@1.2".
 * @param opts.onReceipt   called with each signed document. Required: a middleware that
 *                         silently drops receipts is worse than none, because the operator
 *                         believes there is a trail.
 * @param opts.capability  optional `work.capability`; defaults to the tool name.
 */
export function withAwrReceipts(handler, opts) {
  const { key, modelId, onReceipt, capability } = opts || {};
  if (typeof handler !== 'function') throw new TypeError('handler must be a function');
  if (!key || !key.did) throw new TypeError('opts.key must be a signing key');
  if (typeof modelId !== 'string' || !modelId) throw new TypeError('opts.modelId is required');
  if (typeof onReceipt !== 'function') throw new TypeError('opts.onReceipt is required');

  return async function awrWrappedCallTool(request, extra) {
    const started = Date.now();
    // The request params are the input. Canonicalized, so a client holding the same
    // arguments computes the same digest whatever its JSON library did with key order.
    const inputPayload = jcsPayload((request && request.params) ?? null);
    const toolName = request && request.params && request.params.name;

    let result;
    let status = 'succeeded';
    let outputPayload;
    try {
      result = await handler(request, extra);
      // An MCP handler signals a tool-level failure with isError rather than by throwing.
      // That is a failed unit of work and §3.3 keeps it first-class.
      if (result && result.isError) status = 'failed';
      outputPayload = jcsPayload(result ?? null);
    } catch (err) {
      status = 'failed';
      // The thrown error is OUR narration, not the tool's output: committing to it would
      // misrepresent what the receipt covers. The empty payload is the honest digest.
      outputPayload = Buffer.alloc(0);
      emitAndForward(err);
      throw err;
    }
    emitAndForward(null);
    return result;

    function emitAndForward(error) {
      let document = null;
      try {
        document = emitReceipt({
          key,
          modelId,
          capability: capability || (typeof toolName === 'string' ? toolName : undefined),
          inputPayload,
          outputPayload,
          status,
          latencyMs: Date.now() - started,
        });
      } catch (emitError) {
        // Emitting a receipt must never turn a working tool call into a failed one, but it
        // must not be swallowed either: the sink is told, so an operator can see that the
        // trail has a hole rather than assuming it is complete.
        try { onReceipt(null, emitError); } catch { /* the sink's problem, not ours */ }
        return;
      }
      try { onReceipt(document, error); } catch { /* the sink's problem, not ours */ }
    }
  };
}
