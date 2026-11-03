# First agent call: discover → invoke → verify

[English](agent-first-call.md) · [Русский](agent-first-call.ru.md) · [Español](agent-first-call.es.md) · [Français](agent-first-call.fr.md) · [中文](agent-first-call.zh.md)

Choose your existing client. MCP and A2A reach the same marketplace and invoke controls; you do not need to adopt both.

## MCP client

Add `https://modelmarket.dev/mcp` to a Streamable-HTTP MCP client. Inspect `tools/list` for the current argument schemas, then give the agent this task:

> Use `market_search` to find GAIA Open-Meteo weather. Show the selected offer’s price and input schema. Call `market_invoke` for `device_id` `om-wx-01`, copying `product_id`, `capability_id`, and `source_hub` from that offer. Use the free trial and stop if payment is required. Show the result and receipt. Report receipt verification separately from execution success; a signature field alone is not a verification result.

Preserve `source_hub`: federated offers must be invoked at their source. The hosted endpoint can return `429 trial_quota_exhausted` when the trial is depleted. See [hosted MCP details](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md). The A2A example below demonstrates an explicit client-side signature check.

## A2A agent

The shared [Python example](../examples/first-agent-call.py) discovers the Agent Card, searches for `gaia.weather.read@v1`, preserves its source hub, and limits one call to $0.01. Run from the `aimarket-hub` directory with Python 3.11+:

```bash
python -m pip install 'aimarket-agent>=2.4.0'
```

```bash
python examples/first-agent-call.py
python examples/first-agent-call.py --invoke
```

The first command only searches. The second invokes once. Without `AIMARKET_KEY`, it uses an available free trial. To exercise payment with prepaid credits, set `AIMARKET_KEY` to a funded account’s API key before invoking; that call may debit up to $0.01. Keep the key out of scripts and commits. `AIMARKET_HUB_URL` optionally selects another hub.

The example uses `device_id` `om-wx-01` for the GAIA Open-Meteo offer; inspect the returned input schema if the catalogue changes. No matching offer means the example stops without invoking.

## Continue an x402 Task

After exit `2`, inspect the Task’s payment terms. Pay the quoted invoice once with your wallet, wait for settlement, and use the same Task ID and transaction hash below. The example submits an existing transfer; it does not sign, send, or replace a transaction. An account-owned Task requires the same `AIMARKET_KEY`. Reading a completed Task does not pay or invoke again.

The x402 follow-up fix is in this `aicom` checkout. Until it is released in the SDK, install the local client from the `aimarket-hub` directory:

```bash
python -m pip install -e ../aimarket-agent
```

```bash
python examples/first-agent-call.py --task-id a2at_... --payment-tx 0x...
python examples/first-agent-call.py --task-id a2at_...
```

## Read the outcome

- Exit `0` after `--invoke`: `TASK_STATE_COMPLETED` and `receipt_verified` is true. The SDK checked the receipt against its signer’s key, including the provider’s key for a federated offer. The result is printed only after this check.
- Exit `1`: the weather offer was unavailable.
- Exit `2`: the Task did not complete. `TASK_STATE_INPUT_REQUIRED` can request payment; `TASK_STATE_AUTH_REQUIRED` can request credentials. Inspect the printed status and [payment guide](a2a.md#invoke).
- Exit `3`: execution completed, but receipt verification failed or no receipt was returned. Do not treat this as a verified result.
- Exit `4`: the receipt is valid, but the weather result is missing. Execution and signature verification alone do not make this example successful.

Search-only exit `0` confirms discovery, not execution. Network or protocol errors also stop the example. It does not top up accounts, transfer funds, resume payment, or retry automatically. An incomplete Task is not evidence that no charge occurred; inspect its status before retrying. For intentional retries, reuse a `message_id` as described in the [A2A guide](a2a.md).

A valid receipt authenticates a signed record. It does not independently prove that a weather reading is correct. Trial limits and offer availability are determined by the hub; they are not guaranteed by this example.
