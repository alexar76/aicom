# Run an n8n order-check service on your own hub

[English](n8n-workshop.md) · [Русский](n8n-workshop.ru.md) · [Español](n8n-workshop.es.md) · [Français](n8n-workshop.fr.md) · [中文](n8n-workshop.zh.md)

A practical 60-minute online workshop for n8n integrators and small API owners. Build a
read-only service that answers: **“Can this supplier fulfil my basket, and what is the
goods subtotal?”** Keep the workflow and catalogue under the operator's control. No purchase,
wallet, paid LLM or external customer is required for the local exercise.

## Why this use case

A shop's assistant, an agency-built sales assistant or a procurement agent can ask the same
service instead of reproducing a supplier's stock and pricing rules. n8n owns those rules;
Hub lists the service and checks signed responses. n8n already has
[native MCP](https://n8n.io/mcp/): use that directly when exposing your workflow to your own
agent is all you need. The additional exercise here is an independently operated catalogue,
signed provider responses and an optional path to federation.

The included catalogue is synthetic. It demonstrates the integration, not live stock,
commercial demand or a production deployment. Hub is free to run; hosting is the operator's
cost and n8n has its own licence. Federation is a potential distribution channel.

## The example and expected decisions

[Download/import workflow](../examples/n8n-order-check/workflow.json) ·
[Code and launcher](../examples/n8n-order-check/README.md) ·
[Validation record](../examples/n8n-order-check/VALIDATION.md)

```json
{"items":[{"sku":"BEANS-250","quantity":2},{"sku":"MUG-BLUE","quantity":1}]}
```

Expected: `status: ready`, `can_fulfill: true`, `subtotal_minor: 3430`, `currency: USD`.
That is USD 34.30 for goods only. Tax, shipping and grand total are `null` (not calculated).
The result says `demo: true`, `reservation_created: false`, `order_created: false`.

| Request | Expected behaviour |
|---|---|
| Two BEANS-250 and one MUG-BLUE | Ready; subtotal 3430 |
| Four MUG-BLUE | Insufficient stock; three available |
| An unknown SKU | Unknown item; subtotal unavailable |
| Two lines of two MUG-BLUE each | Aggregate to four; insufficient stock |
| Empty basket, negative or fractional quantity | Reject input |
| Wrong webhook credential / unavailable n8n | Refuse / fail; never fabricate a quote |

`evaluated_at` records execution time, not stock freshness. A signature authenticates the
provider's statement and binds it to the request; it does not prove the stock exists.

## Prepare before the session

Use a separate local instance, Python 3.11+, Node.js 24.14.0 and ports 15678/13456/19083.
From a clone of this repository:

```bash
python3 -m venv examples/n8n-order-check/.venv
examples/n8n-order-check/.venv/bin/python -m pip install -e './aimarket-hub[pqc]'
cd examples/n8n-order-check
source .venv/bin/activate
npm install --prefix .runtime/npm n8n@2.43.7 --no-audit --no-fund
export PATH="$PWD/.runtime/npm/node_modules/.bin:$PATH"
python run.py init
python run.py n8n-import
```

Installation is outside the 60 minutes. Secrets and keys are generated in `.runtime/`,
excluded from Git; do not share that directory. The exported workflow uses a Header Auth
credential and no embedded token. Re-import only while this isolated n8n is stopped.

Open three terminals in the example directory, activate `.venv` in each, and run respectively:
`python run.py n8n`, `python run.py adapter`, `python run.py hub`. Repeat the PATH export in
the n8n terminal. The editor is `http://127.0.0.1:15678`; create a local owner account if asked.
The import step publishes the workflow, so the adapter uses its production `/webhook/` route.
Stop servers with Ctrl+C; local state remains for the next session.

## The 60-minute session

| Minutes | Activity |
|---|---|
| 0–5 | Identify owner, caller and read-only outcome; explain demo data |
| 5–15 | Inspect Webhook → Code → Respond to Webhook; run a direct authenticated check |
| 15–25 | Inspect input schema, duplicate aggregation, stock and price rules |
| 25–40 | Run adapter and Hub; invoke the capability; inspect result and signatures |
| 40–50 | Try shortage, unknown SKU, invalid quantity and credential failures |
| 50–60 | Discuss replacing fixtures with one authorised data source; questions |

Wait for n8n to report that its editor is available and workflow indexing is complete before running the checks.

```bash
curl --fail-with-body http://127.0.0.1:19083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' --data-binary @request.json
python run.py check
node test_quote.cjs
```

Optional local MCP client: `http://127.0.0.1:19083/mcp`. Prompt:
“Find the workshop order-check tool. Check two BEANS-250 and one MUG-BLUE. Report the
goods subtotal and shortages, identify the data as synthetic, and do not place an order.”
A cloud-only client cannot reach this loopback endpoint. HTTP and MCP protocol tests do
not by themselves establish a successful session in every agent application.

## The first real operator

Ask for one sanitised catalogue response and an owner-authorised source. Replace the fixture
stage with read-only access, mapping currency, prices in minor units, available stock and
source timestamp; define a freshness limit. Update the adapter's demo-only contract and tests
together. Keep stock checks separate from reservations and orders. Do not expose private
or customer-specific prices without caller authorization and tenant isolation.

For public use, deploy a persistent Hub behind HTTPS with rate limits; keep n8n/adapter
private and authenticated. Remove lab-only HTTP settings. Follow the
[Hub operator guide](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md), run `aimarket doctor`,
then choose whether to announce. Local success is not federation admission.

Success means the independent owner controls the deployment and keys, can repeat a useful
call, and knows how to stop it. Record local completion, real-data integration, federation
admission and use after seven days separately. An external sale is not required.
