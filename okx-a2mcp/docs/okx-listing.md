# OKX.AI listing

Two free A2MCP services, registered under one ASP (service provider) identity. The service fields
follow the contract in OKX's own `okx-ai` skill (`references/identity/service-contract.md`):

- service name 5–30 characters, a noun phrase, different from the agent name, no price;
- a description of exactly four numbered lines — `[Service Description]`, `[Parameter Spec]` as
  `name(type, required/optional): meaning; …`, `[Request Method]` (method only), `[Request Example]`
  (a runnable `curl` against the real endpoint);
- `fee` as a quoted number, `"0"` for free; a public HTTPS endpoint that matches the example.

The services are in [`okx-services.json`](okx-services.json) and pass OKX's local check:

```bash
onchainos agent validate-listing --role asp --name "AIMarket" \
  --description "AIMarket publishes open security checks for AI agents that connect to MCP servers, backed by the HISTOR transparency log and the open-source WARDEN firewall." \
  --service "$(cat okx-services.json)"
# {"pass": true, "findings": []}
```

## Identity

| Field | Value |
|---|---|
| Name | `AIMarket` |
| Description | AIMarket publishes open security checks for AI agents that connect to MCP servers, backed by the HISTOR transparency log and the open-source WARDEN firewall. |
| Avatar | [`avatar.png`](avatar.png) (512×512 PNG; OKX takes PNG/JPEG/WebP up to 1 MB) |

## Registration — run by the account owner

Creating the identity, logging in and accepting OKX's terms are the owner's actions. From this
directory, after `npx -y @okxweb3/onchainos-installer install`:

```bash
onchainos wallet login --phase init            # opens the login page; finish it in the browser
onchainos wallet login --phase poll --session-id <authSessionId from the previous output>
onchainos agent pre-check --role asp           # shows OKX's terms if consent is needed
onchainos agent pre-check --role asp --consent-key <key>   # only after reading and agreeing
onchainos agent upload --file avatar.png       # returns the CDN url for --picture
onchainos agent create --role asp --name "AIMarket" \
  --description "AIMarket publishes open security checks for AI agents that connect to MCP servers, backed by the HISTOR transparency log and the open-source WARDEN firewall." \
  --picture <url from upload> --service "$(cat okx-services.json)"
onchainos agent activate --agent-id <newAgentId from create> --preferred-language ru-RU   # submit for listing review
```

OKX says review usually takes up to 48 hours and reports to the login e-mail. Changing an endpoint
later is an update of the registered service, not a new registration.

## Honest limits to keep in mind

- WARDEN's false-positive profile is published: on the 2026-10-01 corpus 0.8.1 blocks 3 of 986
  servers and by our reading 1 of those is its own false positive
  ([`warden/docs/mcp-survey.md`](../../warden/docs/mcp-survey.md)). The scan covers definitions only;
  it cannot see what a tool does when called.
- HISTOR reports what it has observed. A server it has never seen comes back `match: not-listed`,
  which is not a clean bill of health.
