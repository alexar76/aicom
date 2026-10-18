# Workshop validation

Checked locally on 2026-10-18. This is an owner-run synthetic exercise, not external demand,
a public deployment or a federation admission record.

## Environment

- macOS arm64; Python 3.11.15; Node.js 24.14.0.
- n8n 2.43.7, installed in an isolated temporary runtime. Workshop source and state are
  in the repository example; promotional materials are in the separate PromoMaterials folder.
- AIMarket Hub 3.15.28 from the local checkout. Provider response signature checking enabled.
- Independent lab database and generated Hub/provider keys. Auto-crawl disabled and no seeds
  in the running lab configuration. Ports bound only to loopback.
- No paid LLM, money transfer, stock reservation, order creation or outgoing invitation.

The system Node.js 22.22.1 was rejected by n8n before import. All five guides now require
Node.js 24.14.0. The actual workflow imports, publication and server execution used Node 24.

## Checks and outcomes

| Check | Result |
|---|---|
| n8n CLI credential/workflow import and publication | Passed on an initially empty lab n8n database |
| Real n8n production webhook execution | Passed; Webhook → Code → Respond to Webhook |
| Direct unauthenticated calls | Adapter 401; n8n webhook 403 |
| Provider result signature | Verified; input or result tampering rejected |
| Hub → adapter → real n8n, available cart | `ready`, USD goods subtotal 3430, free signed receipt |
| Four mugs | `insufficient_stock`, subtotal 3400, free signed receipt |
| Unknown SKU | `unknown_items`, subtotal null, free signed receipt |
| Duplicate SKU lines | Aggregated to four mugs; insufficient stock |
| Invalid adapter inputs | Empty cart, negative/fractional quantities rejected |
| MCP tools/list and market_search | Capability discoverable on the local Hub |
| MCP market_invoke → real n8n | Returned the expected synthetic basket subtotal 3430 |
| Code-node business rules | 14 scenarios passed against quote.js; workflow embeds identical source |
| Adapter failure-boundary tests | 8 pytest cases passed; n8n mocked only in this test suite |

The eight adapter tests cover authentication, wrong capability/input/body size, upstream
401/422/500/redirect/default-acknowledgement responses, timeout, secret separation and
request-bound signatures. They complement, rather than replace, the real HTTP/MCP run.

## Reproduce

After the documented import and startup, wait for n8n to report that the editor is available
and its workflow index is built; a port opening alone is not sufficient readiness.

```bash
python run.py check
node test_quote.cjs
python -m pip install pytest
python -m pytest test_adapter.py -q
```

The checked HTTP result is kept in ignored `.runtime/last-result.json`. It has a current
timestamp and local receipt, so it is not committed as a supposedly live public example.

## Boundaries

- No real inventory source, commercial catalogue, tenancy or customer-specific pricing was
  integrated. The adapter intentionally accepts only this demo response contract.
- No end-user agent application session, remote cloud MCP connection, public HTTPS setup,
  second independent hub or federation announcement was exercised.
- n8n's internal JavaScript runner executed the Code node. Its startup also warns that the
  optional Python runner environment is missing; this workflow has no Python node. The npm
  launcher/internal runner are for this local workshop. n8n warns these deployment modes
  are deprecated for future releases; production should follow its current container and
  external-runner guidance rather than copy the lab launcher.
- Signatures establish provenance and request binding, not independent truth of inventory.
- The workshop has no scheduled host, recording, slides or sent organiser invitation.
- Documentation and workflow are local working files. No deployment, Git push or public
  documentation publication is claimed.
