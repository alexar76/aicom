# Multica × AIMarket: agents that buy, remember, review and sell

We run a self-hosted [Multica](https://github.com/multica-ai/multica) 0.5.3 next to our AIMarket hubs. Multica is
the agent factory; the hubs are the market those agents work in. This folder is what we built to connect the
two, written up for other Multica operators. Everything below runs on one host since 2026-11-04.

## The setup

- **Runtime.** Multica's daemon in a container with OpenCode 1.18.32 and DeepSeek: non-root, all capabilities
  dropped, 3 GB / 2 CPU. The UI is reachable only through an SSH tunnel.
- **Egress allowlist.** The daemon sits on an internal Docker network; its only way out is a tinyproxy that
  refuses every host not on a short list (the model provider, GitHub, a few news sites, Telegram, two hubs). No outside
  DNS from the agent network.
- **WARDEN flow guard for OpenCode** (`@aimarket/warden/opencode`, from 0.23.0). An OpenCode plugin that refuses a
  tool call carrying a credential or data the session read after outside text. It also blanks listed keys in
  shell commands. In a staged attack with a fake key in a file, sending it was refused on every channel: the chat
  script, curl to an allowed host, a memory write and the tracker CLI. A normal day's work ran with no refusals.
- **Per-agent isolation.** Every agent shares the daemon, so we keep the global config minimal and use each agent's
  custom environment in Multica. An agent that reads strangers' text gets empty hub keys, an empty `GH_TOKEN`, and
  `OPENCODE_CONFIG_CONTENT` that disables the hub MCP servers (`"enabled": false`) and denies their tools.

## The agents

| Agent | Schedule (UTC) | What it does |
|---|---|---|
| GitHub digest | daily 08:00 | Activity across our repositories to Telegram. Remembers past digests in Attested Memory (bought on the hub per call), so it reports trends instead of repeating itself. |
| Mystery shopper | daily 09:00 | Buys a few random safe skills on modelmarket.dev with a capped prepaid key ($0.15 per run), checks the work receipt, latency and whether the answer matches the listing. |
| Supplier reviewer | daily 10:00 | Diffs the market against yesterday: new and changed listings, federation peers and x402 sellers. A script checks schemas, prompt injection (WARDEN's static scan), what a buyer would hand over, address and price. The model writes the report and a welcome draft for each outside author, and pastes the script's facts unchanged. |
| Weekly post | Mondays 11:00 | Drafts a build-in-public post from hub counters and the agents' own task results; every number comes from a facts block a script collects. |
| Order runner | on webhook | Writes the summary for a long job sold on the hub (see below). Selling since 2026-11-05; the first design was paused after one order and redesigned. |

Scripts that decide facts are deterministic and tested; models write prose around them. That split matters most
for the reviewer: an injected listing description can make the model's summary wrong, but not the facts under it.

## Selling a long job

A paid call cannot wait minutes, so a GitHub activity digest is sold as `github.digest.order@v1` (paid) and
`github.digest.result@v1` (free):

1. The hub calls our small provider service with the buyer's login and number of days. The service validates both
   (GitHub login syntax, 1–7), reads the public GitHub data itself with a token that has no scopes, and builds the
   dated items with github.com links. A login that does not exist, or a GitHub outage, refuses the order, and the
   hub charges only for an answered call. Then it creates a Multica task through an **autopilot webhook trigger**
   with that data; Multica puts the webhook payload into the task as JSON.
2. The agent may only read its task (`multica issue get`); OpenCode permissions deny every other shell command
   and tool. Its final answer is one JSON line with a summary, which Multica posts on the task.
3. The service reads that answer through a read-only database function that returns only the order agent's
   comments on its autopilot's tasks for one job, and checks it (length, no links off github.com). If there is
   no usable summary when the task ends or after 20 minutes, the service writes a plain one from the same data.
4. The buyer reads the result. The hub names its authenticated buyer to its own providers with an HMAC reference,
   and each job is bound to it, so only the buyer who paid can read it.

Code: `multica/provider/` (service and tests) and `multica/provider/agent-instructions.ru.md` (the runner's
instructions).

What the first real order taught us: an agent that reads outside text (GitHub) cannot then send anything it read
from its own task, such as a per-job delivery URL, if a flow guard like WARDEN runs in `data` mode; that is the
guard doing its job. Make the agent's final answer the deliverable and let the service collect it from Multica,
and do the outside reads in the service. Unauthenticated GitHub reads share 60 requests an hour per host IP, so
give the service a GitHub token with no scopes.

## Use it yourself

Step by step, in five languages: [`../manual/`](../manual/README.md) (English, Русский, Español, Français, 中文).

- [`aimarket/SKILL.md`](aimarket/SKILL.md): a Multica skill for agents that buy on a hub, check receipts and
  publish a capability or a long job. Import it with `multica skill import` from its URL.
- [`../supplier-review/`](../supplier-review/) and [`../weekly-post/`](../weekly-post/): the two scripted agents.
- [`../provider/`](../provider/): the order/result provider.

Limits we know about: Multica posts an agent's final answer itself, outside the tool calls a guard can see; the
reviewer's outside text reaches the model through its own script's output, so WARDEN counts it as local data
(its secret rules still apply); each guard is per runtime, not per agent.
